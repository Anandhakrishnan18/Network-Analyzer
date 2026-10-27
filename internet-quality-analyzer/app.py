"""
Flask Application Entrypoint & REST API for Internet Quality Analyzer.

Provides RESTful endpoints for network diagnostics, historical analysis,
configuration management, and data export.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
import sys
from typing import Optional, Dict, Any

from flask import Flask, jsonify, request, render_template, Response

import config
from database.db import (
    init_db,
    save_test_run,
    get_test_run,
    get_recent_history,
    get_historical_summary_stats,
    export_history_as_csv,
    get_recent_alerts,
)
from network.engine import run_full_diagnostic_probe
from analysis.troubleshooter import Troubleshooter
from analysis.comparator import compare_runs, compare_destinations, export_comparison_as_csv
from services.monitoring_service import monitoring_service


def create_app(test_config: Optional[Dict[str, Any]] = None) -> Flask:
    """Application factory for Flask app."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # Base configuration
    app.config["DATABASE_PATH"] = config.DATABASE_PATH
    app.config["THRESHOLDS"] = config.THRESHOLDS.copy()

    if test_config:
        app.config.update(test_config)

    # Ensure DB schema is initialized
    init_db(app.config["DATABASE_PATH"])

    # -------------------------------------------------------------
    # Response Formatting Helpers
    # -------------------------------------------------------------
    def success_response(data: Any, message: Optional[str] = None, status_code: int = 200):
        return jsonify({
            "status": "success",
            "data": data,
            "message": message,
        }), status_code

    def error_response(message: str, status_code: int = 400, data: Any = None):
        return jsonify({
            "status": "error",
            "data": data,
            "message": message,
        }), status_code

    # -------------------------------------------------------------
    # Frontend Route
    # -------------------------------------------------------------
    @app.route("/")
    def index():
        return render_template("index.html")

    # -------------------------------------------------------------
    # API: Health & System Status
    # -------------------------------------------------------------
    @app.route("/api/health", methods=["GET"])
    def api_health():
        return success_response({
            "service": "Internet Quality Analyzer",
            "status": "healthy",
            "python_version": sys.version.split()[0],
            "platform": sys.platform,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "database_initialized": Path(app.config["DATABASE_PATH"]).exists(),
        })

    # -------------------------------------------------------------
    # API: Configuration & Targets
    # -------------------------------------------------------------
    @app.route("/api/config", methods=["GET"])
    def api_get_config():
        return success_response({
            "allowed_targets": config.ALLOWED_TARGETS,
            "dns_resolvers": config.DNS_RESOLVERS,
            "thresholds": app.config["THRESHOLDS"],
            "sampling": {
                "default_probe_count": config.DEFAULT_PROBE_COUNT,
                "min_probe_count": config.MIN_PROBE_COUNT,
                "max_probe_count": config.MAX_PROBE_COUNT,
                "probe_timeout_sec": config.PROBE_TIMEOUT_SECONDS,
            },
        })

    @app.route("/api/config", methods=["POST"])
    def api_update_config():
        """Update diagnostic thresholds with validation."""
        payload = request.get_json(silent=True)
        if not payload or not isinstance(payload, dict):
            return error_response("Invalid JSON payload.")

        thresholds = app.config["THRESHOLDS"]
        new_thresholds = payload.get("thresholds")

        if not new_thresholds or not isinstance(new_thresholds, dict):
            return error_response("Missing or invalid 'thresholds' object.")

        for metric, values in new_thresholds.items():
            if metric in thresholds and isinstance(values, dict):
                for key, val in values.items():
                    try:
                        f_val = float(val)
                        if f_val < 0.0:
                            return error_response(f"Threshold value for {metric}.{key} cannot be negative.")
                        thresholds[metric][key] = f_val
                    except (ValueError, TypeError):
                        return error_response(f"Threshold value for {metric}.{key} must be a valid number.")

        return success_response({"thresholds": thresholds}, "Configuration updated successfully.")

    # -------------------------------------------------------------
    # API: Run Diagnostic Test
    # -------------------------------------------------------------
    @app.route("/api/tests", methods=["POST"])
    def api_run_test():
        """
        Execute an on-demand multi-layer network quality test.

        Payload (optional):
        {
            "targets": ["gateway", "cloudflare_dns", "google_web"],
            "probe_count": 5
        }
        """
        payload = request.get_json(silent=True) or {}
        requested_targets = payload.get("targets")
        probe_count = payload.get("probe_count", config.DEFAULT_PROBE_COUNT)

        # Validate probe count
        try:
            probe_count = int(probe_count)
            if not (config.MIN_PROBE_COUNT <= probe_count <= config.MAX_PROBE_COUNT):
                return error_response(
                    f"probe_count must be between {config.MIN_PROBE_COUNT} and {config.MAX_PROBE_COUNT}."
                )
        except (ValueError, TypeError):
            return error_response("probe_count must be an integer.")

        # Validate targets against allowlist
        allowed_ids = {t["id"] for t in config.ALLOWED_TARGETS}
        if requested_targets is not None:
            if not isinstance(requested_targets, list) or len(requested_targets) == 0:
                return error_response("targets must be a non-empty list of target identifiers.")
            invalid_ids = [t for t in requested_targets if t not in allowed_ids]
            if invalid_ids:
                return error_response(
                    f"Invalid target identifier(s): {invalid_ids}. Allowed targets: {list(allowed_ids)}"
                )

        # 1. Execute probe
        try:
            probe_report = run_full_diagnostic_probe(
                target_ids=requested_targets,
                probe_count=probe_count
            )
        except Exception as exc:
            return error_response(f"Measurement probe failed: {str(exc)}", status_code=500)

        # 2. Run diagnostic troubleshooter
        troubleshooter = Troubleshooter(thresholds=app.config["THRESHOLDS"])
        diagnostic_report = troubleshooter.diagnose(probe_report)

        # 3. Persist to SQLite
        try:
            run_id = save_test_run(
                probe_report,
                diagnostic_report,
                trigger_type="manual",
                db_path=app.config["DATABASE_PATH"]
            )
        except Exception as exc:
            return error_response(f"Failed to persist test run to database: {str(exc)}", status_code=500)

        # 4. Fetch full persisted record
        saved_record = get_test_run(run_id, db_path=app.config["DATABASE_PATH"])

        return success_response(saved_record, "Test run completed and saved successfully.", status_code=201)

    # -------------------------------------------------------------
    # API: Fetch Specific Test Run
    # -------------------------------------------------------------
    @app.route("/api/tests/<int:run_id>", methods=["GET"])
    def api_get_test(run_id: int):
        record = get_test_run(run_id, db_path=app.config["DATABASE_PATH"])
        if not record:
            return error_response(f"Test run with ID {run_id} not found.", status_code=404)
        return success_response(record)

    # -------------------------------------------------------------
    # API: Compare Two Test Sessions
    # -------------------------------------------------------------
    @app.route("/api/compare", methods=["GET"])
    def api_compare_runs():
        """
        Compare two distinct test runs:
        GET /api/compare?run_a=<id>&run_b=<id>
        """
        try:
            run_a_id = int(request.args.get("run_a"))
            run_b_id = int(request.args.get("run_b"))
        except (ValueError, TypeError):
            return error_response("Query parameters 'run_a' and 'run_b' must be valid integers.")

        run_a = get_test_run(run_a_id, db_path=app.config["DATABASE_PATH"])
        if not run_a:
            return error_response(f"Baseline test run #{run_a_id} not found.", status_code=404)

        run_b = get_test_run(run_b_id, db_path=app.config["DATABASE_PATH"])
        if not run_b:
            return error_response(f"Comparison test run #{run_b_id} not found.", status_code=404)

        comparison = compare_runs(run_a, run_b)
        return success_response(comparison)

    # -------------------------------------------------------------
    # API: Destination Benchmarks & WAN Penalty Breakdown
    # -------------------------------------------------------------
    @app.route("/api/compare/destinations", methods=["GET"])
    def api_compare_destinations():
        """
        Compare all destinations tested within a test run (WAN penalties, rankings).
        GET /api/compare/destinations?run_id=<id>
        If run_id is omitted, analyzes the most recent test run.
        """
        run_id_param = request.args.get("run_id")
        if run_id_param:
            try:
                run_id = int(run_id_param)
            except ValueError:
                return error_response("Query parameter 'run_id' must be an integer.")
            run = get_test_run(run_id, db_path=app.config["DATABASE_PATH"])
            if not run:
                return error_response(f"Test run #{run_id} not found.", status_code=404)
        else:
            recent = get_recent_history(limit=1, db_path=app.config["DATABASE_PATH"])
            if not recent:
                return error_response("No test runs found in database.", status_code=404)
            run = get_test_run(recent[0]["id"], db_path=app.config["DATABASE_PATH"])

        result = compare_destinations(run)
        return success_response(result)

    # -------------------------------------------------------------
    # API: Query History
    # -------------------------------------------------------------
    @app.route("/api/history", methods=["GET"])
    def api_get_history():
        """
        Query parameters:
        - hours: int (default 24; 0 = all)
        - limit: int (default 50, max 100)
        - target_id: optional string to filter
        """
        try:
            hours = int(request.args.get("hours", 24))
            limit = min(int(request.args.get("limit", 50)), 100)
        except ValueError:
            return error_response("Query parameters 'hours' and 'limit' must be integers.")

        target_id = request.args.get("target_id")
        history = get_recent_history(
            hours=hours,
            limit=limit,
            target_id=target_id,
            db_path=app.config["DATABASE_PATH"]
        )
        return success_response(history)

    # -------------------------------------------------------------
    # API: Historical Summary KPIs
    # -------------------------------------------------------------
    @app.route("/api/stats", methods=["GET"])
    def api_get_stats():
        """
        Query parameters:
        - hours: int (default 24)
        """
        try:
            hours = int(request.args.get("hours", 24))
        except ValueError:
            return error_response("Query parameter 'hours' must be an integer.")

        stats = get_historical_summary_stats(hours=hours, db_path=app.config["DATABASE_PATH"])
        return success_response(stats)

    # -------------------------------------------------------------
    # API: Alerts
    # -------------------------------------------------------------
    @app.route("/api/alerts", methods=["GET"])
    def api_get_alerts():
        limit = min(int(request.args.get("limit", 20)), 100)
        alerts = get_recent_alerts(limit=limit, db_path=app.config["DATABASE_PATH"])
        return success_response(alerts)

    # -------------------------------------------------------------
    # API: Export History as CSV
    # -------------------------------------------------------------
    @app.route("/api/export/csv", methods=["GET"])
    def api_export_csv():
        try:
            hours = int(request.args.get("hours", 168))  # default 7 days
        except ValueError:
            hours = 168

        csv_content = export_history_as_csv(hours=hours, db_path=app.config["DATABASE_PATH"])
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        filename = f"network_quality_history_{timestamp}.csv"

        return Response(
            csv_content,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    # -------------------------------------------------------------
    # API: Export Comparison as CSV
    # -------------------------------------------------------------
    @app.route("/api/export/comparison/csv", methods=["GET"])
    def api_export_comparison_csv():
        """
        Export comparison of two test runs to CSV:
        GET /api/export/comparison/csv?run_a=<id>&run_b=<id>
        """
        try:
            run_a_id = int(request.args.get("run_a"))
            run_b_id = int(request.args.get("run_b"))
        except (ValueError, TypeError):
            return error_response("Query parameters 'run_a' and 'run_b' must be valid integers.")

        run_a = get_test_run(run_a_id, db_path=app.config["DATABASE_PATH"])
        if not run_a:
            return error_response(f"Baseline test run #{run_a_id} not found.", status_code=404)
        run_b = get_test_run(run_b_id, db_path=app.config["DATABASE_PATH"])
        if not run_b:
            return error_response(f"Comparison test run #{run_b_id} not found.", status_code=404)

        comparison = compare_runs(run_a, run_b)
        csv_content = export_comparison_as_csv(comparison)
        filename = f"network_comparison_run{run_a_id}_vs_run{run_b_id}.csv"

        return Response(
            csv_content,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    # -------------------------------------------------------------
    # API: Export Comparison as JSON
    # -------------------------------------------------------------
    @app.route("/api/export/comparison/json", methods=["GET"])
    def api_export_comparison_json():
        """
        Export comparison of two test runs as JSON attachment:
        GET /api/export/comparison/json?run_a=<id>&run_b=<id>
        """
        try:
            run_a_id = int(request.args.get("run_a"))
            run_b_id = int(request.args.get("run_b"))
        except (ValueError, TypeError):
            return error_response("Query parameters 'run_a' and 'run_b' must be valid integers.")

        run_a = get_test_run(run_a_id, db_path=app.config["DATABASE_PATH"])
        if not run_a:
            return error_response(f"Baseline test run #{run_a_id} not found.", status_code=404)
        run_b = get_test_run(run_b_id, db_path=app.config["DATABASE_PATH"])
        if not run_b:
            return error_response(f"Comparison test run #{run_b_id} not found.", status_code=404)

        comparison = compare_runs(run_a, run_b)
        import json
        json_content = json.dumps(comparison, indent=2)
        filename = f"network_comparison_run{run_a_id}_vs_run{run_b_id}.json"

        return Response(
            json_content,
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    # -------------------------------------------------------------
    # API: Export Single Test Run as JSON
    # -------------------------------------------------------------
    @app.route("/api/export/test/<int:run_id>/json", methods=["GET"])
    def api_export_test_json(run_id: int):
        """
        Export a full test run diagnostic report as JSON download.
        GET /api/export/test/<run_id>/json
        """
        run = get_test_run(run_id, db_path=app.config["DATABASE_PATH"])
        if not run:
            return error_response(f"Test run #{run_id} not found.", status_code=404)

        import json
        json_content = json.dumps(run, indent=2)
        filename = f"netpulse_diagnostic_run_{run_id}.json"

        return Response(
            json_content,
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    # -------------------------------------------------------------
    # API: Background Monitoring Controls
    # -------------------------------------------------------------
    @app.route("/api/monitoring/status", methods=["GET"])
    def api_monitoring_status():
        return success_response(monitoring_service.get_status())

    @app.route("/api/monitoring/start", methods=["POST"])
    def api_monitoring_start():
        payload = request.get_json(silent=True) or {}
        interval = payload.get("interval_seconds")
        res = monitoring_service.start(interval_seconds=interval)
        return success_response(res, res.get("message"))

    @app.route("/api/monitoring/stop", methods=["POST"])
    def api_monitoring_stop():
        res = monitoring_service.stop()
        return success_response(res, res.get("message"))

    # -------------------------------------------------------------
    # Error Handlers
    # -------------------------------------------------------------
    @app.errorhandler(404)
    def handle_not_found(err):
        return error_response("Endpoint or resource not found.", status_code=404)

    @app.errorhandler(405)
    def handle_method_not_allowed(err):
        return error_response("HTTP method not allowed for this endpoint.", status_code=405)

    @app.errorhandler(500)
    def handle_internal_error(err):
        return error_response("Internal server error occurred.", status_code=500)

    return app


if __name__ == "__main__":
    application = create_app()
    # Runs on localhost only for secure development
    print("Starting Internet Quality Analyzer on http://127.0.0.1:5000")
    application.run(host="127.0.0.1", port=5000, debug=False)

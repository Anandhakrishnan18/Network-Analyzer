"""
Unit tests for the SQLite Database Access Layer (DAL).
"""

from datetime import datetime, timezone
from database.db import (
    init_db,
    save_test_run,
    get_test_run,
    get_recent_history,
    get_historical_summary_stats,
    save_alert,
    get_recent_alerts,
    export_history_as_csv,
    get_connection,
)


def create_sample_payloads():
    """Helper returning valid sample probe and diagnostic payloads."""
    probe_report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": 2.5,
        "interface_info": {"local_ip": "192.168.1.50", "default_gateway": "192.168.1.1"},
        "gateway_detected": True,
        "gateway_ip": "192.168.1.1",
        "target_results": [
            {
                "target_id": "gateway",
                "target_name": "Default Gateway",
                "target_type": "gateway",
                "target_address": "192.168.1.1",
                "target_port": None,
                "ping": {
                    "sent": 3,
                    "received": 3,
                    "lost": 0,
                    "packet_loss_pct": 0.0,
                    "min_ms": 1.5,
                    "max_ms": 2.5,
                    "avg_ms": 2.0,
                    "median_ms": 2.0,
                    "jitter_ms": 0.5,
                    "samples": [1.5, 2.0, 2.5],
                    "status": "success",
                    "error_message": None,
                },
                "dns_lookup_ms": None,
                "tcp_handshake_ms": None,
            },
            {
                "target_id": "google_web",
                "target_name": "Google Web",
                "target_type": "external_host",
                "target_address": "google.com",
                "target_port": 443,
                "ping": {
                    "sent": 3,
                    "received": 3,
                    "lost": 0,
                    "packet_loss_pct": 0.0,
                    "min_ms": 20.0,
                    "max_ms": 26.0,
                    "avg_ms": 23.0,
                    "median_ms": 23.0,
                    "jitter_ms": 3.0,
                    "samples": [20.0, 26.0, 23.0],
                    "status": "success",
                    "error_message": None,
                },
                "dns_lookup_ms": 18.5,
                "tcp_handshake_ms": 22.0,
            },
        ],
        "dns_benchmarks": [
            {
                "resolver_name": "Cloudflare",
                "resolver_ip": "1.1.1.1",
                "domain": "google.com",
                "avg_ms": 15.0,
                "min_ms": 14.0,
                "max_ms": 16.0,
                "status": "success",
                "samples": [14.0, 16.0],
            }
        ],
    }

    diag_report = {
        "overall_status": "healthy",
        "summary": "Connection is healthy.",
        "findings": [
            {
                "rule_id": "RULE_CONNECTION_HEALTHY",
                "severity": "info",
                "symptom": "All metrics within thresholds.",
                "evidence": {"gateway_latency_ms": 2.0},
                "possible_causes": ["Network is operating optimally."],
                "recommendations": ["No action needed."],
                "confidence": "High",
                "limitations": "Instantaneous snapshot.",
            }
        ],
    }

    return probe_report, diag_report


def test_init_db(tmp_path):
    """Verify database schema creation and table existence."""
    db_file = tmp_path / "test.db"
    init_db(db_file)

    conn = get_connection(db_file)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row["name"] for row in cursor.fetchall()]
    conn.close()

    assert "test_runs" in tables
    assert "metric_samples" in tables
    assert "dns_benchmarks" in tables
    assert "diagnostic_findings" in tables
    assert "alerts" in tables


def test_save_and_get_test_run(tmp_path):
    """Verify saving and retrieving a complete test run with all child records."""
    db_file = tmp_path / "test.db"
    init_db(db_file)

    probe_report, diag_report = create_sample_payloads()
    run_id = save_test_run(probe_report, diag_report, trigger_type="manual", db_path=db_file)
    assert run_id > 0

    run = get_test_run(run_id, db_path=db_file)
    assert run is not None
    assert run["id"] == run_id
    assert run["overall_status"] == "healthy"
    assert run["total_targets"] == 2
    assert run["gateway_ip"] == "192.168.1.1"

    # Check metric samples
    assert len(run["metric_samples"]) == 2
    gw_sample = next(s for s in run["metric_samples"] if s["target_id"] == "gateway")
    assert gw_sample["latency_avg_ms"] == 2.0
    assert gw_sample["samples"] == [1.5, 2.0, 2.5]

    web_sample = next(s for s in run["metric_samples"] if s["target_id"] == "google_web")
    assert web_sample["dns_lookup_time_ms"] == 18.5
    assert web_sample["tcp_handshake_time_ms"] == 22.0

    # Check DNS benchmarks
    assert len(run["dns_benchmarks"]) == 1
    assert run["dns_benchmarks"][0]["resolver_name"] == "Cloudflare"

    # Check diagnostic findings
    assert len(run["findings"]) == 1
    assert run["findings"][0]["rule_id"] == "RULE_CONNECTION_HEALTHY"
    assert run["findings"][0]["evidence"]["gateway_latency_ms"] == 2.0


def test_foreign_key_cascade(tmp_path):
    """Verify deleting a test run cascades to delete associated child records."""
    db_file = tmp_path / "test.db"
    init_db(db_file)

    probe_report, diag_report = create_sample_payloads()
    run_id = save_test_run(probe_report, diag_report, db_path=db_file)

    conn = get_connection(db_file)
    conn.execute("DELETE FROM test_runs WHERE id = ?;", (run_id,))
    conn.commit()

    samples_count = conn.execute("SELECT COUNT(*) as c FROM metric_samples WHERE test_run_id = ?;", (run_id,)).fetchone()["c"]
    findings_count = conn.execute("SELECT COUNT(*) as c FROM diagnostic_findings WHERE test_run_id = ?;", (run_id,)).fetchone()["c"]
    conn.close()

    assert samples_count == 0
    assert findings_count == 0


def test_recent_history_and_summary_stats(tmp_path):
    """Verify history queries and aggregate KPI statistics."""
    db_file = tmp_path / "test.db"
    init_db(db_file)

    probe_report, diag_report = create_sample_payloads()
    save_test_run(probe_report, diag_report, db_path=db_file)

    # Fetch recent history
    history = get_recent_history(hours=24, limit=10, db_path=db_file)
    assert len(history) == 1
    assert len(history[0]["samples"]) == 2

    # Fetch historical stats
    stats = get_historical_summary_stats(hours=24, db_path=db_file)
    assert stats["total_runs"] == 1
    assert stats["healthy_count"] == 1
    assert stats["warning_count"] == 0
    assert stats["critical_count"] == 0
    assert stats["avg_latency_ms"] == 23.0  # From external host
    assert stats["avg_loss_pct"] == 0.0


def test_alerts_crud(tmp_path):
    """Verify saving and retrieving threshold alerts."""
    db_file = tmp_path / "test.db"
    init_db(db_file)

    alert_id = save_alert("latency", 50.0, 125.0, "High external latency observed", db_path=db_file)
    assert alert_id > 0

    alerts = get_recent_alerts(limit=5, db_path=db_file)
    assert len(alerts) == 1
    assert alerts[0]["metric_name"] == "latency"
    assert alerts[0]["threshold_value"] == 50.0
    assert alerts[0]["observed_value"] == 125.0


def test_csv_export(tmp_path):
    """Verify historical CSV export output format."""
    db_file = tmp_path / "test.db"
    init_db(db_file)

    probe_report, diag_report = create_sample_payloads()
    save_test_run(probe_report, diag_report, db_path=db_file)

    csv_data = export_history_as_csv(hours=24, db_path=db_file)
    lines = csv_data.strip().splitlines()
    assert len(lines) == 3  # Header + 2 metric sample rows
    assert "Run ID,Timestamp (UTC)" in lines[0]
    assert "Default Gateway" in lines[1] or "Default Gateway" in lines[2]
    assert "Google Web" in lines[1] or "Google Web" in lines[2]

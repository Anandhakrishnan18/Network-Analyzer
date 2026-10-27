"""
SQLite Database Access Layer (DAL) for Internet Quality Analyzer.

Provides thread-safe connection handling, automated schema initialization,
atomic parameterized transactions, historical query filters, and CSV export.

Design Notes:
- WAL (Write-Ahead Logging) is enabled for high concurrency between reader HTTP threads
  and background measurement workers.
- Foreign key constraints are strictly enforced via PRAGMA foreign_keys = ON.
- Queries are strictly parameterized to prevent SQL injection.
"""

from contextlib import contextmanager
import csv
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import sqlite3
from typing import Dict, Any, List, Optional

from config import DATABASE_PATH

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def get_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """
    Establish a connection to the SQLite database with WAL and foreign keys enabled.
    """
    path = db_path or DATABASE_PATH
    # Ensure directory exists
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


@contextmanager
def get_db_cursor(db_path: Optional[Path] = None):
    """
    Context manager providing a transactional database cursor.
    Automatically commits on success or rolls back on exception.
    """
    conn = get_connection(db_path)
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: Optional[Path] = None) -> None:
    """
    Initialize SQLite database schema from schema.sql.
    Idempotent: safe to run on application startup.
    """
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema_sql = f.read()

    conn = get_connection(db_path)
    try:
        conn.executescript(schema_sql)
        conn.commit()
    finally:
        conn.close()


def save_test_run(
    probe_report: Dict[str, Any],
    diagnostic_report: Dict[str, Any],
    trigger_type: str = "manual",
    db_path: Optional[Path] = None
) -> int:
    """
    Persist a complete diagnostic test run, metric samples, DNS benchmarks, and findings.
    Operates within an atomic database transaction.

    Returns:
        The newly created test_runs ID.
    """
    timestamp_utc = probe_report.get(
        "timestamp_utc",
        datetime.now(timezone.utc).isoformat()
    )
    overall_status = diagnostic_report.get("overall_status", "unknown")
    summary = diagnostic_report.get("summary", "")
    target_results = probe_report.get("target_results", [])
    duration_seconds = probe_report.get("duration_seconds", 0.0)
    gateway_ip = probe_report.get("gateway_ip")
    local_ip = probe_report.get("interface_info", {}).get("local_ip")
    dns_benchmarks = probe_report.get("dns_benchmarks", [])
    findings = diagnostic_report.get("findings", [])

    with get_db_cursor(db_path) as cur:
        # 1. Insert test run header
        cur.execute(
            """
            INSERT INTO test_runs (
                timestamp_utc, trigger_type, overall_status, summary,
                total_targets, duration_seconds, gateway_ip, local_ip
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (
                timestamp_utc,
                trigger_type,
                overall_status,
                summary,
                len(target_results),
                duration_seconds,
                gateway_ip,
                local_ip,
            ),
        )
        run_id = cur.lastrowid

        # 2. Insert metric samples per target
        for t in target_results:
            ping_data = t.get("ping", {})
            samples_list = ping_data.get("samples", [])
            cur.execute(
                """
                INSERT INTO metric_samples (
                    test_run_id, target_id, target_name, target_type, target_address,
                    target_port, latency_avg_ms, latency_min_ms, latency_max_ms,
                    latency_median_ms, jitter_ms, packet_loss_pct, probes_sent,
                    probes_received, dns_lookup_time_ms, tcp_handshake_time_ms,
                    status, error_message, samples_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    run_id,
                    t.get("target_id", "unknown"),
                    t.get("target_name", "Unknown"),
                    t.get("target_type", "external_host"),
                    t.get("target_address", ""),
                    t.get("target_port"),
                    ping_data.get("avg_ms"),
                    ping_data.get("min_ms"),
                    ping_data.get("max_ms"),
                    ping_data.get("median_ms"),
                    ping_data.get("jitter_ms"),
                    ping_data.get("packet_loss_pct", 0.0),
                    ping_data.get("sent", 0),
                    ping_data.get("received", 0),
                    t.get("dns_lookup_ms"),
                    t.get("tcp_handshake_ms"),
                    ping_data.get("status", "unknown"),
                    ping_data.get("error_message"),
                    json.dumps(samples_list),
                ),
            )

        # 3. Insert DNS benchmarks
        for b in dns_benchmarks:
            cur.execute(
                """
                INSERT INTO dns_benchmarks (
                    test_run_id, resolver_name, resolver_ip, domain,
                    avg_ms, min_ms, max_ms, status, samples_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    run_id,
                    b.get("resolver_name", "Unknown"),
                    b.get("resolver_ip", ""),
                    b.get("domain", ""),
                    b.get("avg_ms"),
                    b.get("min_ms"),
                    b.get("max_ms"),
                    b.get("status", "unknown"),
                    json.dumps(b.get("samples", [])),
                ),
            )

        # 4. Insert diagnostic findings
        for f in findings:
            cur.execute(
                """
                INSERT INTO diagnostic_findings (
                    test_run_id, rule_id, severity, symptom, evidence_json,
                    possible_causes_json, recommendations_json, confidence, limitations
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    run_id,
                    f.get("rule_id", "UNKNOWN_RULE"),
                    f.get("severity", "info"),
                    f.get("symptom", ""),
                    json.dumps(f.get("evidence", {})),
                    json.dumps(f.get("possible_causes", [])),
                    json.dumps(f.get("recommendations", [])),
                    f.get("confidence", "Moderate"),
                    f.get("limitations", ""),
                ),
            )

        return run_id


def get_test_run(run_id: int, db_path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieve full details of a specific test run by ID, including metric samples,
    DNS benchmarks, and diagnostic findings.
    """
    conn = get_connection(db_path)
    try:
        run_row = conn.execute("SELECT * FROM test_runs WHERE id = ?;", (run_id,)).fetchone()
        if not run_row:
            return None

        run_dict = dict(run_row)

        # Fetch metric samples
        samples_rows = conn.execute(
            "SELECT * FROM metric_samples WHERE test_run_id = ? ORDER BY id ASC;",
            (run_id,)
        ).fetchall()
        metric_samples = []
        for r in samples_rows:
            d = dict(r)
            d["samples"] = json.loads(d["samples_json"]) if d["samples_json"] else []
            metric_samples.append(d)

        # Fetch DNS benchmarks
        bench_rows = conn.execute(
            "SELECT * FROM dns_benchmarks WHERE test_run_id = ? ORDER BY id ASC;",
            (run_id,)
        ).fetchall()
        dns_benchmarks = []
        for r in bench_rows:
            d = dict(r)
            d["samples"] = json.loads(d["samples_json"]) if d["samples_json"] else []
            dns_benchmarks.append(d)

        # Fetch diagnostic findings
        findings_rows = conn.execute(
            "SELECT * FROM diagnostic_findings WHERE test_run_id = ? ORDER BY id ASC;",
            (run_id,)
        ).fetchall()
        findings = []
        for r in findings_rows:
            d = dict(r)
            d["evidence"] = json.loads(d["evidence_json"]) if d["evidence_json"] else {}
            d["possible_causes"] = json.loads(d["possible_causes_json"]) if d["possible_causes_json"] else []
            d["recommendations"] = json.loads(d["recommendations_json"]) if d["recommendations_json"] else []
            findings.append(d)

        run_dict["metric_samples"] = metric_samples
        run_dict["dns_benchmarks"] = dns_benchmarks
        run_dict["findings"] = findings

        return run_dict

    finally:
        conn.close()


def get_recent_history(
    hours: int = 24,
    limit: int = 50,
    target_id: Optional[str] = None,
    db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """
    Retrieve summarized historical test runs formatted for timeline display and Chart.js.

    Args:
        hours: Filter for runs within the last N hours (0 = all time).
        limit: Maximum count of runs to return.
        target_id: Optional target ID to filter sample data (e.g. 'gateway' or 'google_web').
    """
    conn = get_connection(db_path)
    try:
        where_clauses = []
        params = []

        if hours > 0:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            where_clauses.append("timestamp_utc >= ?")
            params.append(cutoff)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        query = f"""
            SELECT * FROM test_runs
            {where_sql}
            ORDER BY id DESC
            LIMIT ?;
        """
        params.append(limit)
        runs = conn.execute(query, tuple(params)).fetchall()

        results = []
        for r in runs:
            run_item = dict(r)
            # Fetch samples for this run
            if target_id:
                s_query = "SELECT * FROM metric_samples WHERE test_run_id = ? AND target_id = ?;"
                s_params = (r["id"], target_id)
            else:
                s_query = "SELECT * FROM metric_samples WHERE test_run_id = ? ORDER BY id ASC;"
                s_params = (r["id"],)

            samples = conn.execute(s_query, s_params).fetchall()
            run_item["samples"] = [dict(s) for s in samples]
            results.append(run_item)

        return results

    finally:
        conn.close()


def get_historical_summary_stats(
    hours: int = 24,
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Compute high-level summary KPIs (average latency, average jitter, max loss, etc.)
    across recent historical test runs.
    """
    conn = get_connection(db_path)
    try:
        where_clauses = []
        params = []

        if hours > 0:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            where_clauses.append("tr.timestamp_utc >= ?")
            params.append(cutoff)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Total runs and status counts
        runs_query = f"""
            SELECT
                COUNT(*) as total_runs,
                SUM(CASE WHEN overall_status = 'healthy' THEN 1 ELSE 0 END) as healthy_count,
                SUM(CASE WHEN overall_status = 'warning' THEN 1 ELSE 0 END) as warning_count,
                SUM(CASE WHEN overall_status = 'critical' THEN 1 ELSE 0 END) as critical_count,
                MAX(timestamp_utc) as last_test_timestamp
            FROM test_runs tr
            {where_sql};
        """
        run_stats = conn.execute(runs_query, tuple(params)).fetchone()

        # External targets metric averages
        metrics_where = ["ms.target_type != 'gateway'"]
        if hours > 0:
            metrics_where.append("tr.timestamp_utc >= ?")

        metrics_query = f"""
            SELECT
                AVG(ms.latency_avg_ms) as avg_latency_ms,
                AVG(ms.jitter_ms) as avg_jitter_ms,
                AVG(ms.packet_loss_pct) as avg_loss_pct,
                AVG(ms.dns_lookup_time_ms) as avg_dns_ms,
                AVG(ms.tcp_handshake_time_ms) as avg_tcp_ms
            FROM metric_samples ms
            JOIN test_runs tr ON ms.test_run_id = tr.id
            WHERE {' AND '.join(metrics_where)};
        """
        metric_stats = conn.execute(metrics_query, tuple(params)).fetchone()

        total_runs = run_stats["total_runs"] if run_stats else 0

        return {
            "total_runs": total_runs,
            "healthy_count": run_stats["healthy_count"] or 0 if run_stats else 0,
            "warning_count": run_stats["warning_count"] or 0 if run_stats else 0,
            "critical_count": run_stats["critical_count"] or 0 if run_stats else 0,
            "last_test_timestamp": run_stats["last_test_timestamp"] if run_stats else None,
            "avg_latency_ms": round(metric_stats["avg_latency_ms"], 2) if metric_stats and metric_stats["avg_latency_ms"] else None,
            "avg_jitter_ms": round(metric_stats["avg_jitter_ms"], 2) if metric_stats and metric_stats["avg_jitter_ms"] else None,
            "avg_loss_pct": round(metric_stats["avg_loss_pct"], 2) if metric_stats and metric_stats["avg_loss_pct"] else 0.0,
            "avg_dns_ms": round(metric_stats["avg_dns_ms"], 2) if metric_stats and metric_stats["avg_dns_ms"] else None,
            "avg_tcp_ms": round(metric_stats["avg_tcp_ms"], 2) if metric_stats and metric_stats["avg_tcp_ms"] else None,
        }

    finally:
        conn.close()


def save_alert(
    metric_name: str,
    threshold_val: float,
    observed_val: float,
    message: str,
    test_run_id: Optional[int] = None,
    db_path: Optional[Path] = None
) -> int:
    """Save a threshold breach alert."""
    timestamp_utc = datetime.now(timezone.utc).isoformat()
    with get_db_cursor(db_path) as cur:
        cur.execute(
            """
            INSERT INTO alerts (
                test_run_id, timestamp_utc, metric_name, threshold_value, observed_value, message
            ) VALUES (?, ?, ?, ?, ?, ?);
            """,
            (test_run_id, timestamp_utc, metric_name, threshold_val, observed_val, message),
        )
        return cur.lastrowid


def get_recent_alerts(limit: int = 20, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Retrieve recent alerts."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM alerts ORDER BY id DESC LIMIT ?;",
            (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def export_history_as_csv(hours: int = 168, db_path: Optional[Path] = None) -> str:
    """
    Generate a CSV formatted string containing detailed historical measurements.

    Args:
        hours: How far back to export (default 168 hours = 7 days).

    Returns:
        String containing CSV data.
    """
    conn = get_connection(db_path)
    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow([
        "Run ID",
        "Timestamp (UTC)",
        "Trigger Type",
        "Overall Status",
        "Target ID",
        "Target Name",
        "Target Type",
        "Target Address",
        "Target Port",
        "Latency Avg (ms)",
        "Latency Min (ms)",
        "Latency Max (ms)",
        "Latency Median (ms)",
        "Jitter (ms)",
        "Packet Loss (%)",
        "Probes Sent",
        "Probes Received",
        "DNS Lookup (ms)",
        "TCP Handshake (ms)",
        "Sample Status",
        "Error Message",
    ])

    try:
        where_sql = ""
        params = []
        if hours > 0:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            where_sql = "WHERE tr.timestamp_utc >= ?"
            params.append(cutoff)

        query = f"""
            SELECT
                tr.id as run_id,
                tr.timestamp_utc,
                tr.trigger_type,
                tr.overall_status,
                ms.target_id,
                ms.target_name,
                ms.target_type,
                ms.target_address,
                ms.target_port,
                ms.latency_avg_ms,
                ms.latency_min_ms,
                ms.latency_max_ms,
                ms.latency_median_ms,
                ms.jitter_ms,
                ms.packet_loss_pct,
                ms.probes_sent,
                ms.probes_received,
                ms.dns_lookup_time_ms,
                ms.tcp_handshake_time_ms,
                ms.status as sample_status,
                ms.error_message
            FROM metric_samples ms
            JOIN test_runs tr ON ms.test_run_id = tr.id
            {where_sql}
            ORDER BY tr.id DESC, ms.id ASC;
        """
        rows = conn.execute(query, tuple(params)).fetchall()

        for r in rows:
            writer.writerow([
                r["run_id"],
                r["timestamp_utc"],
                r["trigger_type"],
                r["overall_status"],
                r["target_id"],
                r["target_name"],
                r["target_type"],
                r["target_address"],
                r["target_port"] or "",
                r["latency_avg_ms"] or "",
                r["latency_min_ms"] or "",
                r["latency_max_ms"] or "",
                r["latency_median_ms"] or "",
                r["jitter_ms"] or "",
                r["packet_loss_pct"],
                r["probes_sent"],
                r["probes_received"],
                r["dns_lookup_time_ms"] or "",
                r["tcp_handshake_time_ms"] or "",
                r["sample_status"],
                r["error_message"] or "",
            ])

        return output.getvalue()

    finally:
        conn.close()

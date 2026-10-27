"""
Stage 9 Validation & Robustness Test Suite.

Simulates and verifies real-world network failure modes and system edge cases:
1. Complete Network Disconnection (Physical media / Wi-Fi disconnected).
2. Upstream WAN / ISP Outage (Local gateway healthy, internet unreachable).
3. Local Gateway / Wi-Fi Congestion (Hop-1 bottleneck isolation).
4. DNS Resolution Failure / Server Outage (Transport layer alive, DNS dead).
5. High Jitter and Bufferbloat (Delay variance under congestion).
6. Single Remote Destination Anomaly (Isolated server failure).
7. Input Validation & SQL Injection Defense (Security boundary checks).
8. Concurrent Access & Thread Safety (Database concurrency and monitoring state).
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app import create_app
from analysis.troubleshooter import Troubleshooter
from analysis.comparator import compare_runs, compare_destinations
from database.db import (
    init_db,
    save_test_run,
    get_test_run,
    get_recent_history,
    get_historical_summary_stats,
    get_connection,
)
from network.engine import run_full_diagnostic_probe
from services.monitoring_service import MonitoringService


# ==============================================================================
# Scenario 1: Complete Media Disconnection (Total Network Failure)
# ==============================================================================

@patch("network.engine.get_network_interface_info")
@patch("network.engine.get_default_gateway")
@patch("network.engine.run_ping_test")
@patch("network.engine.measure_dns_lookup")
@patch("network.engine.measure_tcp_connect")
@patch("network.engine.run_dns_benchmark")
def test_scenario_complete_network_disconnection(
    mock_bench, mock_tcp, mock_dns, mock_ping, mock_gw, mock_iface
):
    """
    Verify behavior when the device has no network connectivity:
    - Gateway detector returns None.
    - Ping returns 100% loss / host unreachable.
    - DNS lookups and TCP connections fail.
    - Troubleshooter diagnoses RULE_ALL_DESTINATIONS_FAILED with critical status.
    - System does not crash or raise unhandled exceptions.
    """
    mock_gw.return_value = None
    mock_iface.return_value = {"local_ip": None, "default_gateway": None}
    mock_bench.return_value = []

    mock_ping.return_value = {
        "target": "example",
        "resolved_ip": None,
        "sent": 5,
        "received": 0,
        "lost": 5,
        "packet_loss_pct": 100.0,
        "min_ms": None,
        "max_ms": None,
        "avg_ms": None,
        "median_ms": None,
        "jitter_ms": None,
        "samples": [None, None, None, None, None],
        "status": "failed",
        "error_message": "Destination host unreachable",
    }
    mock_dns.return_value = {
        "domain": "google.com",
        "resolver": "System Default",
        "query_type": "A",
        "elapsed_ms": None,
        "resolved_ips": [],
        "success": False,
        "error_category": "DNS Resolution Error: [Errno 11001] getaddrinfo failed",
        "status": "failed",
    }
    mock_tcp.return_value = {
        "host": "google.com",
        "port": 443,
        "handshake_ms": None,
        "success": False,
        "status": "failed",
        "error_category": "Socket Error: OSError (Network is unreachable)",
    }

    # Run composite measurement
    report = run_full_diagnostic_probe(target_ids=["gateway", "google_web"])
    assert report["gateway_detected"] is False
    assert report["gateway_ip"] is None

    # Evaluate diagnosis
    ts = Troubleshooter()
    diag = ts.diagnose(report)

    assert diag["overall_status"] == "critical"
    rule_ids = [f["rule_id"] for f in diag["findings"]]
    assert "RULE_ALL_DESTINATIONS_FAILED" in rule_ids

    crit_finding = next(f for f in diag["findings"] if f["rule_id"] == "RULE_ALL_DESTINATIONS_FAILED")
    assert crit_finding["confidence"] == "High"
    assert any("cable" in r.lower() or "wi-fi" in r.lower() for r in crit_finding["recommendations"])
    assert "firewall" in crit_finding["limitations"].lower()


# ==============================================================================
# Scenario 2: Upstream WAN Outage (Gateway Reachable, Internet Down)
# ==============================================================================

def test_scenario_wan_outage_gateway_intact():
    """
    Verify differential diagnosis when hop-1 gateway is responsive, but all WAN
    destinations are unreachable:
    - Gateway RTT is 1.8ms (0% loss).
    - External destinations suffer 100% loss.
    - Troubleshooter pinpoints WAN / ISP failure, explicitly exonerating local router.
    """
    report = {
        "gateway_detected": True,
        "gateway_ip": "192.168.1.1",
        "target_results": [
            {
                "target_id": "gateway",
                "target_name": "Default Gateway",
                "target_type": "gateway",
                "target_address": "192.168.1.1",
                "ping": {
                    "sent": 5, "received": 5, "lost": 0, "packet_loss_pct": 0.0,
                    "avg_ms": 1.8, "jitter_ms": 0.4, "status": "success"
                },
                "dns_lookup_ms": None,
                "tcp_handshake_ms": None,
            },
            {
                "target_id": "cloudflare_dns",
                "target_name": "Cloudflare DNS",
                "target_type": "dns_resolver",
                "target_address": "1.1.1.1",
                "ping": {
                    "sent": 5, "received": 0, "lost": 5, "packet_loss_pct": 100.0,
                    "avg_ms": None, "jitter_ms": None, "status": "failed"
                },
                "dns_lookup_ms": None,
                "tcp_handshake_ms": None,
            },
            {
                "target_id": "google_web",
                "target_name": "Google Web",
                "target_type": "external_host",
                "target_address": "google.com",
                "ping": {
                    "sent": 5, "received": 0, "lost": 5, "packet_loss_pct": 100.0,
                    "avg_ms": None, "jitter_ms": None, "status": "failed"
                },
                "dns_lookup_ms": None,
                "tcp_handshake_ms": None,
            },
        ],
        "dns_benchmarks": [],
    }

    ts = Troubleshooter()
    diag = ts.diagnose(report)

    rule_ids = [f["rule_id"] for f in diag["findings"]]
    # Should flag WAN packet loss
    assert "RULE_WAN_PACKET_LOSS" in rule_ids
    # Should NOT falsely blame the local gateway
    assert "RULE_LOCAL_GATEWAY_DEGRADED" not in rule_ids
    assert "RULE_LOCAL_GATEWAY_UNREACHABLE" not in rule_ids

    finding = next(f for f in diag["findings"] if f["rule_id"] == "RULE_WAN_PACKET_LOSS")
    assert finding["severity"] == "critical"
    assert finding["evidence"]["gateway_loss_pct"] == 0.0
    assert any("isp" in c.lower() for c in finding["possible_causes"])


# ==============================================================================
# Scenario 3: Local Gateway Bottleneck / Wi-Fi Congestion (LAN Fault)
# ==============================================================================

def test_scenario_local_gateway_degradation_isolation():
    """
    Verify differential diagnosis when latency and packet loss originate on the
    local gateway hop (e.g. Wi-Fi signal attenuation):
    - Gateway RTT is 95ms with 12% loss and 28ms jitter.
    - External hosts show 118ms (95ms gateway + 23ms WAN transit).
    - Troubleshooter identifies the local link as the primary root cause.
    """
    report = {
        "gateway_detected": True,
        "gateway_ip": "192.168.1.1",
        "target_results": [
            {
                "target_id": "gateway",
                "target_name": "Default Gateway",
                "target_type": "gateway",
                "target_address": "192.168.1.1",
                "ping": {
                    "sent": 5, "received": 4, "lost": 1, "packet_loss_pct": 20.0,
                    "avg_ms": 95.0, "jitter_ms": 28.0, "status": "degraded"
                },
            },
            {
                "target_id": "google_web",
                "target_name": "Google Web",
                "target_type": "external_host",
                "target_address": "google.com",
                "ping": {
                    "sent": 5, "received": 4, "lost": 1, "packet_loss_pct": 20.0,
                    "avg_ms": 118.0, "jitter_ms": 29.0, "status": "degraded"
                },
            },
        ],
        "dns_benchmarks": [],
    }

    ts = Troubleshooter()
    diag = ts.diagnose(report)

    rule_ids = [f["rule_id"] for f in diag["findings"]]
    assert "RULE_LOCAL_GATEWAY_DEGRADED" in rule_ids

    gw_finding = next(f for f in diag["findings"] if f["rule_id"] == "RULE_LOCAL_GATEWAY_DEGRADED")
    assert gw_finding["confidence"] == "High"
    assert any("5 ghz" in r.lower() or "closer" in r.lower() or "ethernet" in r.lower() for r in gw_finding["recommendations"])

    # Destination comparison should compute a modest WAN penalty (~23ms)
    dest_comp = compare_destinations({
        "id": 1,
        "timestamp_utc": "2026-10-21T12:00:00Z",
        "metric_samples": [
            {
                "target_id": "gateway", "target_name": "Default Gateway", "target_type": "gateway",
                "latency_avg_ms": 95.0, "jitter_ms": 28.0, "packet_loss_pct": 20.0,
            },
            {
                "target_id": "google_web", "target_name": "Google Web", "target_type": "external_host",
                "latency_avg_ms": 118.0, "jitter_ms": 29.0, "packet_loss_pct": 20.0,
            },
        ],
    })
    google_target = next(d for d in dest_comp["all_destinations"] if d["target_id"] == "google_web")
    assert google_target["wan_penalty_ms"] == 23.0  # 118 - 95


# ==============================================================================
# Scenario 4: DNS Outage with Healthy Transport Layer
# ==============================================================================

def test_scenario_dns_nameserver_outage_with_working_transport():
    """
    Verify diagnosis when ICMP and TCP connection establishment are healthy,
    but DNS resolution is severely delayed (>150ms).
    """
    report = {
        "gateway_detected": True,
        "gateway_ip": "192.168.1.1",
        "target_results": [
            {
                "target_id": "gateway",
                "target_name": "Default Gateway",
                "target_type": "gateway",
                "target_address": "192.168.1.1",
                "ping": {"avg_ms": 2.0, "packet_loss_pct": 0.0, "jitter_ms": 0.5, "status": "success"},
            },
            {
                "target_id": "google_web",
                "target_name": "Google Web",
                "target_type": "external_host",
                "target_address": "google.com",
                "ping": {"avg_ms": 22.0, "packet_loss_pct": 0.0, "jitter_ms": 2.0, "status": "success"},
                "dns_lookup_ms": 280.0,  # Well above 150ms warning threshold
                "tcp_handshake_ms": 25.0,
            },
        ],
        "dns_benchmarks": [],
    }

    ts = Troubleshooter()
    diag = ts.diagnose(report)

    rule_ids = [f["rule_id"] for f in diag["findings"]]
    assert "RULE_DNS_RESOLUTION_BOTTLENECK" in rule_ids

    dns_finding = next(f for f in diag["findings"] if f["rule_id"] == "RULE_DNS_RESOLUTION_BOTTLENECK")
    assert any("1.1.1.1" in r or "8.8.8.8" in r for r in dns_finding["recommendations"])


# ==============================================================================
# Scenario 5: High Jitter and Bufferbloat
# ==============================================================================

def test_scenario_high_jitter_bufferbloat():
    """
    Verify detection of high delay variability (jitter > 30ms) while packet loss is zero.
    """
    report = {
        "gateway_detected": True,
        "gateway_ip": "192.168.1.1",
        "target_results": [
            {
                "target_id": "gateway",
                "target_name": "Default Gateway",
                "target_type": "gateway",
                "target_address": "192.168.1.1",
                "ping": {"avg_ms": 2.0, "packet_loss_pct": 0.0, "jitter_ms": 0.5, "status": "success"},
            },
            {
                "target_id": "cloudflare_dns",
                "target_name": "Cloudflare DNS",
                "target_type": "dns_resolver",
                "target_address": "1.1.1.1",
                "ping": {
                    "avg_ms": 55.0,
                    "packet_loss_pct": 0.0,
                    "jitter_ms": 65.0,  # High jitter > 30ms
                    "status": "warning",
                },
            },
        ],
        "dns_benchmarks": [],
    }

    ts = Troubleshooter()
    diag = ts.diagnose(report)

    rule_ids = [f["rule_id"] for f in diag["findings"]]
    assert "RULE_HIGH_JITTER_BUFFERBLOAT" in rule_ids

    jitter_finding = next(f for f in diag["findings"] if f["rule_id"] == "RULE_HIGH_JITTER_BUFFERBLOAT")
    assert any("sqm" in r.lower() or "fq_codel" in r.lower() or "cake" in r.lower() for r in jitter_finding["recommendations"])


# ==============================================================================
# Scenario 6: Single Remote Destination Failure
# ==============================================================================

def test_scenario_single_destination_outage():
    """
    Verify that an isolated destination failure (e.g. 1 out of 4 targets down)
    is diagnosed as a remote endpoint issue rather than a local or ISP failure.
    """
    report = {
        "gateway_detected": True,
        "gateway_ip": "192.168.1.1",
        "target_results": [
            {
                "target_id": "gateway",
                "target_name": "Default Gateway",
                "target_type": "gateway",
                "ping": {"avg_ms": 2.0, "packet_loss_pct": 0.0, "jitter_ms": 0.5, "status": "success"},
            },
            {
                "target_id": "cloudflare_dns",
                "target_name": "Cloudflare DNS",
                "target_type": "dns_resolver",
                "ping": {"avg_ms": 15.0, "packet_loss_pct": 0.0, "jitter_ms": 1.0, "status": "success"},
            },
            {
                "target_id": "google_dns",
                "target_name": "Google DNS",
                "target_type": "dns_resolver",
                "ping": {"avg_ms": 16.0, "packet_loss_pct": 0.0, "jitter_ms": 1.2, "status": "success"},
            },
            {
                "target_id": "remote_problematic_host",
                "target_name": "Remote Problematic Host",
                "target_type": "external_host",
                "ping": {"avg_ms": None, "packet_loss_pct": 100.0, "jitter_ms": None, "status": "failed"},
            },
        ],
        "dns_benchmarks": [],
    }

    ts = Troubleshooter()
    diag = ts.diagnose(report)

    rule_ids = [f["rule_id"] for f in diag["findings"]]
    assert "RULE_SINGLE_DESTINATION_ANOMALY" in rule_ids
    # Should not blame the whole WAN connection
    assert "RULE_WAN_PACKET_LOSS" not in rule_ids


# ==============================================================================
# Scenario 7: Input Validation & SQL Injection Boundary Testing
# ==============================================================================

def test_scenario_input_validation_and_sql_injection(tmp_path):
    """
    Verify parameterized SQL queries prevent SQL injection payloads and
    database corruption under malicious inputs.
    """
    db_file = tmp_path / "security_test.db"
    init_db(db_file)

    # Malicious injection payloads
    sql_payload = "'; DROP TABLE test_runs; --"
    html_payload = "<script>alert('xss')</script>"

    probe_report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "duration_seconds": 1.5,
        "interface_info": {"local_ip": "127.0.0.1", "default_gateway": "127.0.0.1"},
        "gateway_detected": True,
        "gateway_ip": sql_payload,  # injected in gateway_ip
        "target_results": [
            {
                "target_id": sql_payload,
                "target_name": html_payload,
                "target_type": "external_host",
                "target_address": "127.0.0.1",
                "target_port": 80,
                "ping": {
                    "sent": 3, "received": 3, "lost": 0, "packet_loss_pct": 0.0,
                    "avg_ms": 10.0, "status": "success",
                },
                "dns_lookup_ms": None,
                "tcp_handshake_ms": None,
            }
        ],
        "dns_benchmarks": [],
    }

    diagnostic_report = {
        "overall_status": "healthy",
        "summary": sql_payload,
        "findings": [
            {
                "rule_id": "RULE_TEST_INJECTION",
                "severity": "info",
                "symptom": sql_payload,
                "evidence": {"input": sql_payload},
                "possible_causes": [sql_payload],
                "recommendations": [sql_payload],
                "confidence": "High",
                "limitations": sql_payload,
            }
        ],
    }

    # Save test run with malicious payload
    run_id = save_test_run(probe_report, diagnostic_report, trigger_type="manual", db_path=db_file)
    assert run_id > 0

    # Verify table was NOT dropped and database is intact
    with get_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM test_runs")
        count = cursor.fetchone()[0]
        assert count == 1

    # Verify data was safely stored and retrieved verbatim
    saved_run = get_test_run(run_id, db_path=db_file)
    assert saved_run["gateway_ip"] == sql_payload
    assert saved_run["summary"] == sql_payload
    assert saved_run["findings"][0]["symptom"] == sql_payload


# ==============================================================================
# Scenario 8: Concurrency & Database Thread Safety
# ==============================================================================

def test_scenario_concurrency_and_database_thread_safety(tmp_path):
    """
    Verify multi-threaded concurrent database writes and reads under SQLite WAL mode:
    - 10 worker threads write and query simultaneously.
    - Zero 'database is locked' errors occur.
    - All records are safely committed.
    """
    db_file = tmp_path / "concurrent_test.db"
    init_db(db_file)

    def worker_write_and_read(worker_id: int):
        probe_report = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "duration_seconds": 0.5,
            "interface_info": {},
            "gateway_detected": True,
            "gateway_ip": f"192.168.1.{worker_id}",
            "target_results": [
                {
                    "target_id": "google_web",
                    "target_name": "Google Web",
                    "target_type": "external_host",
                    "target_address": "google.com",
                    "target_port": 443,
                    "ping": {
                        "sent": 3, "received": 3, "lost": 0, "packet_loss_pct": 0.0,
                        "avg_ms": 20.0 + worker_id, "status": "success",
                    },
                    "dns_lookup_ms": 15.0,
                    "tcp_handshake_ms": 22.0,
                }
            ],
            "dns_benchmarks": [],
        }
        diagnostic_report = {
            "overall_status": "healthy",
            "summary": f"Worker {worker_id} test run",
            "findings": [],
        }

        # Atomic insert
        run_id = save_test_run(probe_report, diagnostic_report, trigger_type="periodic", db_path=db_file)
        # Concurrent read
        run = get_test_run(run_id, db_path=db_file)
        assert run["id"] == run_id
        # Concurrent history query
        history = get_recent_history(limit=10, db_path=db_file)
        assert len(history) >= 1
        return run_id

    # Execute 10 concurrent database workers
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(worker_write_and_read, i) for i in range(10)]
        results = [f.result() for f in futures]

    assert len(results) == 10
    # Verify all 10 runs were recorded in the database
    with get_connection(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM test_runs")
        total_runs = cursor.fetchone()[0]
        assert total_runs == 10


# ==============================================================================
# Scenario 9: Monitoring Daemon Concurrency & Lifecycle
# ==============================================================================

def test_scenario_monitoring_daemon_rapid_lifecycle():
    """
    Verify MonitoringService handles rapid start/stop/status transitions without deadlocking.
    """
    service = MonitoringService()

    # Rapid lifecycle transitions
    res1 = service.start(interval_seconds=60)
    assert res1["status"] in ("started", "already_running")

    # Double start should not fail or create duplicate threads
    res2 = service.start(interval_seconds=60)
    assert res2["status"] == "already_running"

    status = service.get_status()
    assert status["running"] is True
    assert service.is_running is True

    res3 = service.stop()
    assert res3["status"] == "stopped"

    # Double stop should be idempotent
    res4 = service.stop()
    assert res4["status"] in ("not_running", "already_stopped")

    final_status = service.get_status()
    assert final_status["running"] is False
    assert service.is_running is False


# ==============================================================================
# Scenario 10: API Boundary & HTTP Error Handling
# ==============================================================================

@pytest.fixture
def api_client(tmp_path):
    """Provide isolated API client with fresh temporary database."""
    db_file = tmp_path / "api_boundary_test.db"
    app = create_app({"DATABASE_PATH": db_file, "TESTING": True})
    with app.test_client() as c:
        yield c


def test_scenario_api_boundary_and_error_handling(api_client):
    """
    Verify API robustness against invalid types, non-existent records,
    malformed query params, and unsupported HTTP methods.
    """
    # 1. Non-existent test run retrieval -> 404
    res = api_client.get("/api/tests/999999")
    assert res.status_code == 404
    assert res.get_json()["status"] == "error"

    # 2. Non-existent test run JSON export -> 404
    res = api_client.get("/api/export/test/999999/json")
    assert res.status_code == 404
    assert res.get_json()["status"] == "error"

    # 3. Destination comparison with non-existent ID -> 404
    res = api_client.get("/api/compare/destinations?run_id=999999")
    assert res.status_code == 404
    assert res.get_json()["status"] == "error"

    # 4. Destination comparison with invalid non-integer ID -> 400
    res = api_client.get("/api/compare/destinations?run_id=not_an_int")
    assert res.status_code == 400
    assert "must be an integer" in res.get_json()["message"]

    # 5. Compare sessions with non-integer parameters -> 400
    res = api_client.get("/api/compare?run_a=abc&run_b=def")
    assert res.status_code == 400
    assert "must be valid integers" in res.get_json()["message"]

    # 6. Compare sessions with non-existent run IDs -> 404
    res = api_client.get("/api/compare?run_a=9998&run_b=9999")
    assert res.status_code == 404
    assert "not found" in res.get_json()["message"]

    # 7. Compare export CSV with non-integer parameters -> 400
    res = api_client.get("/api/export/comparison/csv?run_a=abc&run_b=def")
    assert res.status_code == 400

    # 8. Compare export JSON with non-integer parameters -> 400
    res = api_client.get("/api/export/comparison/json?run_a=abc&run_b=def")
    assert res.status_code == 400

    # 9. Invalid query param types on history and stats
    res = api_client.get("/api/history?hours=invalid_hours")
    assert res.status_code == 400

    res = api_client.get("/api/stats?hours=invalid_hours")
    assert res.status_code == 400

    # 10. Unsupported HTTP method -> 405 Method Not Allowed
    res = api_client.delete("/api/health")
    assert res.status_code == 405
    assert res.get_json()["status"] == "error"


"""
Unit and Integration Tests for Periodic Monitoring & Alerting Service.
"""

from unittest.mock import patch
import pytest
from services.monitoring_service import MonitoringService
from database.db import init_db, get_recent_alerts, get_test_run
from app import create_app


@pytest.fixture
def test_db(tmp_path):
    """Temporary database fixture."""
    db_file = tmp_path / "test_mon.db"
    init_db(db_file)
    return db_file


@patch("services.monitoring_service.run_full_diagnostic_probe")
def test_monitoring_lifecycle(mock_probe, test_db):
    """Test start, duplicate start prevention, and stop lifecycle with mocked network probe."""
    mock_probe.return_value = {
        "timestamp_utc": "2026-10-21T16:30:00Z",
        "duration_seconds": 0.5,
        "interface_info": {},
        "gateway_detected": True,
        "gateway_ip": "192.168.1.1",
        "target_results": [],
        "dns_benchmarks": [],
    }

    svc = MonitoringService(db_path=test_db)
    assert svc.is_running is False

    # 1. Start with 60s interval
    start_res = svc.start(interval_seconds=60)
    assert start_res["status"] == "started"
    assert svc.is_running is True
    assert svc.interval_seconds == 60

    # 2. Duplicate start must be rejected gracefully
    dup_res = svc.start(interval_seconds=60)
    assert dup_res["status"] == "already_running"

    # 3. Stop
    stop_res = svc.stop()
    assert stop_res["status"] == "stopped"
    assert svc.is_running is False


@patch("services.monitoring_service.run_full_diagnostic_probe")
def test_monitoring_single_cycle_and_alerts(mock_probe, test_db):
    """Verify single execution cycle creates a periodic run and triggers alerts on threshold breaches."""
    mock_probe.return_value = {
        "timestamp_utc": "2026-10-21T16:30:00Z",
        "duration_seconds": 0.5,
        "interface_info": {"local_ip": "192.168.1.100", "default_gateway": "192.168.1.1"},
        "gateway_detected": True,
        "gateway_ip": "192.168.1.1",
        "target_results": [
            {
                "target_id": "google_web",
                "target_name": "Google Web",
                "target_type": "external_host",
                "target_address": "google.com",
                "target_port": 443,
                "ping": {
                    "sent": 5,
                    "received": 4,
                    "lost": 1,
                    "packet_loss_pct": 20.0,
                    "avg_ms": 150.0,
                    "min_ms": 140.0,
                    "max_ms": 160.0,
                    "jitter_ms": 30.0,
                    "status": "degraded",
                },
                "dns_lookup_ms": 25.0,
                "tcp_handshake_ms": 145.0,
            }
        ],
        "dns_benchmarks": [],
    }

    svc = MonitoringService(db_path=test_db)
    run_id = svc.run_single_cycle()

    assert run_id is not None
    assert run_id > 0

    # Verify run persisted with 'periodic' trigger
    run = get_test_run(run_id, db_path=test_db)
    assert run["trigger_type"] == "periodic"

    # Verify alerts were automatically triggered and saved
    alerts = get_recent_alerts(limit=10, db_path=test_db)
    assert len(alerts) >= 2
    metric_names = [a["metric_name"] for a in alerts]
    assert any("Packet Loss" in m for m in metric_names)
    assert any("Latency" in m for m in metric_names)


@patch("services.monitoring_service.run_full_diagnostic_probe")
def test_monitoring_api_endpoints(mock_probe, tmp_path):
    """Verify Flask REST endpoints for monitoring."""
    mock_probe.return_value = {
        "timestamp_utc": "2026-10-21T16:30:00Z",
        "duration_seconds": 0.1,
        "interface_info": {},
        "gateway_detected": False,
        "gateway_ip": None,
        "target_results": [],
        "dns_benchmarks": [],
    }

    db_file = tmp_path / "test_api_mon.db"
    app = create_app({"DATABASE_PATH": db_file, "TESTING": True})
    client = app.test_client()

    # GET /api/monitoring/status
    res = client.get("/api/monitoring/status")
    assert res.status_code == 200
    assert "running" in res.get_json()["data"]

    # POST /api/monitoring/start
    start_res = client.post("/api/monitoring/start", json={"interval_seconds": 120})
    assert start_res.status_code == 200

    # POST /api/monitoring/stop
    stop_res = client.post("/api/monitoring/stop")
    assert stop_res.status_code == 200

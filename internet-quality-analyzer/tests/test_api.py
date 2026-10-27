"""
API Integration Tests for Internet Quality Analyzer REST Endpoints.
"""

from unittest.mock import patch
import pytest
from app import create_app


@pytest.fixture
def client(tmp_path):
    """Create a test client with an isolated temporary SQLite database."""
    test_db = tmp_path / "test_api.db"
    app = create_app({"DATABASE_PATH": test_db, "TESTING": True})
    with app.test_client() as test_client:
        yield test_client


def test_index_route(client):
    """Verify index HTML route renders properly."""
    res = client.get("/")
    assert res.status_code == 200
    assert b"Internet Quality Analyzer" in res.data


def test_api_health(client):
    """Verify GET /api/health endpoint."""
    res = client.get("/api/health")
    assert res.status_code == 200
    json_data = res.get_json()
    assert json_data["status"] == "success"
    assert json_data["data"]["service"] == "Internet Quality Analyzer"
    assert "python_version" in json_data["data"]
    assert json_data["data"]["database_initialized"] is True


def test_api_config_get_and_post(client):
    """Verify reading and updating configuration thresholds."""
    # 1. GET configuration
    res = client.get("/api/config")
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert len(data["allowed_targets"]) > 0
    assert "latency" in data["thresholds"]

    # 2. POST update thresholds
    update_payload = {
        "thresholds": {
            "latency": {"good": 40.0, "warning": 100.0}
        }
    }
    post_res = client.post("/api/config", json=update_payload)
    assert post_res.status_code == 200
    updated_data = post_res.get_json()["data"]
    assert updated_data["thresholds"]["latency"]["good"] == 40.0
    assert updated_data["thresholds"]["latency"]["warning"] == 100.0


def test_api_config_update_invalid(client):
    """Verify validation rejects invalid threshold values."""
    # Negative value
    res = client.post("/api/config", json={"thresholds": {"latency": {"good": -5.0}}})
    assert res.status_code == 400
    assert "cannot be negative" in res.get_json()["message"]

    # Non-numeric value
    res = client.post("/api/config", json={"thresholds": {"latency": {"good": "not_a_number"}}})
    assert res.status_code == 400
    assert "must be a valid number" in res.get_json()["message"]


def test_api_run_test_validation_errors(client):
    """Verify request validation for test execution."""
    # Invalid target
    res = client.post("/api/tests", json={"targets": ["unapproved_target_id"]})
    assert res.status_code == 400
    assert "Invalid target identifier" in res.get_json()["message"]

    # Invalid probe count (too low)
    res = client.post("/api/tests", json={"probe_count": 1})
    assert res.status_code == 400
    assert "probe_count must be between" in res.get_json()["message"]

    # Invalid probe count (too high)
    res = client.post("/api/tests", json={"probe_count": 50})
    assert res.status_code == 400
    assert "probe_count must be between" in res.get_json()["message"]


@patch("app.run_full_diagnostic_probe")
def test_api_run_test_mocked_success(mock_probe, client):
    """Verify successful diagnostic run creation, database insertion, and return payload."""
    mock_probe.return_value = {
        "timestamp_utc": "2026-10-21T16:00:00Z",
        "duration_seconds": 1.2,
        "interface_info": {"local_ip": "10.0.0.5", "default_gateway": "10.0.0.1"},
        "gateway_detected": True,
        "gateway_ip": "10.0.0.1",
        "target_results": [
            {
                "target_id": "gateway",
                "target_name": "Default Gateway",
                "target_type": "gateway",
                "target_address": "10.0.0.1",
                "target_port": None,
                "ping": {
                    "sent": 3,
                    "received": 3,
                    "lost": 0,
                    "packet_loss_pct": 0.0,
                    "min_ms": 2.0,
                    "max_ms": 3.0,
                    "avg_ms": 2.5,
                    "median_ms": 2.5,
                    "jitter_ms": 0.5,
                    "samples": [2.0, 3.0, 2.5],
                    "status": "success",
                    "error_message": None,
                },
                "dns_lookup_ms": None,
                "tcp_handshake_ms": None,
            }
        ],
        "dns_benchmarks": [],
    }

    res = client.post("/api/tests", json={"targets": ["gateway"], "probe_count": 3})
    assert res.status_code == 201
    json_data = res.get_json()
    assert json_data["status"] == "success"
    data = json_data["data"]
    assert data["id"] > 0
    assert data["overall_status"] == "healthy"
    assert len(data["metric_samples"]) == 1
    assert len(data["findings"]) > 0

    # Test GET /api/tests/<run_id>
    run_id = data["id"]
    get_res = client.get(f"/api/tests/{run_id}")
    assert get_res.status_code == 200
    assert get_res.get_json()["data"]["id"] == run_id


def test_api_get_test_not_found(client):
    """Verify 404 for non-existent test run."""
    res = client.get("/api/tests/99999")
    assert res.status_code == 404
    assert res.get_json()["status"] == "error"


@patch("app.run_full_diagnostic_probe")
def test_api_history_and_stats(mock_probe, client):
    """Verify historical queries and summary statistics endpoints."""
    mock_probe.return_value = {
        "timestamp_utc": "2026-10-21T16:00:00Z",
        "duration_seconds": 1.0,
        "interface_info": {},
        "gateway_detected": False,
        "gateway_ip": None,
        "target_results": [],
        "dns_benchmarks": [],
    }

    # Run one test
    client.post("/api/tests", json={})

    # Test history
    h_res = client.get("/api/history?hours=24&limit=10")
    assert h_res.status_code == 200
    h_data = h_res.get_json()["data"]
    assert len(h_data) == 1

    # Test stats
    s_res = client.get("/api/stats?hours=24")
    assert s_res.status_code == 200
    s_data = s_res.get_json()["data"]
    assert s_data["total_runs"] == 1


def test_api_export_csv(client):
    """Verify CSV export endpoint returns proper MIME type and attachment header."""
    res = client.get("/api/export/csv?hours=24")
    assert res.status_code == 200
    assert res.mimetype == "text/csv"
    assert "attachment; filename=network_quality_history" in res.headers["Content-Disposition"]
    assert b"Run ID,Timestamp (UTC)" in res.data


def test_404_error_handler(client):
    """Verify structured JSON response on unknown URL."""
    res = client.get("/api/unknown_route")
    assert res.status_code == 404
    assert res.get_json()["status"] == "error"


@patch("app.run_full_diagnostic_probe")
def test_api_compare_runs(mock_probe, client):
    """Verify GET /api/compare endpoint comparing two runs."""
    mock_probe.return_value = {
        "timestamp_utc": "2026-10-21T16:00:00Z",
        "duration_seconds": 1.0,
        "interface_info": {},
        "gateway_detected": False,
        "gateway_ip": None,
        "target_results": [
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
                    "avg_ms": 30.0,
                    "status": "success",
                },
            }
        ],
        "dns_benchmarks": [],
    }

    # Create run 1
    res1 = client.post("/api/tests", json={})
    run_1_id = res1.get_json()["data"]["id"]

    # Create run 2
    mock_probe.return_value["target_results"][0]["ping"]["avg_ms"] = 50.0
    res2 = client.post("/api/tests", json={})
    run_2_id = res2.get_json()["data"]["id"]

    # Compare
    cmp_res = client.get(f"/api/compare?run_a={run_1_id}&run_b={run_2_id}")
    assert cmp_res.status_code == 200
    cmp_data = cmp_res.get_json()["data"]
    assert cmp_data["run_a"]["id"] == run_1_id
    assert cmp_data["run_b"]["id"] == run_2_id
    assert cmp_data["trend"] == "degraded"
    assert cmp_data["aggregate_deltas"]["avg_latency_delta_ms"] == 20.0


@patch("app.run_full_diagnostic_probe")
def test_api_compare_destinations(mock_probe, client):
    """Verify GET /api/compare/destinations returns target ranking and WAN penalties."""
    mock_probe.return_value = {
        "timestamp_utc": "2026-10-21T16:00:00Z",
        "duration_seconds": 1.2,
        "interface_info": {},
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
                    "avg_ms": 2.0,
                    "status": "success",
                },
            },
            {
                "target_id": "cloudflare_dns",
                "target_name": "Cloudflare DNS",
                "target_type": "dns_resolver",
                "target_address": "1.1.1.1",
                "target_port": 53,
                "ping": {
                    "sent": 3,
                    "received": 3,
                    "lost": 0,
                    "packet_loss_pct": 0.0,
                    "avg_ms": 14.0,
                    "status": "success",
                },
                "dns_lookup_ms": 12.0,
                "tcp_handshake_ms": 15.0,
            },
        ],
        "dns_benchmarks": [],
    }

    res = client.post("/api/tests", json={})
    run_id = res.get_json()["data"]["id"]

    dest_res = client.get(f"/api/compare/destinations?run_id={run_id}")
    assert dest_res.status_code == 200
    data = dest_res.get_json()["data"]
    assert data["gateway_baseline_ms"] == 2.0
    assert data["fastest_destination"]["target_id"] == "cloudflare_dns"
    assert data["fastest_destination"]["wan_penalty_ms"] == 12.0  # 14.0 - 2.0


@patch("app.run_full_diagnostic_probe")
def test_api_export_comparison_and_test_json(mock_probe, client):
    """Verify CSV and JSON export endpoints for comparisons and single test runs."""
    mock_probe.return_value = {
        "timestamp_utc": "2026-10-21T16:00:00Z",
        "duration_seconds": 1.0,
        "interface_info": {},
        "gateway_detected": False,
        "gateway_ip": None,
        "target_results": [
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
                    "avg_ms": 25.0,
                    "status": "success",
                },
            }
        ],
        "dns_benchmarks": [],
    }

    res1 = client.post("/api/tests", json={})
    run_1_id = res1.get_json()["data"]["id"]

    mock_probe.return_value["target_results"][0]["ping"]["avg_ms"] = 35.0
    res2 = client.post("/api/tests", json={})
    run_2_id = res2.get_json()["data"]["id"]

    # Export comparison CSV
    csv_res = client.get(f"/api/export/comparison/csv?run_a={run_1_id}&run_b={run_2_id}")
    assert csv_res.status_code == 200
    assert csv_res.mimetype == "text/csv"
    assert f"network_comparison_run{run_1_id}_vs_run{run_2_id}.csv" in csv_res.headers["Content-Disposition"]
    assert b"target_id,target_name" in csv_res.data

    # Export comparison JSON
    json_cmp_res = client.get(f"/api/export/comparison/json?run_a={run_1_id}&run_b={run_2_id}")
    assert json_cmp_res.status_code == 200
    assert json_cmp_res.mimetype == "application/json"
    assert b"\"aggregate_deltas\"" in json_cmp_res.data

    # Export single test JSON
    single_json_res = client.get(f"/api/export/test/{run_1_id}/json")
    assert single_json_res.status_code == 200
    assert single_json_res.mimetype == "application/json"
    assert f"netpulse_diagnostic_run_{run_1_id}.json" in single_json_res.headers["Content-Disposition"]
    assert b"\"metric_samples\"" in single_json_res.data



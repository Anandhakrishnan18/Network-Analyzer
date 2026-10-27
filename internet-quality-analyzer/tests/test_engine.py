"""
Unit tests for composite measurement engine orchestrator.
"""

from unittest.mock import patch
from network.engine import run_full_diagnostic_probe, re_is_ip


def test_re_is_ip():
    """Verify IP vs hostname detection helper."""
    assert re_is_ip("8.8.8.8") is True
    assert re_is_ip("192.168.1.1") is True
    assert re_is_ip("2404:6800:4007:82f::200e") is True
    assert re_is_ip("google.com") is False
    assert re_is_ip("cloudflare.net") is False


@patch("network.engine.get_default_gateway")
@patch("network.engine.run_ping_test")
@patch("network.engine.measure_dns_lookup")
@patch("network.engine.measure_tcp_connect")
@patch("network.engine.run_dns_benchmark")
def test_run_full_diagnostic_probe(
    mock_dns_bench,
    mock_tcp,
    mock_dns,
    mock_ping,
    mock_gw
):
    """Verify orchestration of multi-layer probe without hitting external network."""
    mock_gw.return_value = "192.168.1.1"
    mock_ping.return_value = {
        "sent": 3,
        "received": 3,
        "lost": 0,
        "packet_loss_pct": 0.0,
        "min_ms": 10.0,
        "max_ms": 20.0,
        "avg_ms": 15.0,
        "median_ms": 15.0,
        "jitter_ms": 2.0,
        "samples": [10.0, 15.0, 20.0],
        "status": "success",
        "error_message": None,
    }
    mock_dns.return_value = {
        "success": True,
        "elapsed_ms": 25.0,
        "resolved_ips": ["1.2.3.4"],
    }
    mock_tcp.return_value = {
        "success": True,
        "handshake_ms": 30.0,
    }
    mock_dns_bench.return_value = [
        {"resolver_name": "Cloudflare", "avg_ms": 15.0, "status": "success"}
    ]

    report = run_full_diagnostic_probe(target_ids=["gateway", "cloudflare_dns"], probe_count=3)

    assert report["gateway_detected"] is True
    assert report["gateway_ip"] == "192.168.1.1"
    assert len(report["target_results"]) == 2
    assert report["duration_seconds"] >= 0.0
    assert len(report["dns_benchmarks"]) == 1

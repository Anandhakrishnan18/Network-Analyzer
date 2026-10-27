"""
Unit tests for DNS measurement engine.
"""

from unittest.mock import patch, MagicMock
import dns.resolver
from network.dns_test import measure_dns_lookup, run_dns_benchmark


@patch("dns.resolver.Resolver.resolve")
def test_dns_lookup_mocked_success(mock_resolve):
    """Verify measurement formatting on successful DNS query."""
    mock_answer = MagicMock()
    mock_answer.to_text.return_value = "93.184.216.34"
    mock_resolve.return_value = [mock_answer]

    res = measure_dns_lookup("example.com", resolver_ip="1.1.1.1")
    assert res["success"] is True
    assert res["status"] == "success"
    assert res["domain"] == "example.com"
    assert res["resolver"] == "1.1.1.1"
    assert res["resolved_ips"] == ["93.184.216.34"]
    assert res["elapsed_ms"] >= 0.0
    assert res["error_category"] is None


@patch("dns.resolver.Resolver.resolve")
def test_dns_lookup_mocked_nxdomain(mock_resolve):
    """Verify NXDOMAIN handling produces failed status with appropriate error category."""
    mock_resolve.side_effect = dns.resolver.NXDOMAIN()

    res = measure_dns_lookup("nonexistent-domain-12345.test")
    assert res["success"] is False
    assert res["status"] == "failed"
    assert "NXDOMAIN" in res["error_category"]
    assert res["resolved_ips"] == []


@patch("dns.resolver.Resolver.resolve")
def test_dns_lookup_mocked_timeout(mock_resolve):
    """Verify Timeout handling produces clean failed status without crashing."""
    mock_resolve.side_effect = dns.resolver.Timeout()

    res = measure_dns_lookup("example.com", resolver_ip="192.0.2.1", timeout_sec=0.5)
    assert res["success"] is False
    assert res["status"] == "failed"
    assert "Timeout" in res["error_category"]


@patch("network.dns_test.measure_dns_lookup")
def test_run_dns_benchmark(mock_lookup):
    """Verify multi-resolver comparative benchmarking logic."""
    mock_lookup.side_effect = [
        {"success": True, "elapsed_ms": 20.0, "resolved_ips": ["1.2.3.4"], "error_category": None},
        {"success": True, "elapsed_ms": 22.0, "resolved_ips": ["1.2.3.4"], "error_category": None},
        {"success": True, "elapsed_ms": 10.0, "resolved_ips": ["1.2.3.4"], "error_category": None},
        {"success": True, "elapsed_ms": 12.0, "resolved_ips": ["1.2.3.4"], "error_category": None},
    ]

    resolvers = [
        {"name": "Resolver A", "ip": "1.1.1.1"},
        {"name": "Resolver B", "ip": "8.8.8.8"},
    ]

    benchmarks = run_dns_benchmark("example.com", resolvers=resolvers, samples_per_resolver=2)
    assert len(benchmarks) == 2
    assert benchmarks[0]["resolver_name"] == "Resolver A"
    assert benchmarks[0]["avg_ms"] == 21.0
    assert benchmarks[1]["resolver_name"] == "Resolver B"
    assert benchmarks[1]["avg_ms"] == 11.0

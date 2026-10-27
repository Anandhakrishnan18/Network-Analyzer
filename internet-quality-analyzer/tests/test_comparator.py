"""
Unit tests for network telemetry comparator.
"""

from analysis.comparator import compare_runs, compare_destinations, export_comparison_as_csv


def test_compare_identical_runs():
    """Verify comparing identical runs produces zero deltas and comparable trend."""
    run_a = {
        "id": 1,
        "timestamp_utc": "2026-10-21T10:00:00Z",
        "overall_status": "healthy",
        "trigger_type": "manual",
        "gateway_ip": "192.168.1.1",
        "metric_samples": [
            {
                "target_id": "google_web",
                "target_name": "Google Web",
                "target_type": "external_host",
                "latency_avg_ms": 25.0,
                "jitter_ms": 3.0,
                "packet_loss_pct": 0.0,
                "dns_lookup_time_ms": 15.0,
                "tcp_handshake_time_ms": 24.0,
                "status": "success",
            }
        ],
    }

    run_b = {
        "id": 2,
        "timestamp_utc": "2026-10-21T10:05:00Z",
        "overall_status": "healthy",
        "trigger_type": "manual",
        "gateway_ip": "192.168.1.1",
        "metric_samples": [
            {
                "target_id": "google_web",
                "target_name": "Google Web",
                "target_type": "external_host",
                "latency_avg_ms": 25.0,
                "jitter_ms": 3.0,
                "packet_loss_pct": 0.0,
                "dns_lookup_time_ms": 15.0,
                "tcp_handshake_time_ms": 24.0,
                "status": "success",
            }
        ],
    }

    res = compare_runs(run_a, run_b)
    assert res["trend"] == "comparable"
    assert res["aggregate_deltas"]["avg_latency_delta_ms"] == 0.0
    deltas = res["target_comparisons"][0]["deltas"]
    assert deltas["latency_avg_ms"] == 0.0
    assert deltas["packet_loss_pct"] == 0.0


def test_compare_improved_run():
    """Verify negative deltas signify performance improvement."""
    run_a = {
        "id": 1,
        "timestamp_utc": "2026-10-21T10:00:00Z",
        "overall_status": "warning",
        "trigger_type": "manual",
        "metric_samples": [
            {
                "target_id": "google_web",
                "target_name": "Google Web",
                "target_type": "external_host",
                "latency_avg_ms": 85.0,
                "jitter_ms": 18.0,
                "packet_loss_pct": 5.0,
                "dns_lookup_time_ms": 40.0,
                "tcp_handshake_time_ms": 80.0,
                "status": "degraded",
            }
        ],
    }

    run_b = {
        "id": 2,
        "timestamp_utc": "2026-10-21T10:10:00Z",
        "overall_status": "healthy",
        "trigger_type": "manual",
        "metric_samples": [
            {
                "target_id": "google_web",
                "target_name": "Google Web",
                "target_type": "external_host",
                "latency_avg_ms": 25.0,  # 60ms faster
                "jitter_ms": 4.0,        # 14ms less jitter
                "packet_loss_pct": 0.0,  # 5% less loss
                "dns_lookup_time_ms": 15.0,
                "tcp_handshake_time_ms": 24.0,
                "status": "success",
            }
        ],
    }

    res = compare_runs(run_a, run_b)
    assert res["trend"] == "improved"
    assert res["aggregate_deltas"]["avg_latency_delta_ms"] == -60.0
    assert res["aggregate_deltas"]["avg_loss_delta_pct"] == -5.0


def test_compare_degraded_run():
    """Verify positive deltas signify network degradation."""
    run_a = {
        "id": 1,
        "timestamp_utc": "2026-10-21T10:00:00Z",
        "overall_status": "healthy",
        "trigger_type": "manual",
        "metric_samples": [
            {
                "target_id": "google_web",
                "target_name": "Google Web",
                "target_type": "external_host",
                "latency_avg_ms": 25.0,
                "jitter_ms": 3.0,
                "packet_loss_pct": 0.0,
                "dns_lookup_time_ms": 15.0,
                "tcp_handshake_time_ms": 24.0,
                "status": "success",
            }
        ],
    }

    run_b = {
        "id": 2,
        "timestamp_utc": "2026-10-21T10:15:00Z",
        "overall_status": "critical",
        "trigger_type": "manual",
        "metric_samples": [
            {
                "target_id": "google_web",
                "target_name": "Google Web",
                "target_type": "external_host",
                "latency_avg_ms": 145.0,  # +120ms
                "jitter_ms": 35.0,
                "packet_loss_pct": 15.0,  # +15%
                "dns_lookup_time_ms": 50.0,
                "tcp_handshake_time_ms": 140.0,
                "status": "degraded",
            }
        ],
    }

    res = compare_runs(run_a, run_b)
    assert res["trend"] == "degraded"
    assert res["aggregate_deltas"]["avg_latency_delta_ms"] == 120.0
    assert res["aggregate_deltas"]["avg_loss_delta_pct"] == 15.0


def test_compare_destinations_wan_penalty_and_rankings():
    """Verify destination comparison ranks targets and calculates WAN penalty relative to gateway."""
    run = {
        "id": 42,
        "timestamp_utc": "2026-10-21T12:00:00Z",
        "metric_samples": [
            {
                "target_id": "gateway",
                "target_name": "Default Gateway",
                "target_type": "gateway",
                "target_address": "192.168.1.1",
                "latency_avg_ms": 2.5,
                "jitter_ms": 0.5,
                "packet_loss_pct": 0.0,
                "dns_lookup_time_ms": None,
                "tcp_handshake_time_ms": None,
                "status": "success",
            },
            {
                "target_id": "cloudflare_dns",
                "target_name": "Cloudflare DNS",
                "target_type": "dns_resolver",
                "target_address": "1.1.1.1",
                "latency_avg_ms": 14.5,
                "jitter_ms": 1.2,
                "packet_loss_pct": 0.0,
                "dns_lookup_time_ms": 11.0,
                "tcp_handshake_time_ms": 15.0,
                "status": "success",
            },
            {
                "target_id": "google_dns",
                "target_name": "Google DNS",
                "target_type": "dns_resolver",
                "target_address": "8.8.8.8",
                "latency_avg_ms": 24.5,
                "jitter_ms": 2.0,
                "packet_loss_pct": 0.0,
                "dns_lookup_time_ms": 18.0,
                "tcp_handshake_time_ms": 25.0,
                "status": "success",
            },
            {
                "target_id": "distant_server",
                "target_name": "Distant Web",
                "target_type": "external_host",
                "target_address": "example.org",
                "latency_avg_ms": 120.0,
                "jitter_ms": 10.0,
                "packet_loss_pct": 2.0,
                "dns_lookup_time_ms": None,
                "tcp_handshake_time_ms": 125.0,
                "status": "success",
            },
        ],
    }

    result = compare_destinations(run)
    assert result["run_id"] == 42
    assert result["gateway_baseline_ms"] == 2.5

    # Fastest & slowest destination
    assert result["fastest_destination"]["target_id"] == "cloudflare_dns"
    assert result["slowest_destination"]["target_id"] == "distant_server"

    # WAN penalties: target - gateway
    cf_target = next(d for d in result["all_destinations"] if d["target_id"] == "cloudflare_dns")
    assert cf_target["wan_penalty_ms"] == 12.0  # 14.5 - 2.5

    dist_target = next(d for d in result["all_destinations"] if d["target_id"] == "distant_server")
    assert dist_target["wan_penalty_ms"] == 117.5  # 120.0 - 2.5

    # TCP overhead: TCP - ICMP
    assert cf_target["tcp_overhead_ms"] == 0.5  # 15.0 - 14.5
    assert dist_target["tcp_overhead_ms"] == 5.0  # 125.0 - 120.0

    # DNS resolver comparison
    assert result["fastest_dns_resolver"]["target_id"] == "cloudflare_dns"
    assert len(result["dns_resolvers"]) == 2


def test_export_comparison_as_csv():
    """Verify export_comparison_as_csv generates valid RFC 4180 CSV with header and metadata."""
    run_a = {
        "id": 1,
        "timestamp_utc": "2026-10-21T10:00:00Z",
        "overall_status": "healthy",
        "trigger_type": "manual",
        "metric_samples": [
            {
                "target_id": "google_web",
                "target_name": "Google Web",
                "target_type": "external_host",
                "latency_avg_ms": 30.0,
                "jitter_ms": 4.0,
                "packet_loss_pct": 0.0,
                "dns_lookup_time_ms": 15.0,
                "tcp_handshake_time_ms": 31.0,
            }
        ],
    }
    run_b = {
        "id": 2,
        "timestamp_utc": "2026-10-21T10:05:00Z",
        "overall_status": "healthy",
        "trigger_type": "manual",
        "metric_samples": [
            {
                "target_id": "google_web",
                "target_name": "Google Web",
                "target_type": "external_host",
                "latency_avg_ms": 25.0,
                "jitter_ms": 2.0,
                "packet_loss_pct": 0.0,
                "dns_lookup_time_ms": 12.0,
                "tcp_handshake_time_ms": 26.0,
            }
        ],
    }

    comparison = compare_runs(run_a, run_b)
    csv_str = export_comparison_as_csv(comparison)

    assert "# NetPulse Differential Comparison" in csv_str
    assert "target_id,target_name,target_type" in csv_str
    assert "google_web,Google Web,external_host" in csv_str
    assert "-5.0" in csv_str  # latency delta: 25.0 - 30.0 = -5.0


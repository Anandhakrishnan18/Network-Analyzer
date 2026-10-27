"""
Unit tests for the rule-based diagnostic troubleshooter engine.
"""

from analysis.troubleshooter import Troubleshooter


def test_diagnose_insufficient_data():
    """Verify handling when no targets are provided."""
    ts = Troubleshooter()
    res = ts.diagnose({"target_results": []})
    assert res["overall_status"] == "insufficient_data"
    assert res["findings"][0]["rule_id"] == "RULE_INSUFFICIENT_DATA"


def test_diagnose_healthy_connection():
    """Verify clean bill of health when all metrics are within thresholds."""
    ts = Troubleshooter()
    report = {
        "gateway_detected": True,
        "gateway_ip": "192.168.1.1",
        "target_results": [
            {
                "target_type": "gateway",
                "target_name": "Default Gateway",
                "ping": {"avg_ms": 2.5, "packet_loss_pct": 0.0, "jitter_ms": 1.0, "status": "success"},
            },
            {
                "target_type": "external_host",
                "target_name": "Google",
                "ping": {"avg_ms": 25.0, "packet_loss_pct": 0.0, "jitter_ms": 3.0, "status": "success"},
                "dns_lookup_ms": 15.0,
                "tcp_handshake_ms": 24.0,
            },
            {
                "target_type": "dns_resolver",
                "target_name": "Cloudflare DNS",
                "ping": {"avg_ms": 20.0, "packet_loss_pct": 0.0, "jitter_ms": 2.0, "status": "success"},
                "tcp_handshake_ms": 18.0,
            },
        ],
        "dns_benchmarks": [],
    }

    res = ts.diagnose(report)
    assert res["overall_status"] == "healthy"
    assert any(f["rule_id"] == "RULE_CONNECTION_HEALTHY" for f in res["findings"])


def test_diagnose_total_disconnection():
    """Verify critical status when 100% packet loss occurs everywhere."""
    ts = Troubleshooter()
    report = {
        "gateway_detected": True,
        "gateway_ip": "192.168.1.1",
        "target_results": [
            {
                "target_type": "gateway",
                "target_name": "Default Gateway",
                "ping": {"avg_ms": None, "packet_loss_pct": 100.0, "status": "failed"},
            },
            {
                "target_type": "external_host",
                "target_name": "Google",
                "ping": {"avg_ms": None, "packet_loss_pct": 100.0, "status": "failed"},
            },
        ],
    }

    res = ts.diagnose(report)
    assert res["overall_status"] == "critical"
    assert res["findings"][0]["rule_id"] == "RULE_ALL_DESTINATIONS_FAILED"
    assert res["findings"][0]["confidence"] == "High"


def test_diagnose_local_gateway_degradation():
    """Verify local bottleneck detection when gateway latency or loss is high."""
    ts = Troubleshooter()
    report = {
        "gateway_detected": True,
        "gateway_ip": "192.168.1.1",
        "target_results": [
            {
                "target_type": "gateway",
                "target_name": "Default Gateway",
                "ping": {
                    "avg_ms": 45.0,  # Gateway should be < 20ms
                    "packet_loss_pct": 8.0,
                    "jitter_ms": 25.0,
                    "status": "degraded",
                },
            },
            {
                "target_type": "external_host",
                "target_name": "Google",
                "ping": {"avg_ms": 80.0, "packet_loss_pct": 8.0, "jitter_ms": 22.0, "status": "degraded"},
            },
        ],
    }

    res = ts.diagnose(report)
    assert res["overall_status"] == "warning"
    rule_ids = [f["rule_id"] for f in res["findings"]]
    assert "RULE_LOCAL_GATEWAY_DEGRADED" in rule_ids


def test_diagnose_wan_isp_packet_loss():
    """Verify WAN isolation when gateway is fine but multiple external hosts drop packets."""
    ts = Troubleshooter()
    report = {
        "gateway_detected": True,
        "gateway_ip": "192.168.1.1",
        "target_results": [
            {
                "target_type": "gateway",
                "target_name": "Default Gateway",
                "ping": {"avg_ms": 2.0, "packet_loss_pct": 0.0, "jitter_ms": 0.8, "status": "success"},
            },
            {
                "target_type": "external_host",
                "target_name": "Google",
                "ping": {"avg_ms": 35.0, "packet_loss_pct": 15.0, "jitter_ms": 5.0, "status": "degraded"},
            },
            {
                "target_type": "external_host",
                "target_name": "Cloudflare",
                "ping": {"avg_ms": 30.0, "packet_loss_pct": 20.0, "jitter_ms": 6.0, "status": "degraded"},
            },
        ],
    }

    res = ts.diagnose(report)
    rule_ids = [f["rule_id"] for f in res["findings"]]
    assert "RULE_WAN_PACKET_LOSS" in rule_ids
    assert res["overall_status"] == "critical"


def test_diagnose_high_jitter_bufferbloat():
    """Verify bufferbloat / jitter warning."""
    ts = Troubleshooter()
    report = {
        "gateway_detected": True,
        "gateway_ip": "192.168.1.1",
        "target_results": [
            {
                "target_type": "gateway",
                "target_name": "Default Gateway",
                "ping": {"avg_ms": 3.0, "packet_loss_pct": 0.0, "jitter_ms": 1.0, "status": "success"},
            },
            {
                "target_type": "external_host",
                "target_name": "Google",
                "ping": {"avg_ms": 40.0, "packet_loss_pct": 0.0, "jitter_ms": 45.0, "status": "success"},
            },
        ],
    }

    res = ts.diagnose(report)
    rule_ids = [f["rule_id"] for f in res["findings"]]
    assert "RULE_HIGH_JITTER_BUFFERBLOAT" in rule_ids


def test_diagnose_dns_bottleneck():
    """Verify detection when DNS resolution is slow despite normal TCP connectivity."""
    ts = Troubleshooter()
    report = {
        "gateway_detected": True,
        "gateway_ip": "192.168.1.1",
        "target_results": [
            {
                "target_type": "gateway",
                "target_name": "Default Gateway",
                "ping": {"avg_ms": 2.0, "packet_loss_pct": 0.0, "jitter_ms": 1.0, "status": "success"},
            },
            {
                "target_type": "external_host",
                "target_name": "Google Web",
                "ping": {"avg_ms": 25.0, "packet_loss_pct": 0.0, "jitter_ms": 3.0, "status": "success"},
                "dns_lookup_ms": 210.0,  # DNS is severely slow (> 120ms warning)
                "tcp_handshake_ms": 28.0,
            },
        ],
    }

    res = ts.diagnose(report)
    rule_ids = [f["rule_id"] for f in res["findings"]]
    assert "RULE_DNS_RESOLUTION_BOTTLENECK" in rule_ids


def test_diagnose_single_destination_anomaly():
    """Verify isolated failure does not trigger widespread WAN alarm."""
    ts = Troubleshooter()
    report = {
        "gateway_detected": True,
        "gateway_ip": "192.168.1.1",
        "target_results": [
            {
                "target_type": "gateway",
                "target_name": "Default Gateway",
                "ping": {"avg_ms": 2.0, "packet_loss_pct": 0.0, "jitter_ms": 1.0, "status": "success"},
            },
            {
                "target_type": "external_host",
                "target_name": "Google",
                "ping": {"avg_ms": 25.0, "packet_loss_pct": 0.0, "jitter_ms": 2.0, "status": "success"},
            },
            {
                "target_type": "external_host",
                "target_name": "Cloudflare",
                "ping": {"avg_ms": 20.0, "packet_loss_pct": 0.0, "jitter_ms": 2.0, "status": "success"},
            },
            {
                "target_type": "external_host",
                "target_name": "Specific Target",
                "ping": {"avg_ms": None, "packet_loss_pct": 100.0, "jitter_ms": None, "status": "failed"},
            },
        ],
    }

    res = ts.diagnose(report)
    rule_ids = [f["rule_id"] for f in res["findings"]]
    assert "RULE_SINGLE_DESTINATION_ANOMALY" in rule_ids
    assert "RULE_WAN_PACKET_LOSS" not in rule_ids

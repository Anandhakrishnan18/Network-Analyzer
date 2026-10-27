"""
Unit tests for ICMP ping measurement module.
"""

from unittest.mock import patch, MagicMock
from network.ping_test import is_valid_target, parse_ping_output, run_ping_test


def test_target_validation():
    """Verify security allowlist for hostnames and IP addresses."""
    assert is_valid_target("8.8.8.8") is True
    assert is_valid_target("192.168.1.1") is True
    assert is_valid_target("google.com") is True
    assert is_valid_target("sub.domain-name.org") is True

    # Malicious injection attempts must be rejected
    assert is_valid_target("8.8.8.8; ls") is False
    assert is_valid_target("google.com && rm -rf /") is False
    assert is_valid_target("127.0.0.1 | dir") is False
    assert is_valid_target("") is False
    assert is_valid_target("a" * 300) is False


def test_parse_windows_ping_output_success():
    """Verify parsing of Windows ping output with 100% success."""
    sample_output = """
Pinging 1.1.1.1 with 32 bytes of data:
Reply from 1.1.1.1: bytes=32 time=14ms TTL=53
Reply from 1.1.1.1: bytes=32 time=16ms TTL=53
Reply from 1.1.1.1: bytes=32 time=12ms TTL=53

Ping statistics for 1.1.1.1:
    Packets: Sent = 3, Received = 3, Lost = 0 (0% loss),
Approximate round trip times in milli-seconds:
    Minimum = 12ms, Maximum = 16ms, Average = 14ms
"""
    parsed = parse_ping_output(sample_output, attempted_count=3)
    assert parsed["samples"] == [14.0, 16.0, 12.0]


def test_parse_windows_ping_output_interleaved_loss():
    """Verify preservation of dropped probe positions in sample stream."""
    sample_output = """
Pinging 8.8.8.8 with 32 bytes of data:
Reply from 8.8.8.8: bytes=32 time=25ms TTL=117
Request timed out.
Reply from 8.8.8.8: bytes=32 time=30ms TTL=117

Ping statistics for 8.8.8.8:
    Packets: Sent = 3, Received = 2, Lost = 1 (33% loss),
"""
    parsed = parse_ping_output(sample_output, attempted_count=3)
    assert parsed["samples"] == [25.0, None, 30.0]


def test_parse_windows_sub_millisecond():
    """Verify time<1ms is treated as 0.5ms instead of dropping."""
    sample_output = """
Pinging 127.0.0.1 with 32 bytes of data:
Reply from 127.0.0.1: bytes=32 time<1ms TTL=128
Reply from 127.0.0.1: bytes=32 time=2ms TTL=128
"""
    parsed = parse_ping_output(sample_output, attempted_count=2)
    assert parsed["samples"] == [0.5, 2.0]


@patch("subprocess.run")
def test_run_ping_test_mocked_success(mock_subproc):
    """Test full run_ping_test execution with mocked subprocess output."""
    mock_subproc.return_value = MagicMock(
        returncode=0,
        stdout="""
Pinging google.com [142.250.190.46] with 32 bytes of data:
Reply from 142.250.190.46: bytes=32 time=20ms TTL=115
Reply from 142.250.190.46: bytes=32 time=24ms TTL=115
Reply from 142.250.190.46: bytes=32 time=22ms TTL=115

Ping statistics for 142.250.190.46:
    Packets: Sent = 3, Received = 3, Lost = 0 (0% loss),
"""
    )
    res = run_ping_test("google.com", count=3)
    assert res["status"] == "success"
    assert res["resolved_ip"] == "142.250.190.46"
    assert res["sent"] == 3
    assert res["received"] == 3
    assert res["lost"] == 0
    assert res["packet_loss_pct"] == 0.0
    assert res["min_ms"] == 20.0
    assert res["max_ms"] == 24.0
    assert res["avg_ms"] == 22.0
    assert res["jitter_ms"] == 3.0  # |24-20|=4, |22-24|=2 -> (4+2)/2 = 3.0


def test_run_ping_test_loopback():
    """Real ping test to local loopback 127.0.0.1."""
    res = run_ping_test("127.0.0.1", count=2, timeout_ms=1000)
    assert res["sent"] == 2
    assert res["received"] == 2
    assert res["packet_loss_pct"] == 0.0
    assert res["status"] == "success"
    assert res["avg_ms"] is not None

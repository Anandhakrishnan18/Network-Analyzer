"""
Unit tests for TCP handshake measurement engine.
"""

from unittest.mock import patch, MagicMock
import socket
from network.tcp_test import measure_tcp_connect, run_tcp_benchmark


@patch("socket.socket")
def test_tcp_connect_mocked_success(mock_sock_cls):
    """Verify handshake measurement on successful TCP connection."""
    mock_sock = MagicMock()
    mock_sock_cls.return_value = mock_sock

    res = measure_tcp_connect("1.1.1.1", 443, timeout_sec=2.0)
    assert res["success"] is True
    assert res["status"] == "success"
    assert res["host"] == "1.1.1.1"
    assert res["port"] == 443
    assert res["handshake_ms"] is not None
    assert res["error_category"] is None
    mock_sock.connect.assert_called_once_with(("1.1.1.1", 443))
    mock_sock.close.assert_called_once()


@patch("socket.socket")
def test_tcp_connect_mocked_timeout(mock_sock_cls):
    """Verify timeout handling returns failed status and no handshake_ms."""
    mock_sock = MagicMock()
    mock_sock.connect.side_effect = socket.timeout()
    mock_sock_cls.return_value = mock_sock

    res = measure_tcp_connect("192.0.2.1", 80, timeout_sec=0.5)
    assert res["success"] is False
    assert res["status"] == "failed"
    assert res["handshake_ms"] is None
    assert "Timeout" in res["error_category"]


@patch("socket.socket")
def test_tcp_connect_mocked_connection_refused(mock_sock_cls):
    """Verify ConnectionRefusedError is handled without crashing."""
    mock_sock = MagicMock()
    mock_sock.connect.side_effect = ConnectionRefusedError()
    mock_sock_cls.return_value = mock_sock

    res = measure_tcp_connect("127.0.0.1", 65530, timeout_sec=1.0)
    assert res["success"] is False
    assert res["status"] == "failed"
    assert res["handshake_ms"] is None
    assert "Refused" in res["error_category"]


@patch("network.tcp_test.measure_tcp_connect")
def test_run_tcp_benchmark(mock_connect):
    """Verify statistical aggregation across multiple connection attempts."""
    mock_connect.side_effect = [
        {"success": True, "handshake_ms": 30.0, "error_category": None},
        {"success": True, "handshake_ms": 35.0, "error_category": None},
        {"success": True, "handshake_ms": 40.0, "error_category": None},
    ]

    res = run_tcp_benchmark("cloudflare.com", 443, samples=3)
    assert res["status"] == "success"
    assert res["attempts"] == 3
    assert res["successful"] == 3
    assert res["failed"] == 0
    assert res["min_ms"] == 30.0
    assert res["max_ms"] == 40.0
    assert res["avg_ms"] == 35.0
    assert res["median_ms"] == 35.0

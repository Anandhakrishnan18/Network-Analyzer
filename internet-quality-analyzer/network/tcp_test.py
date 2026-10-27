"""
TCP Handshake Timing Engine.

Measures the elapsed time required to establish a TCP connection (the 3-way handshake:
SYN -> SYN/ACK -> ACK) to a target hostname and port.

Network Concepts:
- TCP (Transmission Control Protocol, RFC 793) operates at the Transport Layer (L4).
- Connection establishment time is approximately one full Round Trip Time (RTT) between
  client and server plus server OS TCP listen backlog processing latency.
- TCP Handshake Timing is NOT webpage load time:
  1. DNS resolution must occur first (if using hostname).
  2. TCP 3-Way Handshake establishes the transport socket (measured here).
  3. TLS/SSL handshake (if HTTPS/443) requires additional RTTs.
  4. HTTP request/response exchange transmits the actual application data.
"""

import socket
import time
from typing import Dict, Any, List, Optional
import statistics


def measure_tcp_connect(
    host: str,
    port: int,
    timeout_sec: float = 3.0
) -> Dict[str, Any]:
    """
    Measure the time required to complete a TCP 3-way handshake.

    Args:
        host: Destination IP or hostname.
        port: Destination TCP port (e.g., 80, 443, 53).
        timeout_sec: Maximum timeout in seconds.

    Returns:
        Structured measurement dictionary.
    """
    sock = None
    start = time.perf_counter()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout_sec)
        # socket.connect triggers SYN and blocks until SYN-ACK received and ACK sent
        sock.connect((host, port))
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)

        return {
            "host": host,
            "port": port,
            "handshake_ms": elapsed_ms,
            "success": True,
            "status": "success",
            "error_category": None,
        }

    except socket.timeout:
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
        return {
            "host": host,
            "port": port,
            "handshake_ms": None,
            "success": False,
            "status": "failed",
            "error_category": f"Timeout after {timeout_sec:.1f}s",
        }

    except ConnectionRefusedError:
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
        return {
            "host": host,
            "port": port,
            "handshake_ms": None,
            "success": False,
            "status": "failed",
            "error_category": "Connection Refused (Port closed or RST returned)",
        }

    except socket.gaierror as gai_err:
        return {
            "host": host,
            "port": port,
            "handshake_ms": None,
            "success": False,
            "status": "failed",
            "error_category": f"DNS Resolution Error: {gai_err.strerror}",
        }

    except Exception as exc:
        return {
            "host": host,
            "port": port,
            "handshake_ms": None,
            "success": False,
            "status": "failed",
            "error_category": f"Socket Error: {type(exc).__name__}",
        }

    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


def run_tcp_benchmark(
    host: str,
    port: int,
    samples: int = 3,
    timeout_sec: float = 3.0
) -> Dict[str, Any]:
    """
    Perform multiple TCP connection measurements to compute handshake statistics.

    Args:
        host: Destination target host.
        port: Destination target port.
        samples: Count of handshake attempts.
        timeout_sec: Timeout per attempt.

    Returns:
        Aggregated TCP benchmark summary.
    """
    sample_times: List[float] = []
    errors: List[str] = []

    for _ in range(samples):
        res = measure_tcp_connect(host, port, timeout_sec=timeout_sec)
        if res["success"] and res["handshake_ms"] is not None:
            sample_times.append(res["handshake_ms"])
        else:
            if res["error_category"]:
                errors.append(res["error_category"])

    total_attempts = samples
    successful_attempts = len(sample_times)
    failed_attempts = total_attempts - successful_attempts

    if successful_attempts > 0:
        avg_ms = round(statistics.mean(sample_times), 2)
        min_ms = round(min(sample_times), 2)
        max_ms = round(max(sample_times), 2)
        median_ms = round(statistics.median(sample_times), 2)
        status = "success" if failed_attempts == 0 else "degraded"
    else:
        avg_ms = None
        min_ms = None
        max_ms = None
        median_ms = None
        status = "failed"

    return {
        "host": host,
        "port": port,
        "attempts": total_attempts,
        "successful": successful_attempts,
        "failed": failed_attempts,
        "avg_ms": avg_ms,
        "min_ms": min_ms,
        "max_ms": max_ms,
        "median_ms": median_ms,
        "samples": sample_times,
        "errors": errors,
        "status": status,
    }

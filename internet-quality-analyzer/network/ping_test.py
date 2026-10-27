"""
ICMP Ping Measurement Engine.

Executes platform-native ICMP echo requests via subprocess, parses individual probe
responses preserving sample sequence, and computes precise latency statistics, packet loss,
and jitter.

Network Concepts:
- ICMP (Internet Control Message Protocol, RFC 792) operates at the Network Layer (L3).
- Ping sends Type 8 (Echo Request) and expects Type 0 (Echo Reply).
- Intermediate routers may de-prioritize or filter ICMP traffic, meaning an unanswered
  ping does not necessarily mean a destination or service is completely down.
"""

import platform
import re
import subprocess
from typing import Dict, Any, List, Optional
from network.jitter_calculator import calculate_latency_stats


def is_valid_target(target: str) -> bool:
    """Validate target hostname or IP address to prevent command injection."""
    if not target or len(target) > 255:
        return False
    # Allow standard alphanumeric, dot, hyphen, and colon (for IPv6)
    pattern = r"^[a-zA-Z0-9\.\-:]+$"
    return bool(re.match(pattern, target))


def parse_ping_output(stdout: str, attempted_count: int) -> Dict[str, Any]:
    """
    Parse operating system ping output line by line to extract sequential RTT values.

    Args:
        stdout: Standard output string from ping command.
        attempted_count: Number of probes configured.

    Returns:
        Dict containing resolved_ip and list of probe sample RTTs (floats or None).
    """
    system = platform.system()
    resolved_ip: Optional[str] = None
    samples: List[Optional[float]] = []

    # Attempt to extract resolved IP from header line:
    # Windows: Pinging google.com [142.251.221.110] with 32 bytes...
    # Linux/Mac: PING google.com (142.251.221.110) 56(84) bytes...
    ip_match = re.search(r"[\[\(]([0-9a-fA-F:\.]+)[\]\)]", stdout)
    if ip_match:
        resolved_ip = ip_match.group(1)

    lines = stdout.splitlines()

    for line in lines:
        line_clean = line.strip()

        # Windows ping output patterns
        if system == "Windows":
            # Successful reply: "Reply from 1.1.1.1: bytes=32 time=14ms TTL=53" or "time<1ms"
            if "Reply from" in line_clean or "bytes=" in line_clean.lower():
                time_match = re.search(r"time[=<]([0-9]+)ms", line_clean, re.IGNORECASE)
                if time_match:
                    if "<" in time_match.group(0):
                        samples.append(0.5)
                    else:
                        samples.append(float(time_match.group(1)))
                elif "unreachable" in line_clean.lower():
                    samples.append(None)

            # Explicit timeout or failure line
            elif (
                "Request timed out" in line_clean
                or "Destination host unreachable" in line_clean
                or "General failure" in line_clean
                or "Transmit failed" in line_clean
            ):
                samples.append(None)

        # Linux / Unix ping output patterns
        else:
            if "bytes from" in line_clean.lower():
                time_match = re.search(r"time=([0-9\.]+)\s*ms", line_clean, re.IGNORECASE)
                if time_match:
                    samples.append(float(time_match.group(1)))
            elif (
                "Request timeout" in line_clean
                or "Destination Host Unreachable" in line_clean
                or "100.0% packet loss" in line_clean
            ):
                samples.append(None)

    # If line-by-line parsing captured fewer samples than attempted due to silent drops,
    # pad with None up to the attempted count to ensure accurate loss calculation.
    if len(samples) < attempted_count:
        # Check summary for packet loss if available
        loss_match = re.search(r"Lost\s*=\s*([0-9]+)", stdout, re.IGNORECASE)
        if loss_match:
            lost = int(loss_match.group(1))
            missing = attempted_count - len(samples)
            if missing > 0:
                samples.extend([None] * min(missing, lost))
        else:
            # Pad remaining as None
            samples.extend([None] * (attempted_count - len(samples)))
    elif len(samples) > attempted_count:
        samples = samples[:attempted_count]

    return {
        "resolved_ip": resolved_ip,
        "samples": samples,
    }


def run_ping_test(
    target: str,
    count: int = 5,
    timeout_ms: int = 1500,
    force_ipv4: bool = True
) -> Dict[str, Any]:
    """
    Execute ICMP ping probes against the target destination.

    Args:
        target: IP address or hostname.
        count: Number of echo request probes (default 5).
        timeout_ms: Milliseconds to wait per probe.
        force_ipv4: If True, forces IPv4 ping where supported.

    Returns:
        Structured measurement dictionary.
    """
    if not is_valid_target(target):
        return {
            "target": target,
            "resolved_ip": None,
            "sent": 0,
            "received": 0,
            "lost": 0,
            "packet_loss_pct": 100.0,
            "min_ms": None,
            "max_ms": None,
            "avg_ms": None,
            "median_ms": None,
            "jitter_ms": None,
            "samples": [],
            "status": "failed",
            "error_message": f"Invalid target destination format: '{target}'",
        }

    system = platform.system()
    cmd: List[str] = []

    if system == "Windows":
        cmd = ["ping"]
        if force_ipv4:
            cmd.append("-4")
        cmd.extend(["-n", str(count), "-w", str(timeout_ms), target])
    elif system == "Darwin":
        cmd = ["ping"]
        if force_ipv4:
            cmd.append("-4")
        cmd.extend(["-c", str(count), "-W", str(timeout_ms), target])
    else:  # Linux
        cmd = ["ping"]
        if force_ipv4:
            cmd.append("-4")
        # Linux -W is in seconds
        timeout_sec = max(1, int(timeout_ms / 1000))
        cmd.extend(["-c", str(count), "-W", str(timeout_sec), target])

    # Allow overall command timeout slightly larger than total probe window
    cmd_timeout_sec = (count * (timeout_ms / 1000.0)) + 3.0

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=cmd_timeout_sec,
            check=False
        )
        parsed = parse_ping_output(proc.stdout, attempted_count=count)
        samples = parsed["samples"]
        resolved_ip = parsed["resolved_ip"]

        stats = calculate_latency_stats(samples)

        # Determine qualitative status
        if stats["received"] == 0:
            status = "failed"
            error_msg = "All probes timed out or host is unreachable."
        elif stats["packet_loss_pct"] > 0:
            status = "degraded"
            error_msg = f"Packet loss detected: {stats['packet_loss_pct']}%."
        else:
            status = "success"
            error_msg = None

        return {
            "target": target,
            "resolved_ip": resolved_ip,
            "sent": stats["sent"],
            "received": stats["received"],
            "lost": stats["lost"],
            "packet_loss_pct": stats["packet_loss_pct"],
            "min_ms": stats["min_ms"],
            "max_ms": stats["max_ms"],
            "avg_ms": stats["avg_ms"],
            "median_ms": stats["median_ms"],
            "jitter_ms": stats["jitter_ms"],
            "samples": samples,
            "status": status,
            "error_message": error_msg,
        }

    except subprocess.TimeoutExpired:
        return {
            "target": target,
            "resolved_ip": None,
            "sent": count,
            "received": 0,
            "lost": count,
            "packet_loss_pct": 100.0,
            "min_ms": None,
            "max_ms": None,
            "avg_ms": None,
            "median_ms": None,
            "jitter_ms": None,
            "samples": [None] * count,
            "status": "failed",
            "error_message": f"Ping command timed out after {cmd_timeout_sec:.1f} seconds.",
        }
    except Exception as exc:
        return {
            "target": target,
            "resolved_ip": None,
            "sent": count,
            "received": 0,
            "lost": count,
            "packet_loss_pct": 100.0,
            "min_ms": None,
            "max_ms": None,
            "avg_ms": None,
            "median_ms": None,
            "jitter_ms": None,
            "samples": [None] * count,
            "status": "failed",
            "error_message": f"Unexpected execution error: {str(exc)}",
        }

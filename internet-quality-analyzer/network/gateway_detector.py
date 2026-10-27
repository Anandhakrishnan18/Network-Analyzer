"""
Default Gateway Detector Module.

Identifies the first-hop default gateway IP address on the local network.
Distinguishing local router (hop 1) latency and packet loss from external
internet path degradation is essential for isolating Wi-Fi/LAN problems from WAN/ISP issues.
"""

import platform
import re
import socket
import subprocess
from typing import Optional, Dict


def get_local_ip() -> Optional[str]:
    """
    Get the primary local IPv4 address of this machine.
    Uses a non-sending UDP socket connected to a public address to determine
    which local interface routes outward.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # Does not send actual traffic, but asks OS routing table for outbound interface
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def get_default_gateway() -> Optional[str]:
    """
    Detect the default network gateway IPv4 address.
    Supports Windows, Linux, and macOS.

    Returns:
        IPv4 address string (e.g. '192.168.1.1' or '10.142.251.125') or None if undetected.
    """
    system = platform.system()

    try:
        if system == "Windows":
            # Execute Windows route print command
            result = subprocess.run(
                ["route", "print", "0.0.0.0"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False
            )
            if result.returncode == 0:
                # Look for the active default route line:
                # 0.0.0.0          0.0.0.0      <Gateway-IP>     <Interface-IP>
                match = re.search(
                    r"0\.0\.0\.0\s+0\.0\.0\.0\s+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)",
                    result.stdout
                )
                if match:
                    gateway_ip = match.group(1).strip()
                    # Filter out loopback or invalid default route markers
                    if not gateway_ip.startswith("127.") and gateway_ip != "0.0.0.0":
                        return gateway_ip

        elif system == "Linux":
            result = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False
            )
            if result.returncode == 0:
                # Format: default via 192.168.1.1 dev eth0 ...
                match = re.search(r"default\s+via\s+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", result.stdout)
                if match:
                    return match.group(1).strip()

        elif system == "Darwin":
            result = subprocess.run(
                ["netstat", "-nr", "-f", "inet"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False
            )
            if result.returncode == 0:
                # Format: default 192.168.1.1 UGSc ...
                match = re.search(r"default\s+([0-9]+\.[0-9]+\.[0-9]+\.[0-9]+)", result.stdout)
                if match:
                    return match.group(1).strip()

    except Exception:
        pass

    return None


def get_network_interface_info() -> Dict[str, Optional[str]]:
    """
    Return basic local networking interface info (Local IP and Default Gateway).
    """
    return {
        "local_ip": get_local_ip(),
        "default_gateway": get_default_gateway(),
        "platform": platform.system(),
    }

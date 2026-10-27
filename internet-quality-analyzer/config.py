"""
Configuration module for Internet Quality Analyzer & Connection Troubleshooter.
Defines target allowlists, network thresholds, timing configurations, and database paths.
"""

from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)
DATABASE_PATH = INSTANCE_DIR / "network_quality.db"

# Allowed Test Targets (Strict allowlist for security against arbitrary network scanning)
ALLOWED_TARGETS = [
    {
        "id": "gateway",
        "name": "Default Gateway",
        "type": "gateway",
        "host": "auto",  # Resolved dynamically at runtime
        "port": None,
        "description": "Local Wi-Fi or Ethernet router gateway",
    },
    {
        "id": "cloudflare_dns",
        "name": "Cloudflare DNS",
        "type": "dns_resolver",
        "host": "1.1.1.1",
        "port": 53,
        "description": "Anycast public DNS resolver (Cloudflare)",
    },
    {
        "id": "google_dns",
        "name": "Google DNS",
        "type": "dns_resolver",
        "host": "8.8.8.8",
        "port": 53,
        "description": "Anycast public DNS resolver (Google)",
    },
    {
        "id": "google_web",
        "name": "Google Web",
        "type": "external_host",
        "host": "google.com",
        "port": 443,
        "description": "Global search endpoint (HTTPS)",
    },
    {
        "id": "cloudflare_web",
        "name": "Cloudflare Web",
        "type": "external_host",
        "host": "cloudflare.com",
        "port": 443,
        "description": "Global edge CDN endpoint (HTTPS)",
    },
]

# Supported DNS Resolvers for comparative DNS resolution testing
DNS_RESOLVERS = [
    {"name": "System Default", "ip": None},
    {"name": "Cloudflare (1.1.1.1)", "ip": "1.1.1.1"},
    {"name": "Google (8.8.8.8)", "ip": "8.8.8.8"},
]

# Probe Sampling Settings
DEFAULT_PROBE_COUNT = 5
MAX_PROBE_COUNT = 15
MIN_PROBE_COUNT = 3
PROBE_TIMEOUT_SECONDS = 2.0  # Per-probe timeout
TCP_TIMEOUT_SECONDS = 3.0    # TCP 3-way handshake timeout
DNS_TIMEOUT_SECONDS = 3.0    # DNS resolution timeout

# Diagnostic Thresholds (Used by analysis/troubleshooter.py)
THRESHOLDS = {
    # Latency (RTT) thresholds in milliseconds
    "latency": {
        "good": 50.0,
        "warning": 120.0,
    },
    # Gateway specific latency (Local hop should be very fast)
    "gateway_latency": {
        "good": 5.0,
        "warning": 20.0,
    },
    # Jitter (RTT variability) in milliseconds
    "jitter": {
        "good": 10.0,
        "warning": 25.0,
    },
    # Packet Loss in percentage (0 - 100)
    "packet_loss": {
        "good": 0.0,
        "warning": 3.0,
        "critical": 10.0,
    },
    # DNS lookup time in milliseconds
    "dns_lookup": {
        "good": 40.0,
        "warning": 120.0,
    },
    # TCP connection establishment (3-way handshake) in milliseconds
    "tcp_handshake": {
        "good": 60.0,
        "warning": 150.0,
    },
}

# Monitoring Settings
MONITORING_DEFAULT_INTERVAL_SECONDS = 300  # 5 minutes
MONITORING_MIN_INTERVAL_SECONDS = 30

"""
Composite Network Measurement Orchestrator.

Orchestrates multi-layer diagnostics across:
1. Local Default Gateway (Hop-1 L2/L3 isolation)
2. External Target ICMP Latency & Jitter
3. DNS Lookup Timing across configured Resolvers
4. TCP 3-Way Handshake Connection Timing

Produces an aggregated measurement report ready for diagnostic rule evaluation and persistence.
"""

from datetime import datetime, timezone
import time
from typing import Dict, Any, List, Optional

from config import ALLOWED_TARGETS, DNS_RESOLVERS, DEFAULT_PROBE_COUNT, PROBE_TIMEOUT_SECONDS
from network.gateway_detector import get_default_gateway, get_network_interface_info
from network.ping_test import run_ping_test
from network.dns_test import measure_dns_lookup, run_dns_benchmark
from network.tcp_test import measure_tcp_connect


def run_full_diagnostic_probe(
    target_ids: Optional[List[str]] = None,
    probe_count: int = DEFAULT_PROBE_COUNT
) -> Dict[str, Any]:
    """
    Execute a comprehensive multi-layer network quality measurement run.

    Args:
        target_ids: Optional list of target IDs to probe (e.g. ['gateway', 'cloudflare_dns']).
                    If None, probes all ALLOWED_TARGETS.
        probe_count: Number of ICMP probes per target.

    Returns:
        Structured measurement dictionary containing all raw samples and aggregated statistics.
    """
    start_wall_time = datetime.now(timezone.utc)
    start_perf = time.perf_counter()

    # Detect Gateway
    gateway_ip = get_default_gateway()
    interface_info = get_network_interface_info()

    # Filter targets against allowlist
    if target_ids:
        selected_targets = [t for t in ALLOWED_TARGETS if t["id"] in target_ids]
    else:
        selected_targets = list(ALLOWED_TARGETS)

    samples_results: List[Dict[str, Any]] = []

    for target in selected_targets:
        t_id = target["id"]
        t_name = target["name"]
        t_type = target["type"]
        t_host = target["host"]
        t_port = target["port"]

        # If gateway target, use detected gateway IP
        if t_type == "gateway":
            actual_host = gateway_ip
            if not actual_host:
                samples_results.append({
                    "target_id": t_id,
                    "target_name": t_name,
                    "target_type": t_type,
                    "target_address": "unavailable",
                    "target_port": None,
                    "ping": {
                        "sent": probe_count,
                        "received": 0,
                        "lost": probe_count,
                        "packet_loss_pct": 100.0,
                        "min_ms": None,
                        "max_ms": None,
                        "avg_ms": None,
                        "median_ms": None,
                        "jitter_ms": None,
                        "status": "failed",
                        "error_message": "Default gateway could not be detected on local network interface.",
                    },
                    "dns_lookup_ms": None,
                    "tcp_handshake_ms": None,
                })
                continue
        else:
            actual_host = t_host

        # 1. ICMP Ping measurement
        timeout_ms = int(PROBE_TIMEOUT_SECONDS * 1000)
        ping_res = run_ping_test(actual_host, count=probe_count, timeout_ms=timeout_ms)

        # 2. DNS resolution measurement (if target is a domain name)
        dns_ms: Optional[float] = None
        if not re_is_ip(actual_host):
            dns_res = measure_dns_lookup(actual_host)
            if dns_res["success"]:
                dns_ms = dns_res["elapsed_ms"]

        # 3. TCP Handshake measurement (if target specifies a port)
        tcp_ms: Optional[float] = None
        if t_port is not None:
            tcp_res = measure_tcp_connect(actual_host, t_port)
            if tcp_res["success"]:
                tcp_ms = tcp_res["handshake_ms"]

        samples_results.append({
            "target_id": t_id,
            "target_name": t_name,
            "target_type": t_type,
            "target_address": actual_host,
            "target_port": t_port,
            "ping": ping_res,
            "dns_lookup_ms": dns_ms,
            "tcp_handshake_ms": tcp_ms,
        })

    # DNS benchmark across standard resolvers
    dns_benchmarks = run_dns_benchmark("google.com", resolvers=DNS_RESOLVERS, samples_per_resolver=2)

    total_duration = round(time.perf_counter() - start_perf, 2)

    return {
        "timestamp_utc": start_wall_time.isoformat(),
        "duration_seconds": total_duration,
        "interface_info": interface_info,
        "gateway_detected": gateway_ip is not None,
        "gateway_ip": gateway_ip,
        "target_results": samples_results,
        "dns_benchmarks": dns_benchmarks,
    }


def re_is_ip(host: str) -> bool:
    """Helper to detect if a host string is an IPv4 or IPv6 address."""
    import re
    # Simple IPv4 check
    if re.match(r"^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$", host):
        return True
    # Simple IPv6 check
    if ":" in host:
        return True
    return False

"""
DNS Resolution Timing Engine.

Measures the elapsed network time required to resolve a domain name into IP addresses
using dnspython.

Network Concepts:
- DNS (Domain Name System, RFC 1035) operates at Application Layer (L7) typically over UDP/53.
- When querying specific resolvers (e.g., 1.1.1.1 or 8.8.8.8), queries bypass the local OS
  client resolver cache (e.g., Windows DNS Client service), measuring actual network RTT
  and recursive resolver processing time.
- DNS lookup latency is only the address resolution phase; it does NOT include TCP 3-way
  handshake or HTTP data transfer.
"""

import time
from typing import Dict, Any, List, Optional
import dns.resolver
import dns.exception


def measure_dns_lookup(
    domain: str,
    resolver_ip: Optional[str] = None,
    query_type: str = "A",
    timeout_sec: float = 3.0
) -> Dict[str, Any]:
    """
    Perform a single DNS resolution query and measure elapsed time with monotonic precision.

    Args:
        domain: Fully qualified domain name (e.g., 'google.com').
        resolver_ip: Specific resolver IP (e.g., '1.1.1.1') or None for OS default.
        query_type: DNS record type (default 'A').
        timeout_sec: Resolution timeout in seconds.

    Returns:
        Structured measurement dictionary.
    """
    custom_resolver = dns.resolver.Resolver(configure=resolver_ip is None)
    if resolver_ip:
        custom_resolver.nameservers = [resolver_ip]

    custom_resolver.lifetime = timeout_sec
    custom_resolver.timeout = timeout_sec

    start = time.perf_counter()
    try:
        answers = custom_resolver.resolve(domain, query_type)
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
        resolved_ips = [rdata.to_text() for rdata in answers]

        return {
            "domain": domain,
            "resolver": resolver_ip or "System Default",
            "query_type": query_type,
            "elapsed_ms": elapsed_ms,
            "resolved_ips": resolved_ips,
            "success": True,
            "error_category": None,
            "status": "success",
        }

    except dns.resolver.NXDOMAIN:
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
        return {
            "domain": domain,
            "resolver": resolver_ip or "System Default",
            "query_type": query_type,
            "elapsed_ms": elapsed_ms,
            "resolved_ips": [],
            "success": False,
            "error_category": "NXDOMAIN (Non-Existent Domain)",
            "status": "failed",
        }

    except dns.resolver.NoAnswer:
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
        return {
            "domain": domain,
            "resolver": resolver_ip or "System Default",
            "query_type": query_type,
            "elapsed_ms": elapsed_ms,
            "resolved_ips": [],
            "success": False,
            "error_category": "NoAnswer (No records of requested type)",
            "status": "failed",
        }

    except dns.resolver.Timeout:
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
        return {
            "domain": domain,
            "resolver": resolver_ip or "System Default",
            "query_type": query_type,
            "elapsed_ms": elapsed_ms,
            "resolved_ips": [],
            "success": False,
            "error_category": "Timeout (Resolver did not respond)",
            "status": "failed",
        }

    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)
        return {
            "domain": domain,
            "resolver": resolver_ip or "System Default",
            "query_type": query_type,
            "elapsed_ms": elapsed_ms,
            "resolved_ips": [],
            "success": False,
            "error_category": f"Error: {type(exc).__name__}",
            "status": "failed",
        }


def run_dns_benchmark(
    domain: str,
    resolvers: Optional[List[Dict[str, Optional[str]]]] = None,
    samples_per_resolver: int = 3
) -> List[Dict[str, Any]]:
    """
    Benchmark multiple DNS resolvers against a target domain.

    Args:
        domain: Domain name to query.
        resolvers: List of dicts e.g. [{'name': 'Cloudflare', 'ip': '1.1.1.1'}]
        samples_per_resolver: Number of queries per resolver to analyze variance.

    Returns:
        List of benchmark result summaries per resolver.
    """
    if resolvers is None:
        resolvers = [
            {"name": "System Default", "ip": None},
            {"name": "Cloudflare", "ip": "1.1.1.1"},
            {"name": "Google", "ip": "8.8.8.8"},
        ]

    benchmarks = []

    for r in resolvers:
        r_name = r.get("name", "Unknown")
        r_ip = r.get("ip")
        sample_times = []
        errors = []
        resolved_ips = []

        for _ in range(samples_per_resolver):
            res = measure_dns_lookup(domain, resolver_ip=r_ip)
            if res["success"]:
                sample_times.append(res["elapsed_ms"])
                if not resolved_ips and res["resolved_ips"]:
                    resolved_ips = res["resolved_ips"]
            else:
                errors.append(res["error_category"])

        if sample_times:
            avg_ms = round(sum(sample_times) / len(sample_times), 2)
            min_ms = round(min(sample_times), 2)
            max_ms = round(max(sample_times), 2)
            status = "success"
        else:
            avg_ms = None
            min_ms = None
            max_ms = None
            status = "failed"

        benchmarks.append({
            "resolver_name": r_name,
            "resolver_ip": r_ip or "System Default",
            "domain": domain,
            "avg_ms": avg_ms,
            "min_ms": min_ms,
            "max_ms": max_ms,
            "samples": sample_times,
            "resolved_ips": resolved_ips,
            "errors": errors,
            "status": status,
        })

    return benchmarks

"""
Network Telemetry Comparison Engine.

Compares two distinct network test runs (e.g. Wi-Fi vs. Mobile Hotspot, peak vs. off-peak,
or before vs. after router restart) and calculates metric deltas across matched targets.

Design Notes:
- Objectively calculates quantitative differences:
    Delta = Run B (Current/Target) - Run A (Baseline/Reference)
- Strictly avoids speculating on external causes without verifiable evidence.
"""

from typing import Dict, Any, List, Optional


def compare_runs(run_a: Dict[str, Any], run_b: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare two test runs and calculate metric deltas across common targets.

    Args:
        run_a: Reference baseline run dictionary.
        run_b: Comparative run dictionary.

    Returns:
        Structured comparison dictionary with target-by-target deltas and summary.
    """
    samples_a = {s["target_id"]: s for s in run_a.get("metric_samples", [])}
    samples_b = {s["target_id"]: s for s in run_b.get("metric_samples", [])}

    all_target_ids = sorted(list(set(samples_a.keys()) | set(samples_b.keys())))
    target_comparisons: List[Dict[str, Any]] = []

    latency_deltas = []
    loss_deltas = []
    jitter_deltas = []

    for t_id in all_target_ids:
        sa = samples_a.get(t_id)
        sb = samples_b.get(t_id)

        target_name = (sb or sa).get("target_name", t_id)
        target_type = (sb or sa).get("target_type", "external_host")

        # Metric deltas: B - A
        lat_a = sa.get("latency_avg_ms") if sa else None
        lat_b = sb.get("latency_avg_ms") if sb else None
        delta_lat = round(lat_b - lat_a, 2) if (lat_a is not None and lat_b is not None) else None
        if delta_lat is not None and target_type != "gateway":
            latency_deltas.append(delta_lat)

        jitter_a = sa.get("jitter_ms") if sa else None
        jitter_b = sb.get("jitter_ms") if sb else None
        delta_jitter = round(jitter_b - jitter_a, 2) if (jitter_a is not None and jitter_b is not None) else None
        if delta_jitter is not None and target_type != "gateway":
            jitter_deltas.append(delta_jitter)

        loss_a = sa.get("packet_loss_pct") if sa else None
        loss_b = sb.get("packet_loss_pct") if sb else None
        delta_loss = round(loss_b - loss_a, 2) if (loss_a is not None and loss_b is not None) else None
        if delta_loss is not None and target_type != "gateway":
            loss_deltas.append(delta_loss)

        dns_a = sa.get("dns_lookup_time_ms") if sa else None
        dns_b = sb.get("dns_lookup_time_ms") if sb else None
        delta_dns = round(dns_b - dns_a, 2) if (dns_a is not None and dns_b is not None) else None

        tcp_a = sa.get("tcp_handshake_time_ms") if sa else None
        tcp_b = sb.get("tcp_handshake_time_ms") if sb else None
        delta_tcp = round(tcp_b - tcp_a, 2) if (tcp_a is not None and tcp_b is not None) else None

        target_comparisons.append({
            "target_id": t_id,
            "target_name": target_name,
            "target_type": target_type,
            "run_a": {
                "latency_avg_ms": lat_a,
                "jitter_ms": jitter_a,
                "packet_loss_pct": loss_a,
                "dns_ms": dns_a,
                "tcp_ms": tcp_a,
                "status": sa.get("status") if sa else "not_tested",
            },
            "run_b": {
                "latency_avg_ms": lat_b,
                "jitter_ms": jitter_b,
                "packet_loss_pct": loss_b,
                "dns_ms": dns_b,
                "tcp_ms": tcp_b,
                "status": sb.get("status") if sb else "not_tested",
            },
            "deltas": {
                "latency_avg_ms": delta_lat,
                "jitter_ms": delta_jitter,
                "packet_loss_pct": delta_loss,
                "dns_ms": delta_dns,
                "tcp_ms": delta_tcp,
            },
        })

    # Overall comparative narrative
    avg_lat_delta = round(sum(latency_deltas) / len(latency_deltas), 2) if latency_deltas else None
    avg_loss_delta = round(sum(loss_deltas) / len(loss_deltas), 2) if loss_deltas else None
    avg_jitter_delta = round(sum(jitter_deltas) / len(jitter_deltas), 2) if jitter_deltas else None

    # Determine general trend
    if avg_lat_delta is not None and avg_loss_delta is not None:
        if avg_lat_delta < -10.0 or avg_loss_delta < -2.0:
            trend = "improved"
            trend_summary = f"Run #{run_b['id']} showed improved network performance compared to Run #{run_a['id']} (average external latency changed by {avg_lat_delta:+.1f}ms, packet loss changed by {avg_loss_delta:+.1f}%)."
        elif avg_lat_delta > 10.0 or avg_loss_delta > 2.0:
            trend = "degraded"
            trend_summary = f"Run #{run_b['id']} showed degraded network metrics compared to Run #{run_a['id']} (average external latency changed by {avg_lat_delta:+.1f}ms, packet loss changed by {avg_loss_delta:+.1f}%)."
        else:
            trend = "comparable"
            trend_summary = f"Run #{run_b['id']} and Run #{run_a['id']} exhibited comparable network performance (latency delta: {avg_lat_delta:+.1f}ms, loss delta: {avg_loss_delta:+.1f}%)."
    else:
        trend = "insufficient_overlap"
        trend_summary = "Insufficient common target measurements to determine overall trend."

    return {
        "run_a": {
            "id": run_a["id"],
            "timestamp_utc": run_a["timestamp_utc"],
            "overall_status": run_a["overall_status"],
            "trigger_type": run_a["trigger_type"],
            "gateway_ip": run_a.get("gateway_ip"),
        },
        "run_b": {
            "id": run_b["id"],
            "timestamp_utc": run_b["timestamp_utc"],
            "overall_status": run_b["overall_status"],
            "trigger_type": run_b["trigger_type"],
            "gateway_ip": run_b.get("gateway_ip"),
        },
        "trend": trend,
        "summary": trend_summary,
        "aggregate_deltas": {
            "avg_latency_delta_ms": avg_lat_delta,
            "avg_loss_delta_pct": avg_loss_delta,
            "avg_jitter_delta_ms": avg_jitter_delta,
        },
        "target_comparisons": target_comparisons,
    }


def compare_destinations(run: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare and benchmark all tested destinations within a single diagnostic run.

    Calculates:
    - Target rankings by latency (lowest to highest).
    - WAN penalty (L3 target latency - L3 gateway latency) to isolate LAN vs WAN overhead.
    - Protocol overhead (L4 TCP 3-way handshake - L3 ICMP RTT).
    - DNS resolver benchmarking comparison.

    Args:
        run: Test run dictionary containing 'metric_samples'.

    Returns:
        Structured destination comparison dictionary.
    """
    samples = run.get("metric_samples", [])
    if not samples:
        return {
            "run_id": run.get("id"),
            "timestamp_utc": run.get("timestamp_utc"),
            "destinations": [],
            "ranked_by_latency": [],
            "dns_resolvers": [],
            "gateway": None,
        }

    # Find gateway sample
    gw_sample = next((s for s in samples if s.get("target_type") == "gateway"), None)
    gw_latency = gw_sample.get("latency_avg_ms") if gw_sample else None

    destinations: List[Dict[str, Any]] = []
    dns_resolvers: List[Dict[str, Any]] = []

    for s in samples:
        lat = s.get("latency_avg_ms")
        tcp = s.get("tcp_handshake_time_ms")
        dns = s.get("dns_lookup_time_ms")
        is_gw = s.get("target_type") == "gateway"

        # WAN penalty: target latency - gateway latency
        wan_penalty = None
        if not is_gw and lat is not None and gw_latency is not None:
            wan_penalty = round(max(0.0, lat - gw_latency), 2)

        # TCP overhead: TCP 3-way handshake - ICMP RTT
        tcp_overhead = None
        if tcp is not None and lat is not None:
            tcp_overhead = round(tcp - lat, 2)

        item = {
            "target_id": s.get("target_id"),
            "target_name": s.get("target_name"),
            "target_type": s.get("target_type"),
            "target_address": s.get("target_address"),
            "latency_avg_ms": lat,
            "jitter_ms": s.get("jitter_ms"),
            "packet_loss_pct": s.get("packet_loss_pct"),
            "dns_lookup_time_ms": dns,
            "tcp_handshake_time_ms": tcp,
            "wan_penalty_ms": wan_penalty,
            "tcp_overhead_ms": tcp_overhead,
            "status": s.get("status"),
        }
        destinations.append(item)

        if s.get("target_type") == "dns_resolver" or dns is not None:
            dns_resolvers.append({
                "target_id": s.get("target_id"),
                "target_name": s.get("target_name"),
                "dns_lookup_time_ms": dns,
                "latency_avg_ms": lat,
            })

    # Sort external destinations by latency
    external_destinations = [d for d in destinations if d.get("target_type") != "gateway" and d.get("latency_avg_ms") is not None]
    ranked_by_latency = sorted(external_destinations, key=lambda x: x["latency_avg_ms"])

    # Sort DNS resolvers by DNS lookup time
    ranked_dns = sorted(
        [r for r in dns_resolvers if r.get("dns_lookup_time_ms") is not None],
        key=lambda x: x["dns_lookup_time_ms"]
    )

    fastest_destination = ranked_by_latency[0] if ranked_by_latency else None
    slowest_destination = ranked_by_latency[-1] if ranked_by_latency else None
    fastest_dns = ranked_dns[0] if ranked_dns else None

    return {
        "run_id": run.get("id"),
        "timestamp_utc": run.get("timestamp_utc"),
        "gateway_baseline_ms": gw_latency,
        "fastest_destination": fastest_destination,
        "slowest_destination": slowest_destination,
        "fastest_dns_resolver": fastest_dns,
        "ranked_by_latency": ranked_by_latency,
        "dns_resolvers": ranked_dns,
        "all_destinations": destinations,
    }


def export_comparison_as_csv(comparison: Dict[str, Any]) -> str:
    """
    Format differential test comparison results into RFC 4180 compliant CSV.

    Args:
        comparison: Comparison dictionary produced by compare_runs().

    Returns:
        CSV string with comparison header metadata and target delta rows.
    """
    import csv
    import io

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n")

    run_a = comparison.get("run_a", {})
    run_b = comparison.get("run_b", {})
    deltas = comparison.get("aggregate_deltas", {})

    # Metadata comments
    writer.writerow([f"# NetPulse Differential Comparison: Run #{run_a.get('id')} vs Run #{run_b.get('id')}"])
    writer.writerow([f"# Baseline Run A: #{run_a.get('id')} ({run_a.get('timestamp_utc')}) Status: {run_a.get('overall_status')}"])
    writer.writerow([f"# Compare Run B:  #{run_b.get('id')} ({run_b.get('timestamp_utc')}) Status: {run_b.get('overall_status')}"])
    writer.writerow([f"# Overall Trend: {comparison.get('trend')} - {comparison.get('summary')}"])
    writer.writerow([f"# Avg Latency Delta: {deltas.get('avg_latency_delta_ms')} ms | Avg Loss Delta: {deltas.get('avg_loss_delta_pct')} % | Avg Jitter Delta: {deltas.get('avg_jitter_delta_ms')} ms"])
    writer.writerow([])  # Blank separator

    # Header
    writer.writerow([
        "target_id",
        "target_name",
        "target_type",
        "run_a_latency_ms",
        "run_b_latency_ms",
        "delta_latency_ms",
        "run_a_jitter_ms",
        "run_b_jitter_ms",
        "delta_jitter_ms",
        "run_a_loss_pct",
        "run_b_loss_pct",
        "delta_loss_pct",
        "run_a_dns_ms",
        "run_b_dns_ms",
        "delta_dns_ms",
        "run_a_tcp_ms",
        "run_b_tcp_ms",
        "delta_tcp_ms",
    ])

    for tc in comparison.get("target_comparisons", []):
        sa = tc.get("run_a", {})
        sb = tc.get("run_b", {})
        d = tc.get("deltas", {})
        writer.writerow([
            tc.get("target_id"),
            tc.get("target_name"),
            tc.get("target_type"),
            sa.get("latency_avg_ms"),
            sb.get("latency_avg_ms"),
            d.get("latency_avg_ms"),
            sa.get("jitter_ms"),
            sb.get("jitter_ms"),
            d.get("jitter_ms"),
            sa.get("packet_loss_pct"),
            sb.get("packet_loss_pct"),
            d.get("packet_loss_pct"),
            sa.get("dns_ms"),
            sb.get("dns_ms"),
            d.get("dns_ms"),
            sa.get("tcp_ms"),
            sb.get("tcp_ms"),
            d.get("tcp_ms"),
        ])

    return output.getvalue()


"""
Explainable Rule-Based Diagnostic Engine.

Analyzes telemetry from the network measurement engine, correlates hop-1 gateway metrics
with multi-destination external performance, isolates the layer of degradation, and produces
evidence-backed diagnostic findings with confidence levels and explicit limitations.

Design Principles:
- Strictly deterministic: Rules evaluate concrete quantitative thresholds from config.py.
- Explainable: Every finding states the symptom, supporting evidence, possible causes,
  recommended actions, confidence level, and diagnostic caveats.
- Non-fabricating: Does not guess when telemetry is absent or insufficient.
"""

from typing import Dict, Any, List, Optional
from config import THRESHOLDS


class Troubleshooter:
    """Evaluates network telemetry against diagnostic rules."""

    def __init__(self, thresholds: Optional[Dict[str, Any]] = None):
        self.thresholds = thresholds or THRESHOLDS

    def diagnose(self, probe_report: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze a complete diagnostic probe report and produce structured findings.

        Args:
            probe_report: Dictionary returned by network.engine.run_full_diagnostic_probe().

        Returns:
            Structured diagnostic dictionary with overall_status, summary, and findings list.
        """
        target_results = probe_report.get("target_results", [])
        dns_benchmarks = probe_report.get("dns_benchmarks", [])
        gateway_detected = probe_report.get("gateway_detected", False)
        gateway_ip = probe_report.get("gateway_ip")

        if not target_results:
            return {
                "overall_status": "insufficient_data",
                "summary": "Insufficient measurement telemetry to perform diagnosis.",
                "findings": [
                    {
                        "rule_id": "RULE_INSUFFICIENT_DATA",
                        "severity": "info",
                        "symptom": "No target measurements were recorded.",
                        "evidence": {"targets_tested": 0},
                        "possible_causes": ["Test run aborted before metrics could be collected."],
                        "recommendations": ["Re-run the diagnostic test with approved default targets."],
                        "confidence": "Low",
                        "limitations": "Analysis requires at least one responsive network destination.",
                    }
                ],
            }

        findings: List[Dict[str, Any]] = []

        # Categorize targets
        gateway_target = None
        external_targets = []

        for tr in target_results:
            if tr.get("target_type") == "gateway":
                gateway_target = tr
            else:
                external_targets.append(tr)

        # -------------------------------------------------------------
        # Rule 1: Total Disconnection (All destinations failed)
        # -------------------------------------------------------------
        all_targets = target_results
        all_failed = all(
            t.get("ping", {}).get("packet_loss_pct", 100.0) == 100.0 for t in all_targets
        )

        if all_failed and len(all_targets) > 0:
            findings.append({
                "rule_id": "RULE_ALL_DESTINATIONS_FAILED",
                "severity": "critical",
                "symptom": "Complete network failure: 100% packet loss across all tested destinations.",
                "evidence": {
                    "total_targets_tested": len(all_targets),
                    "failed_targets_count": len(all_targets),
                    "gateway_reachable": False,
                },
                "possible_causes": [
                    "Local Wi-Fi is disconnected or Ethernet cable is unplugged.",
                    "Network interface is disabled or in Airplane mode.",
                    "Local router/modem is powered off or not assigning IP addresses (DHCP failure).",
                ],
                "recommendations": [
                    "Verify physical network cables or reconnect to your Wi-Fi network.",
                    "Check if other devices on the same local network have internet connectivity.",
                    "Restart your network adapter or computer's network interface.",
                ],
                "confidence": "High",
                "limitations": (
                    "If a host-level firewall completely blocks outbound ICMP/UDP/TCP sockets, "
                    "all tests will fail even if basic network layer link is up."
                ),
            })
            return {
                "overall_status": "critical",
                "summary": "Total network disconnection detected. No targets or gateway responded.",
                "findings": findings,
            }

        # -------------------------------------------------------------
        # Rule 2: Local Gateway Degradation (Hop-1 Bottleneck)
        # -------------------------------------------------------------
        gw_ping = gateway_target.get("ping", {}) if gateway_target else {}
        gw_loss = gw_ping.get("packet_loss_pct", 0.0)
        gw_avg = gw_ping.get("avg_ms")
        gw_jitter = gw_ping.get("jitter_ms")

        gw_loss_warn = self.thresholds["packet_loss"]["warning"]
        gw_lat_warn = self.thresholds["gateway_latency"]["warning"]
        gw_is_degraded = False

        if gateway_target and gateway_detected:
            if gw_loss >= 100.0:
                gw_is_degraded = True
                findings.append({
                    "rule_id": "RULE_LOCAL_GATEWAY_UNREACHABLE",
                    "severity": "critical",
                    "symptom": f"Local default router/gateway ({gateway_ip}) did not respond to any probes.",
                    "evidence": {
                        "gateway_ip": gateway_ip,
                        "packet_loss_pct": 100.0,
                    },
                    "possible_causes": [
                        "Wi-Fi connection is degraded or dropping local frames.",
                        "Router control plane firewall is discarding ICMP echo requests.",
                        "Local IP address lease expired.",
                    ],
                    "recommendations": [
                        "Disconnect and reconnect to Wi-Fi, or reseat the Ethernet cable.",
                        "Reboot the local Wi-Fi router / gateway.",
                    ],
                    "confidence": "High",
                    "limitations": "Some enterprise routers explicitly disable ICMP echo replies on the gateway interface.",
                })
            elif gw_loss >= gw_loss_warn or (gw_avg is not None and gw_avg > gw_lat_warn) or (gw_jitter is not None and gw_jitter > 20.0):
                gw_is_degraded = True
                findings.append({
                    "rule_id": "RULE_LOCAL_GATEWAY_DEGRADED",
                    "severity": "warning",
                    "symptom": "Elevated latency, jitter, or packet loss detected on the local router/gateway hop.",
                    "evidence": {
                        "gateway_ip": gateway_ip,
                        "gateway_avg_latency_ms": gw_avg,
                        "gateway_latency_threshold_ms": gw_lat_warn,
                        "gateway_packet_loss_pct": gw_loss,
                        "gateway_jitter_ms": gw_jitter,
                    },
                    "possible_causes": [
                        "Wi-Fi signal attenuation, physical distance, or wall obstructions.",
                        "Co-channel Wi-Fi interference on 2.4 GHz spectrum (e.g. neighboring APs, microwave ovens).",
                        "High local router CPU load or router bufferbloat from local LAN traffic.",
                    ],
                    "recommendations": [
                        "Move closer to the Wi-Fi router or connect using an Ethernet cable.",
                        "Switch your Wi-Fi network from 2.4 GHz to 5 GHz or 6 GHz band.",
                        "Restart the local Wi-Fi access point or router.",
                    ],
                    "confidence": "High",
                    "limitations": "High gateway RTT may occasionally occur if the router's management processor is temporarily busy.",
                })

        # -------------------------------------------------------------
        # Rule 3: Upstream WAN / ISP Degradation (Gateway healthy, External degraded)
        # -------------------------------------------------------------
        ext_with_loss = [t for t in external_targets if t.get("ping", {}).get("packet_loss_pct", 0.0) >= self.thresholds["packet_loss"]["warning"]]
        ext_with_high_latency = [t for t in external_targets if (t.get("ping", {}).get("avg_ms") or 0.0) > self.thresholds["latency"]["warning"]]
        ext_with_high_jitter = [t for t in external_targets if (t.get("ping", {}).get("jitter_ms") or 0.0) > self.thresholds["jitter"]["warning"]]

        total_ext = len(external_targets)

        if not gw_is_degraded and total_ext > 1:
            # Widespread external packet loss
            if len(ext_with_loss) >= 2:
                findings.append({
                    "rule_id": "RULE_WAN_PACKET_LOSS",
                    "severity": "critical" if any(t.get("ping", {}).get("packet_loss_pct", 0.0) > 10.0 for t in ext_with_loss) else "warning",
                    "symptom": "Packet loss detected across multiple public internet destinations, while local gateway is healthy.",
                    "evidence": {
                        "affected_destinations_count": len(ext_with_loss),
                        "total_external_destinations": total_ext,
                        "gateway_loss_pct": gw_loss,
                        "examples": [
                            {"target": t["target_name"], "loss_pct": t.get("ping", {}).get("packet_loss_pct")}
                            for t in ext_with_loss[:3]
                        ],
                    },
                    "possible_causes": [
                        "Upstream ISP line degradation (fiber/coaxial cable signal-to-noise ratio issue).",
                        "ISP peering link congestion or packet drops at the ISP broadband access server (BRAS).",
                        "Bufferbloat on the ISP modem WAN uplink due to heavy concurrent upload traffic.",
                    ],
                    "recommendations": [
                        "Check if high-bandwidth uploads (cloud backup, torrents) are saturating the upstream connection.",
                        "Check your ISP's official service outage dashboard.",
                        "Contact your Internet Service Provider with recorded timestamped packet loss data.",
                    ],
                    "confidence": "High",
                    "limitations": "Cannot pinpoint the exact upstream autonomous system (AS) hop without traceroute hop-by-hop probing.",
                })

            # Widespread external high latency
            elif len(ext_with_high_latency) >= 2:
                findings.append({
                    "rule_id": "RULE_WAN_HIGH_LATENCY",
                    "severity": "warning",
                    "symptom": "High round-trip latency to multiple internet destinations with normal local gateway response.",
                    "evidence": {
                        "affected_destinations_count": len(ext_with_high_latency),
                        "latency_threshold_ms": self.thresholds["latency"]["warning"],
                        "examples": [
                            {"target": t["target_name"], "avg_ms": t.get("ping", {}).get("avg_ms")}
                            for t in ext_with_high_latency[:3]
                        ],
                    },
                    "possible_causes": [
                        "Sub-optimal ISP routing or long-haul transit path.",
                        "Peak-hour ISP node congestion.",
                        "Active downloads or video streams consuming local connection capacity.",
                    ],
                    "recommendations": [
                        "Test during off-peak hours to identify if congestion is time-dependent.",
                        "Check router bandwidth usage to see if another device is saturating bandwidth.",
                    ],
                    "confidence": "Moderate",
                    "limitations": "Physical geographical distance to remote servers naturally introduces base propagation delay (~5ms per 1000km).",
                })

        # -------------------------------------------------------------
        # Rule 4: High Jitter / Bufferbloat
        # -------------------------------------------------------------
        if len(ext_with_high_jitter) >= 1:
            findings.append({
                "rule_id": "RULE_HIGH_JITTER_BUFFERBLOAT",
                "severity": "warning",
                "symptom": "Significant round-trip time variation (high jitter) observed.",
                "evidence": {
                    "jitter_threshold_ms": self.thresholds["jitter"]["warning"],
                    "high_jitter_targets": [
                        {"target": t["target_name"], "jitter_ms": t.get("ping", {}).get("jitter_ms")}
                        for t in ext_with_high_jitter
                    ],
                },
                "possible_causes": [
                    "Bufferbloat: Router queuing unmanaged packets causing fluctuating delay.",
                    "Bursty Wi-Fi retransmissions caused by transient RF interference.",
                    "Background peer-to-peer traffic or auto-updating applications.",
                ],
                "recommendations": [
                    "Enable Smart Queue Management (SQM like fq_codel or CAKE) in your router settings.",
                    "Pause large downloads or video uploads during real-time calls or gaming sessions.",
                ],
                "confidence": "Moderate",
                "limitations": "Jitter is measured over periodic probes; micro-bursts of sub-millisecond traffic may not appear in short probe sets.",
            })

        # -------------------------------------------------------------
        # Rule 5: DNS Bottleneck vs Normal Transport Layer
        # -------------------------------------------------------------
        dns_slow_targets = []
        for t in external_targets:
            dns_time = t.get("dns_lookup_ms")
            tcp_time = t.get("tcp_handshake_ms")
            if dns_time is not None and dns_time > self.thresholds["dns_lookup"]["warning"]:
                dns_slow_targets.append({
                    "target": t["target_name"],
                    "dns_lookup_ms": dns_time,
                    "tcp_handshake_ms": tcp_time,
                })

        if dns_slow_targets:
            findings.append({
                "rule_id": "RULE_DNS_RESOLUTION_BOTTLENECK",
                "severity": "warning",
                "symptom": "Domain name resolution (DNS) is notably slow, delaying initial connection setup.",
                "evidence": {
                    "dns_warning_threshold_ms": self.thresholds["dns_lookup"]["warning"],
                    "slow_dns_lookups": dns_slow_targets,
                },
                "possible_causes": [
                    "Local ISP default DNS resolver is sluggish or under heavy query load.",
                    "Resolver cache miss requiring full root-to-TLD iterative lookup.",
                    "High latency to the configured primary DNS nameserver.",
                ],
                "recommendations": [
                    "Switch your network adapter DNS to fast anycast public resolvers (e.g. 1.1.1.1 or 8.8.8.8).",
                    "Repeat the test to verify if repeated lookups resolve faster via resolver caching.",
                ],
                "confidence": "High",
                "limitations": "First-time (uncached) queries take longer than cached queries; this is normal DNS behavior.",
            })

        # -------------------------------------------------------------
        # Rule 6: Comparative DNS Benchmark Findings
        # -------------------------------------------------------------
        if dns_benchmarks:
            sys_bench = next((b for b in dns_benchmarks if b["resolver_name"] == "System Default"), None)
            fastest_bench = None
            valid_benches = [b for b in dns_benchmarks if b.get("avg_ms") is not None]

            if valid_benches:
                fastest_bench = min(valid_benches, key=lambda b: b["avg_ms"])

            if sys_bench and fastest_bench and sys_bench["avg_ms"] and fastest_bench["avg_ms"]:
                diff = sys_bench["avg_ms"] - fastest_bench["avg_ms"]
                if diff >= 25.0 and fastest_bench["resolver_name"] != "System Default":
                    findings.append({
                        "rule_id": "RULE_DNS_RESOLVER_OPTIMIZATION",
                        "severity": "info",
                        "symptom": f"Alternative DNS resolver '{fastest_bench['resolver_name']}' is {diff:.1f}ms faster than System Default.",
                        "evidence": {
                            "system_default_avg_ms": sys_bench["avg_ms"],
                            "fastest_resolver": fastest_bench["resolver_name"],
                            "fastest_resolver_avg_ms": fastest_bench["avg_ms"],
                            "latency_improvement_ms": round(diff, 1),
                        },
                        "possible_causes": [
                            "Public anycast DNS resolvers have closer edge points-of-presence (PoPs) than the ISP resolver.",
                        ],
                        "recommendations": [
                            f"Consider configuring your router or PC to use {fastest_bench['resolver_name']} ({fastest_bench['resolver_ip']}).",
                        ],
                        "confidence": "Moderate",
                        "limitations": "Benchmark measured resolution for a single domain; resolver performance can vary across diverse domains.",
                    })

        # -------------------------------------------------------------
        # Rule 7: Single Destination Anomaly (Isolated Remote Issue)
        # -------------------------------------------------------------
        if total_ext >= 3:
            single_failed_ext = [t for t in external_targets if t.get("ping", {}).get("packet_loss_pct", 0.0) == 100.0]
            if len(single_failed_ext) == 1 and not gw_is_degraded:
                f_target = single_failed_ext[0]
                findings.append({
                    "rule_id": "RULE_SINGLE_DESTINATION_ANOMALY",
                    "severity": "info",
                    "symptom": f"Only destination '{f_target['target_name']}' failed, while other destinations and gateway are healthy.",
                    "evidence": {
                        "failed_target": f_target.get("target_name", "Unknown"),
                        "failed_target_address": f_target.get("target_address", f_target.get("target_name", "Unknown")),
                        "healthy_destinations_count": total_ext - 1,
                    },
                    "possible_causes": [
                        "The target host is temporarily offline or undergoing maintenance.",
                        "Target host has an upstream firewall policy dropping ICMP echo requests.",
                        "Localized routing issue specific to that destination's hosting provider.",
                    ],
                    "recommendations": [
                        "Check the specific service's operational status page (e.g. Downdetector).",
                        "Your general internet connection is functioning normally.",
                    ],
                    "confidence": "High",
                    "limitations": "Lack of ping response alone does not mean the HTTP/HTTPS web service is down (ICMP blocking is common).",
                })

        # -------------------------------------------------------------
        # Rule 8: All Clear / Connection Healthy
        # -------------------------------------------------------------
        if not findings:
            findings.append({
                "rule_id": "RULE_CONNECTION_HEALTHY",
                "severity": "info",
                "symptom": "All network quality metrics are within healthy operational thresholds.",
                "evidence": {
                    "gateway_latency_ms": gw_avg,
                    "external_targets_tested": total_ext,
                    "average_packet_loss_pct": 0.0,
                },
                "possible_causes": [
                    "Local Wi-Fi, default gateway, DNS resolvers, and external transit routing are performing optimally.",
                ],
                "recommendations": [
                    "No troubleshooting required. The connection is in good health for streaming, gaming, and calls.",
                ],
                "confidence": "High",
                "limitations": "Short sample periods reflect connection quality at the time of the test only.",
            })

        # Compute overall status
        severities = [f["severity"] for f in findings]
        if "critical" in severities:
            overall_status = "critical"
            summary = "Critical network degradation detected. Immediate troubleshooting advised."
        elif "warning" in severities:
            overall_status = "warning"
            summary = "Connection degradation detected. Performance in real-time applications may be impacted."
        else:
            overall_status = "healthy"
            summary = "Connection quality is healthy and operating within acceptable parameters."

        return {
            "overall_status": overall_status,
            "summary": summary,
            "findings": findings,
        }

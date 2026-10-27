"""
Jitter and Latency Statistics Calculator.

Mathematical Foundation:
Jitter (packet delay variation) measures the statistical variance in packet arrival times.
In this project, jitter is defined as the mean absolute difference between consecutive
successful round-trip time (RTT) measurements in their original transmission order:

    Jitter = (1 / (M - 1)) * sum(|RTT(i) - RTT(i-1)|)

Where M is the count of consecutive successful probe pairs.

Handling Missing Samples:
When packet loss occurs (e.g. [20ms, None, 25ms, 24ms]), probes separated by a lost packet
are NOT treated as adjacent consecutive measurements unless explicitly configured, because
the intervening dropped packet masks the real RTT transition. Gaps are tracked and skipped
to ensure accuracy.
"""

from typing import List, Optional, Dict, Any
import statistics


def calculate_jitter(
    samples: List[Optional[float]],
    strict_consecutive: bool = True
) -> Optional[float]:
    """
    Calculate RTT jitter across probe samples.

    Args:
        samples: Ordered list of RTT measurements in milliseconds (None indicates a lost probe).
        strict_consecutive: If True, only adjacent indices [i] and [i+1] that both succeeded
                            are compared. If False, lost probes are simply filtered out before
                            calculating differences.

    Returns:
        Mean jitter in milliseconds rounded to 2 decimal places, or None if fewer than 2 valid
        consecutive samples exist.
    """
    if not samples or len(samples) < 2:
        return None

    diffs: List[float] = []

    if strict_consecutive:
        for i in range(len(samples) - 1):
            s1 = samples[i]
            s2 = samples[i + 1]
            if s1 is not None and s2 is not None:
                diffs.append(abs(s2 - s1))
    else:
        valid_samples = [s for s in samples if s is not None]
        for i in range(len(valid_samples) - 1):
            diffs.append(abs(valid_samples[i + 1] - valid_samples[i]))

    if not diffs:
        return None

    return round(statistics.mean(diffs), 2)


def calculate_latency_stats(samples: List[Optional[float]]) -> Dict[str, Any]:
    """
    Calculate summary statistics for a list of RTT probe samples.

    Args:
        samples: List of RTT measurements in ms (None indicates dropped/failed probe).

    Returns:
        Dictionary containing:
            - sent: total attempted probes
            - received: count of successful probes
            - lost: count of failed probes
            - packet_loss_pct: packet loss percentage (0.0 to 100.0)
            - min_ms: minimum RTT or None
            - max_ms: maximum RTT or None
            - avg_ms: mean RTT or None
            - median_ms: median RTT or None
            - jitter_ms: jitter or None
    """
    total_sent = len(samples)
    if total_sent == 0:
        return {
            "sent": 0,
            "received": 0,
            "lost": 0,
            "packet_loss_pct": 0.0,
            "min_ms": None,
            "max_ms": None,
            "avg_ms": None,
            "median_ms": None,
            "jitter_ms": None,
        }

    valid_samples = [s for s in samples if s is not None]
    received_count = len(valid_samples)
    lost_count = total_sent - received_count
    loss_pct = round((lost_count / total_sent) * 100.0, 2)

    if received_count == 0:
        return {
            "sent": total_sent,
            "received": 0,
            "lost": lost_count,
            "packet_loss_pct": loss_pct,
            "min_ms": None,
            "max_ms": None,
            "avg_ms": None,
            "median_ms": None,
            "jitter_ms": None,
        }

    return {
        "sent": total_sent,
        "received": received_count,
        "lost": lost_count,
        "packet_loss_pct": loss_pct,
        "min_ms": round(min(valid_samples), 2),
        "max_ms": round(max(valid_samples), 2),
        "avg_ms": round(statistics.mean(valid_samples), 2),
        "median_ms": round(statistics.median(valid_samples), 2),
        "jitter_ms": calculate_jitter(samples, strict_consecutive=True),
    }

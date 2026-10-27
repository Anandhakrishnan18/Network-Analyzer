"""
Unit tests for jitter and latency statistics calculator.
"""

from network.jitter_calculator import calculate_jitter, calculate_latency_stats


def test_jitter_perfect_stream():
    """Jitter should be 0.0 for identical RTT measurements."""
    samples = [20.0, 20.0, 20.0, 20.0]
    jitter = calculate_jitter(samples)
    assert jitter == 0.0


def test_jitter_variable_stream():
    """Verify mean absolute difference formula across consecutive probes."""
    samples = [20.0, 24.0, 21.0, 26.0]
    # Diffs: |24-20|=4, |21-24|=3, |26-21|=5 -> Mean = (4 + 3 + 5) / 3 = 4.0
    jitter = calculate_jitter(samples)
    assert jitter == 4.0


def test_jitter_with_packet_loss_strict():
    """Verify strict consecutive handling when packet loss occurs."""
    samples = [20.0, None, 25.0, 30.0]
    # In strict mode: index 0 to 1 has None, index 1 to 2 has None.
    # Only index 2 to 3 (25.0 -> 30.0) is strictly consecutive: diff = 5.0
    jitter = calculate_jitter(samples, strict_consecutive=True)
    assert jitter == 5.0


def test_jitter_with_packet_loss_non_strict():
    """Verify non-strict mode skips None and compares adjacent available probes."""
    samples = [20.0, None, 25.0, 30.0]
    # Non-strict filters valid: [20.0, 25.0, 30.0] -> diffs: 5.0, 5.0 -> mean 5.0
    jitter = calculate_jitter(samples, strict_consecutive=False)
    assert jitter == 5.0


def test_jitter_insufficient_samples():
    """Return None when fewer than 2 valid samples exist."""
    assert calculate_jitter([]) is None
    assert calculate_jitter([25.0]) is None
    assert calculate_jitter([None, None]) is None
    assert calculate_jitter([25.0, None]) is None


def test_latency_stats_complete_success():
    """Calculate min, max, avg, median, and 0% loss on full success."""
    samples = [10.0, 20.0, 30.0, 40.0, 50.0]
    stats = calculate_latency_stats(samples)
    assert stats["sent"] == 5
    assert stats["received"] == 5
    assert stats["lost"] == 0
    assert stats["packet_loss_pct"] == 0.0
    assert stats["min_ms"] == 10.0
    assert stats["max_ms"] == 50.0
    assert stats["avg_ms"] == 30.0
    assert stats["median_ms"] == 30.0
    assert stats["jitter_ms"] == 10.0


def test_latency_stats_with_partial_loss():
    """Calculate correct loss percentage and ignore None for RTT stats."""
    samples = [10.0, None, 30.0, None]
    stats = calculate_latency_stats(samples)
    assert stats["sent"] == 4
    assert stats["received"] == 2
    assert stats["lost"] == 2
    assert stats["packet_loss_pct"] == 50.0
    assert stats["min_ms"] == 10.0
    assert stats["max_ms"] == 30.0
    assert stats["avg_ms"] == 20.0
    assert stats["median_ms"] == 20.0
    # No strictly consecutive pairs
    assert stats["jitter_ms"] is None


def test_latency_stats_total_loss():
    """Calculate 100% loss and return None for all latency metrics."""
    samples = [None, None, None]
    stats = calculate_latency_stats(samples)
    assert stats["sent"] == 3
    assert stats["received"] == 0
    assert stats["lost"] == 3
    assert stats["packet_loss_pct"] == 100.0
    assert stats["min_ms"] is None
    assert stats["max_ms"] is None
    assert stats["avg_ms"] is None
    assert stats["median_ms"] is None
    assert stats["jitter_ms"] is None

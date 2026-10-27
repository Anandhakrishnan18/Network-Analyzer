"""
Background Monitoring & Periodic Diagnostic Service.

Provides a thread-safe scheduler to execute periodic network diagnostics,
detect threshold breaches, and persist alert notifications.

Design Notes:
- Runs in a background daemon thread (`daemon=True`) to not block server shutdown.
- Uses `threading.Event()` for responsive, non-busy sleep and instant cancellation.
- Employs a mutex lock to guarantee prevention of duplicate or overlapping test runs.
"""

from datetime import datetime, timezone
from pathlib import Path
import threading
from typing import Dict, Any, Optional, List

from config import (
    THRESHOLDS,
    MONITORING_DEFAULT_INTERVAL_SECONDS,
    MONITORING_MIN_INTERVAL_SECONDS,
    DATABASE_PATH,
)
from network.engine import run_full_diagnostic_probe
from analysis.troubleshooter import Troubleshooter
from database.db import save_test_run, save_alert


class MonitoringService:
    """Manages periodic network diagnosis and automated threshold alerting."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        thresholds: Optional[Dict[str, Any]] = None
    ):
        self.db_path = db_path or DATABASE_PATH
        self.thresholds = thresholds or THRESHOLDS

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        self._is_running = False
        self._interval_sec = MONITORING_DEFAULT_INTERVAL_SECONDS
        self._last_run_utc: Optional[str] = None
        self._total_runs = 0
        self._last_error: Optional[str] = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def interval_seconds(self) -> int:
        return self._interval_sec

    def get_status(self) -> Dict[str, Any]:
        """Return the current operating status of the monitoring daemon."""
        with self._lock:
            return {
                "running": self._is_running,
                "interval_seconds": self._interval_sec,
                "last_run_utc": self._last_run_utc,
                "total_runs_completed": self._total_runs,
                "last_error": self._last_error,
            }

    def start(self, interval_seconds: Optional[int] = None) -> Dict[str, Any]:
        """
        Start the background monitoring worker.

        Args:
            interval_seconds: Polling interval in seconds (minimum 30s).
        """
        with self._lock:
            if self._is_running:
                return {
                    "status": "already_running",
                    "message": "Background monitoring service is already active.",
                    "details": self.get_status(),
                }

            if interval_seconds is not None:
                self._interval_sec = max(
                    int(interval_seconds),
                    MONITORING_MIN_INTERVAL_SECONDS
                )

            self._stop_event.clear()
            self._is_running = True
            self._last_error = None

            self._thread = threading.Thread(
                target=self._worker_loop,
                name="NetPulse-MonitoringWorker",
                daemon=True,
            )

        # Start thread after releasing the start mutex
        self._thread.start()

        return {
            "status": "started",
            "message": f"Periodic monitoring started with an interval of {self._interval_sec} seconds.",
            "details": self.get_status(),
        }

    def stop(self) -> Dict[str, Any]:
        """Signal the background monitoring worker to gracefully shut down."""
        with self._lock:
            if not self._is_running:
                return {
                    "status": "not_running",
                    "message": "Background monitoring service is not active.",
                    "details": self.get_status(),
                }

            self._stop_event.set()
            self._is_running = False

        if self._thread and self._thread.is_alive():
            # Wait up to 3 seconds for active probe cycle to complete
            self._thread.join(timeout=3.0)

        return {
            "status": "stopped",
            "message": "Background monitoring service has been stopped.",
            "details": self.get_status(),
        }

    def run_single_cycle(self) -> Optional[int]:
        """
        Execute a single monitoring pass, check thresholds for alerts, and persist.
        Returns the created test_run_id.
        """
        try:
            # 1. Run diagnostic probe
            probe_report = run_full_diagnostic_probe(probe_count=3)

            # 2. Analyze results
            troubleshooter = Troubleshooter(thresholds=self.thresholds)
            diagnostic_report = troubleshooter.diagnose(probe_report)

            # 3. Persist run
            run_id = save_test_run(
                probe_report,
                diagnostic_report,
                trigger_type="periodic",
                db_path=self.db_path,
            )

            # 4. Check thresholds and record alerts
            self._evaluate_and_record_alerts(run_id, probe_report)

            with self._lock:
                self._last_run_utc = datetime.now(timezone.utc).isoformat()
                self._total_runs += 1
                self._last_error = None

            return run_id

        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
            return None

    def _worker_loop(self) -> None:
        """Main loop executed by the daemon worker thread."""
        while not self._stop_event.is_set():
            # Run one diagnostic cycle
            self.run_single_cycle()

            # Responsive sleep: waits up to interval_sec, wakes instantly on stop()
            if self._stop_event.wait(timeout=self._interval_sec):
                break

    def _evaluate_and_record_alerts(self, run_id: int, probe_report: Dict[str, Any]) -> None:
        """Evaluate probe metrics against alert thresholds and save violations."""
        target_results = probe_report.get("target_results", [])
        warn_loss = self.thresholds["packet_loss"]["warning"]
        warn_lat = self.thresholds["latency"]["warning"]
        warn_gw_lat = self.thresholds["gateway_latency"]["warning"]
        warn_jitter = self.thresholds["jitter"]["warning"]

        for tr in target_results:
            t_name = tr.get("target_name", "Target")
            t_type = tr.get("target_type")
            ping = tr.get("ping", {})

            loss = ping.get("packet_loss_pct", 0.0)
            avg_ms = ping.get("avg_ms")
            jitter_ms = ping.get("jitter_ms")

            # Check packet loss
            if loss >= warn_loss:
                save_alert(
                    metric_name=f"{t_name} Packet Loss",
                    threshold_val=warn_loss,
                    observed_val=loss,
                    message=f"Packet loss of {loss:.1f}% to '{t_name}' exceeds threshold of {warn_loss}%.",
                    test_run_id=run_id,
                    db_path=self.db_path,
                )

            # Check latency
            if avg_ms is not None:
                threshold = warn_gw_lat if t_type == "gateway" else warn_lat
                if avg_ms > threshold:
                    save_alert(
                        metric_name=f"{t_name} Latency",
                        threshold_val=threshold,
                        observed_val=avg_ms,
                        message=f"Latency of {avg_ms:.1f}ms to '{t_name}' exceeds threshold of {threshold:.1f}ms.",
                        test_run_id=run_id,
                        db_path=self.db_path,
                    )

            # Check jitter
            if jitter_ms is not None and jitter_ms > warn_jitter:
                save_alert(
                    metric_name=f"{t_name} Jitter",
                    threshold_val=warn_jitter,
                    observed_val=jitter_ms,
                    message=f"Jitter of {jitter_ms:.1f}ms to '{t_name}' exceeds threshold of {warn_jitter:.1f}ms.",
                    test_run_id=run_id,
                    db_path=self.db_path,
                )


# Global singleton instance for Flask
monitoring_service = MonitoringService()

"""
Multiprocessing FPU heat generator for CPU Thermal Controller.
Runs worker processes executing floating point power calculations to warm up the CPU.
"""

import logging
import multiprocessing
import os
import signal
import sys
import time
from typing import List

logger = logging.getLogger(__name__)


def _fpu_heat_worker() -> None:
    """
    Worker function running in a separate process.
    Engages CPU Floating Point Unit (FPU) via continuous exponentiation.
    """
    # Ignore SIGINT in child worker processes so main process controls lifecycle
    try:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except Exception:
        pass

    try:
        while True:
            _ = 3.14159 ** 2.71828
    except (KeyboardInterrupt, SystemExit):
        pass


class HeatGenerator:
    """
    Manages the lifecycle of FPU heat-generating worker processes.
    Supports dynamic scaling (adding/removing workers) and instant emergency kill.
    """

    def __init__(self, max_workers: int = None) -> None:
        cpu_count = os.cpu_count() or 4
        self.max_workers: int = max_workers if max_workers is not None else cpu_count
        self._workers: List[multiprocessing.Process] = []
        self._ctx = multiprocessing.get_context()

    @property
    def active_worker_count(self) -> int:
        """Returns the number of currently running worker processes."""
        self._cleanup_dead_workers()
        return len(self._workers)

    def _cleanup_dead_workers(self) -> None:
        """Removes any terminated worker processes from the active tracking list."""
        alive_workers = []
        for p in self._workers:
            if p.is_alive():
                alive_workers.append(p)
            else:
                try:
                    p.join(timeout=0.01)
                except Exception:
                    pass
        self._workers = alive_workers

    def spawn_worker(self) -> bool:
        """
        Spawns a single worker process if below max_workers limit.
        Returns True if a worker was spawned, False otherwise.
        """
        self._cleanup_dead_workers()
        if len(self._workers) >= self.max_workers:
            return False

        try:
            p = self._ctx.Process(target=_fpu_heat_worker, daemon=True)
            p.start()
            self._workers.append(p)
            logger.debug("Spawned worker PID %s (total: %d)", p.pid, len(self._workers))
            return True
        except Exception as e:
            logger.error("Failed to spawn worker: %s", e)
            return False

    def kill_worker(self) -> bool:
        """
        Terminates the most recently spawned worker process.
        Returns True if a worker was terminated, False if none were running.
        """
        self._cleanup_dead_workers()
        if not self._workers:
            return False

        p = self._workers.pop()
        try:
            if p.is_alive():
                p.terminate()
                p.join(timeout=0.1)
                if p.is_alive():
                    p.kill()
                    p.join(timeout=0.05)
            logger.debug("Terminated worker PID %s (remaining: %d)", p.pid, len(self._workers))
            return True
        except Exception as e:
            logger.error("Error terminating worker %s: %s", getattr(p, "pid", None), e)
            return False

    def set_worker_count(self, target_count: int) -> int:
        """
        Adjusts running workers to match target_count (clamped between 0 and max_workers).
        Returns current active worker count.
        """
        target = max(0, min(self.max_workers, target_count))
        self._cleanup_dead_workers()

        while len(self._workers) < target:
            if not self.spawn_worker():
                break

        while len(self._workers) > target:
            if not self.kill_worker():
                break

        return len(self._workers)

    def stop_all(self) -> None:
        """
        Instantly terminates all running worker processes (kill-switch).
        """
        for p in self._workers:
            try:
                if p.is_alive():
                    p.terminate()
            except Exception:
                pass

        # Wait briefly for termination, then force kill if any remain
        for p in self._workers:
            try:
                p.join(timeout=0.05)
                if p.is_alive():
                    p.kill()
                    p.join(timeout=0.02)
            except Exception:
                pass

        self._workers.clear()
        logger.info("All heat generator workers stopped.")

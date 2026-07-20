## @file runtime_tracker.py
#  @brief Persistent total-runtime counter, crash-safe via periodic atomic flush.
import os
import json
import time
from Utils.logger import log


## @class RuntimeTracker
#  @brief Tracks total device runtime across restarts/crashes and the current session uptime.
#  @details Time is accumulated in memory and flushed to disk periodically (not every
#           call) to limit SD card wear. On an unclean shutdown, at most one flush
#           interval of runtime is lost - acceptable for a maintenance-hours counter.
class RuntimeTracker:
    def __init__(self, path, flush_interval_sec=60):
        self.path = path
        self.flush_interval_sec = flush_interval_sec
        self._session_start = time.monotonic()
        self._last_flush = self._session_start
        self.total_seconds = self._load()

    ## @brief Loads the previously persisted total runtime, defaulting to 0 on any error.
    def _load(self):
        try:
            with open(self.path, "r") as f:
                return float(json.load(f)["total_seconds"])
        except (FileNotFoundError, KeyError, ValueError, json.JSONDecodeError) as e:
            log.info(f"[RUNTIME] No valid runtime file found ({e}); starting from 0.")
            return 0.0

    ## @brief Atomically writes total_seconds to disk (tmp file + os.replace).
    def _save(self):
        tmp_path = self.path + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                json.dump({"total_seconds": self.total_seconds}, f)
            os.replace(tmp_path, self.path)
        except Exception as e:
            log.warning(f"[RUNTIME] Failed to persist runtime counter: {e}")

    ## @brief Call once per main-loop iteration; flushes to disk every flush_interval_sec.
    def tick(self):
        now = time.monotonic()
        elapsed = now - self._last_flush
        if elapsed >= self.flush_interval_sec:
            self.total_seconds += elapsed
            self._last_flush = now
            self._save()

    ## @brief Seconds since this process started (resets on restart).
    @property
    def session_seconds(self):
        return time.monotonic() - self._session_start

    ## @brief Total lifetime runtime in hours, including the current, not-yet-flushed session.
    @property
    def total_hours(self):
        pending = time.monotonic() - self._last_flush
        return (self.total_seconds + pending) / 3600.0

    ## @brief Current session uptime in hours.
    @property
    def session_hours(self):
        return self.session_seconds / 3600.0

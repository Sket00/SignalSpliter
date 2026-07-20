## @file lock_manager.py
#  @brief Manages access locks and priority for local and remote operations.
import time
import threading
from Utils.logger import log


## @class LockManager
#  @brief Handles mutual exclusion between the physical encoder and OPC UA clients.
#  @details Thread-safe: state is read/written both from the main loop and the OPC UA
#           thread, so every state-changing operation is guarded by an internal mutex.
#           All events are logged under a single [LOCK] tag for easy log filtering.
class LockManager:
    def __init__(self):
        self.owner = None             ##< None, "LOCAL", or "IP: XXX"
        self.last_active = 0          ##< Timestamp of last action
        self.timeout_sec = 30         ##< Seconds of inactivity before lock drops
        self.priority = "LOCAL"       ##< "LOCAL" or "REMOTE"
        self._mutex = threading.Lock()

    ## @brief Returns the current lock owner.
    def get_owner(self):
        with self._mutex:
            return self.owner

    ## @brief Refreshes the activity timer for the current owner.
    def update_activity(self):
        with self._mutex:
            if self.owner:
                self.last_active = time.time()

    ## @brief Checks and clears the lock if it has expired due to inactivity.
    #  @return True if the lock was just dropped, False otherwise.
    def check_timeout(self):
        with self._mutex:
            return self._check_timeout_locked()

    ## @brief Internal, non-locking timeout check - caller must already hold _mutex.
    def _check_timeout_locked(self):
        if self.owner and (time.time() - self.last_active > self.timeout_sec):
            log.info(f"[LOCK] event=timeout owner={self.owner}")
            self.owner = None
            return True
        return False

    ## @brief Attempts to acquire the lock for the requester.
    #  @param requester String identifier (e.g. "LOCAL" or a client IP).
    #  @return True if acquired or already owned, False if blocked by another owner.
    def try_acquire(self, requester):
        with self._mutex:
            self._check_timeout_locked()
            if self.owner is None or self.owner == requester:
                if self.owner is None:
                    log.info(f"[LOCK] event=acquired owner={requester}")
                self.owner = requester
                self.last_active = time.time()
                return True
            return False

    ## @brief Forcefully steals the lock from the current owner.
    def force_steal(self, requester):
        with self._mutex:
            log.warning(f"[LOCK] event=stolen previous_owner={self.owner} new_owner={requester}")
            self.owner = requester
            self.last_active = time.time()

    ## @brief Releases the lock if held by the requester (or unconditionally if requester=None).
    def release(self, requester=None):
        with self._mutex:
            if requester is None or self.owner == requester:
                if self.owner:
                    log.info(f"[LOCK] event=released owner={self.owner}")
                self.owner = None

    # Note: `priority` remains a plain attribute (no mutex). It is a simple string
    # read/written from a single thread at a time (local encoder), so a single
    # attribute read/write is atomic under the GIL - no real race risk here,
    # unlike `owner` above.

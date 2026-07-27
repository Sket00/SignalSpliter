## @file network_info.py
#  @brief Cached IP lookup, shared by the device clock, logger and GUI.

import subprocess
import time

_CACHE_INTERVAL_SEC = 15.0
_last_check = 0.0
_last_ip = None


## @brief Returns the device's IP address, or None if offline.
#  @details Cached for _CACHE_INTERVAL_SEC to avoid spawning a subprocess on
#           every call.
def get_ip():
    global _last_check, _last_ip
    now = time.monotonic()
    if now - _last_check >= _CACHE_INTERVAL_SEC:
        _last_check = now
        try:
            out = subprocess.check_output(["hostname", "-I"], text=True, timeout=1).strip()
            _last_ip = out.split()[0] if out else None
        except Exception:
            _last_ip = None
    return _last_ip

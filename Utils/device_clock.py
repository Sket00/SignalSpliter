## @file device_clock.py
#  @brief Best-effort clock for log timestamps only (Pi Zero W has no RTC).
#  @details Online (any IP present): trusts the OS clock, assumed NTP-synced.
#           Offline: unknown ("--:--") until manually set via the GUI Settings
#           screen; the manual value is a plain in-memory offset from
#           time.monotonic() and does NOT persist across restarts by design -
#           an accepted trade-off given there's no battery-backed RTC.
import time
from Utils.network_info import get_ip

_manual_seconds_of_day = None
_manual_monotonic_anchor = None


## @brief Manually sets the wall-clock time (hour, minute) for offline use.
def set_manual_time(hour: int, minute: int):
    global _manual_seconds_of_day, _manual_monotonic_anchor
    _manual_seconds_of_day = hour * 3600 + minute * 60
    _manual_monotonic_anchor = time.monotonic()


## @brief Returns (hour, minute) for the current best-effort time, or None if unknown.
def current_hm():
    if get_ip() is not None:
        t = time.localtime()
        return t.tm_hour, t.tm_min
    if _manual_seconds_of_day is not None:
        elapsed = time.monotonic() - _manual_monotonic_anchor
        total = int(_manual_seconds_of_day + elapsed) % 86400
        return total // 3600, (total % 3600) // 60
    return None


## @brief Formatted "HH:MM:SS" string for log timestamps, or "--:--" if unknown.
def now_str():
    if get_ip() is not None:
        return time.strftime("%H:%M:%S")
    if _manual_seconds_of_day is not None:
        elapsed = time.monotonic() - _manual_monotonic_anchor
        total = int(_manual_seconds_of_day + elapsed) % 86400
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    return "--:--"

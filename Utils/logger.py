## @file logger.py
#  @brief Centralized logging utility with memory buffer for OPC UA.
import logging
from logging.handlers import TimedRotatingFileHandler
from collections import deque
from Config import settings


## @class MemoryHandler
#  @brief Custom logging handler that keeps the last N logs in memory.
class MemoryHandler(logging.Handler):
    def __init__(self, capacity=10):
        super().__init__()
        self.history = deque(maxlen=capacity)
    def emit(self, record):
        self.history.append(self.format(record))

memory_handler = MemoryHandler(10)


## @class DeviceClockFormatter
#  @brief Uses Utils.device_clock instead of the OS clock for timestamps.
#  @details The Pi Zero W has no RTC. Without this, an offline device with an
#           unsynced system clock would print a bogus, misleading timestamp
#           (e.g. Jan 1970) instead of honestly showing that time is unknown.
class DeviceClockFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        from Utils.device_clock import now_str
        return now_str()

## @brief Sets up the application logger with a size-unbounded but time-rotated
#         log file.
def setup_logger():
    logger = logging.getLogger("MatrixLogger")
    logger.setLevel(logging.DEBUG)
    formatter = DeviceClockFormatter('[%(asctime)s] %(message)s')

    file_handler = TimedRotatingFileHandler(
        settings.LOG_FILE,
        when="midnight",
        backupCount=14,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    memory_handler.setFormatter(formatter)
    logger.addHandler(memory_handler)

    return logger

log = setup_logger()

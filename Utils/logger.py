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

## @brief Sets up the application logger with a size-unbounded but time-rotated
#         log file
def setup_logger():
    logger = logging.getLogger("MatrixLogger")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%H:%M:%S')

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

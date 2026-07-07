import json
import logging
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import Any, Dict

class JSONFormatter(logging.Formatter):
    """
    Custom JSON formatter for structured logging.
    Formats logs into JSON objects suitable for aggregation and analytics.
    """
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "process_id": record.process,
            "thread_name": record.threadName
        }

        # Include traceback info if an exception was caught
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Include extra attributes supplied via extra={}
        extra_attrs = {k: v for k, v in record.__dict__.items() if k not in {
            'args', 'asctime', 'created', 'exc_info', 'exc_text', 'filename',
            'funcName', 'levelname', 'levelno', 'lineno', 'module', 'msecs',
            'msg', 'name', 'pathname', 'process', 'processName', 'relativeCreated',
            'stack_info', 'thread', 'threadName'
        }}
        if extra_attrs:
            log_data["extra"] = extra_attrs

        return json.dumps(log_data)

def setup_logging(log_level: str = "INFO") -> None:
    """Configures the root logger with standard and JSON formatted outputs."""
    root_logger = logging.getLogger()
    
    # Clean up existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Console Handler for human-readable output (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s:%(filename)s:%(lineno)d] - %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root_logger.addHandler(console_handler)

    # File Handler for structured JSON logs
    try:
        json_file_handler = RotatingFileHandler(
            "app.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        json_file_formatter = JSONFormatter()
        json_file_handler.setFormatter(json_file_formatter)
        json_file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        root_logger.addHandler(json_file_handler)
    except Exception as e:
        print(f"Failed to initialize JSON file logging: {e}", file=sys.stderr)

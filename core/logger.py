import logging
import logging.handlers
import json
import os
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Formatter that outputs JSON strings after parsing the LogRecord."""
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "lineNo": record.lineno,
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        
        # Add any extra attributes passed to the logger
        for key, value in record.__dict__.items():
            if key not in ["args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName", "levelname", "levelno", "lineno", "module", "msecs", "message", "msg", "name", "pathname", "process", "processName", "relativeCreated", "stack_info", "thread", "threadName", "taskName"]:
                # Ensure it's JSON serializable, fallback to string
                try:
                    json.dumps(value)
                    log_obj[key] = value
                except TypeError:
                    log_obj[key] = str(value)
                    
        return json.dumps(log_obj)


def get_logger(name: str = "tpems") -> logging.Logger:
    """Configures and returns a JSON logger that outputs to stdout and a file."""
    logger = logging.getLogger(name)
    
    # Only configure if not already configured
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = JSONFormatter()

        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File Handler (rotating, max 5MB, keep 5 backups)
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        file_handler = logging.handlers.RotatingFileHandler(
            os.path.join(log_dir, "tpems.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=5
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Prevent propagation to the root logger to avoid duplicate logs in some environments
        logger.propagate = False

    return logger


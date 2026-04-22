"""Logging configuration and utilities."""

import json
import logging
import logging.config
import sys
from typing import Any

from pythonjsonlogger import jsonlogger

from ai_devops_assistant.config.settings import settings


class CustomJsonFormatter(jsonlogger.JsonFormatter):
    """Custom JSON formatter with additional fields."""

    def add_fields(
        self,
        log_record: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        """Add custom fields to log record."""
        super().add_fields(log_record, record, message_dict)
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["timestamp"] = self.formatTime(record)


def setup_logging() -> None:
    """Configure application logging."""
    if settings.LOG_FORMAT == "json":
        setup_json_logging()
    else:
        setup_text_logging()


def setup_json_logging() -> None:
    """Configure JSON structured logging."""
    formatter = CustomJsonFormatter(
        "%(timestamp)s %(level)s %(logger)s %(message)s"
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL))
    root_logger.addHandler(handler)


def setup_text_logging() -> None:
    """Configure text/human-readable logging."""
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, settings.LOG_LEVEL))
    root_logger.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)


# Configure logging on import
setup_logging()

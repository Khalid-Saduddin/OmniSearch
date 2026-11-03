"""Centralized logging configuration for OmniSearch backend."""

import logging
import sys


def setup_logging(log_level: str = "INFO") -> None:
    """Configure standardized logging formatting across the application.

    Args:
        log_level: String log level name, e.g. DEBUG, INFO, WARNING, ERROR.
    """
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    log_format = "%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    # Configure root logger
    logging.basicConfig(
        level=numeric_level,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
        force=True,
    )

    # Set specific third-party loggers to a reasonable level
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(numeric_level)


def get_logger(name: str) -> logging.Logger:
    """Return a logger configured for the specified module namespace.

    Args:
        name: Typically __name__ of the calling module.
    """
    return logging.getLogger(name)


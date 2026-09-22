"""Logging setup shared by the application and its modules."""

import logging
from pathlib import Path


def configure_logging() -> None:
    """Configure console and rotating file logging once at startup."""
    logs_directory = Path("logs")
    logs_directory.mkdir(exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = logging.FileHandler(logs_directory / "odinus.log", encoding="utf-8")
    file_handler.setFormatter(formatter)

    logging.basicConfig(level=logging.INFO, handlers=[console_handler, file_handler])

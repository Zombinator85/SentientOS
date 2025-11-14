"""Logging helper for the persona heartbeat."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from logging_config import get_log_dir

_PERSONA_LOGGER_NAME = "sentientos.persona"
_PERSONA_LOG_FILE = "persona.log"


def _resolve_log_path() -> Path:
    if os.name == "nt":
        base = Path("C:/SentientOS/logs")
        base.mkdir(parents=True, exist_ok=True)
        return base / _PERSONA_LOG_FILE
    log_dir = get_log_dir()
    return log_dir / _PERSONA_LOG_FILE


def get_persona_logger() -> logging.Logger:
    """Return the configured persona logger."""

    logger = logging.getLogger(_PERSONA_LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    log_path = _resolve_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger

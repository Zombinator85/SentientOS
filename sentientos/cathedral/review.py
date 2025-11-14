"""Deterministic Cathedral review pipeline."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

from .amendment import Amendment, amendment_digest
from .invariants import evaluate_invariants
from .quarantine import quarantine_amendment
from .validator import validate_amendment

__all__ = [
    "ReviewResult",
    "review_amendment",
]

_DEFAULT_LOG_PATH = Path("runtime") / "logs" / "cathedral_review.log"


@dataclass(frozen=True)
class ReviewResult:
    status: Literal["accepted", "quarantined", "rejected"]
    invariant_errors: List[str]
    validation_errors: List[str]
    quarantine_path: Optional[str] = None


def _resolve_log_path() -> Path:
    override = os.getenv("SENTIENTOS_CATHEDRAL_REVIEW_LOG")
    if override:
        return Path(override)
    return _DEFAULT_LOG_PATH


def _handler_targets(path: Path, handler: logging.Handler) -> bool:
    if not isinstance(handler, logging.FileHandler):
        return False
    handler_path = Path(getattr(handler, "baseFilename", ""))
    return handler_path == path


def _get_logger() -> logging.Logger:
    path = _resolve_log_path()
    logger = logging.getLogger("sentientos.cathedral.review")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(_handler_targets(path, handler) for handler in logger.handlers):
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    return logger


def review_amendment(amendment: Amendment) -> ReviewResult:
    """Run the amendment through validation and invariant checks."""

    validation_errors = validate_amendment(amendment)
    invariant_errors: List[str] = []
    status: Literal["accepted", "quarantined", "rejected"] = "accepted"
    quarantine_path: Optional[str] = None

    if validation_errors:
        status = "quarantined"
    else:
        invariant_errors = evaluate_invariants(amendment)
        if invariant_errors:
            status = "quarantined"

    combined_errors: List[str] = []
    if status == "quarantined":
        combined_errors = list(dict.fromkeys(validation_errors + invariant_errors))
        if not combined_errors:
            combined_errors = ["Quarantined pending manual review"]
        quarantine_path = quarantine_amendment(amendment, combined_errors)

    digest_value = amendment_digest(amendment)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "amendment_id": amendment.id,
        "status": status,
        "digest": digest_value,
        "validation_errors": validation_errors,
        "invariant_errors": invariant_errors,
    }
    if quarantine_path:
        entry["quarantine_path"] = quarantine_path

    logger = _get_logger()
    logger.info(json.dumps(entry, sort_keys=True))

    return ReviewResult(
        status=status,
        invariant_errors=invariant_errors,
        validation_errors=validation_errors,
        quarantine_path=quarantine_path,
    )

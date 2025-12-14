from __future__ import annotations

from pathlib import Path

from logging_config import get_log_path
from log_utils import append_json

from doctrine_digest import compute_doctrine_digest


DOCTRINE_DIGEST_LOG = get_log_path("doctrine_digest.jsonl", "DOCTRINE_DIGEST_LOG")
_CANONICAL_DOCTRINE_PATH = Path(__file__).resolve().parent / "DOCTRINE.md"
_DOCTRINE_DIGEST_CACHE: dict[Path, str] = {}


def reset_doctrine_digest_cache() -> None:
    _DOCTRINE_DIGEST_CACHE.clear()


def record_doctrine_digest(path: Path | None = None) -> str:
    target = (path or _CANONICAL_DOCTRINE_PATH).resolve()
    if target not in _DOCTRINE_DIGEST_CACHE:
        digest = compute_doctrine_digest(target)
        append_json(
            DOCTRINE_DIGEST_LOG,
            {
                "event": "DOCTRINE_DIGEST_COMPUTED",
                "digest": digest,
                "path": str(target),
            },
        )
        _DOCTRINE_DIGEST_CACHE[target] = digest
    return _DOCTRINE_DIGEST_CACHE[target]


def doctrine_digest_status(
    expected_digest: str | None = None, *, path: Path | None = None
) -> tuple[bool, bool | None]:
    digest = record_doctrine_digest(path)
    present = bool(digest)
    match = None if expected_digest is None else digest == expected_digest
    return present, match


def doctrine_digest_observer(
    *, expected_digest: str | None = None, path: Path | None = None
) -> dict[str, bool | None]:
    present, match = doctrine_digest_status(expected_digest, path=path)
    return {
        "doctrine_digest_present": present,
        "doctrine_digest_match": match,
    }


__all__ = [
    "DOCTRINE_DIGEST_LOG",
    "doctrine_digest_observer",
    "doctrine_digest_status",
    "record_doctrine_digest",
    "reset_doctrine_digest_cache",
]

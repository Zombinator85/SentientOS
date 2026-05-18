from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable, Sequence

BASELINE_PATH = Path("vow/mypy_baseline.json")
DEFAULT_MYPY_COMMAND = (
    "python",
    "-m",
    "mypy",
    "--hide-error-context",
    "--no-color-output",
    "--show-column-numbers",
    "--show-error-codes",
    "scripts/",
    "sentientos/",
)
STABLE_GENERATED_AT = "stable-baseline-refresh"
SCHEMA_VERSION = 1
STATUS_CLEAN = "mypy_baseline_clean"
STATUS_MATCHES = "mypy_baseline_matches_existing_debt"
STATUS_REGRESSION = "mypy_baseline_regression_detected"
STATUS_IMPROVED = "mypy_baseline_improved"
STATUS_MISSING = "mypy_baseline_missing"
STATUS_INVALID = "mypy_baseline_invalid"

_ERROR_RE = re.compile(
    r"^(?P<path>[^:\n]+):(?P<line>\d+)"
    r"(?::(?P<column>\d+))?:\s+"
    r"(?P<severity>error|note):\s+"
    r"(?P<message>.+?)"
    r"(?:\s+\[(?P<code>[^\]]+)\])?$"
)
_NON_POSITION_ERROR_RE = re.compile(
    r"^(?P<path>[^:\n]+):\s+"
    r"(?P<severity>error|note):\s+"
    r"(?P<message>.+?)"
    r"(?:\s+\[(?P<code>[^\]]+)\])?$"
)


@dataclass(frozen=True, order=True)
class MypyErrorRecord:
    path: str
    line: int | None
    column: int | None
    code: str | None
    message: str

    def to_json(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "line": self.line,
            "column": self.column,
            "code": self.code,
            "message": self.message,
        }

    @classmethod
    def from_json(cls, payload: Any) -> "MypyErrorRecord":
        if not isinstance(payload, dict):
            raise ValueError("error record must be an object")
        path = payload.get("path")
        message = payload.get("message")
        if not isinstance(path, str) or not path:
            raise ValueError("error record path must be a non-empty string")
        if not isinstance(message, str) or not message:
            raise ValueError("error record message must be a non-empty string")
        return cls(
            path=normalize_path(path),
            line=_optional_int(payload.get("line")),
            column=_optional_int(payload.get("column")),
            code=_optional_str(payload.get("code")),
            message=normalize_message(message),
        )


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("optional integer field must be an integer or null")
    return value


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("optional string field must be a string or null")
    return value or None


def normalize_path(path: str) -> str:
    normalized = path.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def normalize_message(message: str) -> str:
    return " ".join(message.strip().split())


def parse_mypy_output(output: str) -> list[MypyErrorRecord]:
    records: list[MypyErrorRecord] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        match = _ERROR_RE.match(line) or _NON_POSITION_ERROR_RE.match(line)
        if match is None or match.group("severity") != "error":
            continue
        raw_line_number = match.groupdict().get("line")
        raw_column = match.groupdict().get("column")
        records.append(
            MypyErrorRecord(
                path=normalize_path(match.group("path")),
                line=int(raw_line_number) if raw_line_number is not None else None,
                column=int(raw_column) if raw_column is not None else None,
                code=match.group("code") or None,
                message=normalize_message(match.group("message")),
            )
        )
    return normalize_records(records)


def normalize_records(records: Iterable[MypyErrorRecord]) -> list[MypyErrorRecord]:
    return sorted(records, key=lambda record: (record.path, record.line or -1, record.column or -1, record.code or "", record.message))


def records_digest(records: Iterable[MypyErrorRecord]) -> str:
    payload = [record.to_json() for record in normalize_records(records)]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_manifest(*, records: Sequence[MypyErrorRecord], mypy_command: Sequence[str], mypy_version: str | None) -> dict[str, Any]:
    normalized = normalize_records(records)
    per_file = Counter(record.path for record in normalized)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": STABLE_GENERATED_AT,
        "generator": "scripts.build_mypy_baseline",
        "mypy_command": list(mypy_command),
        "mypy_version": mypy_version or "unknown",
        "total_error_count": len(normalized),
        "affected_file_count": len(per_file),
        "per_file_counts": {path: per_file[path] for path in sorted(per_file)},
        "digest": records_digest(normalized),
        "errors": [record.to_json() for record in normalized],
    }


def manifest_to_text(manifest: dict[str, Any]) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"baseline not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"baseline is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("baseline manifest must be a JSON object")
    validate_manifest(payload)
    return payload


def manifest_records(manifest: dict[str, Any]) -> list[MypyErrorRecord]:
    errors = manifest.get("errors")
    if not isinstance(errors, list):
        raise ValueError("baseline errors must be a list")
    return normalize_records(MypyErrorRecord.from_json(error) for error in errors)


def validate_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported mypy baseline schema_version")
    records = manifest_records(manifest)
    expected_digest = records_digest(records)
    if manifest.get("digest") != expected_digest:
        raise ValueError("baseline digest does not match normalized error records")
    if manifest.get("total_error_count") != len(records):
        raise ValueError("baseline total_error_count does not match errors")
    affected = len({record.path for record in records})
    if manifest.get("affected_file_count") != affected:
        raise ValueError("baseline affected_file_count does not match errors")
    per_file_counts = Counter(record.path for record in records)
    expected_counts = {path: per_file_counts[path] for path in sorted(per_file_counts)}
    if manifest.get("per_file_counts") != expected_counts:
        raise ValueError("baseline per_file_counts does not match errors")


def compare_records(*, baseline_records: Sequence[MypyErrorRecord], current_records: Sequence[MypyErrorRecord]) -> dict[str, Any]:
    baseline = Counter(normalize_records(baseline_records))
    current = Counter(normalize_records(current_records))
    matched_count = sum((baseline & current).values())
    new_counter = current - baseline
    retired_counter = baseline - current
    new_records = list(new_counter.elements())
    retired_records = list(retired_counter.elements())
    baseline_paths = {record.path for record in baseline}
    affected_new_files = sorted({record.path for record in new_records if record.path not in baseline_paths})
    status = _status_for(matched_count=matched_count, new_records=new_records, retired_records=retired_records, current_records=current_records)
    return {
        "status": status,
        "matched_existing_errors": matched_count,
        "new_errors": len(new_records),
        "retired_errors": len(retired_records),
        "affected_new_files": affected_new_files,
        "current_error_count": len(current_records),
        "baseline_error_count": len(baseline_records),
        "new_error_records": [record.to_json() for record in normalize_records(new_records)[:50]],
        "retired_error_records": [record.to_json() for record in normalize_records(retired_records)[:50]],
    }


def _status_for(*, matched_count: int, new_records: Sequence[MypyErrorRecord], retired_records: Sequence[MypyErrorRecord], current_records: Sequence[MypyErrorRecord]) -> str:
    if new_records:
        return STATUS_REGRESSION
    if retired_records:
        return STATUS_IMPROVED
    if not current_records and matched_count == 0:
        return STATUS_CLEAN
    return STATUS_MATCHES

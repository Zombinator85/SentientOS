"""Failure harvesting and clustering utilities for forge remediation."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

MAX_EXCERPT_CHARS = 8000


@dataclass(slots=True)
class FailureSignature:
    nodeid: str
    file: str
    line: int | None
    test_name: str
    error_type: str
    message_digest: str


@dataclass(slots=True)
class FailureCluster:
    signature: FailureSignature
    count: int
    examples: list[str]


@dataclass(slots=True)
class HarvestResult:
    total_failed: int
    clusters: list[FailureCluster]
    raw_excerpt_truncated: str


def harvest_failures(stdout: str, stderr: str = "") -> HarvestResult:
    raw = f"{stdout}\n{stderr}".strip()
    lines = raw.splitlines()
    records = _parse_pytest_blocks(lines)
    if not records:
        records = _parse_run_tests_blocks(lines)

    if not records:
        failed = _parse_failed_count(raw)
        return HarvestResult(total_failed=failed, clusters=[], raw_excerpt_truncated=_truncate(raw))

    clusters_by_key: dict[tuple[str, str, int | None, str, str, str], FailureCluster] = {}
    for rec in records:
        digest = _digest(rec["message"])
        sig = FailureSignature(
            nodeid=rec["nodeid"],
            file=rec["file"],
            line=rec["line"],
            test_name=rec["test_name"],
            error_type=rec["error_type"],
            message_digest=digest,
        )
        key = (sig.nodeid, sig.file, sig.line, sig.test_name, sig.error_type, sig.message_digest)
        if key not in clusters_by_key:
            clusters_by_key[key] = FailureCluster(signature=sig, count=0, examples=[])
        clusters_by_key[key].count += 1
        if len(clusters_by_key[key].examples) < 3:
            clusters_by_key[key].examples.append(rec["message"])

    return HarvestResult(
        total_failed=len(records),
        clusters=list(clusters_by_key.values()),
        raw_excerpt_truncated=_truncate(raw),
    )


def _parse_pytest_blocks(lines: list[str]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("FAILED "):
            failed_line = line
            message_lines: list[str] = []
            j = i + 1
            while j < len(lines):
                probe = lines[j].strip()
                if not probe:
                    j += 1
                    continue
                if probe.startswith("FAILED ") or probe.startswith("="):
                    break
                message_lines.append(probe)
                j += 1
            nodeid, error_type, message = _parse_failed_line(failed_line)
            if message_lines:
                message = " | ".join(message_lines)
            file_path, line_no, test_name = _split_nodeid(nodeid)
            records.append(
                {
                    "nodeid": nodeid,
                    "file": file_path,
                    "line": line_no,
                    "test_name": test_name,
                    "error_type": error_type,
                    "message": message,
                }
            )
            i = j
            continue

        match = re.match(r"([^\s:][^:]*)::([^:]+):\s*([A-Za-z_][A-Za-z0-9_]*):\s*(.+)", line)
        if match:
            file_path = match.group(1)
            test_name = match.group(2)
            error_type = match.group(3)
            message = match.group(4)
            nodeid = f"{file_path}::{test_name}"
            records.append(
                {
                    "nodeid": nodeid,
                    "file": file_path,
                    "line": None,
                    "test_name": test_name,
                    "error_type": error_type,
                    "message": message,
                }
            )
        i += 1
    return records


def _parse_run_tests_blocks(lines: list[str]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    pat = re.compile(r"E\s+(?P<etype>[A-Za-z_][A-Za-z0-9_]*):\s*(?P<message>.+)")
    for i, line in enumerate(lines):
        line_s = line.strip()
        match = pat.match(line_s)
        if not match:
            continue
        file_path = ""
        line_no: int | None = None
        test_name = "unknown"
        nodeid = "unknown"
        for k in range(max(0, i - 6), i):
            m = re.search(r"([\w./\\-]+\.py):(\d+):\s+in\s+([\w_]+)", lines[k])
            if m:
                file_path = m.group(1)
                line_no = int(m.group(2))
                test_name = m.group(3)
                nodeid = f"{file_path}::{test_name}"
        records.append(
            {
                "nodeid": nodeid,
                "file": file_path,
                "line": line_no,
                "test_name": test_name,
                "error_type": match.group("etype"),
                "message": match.group("message"),
            }
        )
    return records


def _parse_failed_line(line: str) -> tuple[str, str, str]:
    rest = line.removeprefix("FAILED ").strip()
    if " - " not in rest:
        return rest, "AssertionError", "failure"
    nodeid, rhs = rest.split(" - ", 1)
    if ": " in rhs:
        error_type, message = rhs.split(": ", 1)
        return nodeid.strip(), error_type.strip(), message.strip()
    return nodeid.strip(), "AssertionError", rhs.strip()


def _split_nodeid(nodeid: str) -> tuple[str, int | None, str]:
    base = nodeid.split("::")
    file_path = base[0] if base else ""
    line_no: int | None = None
    test_name = base[-1] if len(base) > 1 else "unknown"
    file_match = re.match(r"(?P<file>.*\.py):(?P<line>\d+)$", file_path)
    if file_match:
        file_path = file_match.group("file")
        line_no = int(file_match.group("line"))
    return file_path, line_no, test_name


def _parse_failed_count(output: str) -> int:
    for line in output.splitlines():
        compact = line.strip()
        summary = re.search(r"(\d+)\s+failed", compact)
        if summary:
            return int(summary.group(1))
    return 0


def _digest(message: str) -> str:
    normalized = re.sub(r"\s+", " ", message.strip())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _truncate(raw: str) -> str:
    if len(raw) <= MAX_EXCERPT_CHARS:
        return raw
    return raw[:MAX_EXCERPT_CHARS] + "\n...[truncated]"

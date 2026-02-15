from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

DEFAULT_RUN_DIR = Path("glow/test_runs")
DEFAULT_JUNITXML_PATH = DEFAULT_RUN_DIR / "pytest_junitxml.xml"
DEFAULT_DIGEST_PATH = DEFAULT_RUN_DIR / "test_failure_digest.json"
DEFAULT_MESSAGE_LINES = 3


@dataclass(frozen=True)
class FailureCase:
    nodeid: str
    exception_type: str
    message_lines: tuple[str, ...]
    file: str | None
    line: int | None


@dataclass(frozen=True)
class FailureGroup:
    signature: str
    nodeid: str
    exception_type: str
    message_lines: tuple[str, ...]
    count: int
    file: str | None
    line: int | None


def _coerce_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _nodeid_from_case(testcase: ElementTree.Element) -> str:
    classname = (testcase.get("classname") or "").strip()
    name = (testcase.get("name") or "").strip()
    if classname and name:
        return f"{classname}::{name}"
    if name:
        return name
    return classname or "<unknown>"


def _message_lines(raw: str | None, max_lines: int) -> tuple[str, ...]:
    if not raw:
        return ()
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    return tuple(lines[:max_lines])


def _extract_failures(junitxml_path: Path, *, max_message_lines: int) -> list[FailureCase]:
    tree = ElementTree.parse(junitxml_path)
    failures: list[FailureCase] = []
    for testcase in tree.findall(".//testcase"):
        for tag in ("failure", "error"):
            for event in testcase.findall(tag):
                nodeid = _nodeid_from_case(testcase)
                exception_type = (event.get("type") or tag).strip() or tag
                message = event.get("message")
                if not message:
                    message = event.text or ""
                failures.append(
                    FailureCase(
                        nodeid=nodeid,
                        exception_type=exception_type,
                        message_lines=_message_lines(message, max_message_lines),
                        file=(testcase.get("file") or None),
                        line=_coerce_int(testcase.get("line")),
                    )
                )
    return failures


def _group_failures(failures: list[FailureCase]) -> list[FailureGroup]:
    grouped: dict[tuple[str, str, tuple[str, ...]], list[FailureCase]] = {}
    for failure in failures:
        key = (failure.nodeid, failure.exception_type, failure.message_lines)
        grouped.setdefault(key, []).append(failure)

    groups: list[FailureGroup] = []
    for (nodeid, exception_type, message_lines), members in grouped.items():
        first = members[0]
        signature = "|".join([nodeid, exception_type, "\\n".join(message_lines)])
        groups.append(
            FailureGroup(
                signature=signature,
                nodeid=nodeid,
                exception_type=exception_type,
                message_lines=message_lines,
                count=len(members),
                file=first.file,
                line=first.line,
            )
        )

    return sorted(groups, key=lambda group: (-group.count, group.signature, group.nodeid))


def generate_failure_digest(
    *,
    junitxml_path: Path,
    output_path: Path,
    run_provenance_hash: str,
    max_message_lines: int = DEFAULT_MESSAGE_LINES,
) -> dict[str, Any]:
    failures = _extract_failures(junitxml_path, max_message_lines=max_message_lines)
    groups = _group_failures(failures)

    payload: dict[str, Any] = {
        "schema_version": 1,
        "run_provenance_hash": run_provenance_hash,
        "junitxml_path": str(junitxml_path),
        "failure_groups": [
            {
                "count": group.count,
                "signature": group.signature,
                "exception_type": group.exception_type,
                "example_nodeid": group.nodeid,
                "short_message": "\n".join(group.message_lines),
                "file": group.file,
                "line": group.line,
                "rerun_command": f"python -m scripts.run_tests -q {group.nodeid}",
            }
            for group in groups
        ],
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _print_summary(payload: dict[str, Any], *, limit: int = 5) -> None:
    groups = payload.get("failure_groups")
    if not isinstance(groups, list) or not groups:
        print("No failure groups found in structured report.")
        return

    print(f"Top {min(limit, len(groups))} failure groups:")
    for index, group in enumerate(groups[:limit], start=1):
        if not isinstance(group, dict):
            continue
        count = group.get("count")
        exception_type = group.get("exception_type")
        nodeid = group.get("example_nodeid")
        short_message = group.get("short_message", "")
        first_line = short_message.splitlines()[0] if isinstance(short_message, str) and short_message else ""
        print(f"{index}. count={count} type={exception_type} nodeid={nodeid} message={first_line}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate a deterministic digest for pytest failures.")
    parser.add_argument("--junitxml", type=Path, default=DEFAULT_JUNITXML_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_DIGEST_PATH)
    parser.add_argument("--run-provenance-hash", default="unknown")
    parser.add_argument("--message-lines", type=int, default=DEFAULT_MESSAGE_LINES)
    args = parser.parse_args(argv)

    if args.message_lines <= 0:
        raise SystemExit("--message-lines must be > 0")
    if not args.junitxml.exists():
        raise SystemExit(f"junitxml report not found: {args.junitxml}")

    payload = generate_failure_digest(
        junitxml_path=args.junitxml,
        output_path=args.output,
        run_provenance_hash=args.run_provenance_hash,
        max_message_lines=args.message_lines,
    )
    _print_summary(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

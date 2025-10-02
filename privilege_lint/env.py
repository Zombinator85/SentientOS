from __future__ import annotations

import argparse
import json

from ._env import (
    HAS_NODE,
    HAS_GO,
    HAS_DMYPY,
    HAS_PYESPRIMA,
    NODE,
    GO,
    DMYPY,
    PYESPRIMA,
)


def env_status() -> dict[str, dict[str, object]]:
    return {
        "node": {"available": HAS_NODE, "info": NODE.info},
        "go": {"available": HAS_GO, "info": GO.info},
        "dmypy": {"available": HAS_DMYPY, "info": DMYPY.info},
        "pyesprima": {"available": HAS_PYESPRIMA, "info": PYESPRIMA.info},
    }


def report(format: str = "text") -> str:
    if format == "text":
        return report_text()
    if format == "json":
        return report_json()
    raise ValueError(f"unsupported report format: {format}")


def report_text() -> str:
    lines = ["Capability    Status  Info", "-----------    ------  --------------------"]
    for name, caps in env_status().items():
        check = "\u2714\ufe0f" if caps["available"] else "\u274c"
        desc = caps["info"] if caps["available"] else "MISSING"
        lines.append(f"{name:<12} {check:<6} {desc}")
    return "\n".join(lines)


def report_json() -> str:
    return json.dumps(env_status(), indent=2)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", default="report")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--json", action="store_const", const="json", dest="format")
    args = parser.parse_args(argv)

    if args.command != "report":
        parser.error("only 'report' command supported")

    if args.format == "json":
        print(report_json())
    else:
        print(report_text())


if __name__ == "__main__":  # pragma: no cover
    main()

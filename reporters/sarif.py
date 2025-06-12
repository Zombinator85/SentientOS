from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"


def build_sarif(messages: List[str]) -> dict[str, Any]:
    results = []
    for msg in messages:
        try:
            file_part, rest = msg.split(":", 1)
            line_part, text = rest.strip().split(" ", 1)
            line = int(line_part)
        except Exception:
            file_part, line, text = "unknown", 1, msg
        results.append(
            {
                "ruleId": "privilege-lint",
                "message": {"text": text},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": file_part},
                            "region": {"startLine": line},
                        }
                    }
                ],
            }
        )
    return {
        "$schema": SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {"driver": {"name": "privilege-lint"}},
                "results": results,
            }
        ],
    }


def write_sarif(messages: List[str], path: Path) -> None:
    sarif = build_sarif(messages)
    path.write_text(json.dumps(sarif, indent=2), encoding="utf-8")

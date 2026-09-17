from __future__ import annotations

import ast
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/development/effect_authority_archaeology.json"


def _symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            found.add(node.name)
            if isinstance(node, ast.ClassDef):
                found.update(
                    f"{node.name}.{child.name}"
                    for child in node.body
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                )
    return found


def test_effect_authority_archaeology_is_descriptive_and_resolves_symbols() -> None:
    payload = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert payload["authority"] == "none"
    assert payload["runtime_consumers"] == []
    assert payload["artifact_kind"] == "descriptive_effect_authority_archaeology"
    assert json.dumps(payload, indent=2, sort_keys=True) + "\n" == EVIDENCE.read_text(encoding="utf-8")
    for surface in payload["surfaces"]:
        path = ROOT / surface["path"]
        assert path.is_file()
        assert set(surface["symbols"]) <= _symbols(path)


def test_archaeology_artifact_has_no_python_consumer() -> None:
    needle = EVIDENCE.name
    consumers = []
    for path in ROOT.rglob("*.py"):
        if path == Path(__file__):
            continue
        if needle in path.read_text(encoding="utf-8", errors="ignore"):
            consumers.append(path.relative_to(ROOT).as_posix())
    assert consumers == []

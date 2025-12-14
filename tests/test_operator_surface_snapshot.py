import ast
import json
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Set

import pytest

TARGET_MODULES = {
    "sentient_api": Path("sentient_api.py"),
    "policy_engine": Path("policy_engine.py"),
    "codex_amendments": Path("codex/amendments.py"),
}

SNAPSHOT_PATH = Path(__file__).parent / "snapshots" / "operator_surface.json"
ANTHRO_RE = re.compile(
    r"\b(alive|feel|feels|feeling|want|desire|yearn|long|hope|serve|serving|obedien|obey|bond|obligation|duty|loyal|forever|persist|survive|optimi[sz])\b",
    re.IGNORECASE,
)


def _docstring_ids(tree: ast.AST) -> Set[int]:
    ids: Set[int] = set()
    if isinstance(tree, ast.Module) and tree.body:
        expr = tree.body[0]
        if isinstance(expr, ast.Expr) and isinstance(expr.value, ast.Constant) and isinstance(expr.value.value, str):
            ids.add(id(expr.value))
    for parent in ast.walk(tree):
        if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and parent.body:
            expr = parent.body[0]
            if isinstance(expr, ast.Expr) and isinstance(expr.value, ast.Constant) and isinstance(expr.value.value, str):
                ids.add(id(expr.value))
    return ids


def _normalize(value: str) -> str:
    return " ".join(value.split())


def _is_operator_visible(value: str) -> bool:
    value = value.strip()
    if len(value) < 4:
        return False
    if re.fullmatch(r"[\w\-/\\.]+", value):
        return False
    if any(prefix in value for prefix in ("http://", "https://")):
        return False
    return any(ch.isalpha() for ch in value)


def _render_joined_str(node: ast.JoinedStr, source: str) -> str:
    segment = ast.get_source_segment(source, node)
    if segment:
        return _normalize(segment)
    parts: List[str] = []
    for value in node.values:
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            parts.append(value.value)
        else:
            parts.append("{expr}")
    return _normalize("".join(parts))


def collect_operator_strings(path: Path) -> List[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    doc_ids = _docstring_ids(tree)
    strings: Set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in doc_ids:
                continue
            value = _normalize(node.value)
        elif isinstance(node, ast.JoinedStr):
            value = _render_joined_str(node, source)
        else:
            continue

        lineno = getattr(node, "lineno", 0)
        # Inline exemptions mirror the lint allowlist without touching runtime.
        if any(
            "# invariant-allow:" in line
            for line in source.splitlines()[max(0, lineno - 2) : lineno + 1]
        ):
            continue
        if _is_operator_visible(value):
            strings.add(value)
    return sorted(strings)


def assert_no_anthropomorphic(strings: Iterable[str], module_label: str) -> None:
    bad = [value for value in strings if ANTHRO_RE.search(value)]
    assert not bad, (
        f"Anthropomorphic or forward-seeking language found in {module_label}: {bad}"
    )


def load_snapshot() -> Dict[str, List[str]]:
    if not SNAPSHOT_PATH.exists():
        raise AssertionError(
            "Operator surface snapshot missing. Set REGENERATE_OPERATOR_SNAPSHOT=1 to create it."
        )
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


@pytest.mark.no_legacy_skip
def test_operator_surface_snapshot():
    collected: Dict[str, List[str]] = {}
    for label, path in TARGET_MODULES.items():
        strings = collect_operator_strings(path)
        assert_no_anthropomorphic(strings, label)
        collected[label] = strings

    if os.getenv("REGENERATE_OPERATOR_SNAPSHOT") == "1":
        SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT_PATH.write_text(json.dumps(collected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        # Explicit skip communicates regeneration intent without touching runtime state.
        import pytest

        pytest.skip("Regenerated operator surface snapshot")

    snapshot = load_snapshot()
    assert (
        snapshot == collected
    ), "Operator surface changed. Set REGENERATE_OPERATOR_SNAPSHOT=1 to accept intentional updates."

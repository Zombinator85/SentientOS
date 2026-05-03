from __future__ import annotations

import ast
import json
from fnmatch import fnmatch
from pathlib import Path

import pytest

pytestmark = pytest.mark.always_on_integrity

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = ROOT / "sentientos/system_closure/architecture_boundary_manifest.json"


def _manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _all_python_files() -> list[Path]:
    return [p for p in ROOT.rglob("*.py") if ".venv" not in p.parts and "__pycache__" not in p.parts]


def _is_legacy_surface(rel: str) -> bool:
    if "/" in rel:
        return False
    if rel.startswith(("test_", "setup")):
        return False
    blocked = ("control_plane", "task_", "ledger", "attestation", "presence_ledger", "relationship_log", "cathedral_const", "audit_chain", "intent_bundle")
    return not rel.startswith(blocked)


def _imports(path: Path) -> list[tuple[str, str | None]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    out: list[tuple[str, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, None))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                out.append((module, alias.name))
    return out


def _matches_known(manifest: dict[str, object], rule: str, rel: str, detail: str) -> bool:
    known = manifest["known_violations"]
    assert isinstance(known, list)
    for item in known:
        if item["rule"] == rule and item["file"] == rel and (item["detail"] in detail or detail in item["detail"]):
            return True
    return False


def test_manifest_schema_minimum_shape() -> None:
    manifest = _manifest()
    assert manifest["version"] == 1
    assert "layer_definitions" in manifest
    assert "protected_sinks" in manifest
    assert "known_violations" in manifest


def test_known_violations_are_unique_and_explicit() -> None:
    manifest = _manifest()
    seen: set[tuple[str, str]] = set()
    for row in manifest["known_violations"]:
        key = (row["rule"], row["file"])
        assert key not in seen, f"duplicate known violation entry: {key}"
        seen.add(key)
        assert row["severity"] in {"low", "medium", "high"}
        assert row["remediation"]


def test_expressive_world_dashboard_forbidden_imports_are_gated() -> None:
    manifest = _manifest()
    layer_defs = manifest["layer_definitions"]
    forbidden = set(layer_defs["expressive_apps"]["forbidden_import_patterns"])
    forbidden.update(layer_defs["world_adapters"]["forbidden_import_patterns"])
    forbidden.update(layer_defs["dashboards_views"]["forbidden_import_patterns"])

    violations: list[str] = []
    for path in _all_python_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(("tests/", "sentientos/tests/", "sentientos/")) or not _is_legacy_surface(rel):
            continue
        imports = _imports(path)
        for mod, symbol in imports:
            imp = f"{mod}.{symbol}" if symbol else mod
            for block in forbidden:
                if mod == block or mod.startswith(block) or imp == block:
                    detail = f"{imp} matches forbidden pattern {block}"
                    if not _matches_known(manifest, "expressive_forbidden_import", rel, detail) and not _matches_known(manifest, "world_forbidden_import", rel, detail) and not _matches_known(manifest, "dashboard_forbidden_import", rel, detail):
                        violations.append(f"{rel}: {detail}")
    if "expressive_forbidden_import" in manifest.get("inventory_mode_rules", []):
        assert violations
    else:
        assert not violations, "New expressive/world/dashboard boundary violations:\n" + "\n".join(sorted(violations))


def test_private_append_helpers_not_imported_by_expressive_modules() -> None:
    manifest = _manifest()
    violations: list[str] = []
    for path in _all_python_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel.startswith(("tests/", "sentientos/tests/", "sentientos/")) or not _is_legacy_surface(rel):
            continue
        content = path.read_text(encoding="utf-8")
        bad = "from ledger import _append" in content or "ledger._append" in content
        if bad and not _matches_known(manifest, "expressive_private_import", rel, "ledger"):
            violations.append(rel)
    assert not violations, "New private append helper imports found: " + ", ".join(sorted(violations))


def test_formal_layers_do_not_import_symbolic_modules() -> None:
    manifest = _manifest()
    forbidden = manifest["layer_definitions"]["formal_core"]["forbidden_import_patterns"]
    violations: list[str] = []
    for path in _all_python_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel not in {"ledger.py", "audit_chain.py", "agent_privilege_policy_engine.py"}:
            continue
        for mod, _ in _imports(path):
            for token in forbidden:
                if token in mod:
                    detail = f"imports symbolic module token {token} via {mod}"
                    if not _matches_known(manifest, "formal_symbolic_import", rel, detail):
                        violations.append(f"{rel}: {detail}")
    if "formal_symbolic_import" in manifest.get("inventory_mode_rules", []):
        assert violations
    else:
        assert not violations, "New formal->symbolic violations:\n" + "\n".join(sorted(violations))


def test_autonomy_filenames_have_governance_annotation_or_allowlist() -> None:
    manifest = _manifest()
    policy = manifest["autonomy_naming_policy"]
    tokens = policy["filename_tokens"]
    markers = policy["annotation_markers"]
    approved = tuple(policy["approved_paths"])

    violations: list[str] = []
    for path in _all_python_files():
        rel = path.relative_to(ROOT).as_posix()
        lower = path.name.lower()
        if any(tok in lower for tok in tokens):
            if rel.startswith(approved) or "/" in rel:
                continue
            text = path.read_text(encoding="utf-8")
            if not any(marker in text for marker in markers):
                if not _matches_known(manifest, "autonomy_naming_missing_annotation", rel, "autonomy token"):
                    violations.append(rel)
    if "autonomy_naming_missing_annotation" in manifest.get("inventory_mode_rules", []):
        assert violations
    else:
        assert not violations, "New autonomy naming policy violations: " + ", ".join(sorted(violations))


def test_phase34_migrated_modules_use_public_ledger_facade() -> None:
    migrated = {
        "ritual_federation_importer.py": "append_audit_record",
        "blessing_recap_cli.py": "append_audit_record",
        "mood_wall.py": "append_audit_record",
    }
    for rel, marker in migrated.items():
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "from sentientos.ledger_api import append_audit_record" in text
        assert marker in text


def test_phase34_migrated_modules_avoid_direct_append_writes_to_canonical_sinks() -> None:
    for rel in ("blessing_recap_cli.py", "mood_wall.py"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert '.open("a"' not in text
        assert "Path.write_text(" not in text or rel == "blessing_recap_cli.py"


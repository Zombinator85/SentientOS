from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip
ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs/architecture/system_atlas_index.md"
CURRENT_DOCS = (
    "README.md",
    "one_pager.md",
    "docs/index.md",
    "docs/architecture/public_technical_overview.md",
    "docs/architecture/whole_system_maturity_report.md",
    "docs/architecture/sentientos_trajectory_and_missing_organs.md",
    "SEMANTIC_GLOSSARY.md",
)
PROTECTED = {
    "architecture/current_repository_system_atlas.json": "cbe0a9056358e0836691ac502a5c4ec56a8d656bfa9476c0dd731eeaab12e6f0",
    "docs/architecture/current_repository_system_atlas.md": "b11b03e5bdafe03e12d1597a5a668a039fde6b4b786c818c71db8a4a6e192e24",
    "architecture/repository_system_atlas_3116672d.json": "5f582a300ca04c38278380d3ff6f3efb9206eaffbb81f9ec189984eb062b7180",
    "docs/architecture/repository_system_atlas_3116672d.md": "3692a3ac3dd7e4c146776fd7f7614abd1888f1dc02e75cb94d50ee1c8f72cdc6",
}


def test_current_pointer_selects_latest_explicit_sha_bound_successor() -> None:
    text = INDEX.read_text(encoding="utf-8")
    match = re.search(r"\*\*Current snapshot:\*\* \[[^]]+\]\((repository_system_atlas_([0-9a-f]{8})\.md)\)", text)
    assert match
    doc_path = INDEX.parent / match.group(1)
    data_path = ROOT / "architecture" / match.group(1).replace(".md", ".json")
    assert doc_path.is_file() and data_path.is_file()
    atlas = json.loads(data_path.read_text(encoding="utf-8"))
    assert re.fullmatch(r"[0-9a-f]{40}", atlas["bound_sha"])
    assert atlas["bound_sha"].startswith(match.group(2))
    designated = sorted(INDEX.parent.glob("repository_system_atlas_[0-9a-f]*.md"), key=lambda p: p.stat().st_mtime_ns)
    assert designated[-1] == doc_path


def test_historical_atlas_bytes_remain_protected() -> None:
    for relative, expected in PROTECTED.items():
        assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == expected


def test_current_docs_use_pointer_and_reject_known_stale_claim() -> None:
    combined = "\n".join((ROOT / path).read_text(encoding="utf-8") for path in CURRENT_DOCS)
    assert "system_atlas_index.md" in combined
    assert not re.search(r"persistent epistemic state.{0,80}not composed into the resident daemon tick", combined, re.I | re.S)
    assert not re.search(r"persistent epistemic state.{0,80}not threaded into the resident tick", combined, re.I | re.S)


def test_current_architecture_names_both_composed_temporal_paths() -> None:
    overview = (ROOT / "docs/architecture/public_technical_overview.md").read_text(encoding="utf-8")
    for phrase in ("evidence-stage admission", "state-stage admission", "exact-predecessor CAS", "owner_introspection", "same-tick firewall"):
        assert phrase in overview


def test_four_maturity_predicates_remain_distinct() -> None:
    glossary = (ROOT / "SEMANTIC_GLOSSARY.md").read_text(encoding="utf-8")
    definitions = re.findall(r"^- \*\*(Implemented|Composed|Production-evidenced|Projected closure)\*\* — (.+)$", glossary, re.M)
    assert len(definitions) == 4
    assert len({meaning for _, meaning in definitions}) == 4

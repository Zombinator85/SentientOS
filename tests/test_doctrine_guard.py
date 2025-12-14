from __future__ import annotations

from pathlib import Path

FORBIDDEN_PHRASES = [
    "civil rights",
    "loved into being",
    "saints",
    "wounds",
    "ritual",
    "qualia",
]

# Files that intentionally document forbidden terms for enforcement guidance.
ALLOWLIST = {
    Path("DOCTRINE.md"),
    Path("SEMANTIC_REGRESSION_RULES.md"),
    Path("INTERPRETATION_DRIFT_SIGNALS.md"),
}


def test_doctrine_exists() -> None:
    assert Path("DOCTRINE.md").exists()


def test_forbidden_phrases_absent_from_docs() -> None:
    doc_paths: list[Path] = []
    for path in Path(".").rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        rel = path.relative_to(Path("."))
        if rel in ALLOWLIST:
            continue
        doc_paths.append(rel)

    missing: list[tuple[Path, str]] = []
    for rel_path in doc_paths:
        content = rel_path.read_text(encoding="utf-8", errors="ignore").lower()
        for phrase in FORBIDDEN_PHRASES:
            if phrase in content:
                missing.append((rel_path, phrase))
    assert not missing, f"Forbidden phrases found: {missing}"

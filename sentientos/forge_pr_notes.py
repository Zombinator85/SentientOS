"""Helpers for robust, human-readable forge PR narratives."""

from __future__ import annotations


def build_pr_notes(
    diff_stats: dict[str, int],
    touched_paths: list[str],
    key_actions: list[str],
    tests_run: list[str],
    risks: list[str],
) -> str:
    changed = _render_paths(touched_paths)
    actions = _render_list(key_actions, fallback="No explicit action list emitted; see report artifacts.")
    tests = _render_list(tests_run, fallback="No tests recorded.")
    risk_text = _render_list(risks, fallback="No additional risk notes.")

    summary_line = (
        f"Files changed: +{diff_stats.get('files_added', 0)} / "
        f"~{diff_stats.get('files_modified', 0)} / -{diff_stats.get('files_removed', 0)}"
    )

    body = "\n".join(
        [
            "## What changed",
            summary_line,
            changed,
            "",
            "## Key actions",
            actions,
            "",
            "## Gates and tests",
            tests,
            "",
            "## Risks / rollback",
            risk_text,
        ]
    )
    if _is_placeholder(body):
        return "## What changed\nAutomated Forge update with validated artifacts and gate outcomes."
    return body


def _render_paths(paths: list[str]) -> str:
    if not paths:
        return "- No touched paths recorded."
    top_level = sorted({path.split("/", 1)[0] for path in paths})
    return "\n".join(f"- `{item}`" for item in top_level)


def _render_list(items: list[str], *, fallback: str) -> str:
    cleaned = [item.strip() for item in items if item.strip() and not _is_placeholder(item)]
    if not cleaned:
        return f"- {fallback}"
    return "\n".join(f"- {item}" for item in cleaned)


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    if not normalized:
        return True
    placeholders = {
        "placeholder",
        "placeholder pr body",
        "machine-code pr body",
        "todo",
        "tbd",
    }
    return normalized in placeholders

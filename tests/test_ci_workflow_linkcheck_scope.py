from pathlib import Path
from types import SimpleNamespace

import yaml  # type: ignore[import-untyped]
import pytest

from scripts.ci_linkcheck_scope import (
    changed_paths_between,
    main_link_targets_changed,
    strict_main_linkcheck_required,
)


def test_strict_linkcheck_runs_on_pull_requests_and_docs_build_runs_on_push() -> None:
    workflow = yaml.load(
        Path(".github/workflows/ci.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )

    assert workflow["on"]["push"]["branches"] == ["main"]
    assert "pull_request" in workflow["on"]
    steps = workflow["jobs"]["docs"]["steps"]
    checkout = next(step for step in steps if step.get("uses") == "actions/checkout@v4")
    assert checkout["with"]["fetch-depth"] == "2"

    docs_build = [step for step in steps if step.get("run") == "make docs"]
    assert len(docs_build) == 1
    assert docs_build[0]["id"] == "docs-build"
    assert "if" not in docs_build[0]

    strict_linkchecks = [
        step for step in steps
        if step.get("run") == "sphinx-build -b linkcheck -W docs docs/_build/linkcheck"
    ]
    assert len(strict_linkchecks) == 1
    assert "steps.docs-build.outcome == 'success'" in strict_linkchecks[0]["if"]
    assert "github.event_name == 'pull_request'" in strict_linkchecks[0]["if"]
    assert "steps.linkcheck-scope.outcome == 'failure'" in strict_linkchecks[0]["if"]
    assert "steps.linkcheck-scope.outputs.required != 'false'" in strict_linkchecks[0]["if"]
    scope_step = next(step for step in steps if step.get("id") == "linkcheck-scope")
    assert scope_step["if"] == "github.event_name == 'push'"
    assert "continue-on-error" not in scope_step
    assert "github.event.before" in scope_step["run"]
    assert "github.sha" in scope_step["run"]


def test_changed_main_link_targets_require_post_merge_linkcheck(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "index.md").write_text(
        "[instructions](https://github.com/Zombinator85/SentientOS/blob/main/AGENTS.md)\n"
        "[guide](https://github.com/Zombinator85/SentientOS/tree/main/docs/guide)\n",
        encoding="utf-8",
    )
    (docs / "raw.md").write_text(
        "https://raw.githubusercontent.com/Zombinator85/SentientOS/main/README.md\n"
        "https://github.com/Zombinator85/SentientOS/raw/main/README.md\n",
        encoding="utf-8",
    )

    assert main_link_targets_changed(docs, {"AGENTS.md"})
    assert main_link_targets_changed(docs, {"docs/guide/chapter.md"})
    assert main_link_targets_changed(docs, {"README.md"})
    assert not main_link_targets_changed(docs, {"sentientos/runtime.py"})


def test_unreadable_or_empty_doc_sources_fail_closed(tmp_path: Path) -> None:
    assert main_link_targets_changed(tmp_path, {"sentientos/runtime.py"})
    assert strict_main_linkcheck_required(tmp_path, None)


def test_changed_path_reader_preserves_spaces_and_embedded_newlines(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "scripts.ci_linkcheck_scope.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout="AGENTS.md\0file with space\nline.md\0"),
    )

    assert changed_paths_between("base", "head", repository_root=tmp_path) == {
        "AGENTS.md",
        "file with space\nline.md",
    }

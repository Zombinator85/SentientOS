from __future__ import annotations

import pytest

from scripts import formal_check

pytestmark = pytest.mark.no_legacy_skip


def test_human_output_handles_non_mapping_artifact_paths(tmp_path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setattr(
        formal_check,
        "run_formal_verification",
        lambda _root, *, selected_specs: {"status": "passed", "spec_count": 1, "artifact_paths": object()},
    )

    assert formal_check.main(["--repo-root", str(tmp_path)]) == 0

    assert "status=passed spec_count=1 summary=None" in capsys.readouterr().out

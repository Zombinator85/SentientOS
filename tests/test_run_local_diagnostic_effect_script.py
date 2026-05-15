from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import pytest

from scripts import run_local_diagnostic_effect as script

pytestmark = pytest.mark.no_legacy_skip


def _run(args: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO(); stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            code = script.main(args)
        except SystemExit as exc:
            code = int(exc.code or 0)
    return code, stdout.getvalue(), stderr.getvalue()


def test_requires_output_dir() -> None:
    code, _out, err = _run([])
    assert code != 0
    assert "output-dir" in err


def test_dry_run_writes_nothing_and_summary_is_safe(tmp_path: Path) -> None:
    code, out, err = _run(["--output-dir", str(tmp_path), "--dry-run", "--summary"])
    assert code == 0, err
    payload = json.loads(out)
    assert payload["dry_run"] is True
    assert payload["real_effect_performed"] is False
    assert payload["network_performed"] is False
    assert not (tmp_path / "sentientos_local_diagnostic_effect.json").exists()


def test_default_writes_and_refuses_overwrite_without_force(tmp_path: Path) -> None:
    code, out, err = _run(["--output-dir", str(tmp_path), "--summary"])
    assert code == 0, err
    payload = json.loads(out)
    assert payload["real_effect_performed"] is True
    assert (tmp_path / "sentientos_local_diagnostic_effect.json").exists()
    code, out, _err = _run(["--output-dir", str(tmp_path), "--summary"])
    assert code == 1
    payload = json.loads(out)
    assert payload["effect_status"] == "local_diagnostic_effect_blocked"


def test_force_overwrites_target_and_summary_proves_forbidden_flags_false(tmp_path: Path) -> None:
    assert _run(["--output-dir", str(tmp_path), "--summary"])[0] == 0
    code, out, err = _run(["--output-dir", str(tmp_path), "--summary", "--force"])
    assert code == 0, err
    payload = json.loads(out)
    assert payload["local_file_write_performed"] is True
    for flag in ["fan_pwm_write_performed", "thermal_actuation_performed", "power_profile_mutation_performed", "service_restart_performed", "file_cleanup_performed", "network_performed", "provider_invocation_performed", "prompt_assembly_performed"]:
        assert payload[flag] is False


def test_invalid_artifact_name_exits_nonzero(tmp_path: Path) -> None:
    code, _out, err = _run(["--output-dir", str(tmp_path), "--artifact-name", "bad/name.json"])
    assert code == 2
    assert "artifact_name_contains_path_separator" in err

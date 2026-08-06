import pytest
pytestmark = pytest.mark.no_legacy_skip
import os

from sentientos import maintenance_loop_watchdog as watchdog
from sentientos.maintenance_validation_controller import ValidationPolicy
from tests.maintenance_watchdog_implementation_fixtures import NOW, setup


def _ready(tmp_path):
    cfg, roots, _ = setup(tmp_path)
    cfg = dict(cfg)
    cfg["validation_policy"] = ValidationPolicy(
        "watchdog", "repo", external_scratch_root=str(roots["scratch"]),
        per_command_default_ceiling_seconds=2).to_dict()
    cfg = watchdog.validate_config({k: v for k, v in cfg.items() if k != "config_digest"})
    os.environ["FAKE_CODEX_MODE"] = "success"
    for _ in range(5): watchdog.tick(cfg, evaluation_time=NOW)
    return cfg, roots


def test_exact_implementation_ready_result_invokes_validation_controller(tmp_path):
    cfg, roots = _ready(tmp_path)
    tick = watchdog.tick(cfg, evaluation_time=NOW)
    assert tick["transition"] == "validate"
    assert tick["effect_result"]["status"] == "validation_ready_for_commit"
    assert len(list((roots["state"] / "maintenance_validation_results").glob("*.json"))) == 1


def test_validation_binding_ignores_filename_order_and_rejects_wrong_digest(tmp_path):
    cfg, roots = _ready(tmp_path)
    source = next((roots["state"] / "maintenance_worktrees").glob("*.json"))
    decoy = source.read_text().replace('"worktree_digest":"', '"worktree_digest":"sha256:decoy')
    (source.parent / "zzzz-decoy.json").write_text(decoy)
    tick = watchdog.tick(cfg, evaluation_time=NOW)
    assert tick["effect_result"]["status"] == "validation_ready_for_commit"

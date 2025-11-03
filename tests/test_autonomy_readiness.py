from pathlib import Path

import os

from tools.autonomy_readiness import evaluate_autonomy_environment


def _fresh_env() -> dict[str, str]:
    return {key: value for key, value in os.environ.items() if key.startswith("SENTIENTOS_")}


def test_all_checks_pass(tmp_path: Path) -> None:
    env = _fresh_env()
    model_path = tmp_path / "mixtral.gguf"
    model_path.write_text("test")

    env.update(
        {
            "SENTIENTOS_ORACLE": "offline",
            "SENTIENTOS_CODER": "local",
            "SENTIENTOS_MODEL_PATH": str(model_path),
        }
    )

    checks, overall = evaluate_autonomy_environment(env=env)

    assert overall is True
    assert all(check.ok for check in checks)


def test_missing_model_allowed(tmp_path: Path) -> None:
    env = _fresh_env()
    env.update(
        {
            "SENTIENTOS_ORACLE": "none",
            "SENTIENTOS_CODER": "local",
            "SENTIENTOS_MODEL_PATH": str(tmp_path / "does-not-exist.gguf"),
        }
    )

    checks, overall = evaluate_autonomy_environment(env=env, require_model=False)

    assert overall is True
    path_messages = [check.message for check in checks if check.name == "Local model path"]
    assert path_messages and "does not exist" in path_messages[0]


def test_detects_missing_configuration(monkeypatch, tmp_path: Path) -> None:
    env = {}
    monkeypatch.delenv("SENTIENTOS_ORACLE", raising=False)
    monkeypatch.delenv("SENTIENTOS_CODER", raising=False)
    monkeypatch.delenv("SENTIENTOS_MODEL_PATH", raising=False)

    checks, overall = evaluate_autonomy_environment(env=env)

    assert overall is False
    assert {check.name for check in checks if not check.ok} == {
        "Oracle provider",
        "Coder backend",
        "Local model path",
    }

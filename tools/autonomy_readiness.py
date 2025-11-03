"""Utilities for verifying that SentientOS is configured for local autonomy.

This module provides a small CLI helper that inspects the current process
environment and checks for the configuration knobs described in the autonomy
rollout notes.  It intentionally avoids network calls or optional
dependencies so that it can run in minimal offline environments – the exact
scenario it is trying to validate.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple
import argparse
import os
import sys


@dataclass(frozen=True)
class CheckResult:
    """Represents the outcome of a single readiness check."""

    name: str
    ok: bool
    message: str

    def format(self) -> str:
        status = "PASS" if self.ok else "FAIL"
        return f"[{status}] {self.name}: {self.message}"


OFFLINE_ORACLE_VALUES: Sequence[str] = (
    "offline",
    "off",
    "none",
    "no",
    "false",
    "disabled",
)


def _normalise(value: str | None) -> str:
    return (value or "").strip().lower()


def _check_oracle_setting(env: dict[str, str]) -> CheckResult:
    raw_value = env.get("SENTIENTOS_ORACLE") or env.get("SENTIENTOS_ORACLE_PROVIDER")
    normalised = _normalise(raw_value)
    if normalised in OFFLINE_ORACLE_VALUES:
        message = (
            f"Oracle disabled ({raw_value!r} → offline)."
            if raw_value is not None
            else "Oracle defaulting to offline mode."
        )
        return CheckResult("Oracle provider", True, message)
    return CheckResult(
        "Oracle provider",
        False,
        "Expected SENTIENTOS_ORACLE to be disabled or offline.",
    )


def _check_coder_setting(env: dict[str, str]) -> CheckResult:
    raw_value = env.get("SENTIENTOS_CODER")
    normalised = _normalise(raw_value)
    if normalised == "local":
        return CheckResult("Coder backend", True, "Configured for local coder usage.")
    return CheckResult(
        "Coder backend",
        False,
        "Expected SENTIENTOS_CODER to be set to 'local'.",
    )


def _check_model_path(env: dict[str, str], require_model: bool) -> CheckResult:
    raw_value = env.get("SENTIENTOS_MODEL_PATH") or env.get("LOCAL_MODEL_PATH")
    if not raw_value:
        return CheckResult(
            "Local model path",
            not require_model,
            "Model path not provided.",
        )

    path = Path(raw_value).expanduser()
    if path.is_file():
        return CheckResult(
            "Local model path",
            True,
            f"Model file available at {path}.",
        )
    if path.exists():
        message = f"Path {path} exists but is not a file."
    else:
        message = f"Path {path} does not exist."
    return CheckResult("Local model path", not require_model, message)


def evaluate_autonomy_environment(
    *,
    require_model: bool = True,
    env: dict[str, str] | None = None,
) -> Tuple[List[CheckResult], bool]:
    """Evaluate autonomy-related environment variables.

    Parameters
    ----------
    require_model:
        When ``True`` the presence of the local model file is mandatory for a
        passing result.  The flag can be relaxed for diagnostics in CI.
    env:
        Optional environment mapping.  Defaults to ``os.environ``.
    """

    env_map = dict(env or os.environ)

    checks: List[CheckResult] = [
        _check_oracle_setting(env_map),
        _check_coder_setting(env_map),
        _check_model_path(env_map, require_model=require_model),
    ]

    overall = all(check.ok for check in checks)
    return checks, overall


def _render_report(checks: Iterable[CheckResult], overall: bool) -> str:
    lines = [check.format() for check in checks]
    summary = "Autonomy readiness: PASS" if overall else "Autonomy readiness: FAIL"
    return "\n".join([*lines, summary])


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate that SentientOS is configured for local, Codex-free autonomy."
        )
    )
    parser.add_argument(
        "--allow-missing-model",
        action="store_true",
        help=(
            "Do not fail if SENTIENTOS_MODEL_PATH is missing or the file is "
            "unavailable."
        ),
    )
    args = parser.parse_args(argv)

    checks, overall = evaluate_autonomy_environment(
        require_model=not args.allow_missing_model
    )
    report = _render_report(checks, overall)
    print(report)
    return 0 if overall else 1


if __name__ == "__main__":  # pragma: no cover - exercised via CLI usage
    sys.exit(main())

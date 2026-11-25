"""Executable model-free worker for already completed cognition-tick recovery."""
from __future__ import annotations

from .durable_learning_condition_worker_backend import (
    run_condition_worker_recovery_from_environment)


def main() -> int:
    result = run_condition_worker_recovery_from_environment()
    return 0 if (result.get("schema_version") ==
        "sentientos.durable_learning_condition_recovery_worker_once:v1"
        and result.get("requests_processed") == 4) else 1


if __name__ == "__main__":
    raise SystemExit(main())

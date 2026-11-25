"""Executable one-request baseline-only AppContainer worker."""
from __future__ import annotations

from .durable_learning_condition_worker_backend import (
    run_condition_worker_baseline_from_environment)


def main() -> int:
    result = run_condition_worker_baseline_from_environment()
    return 0 if (result.get("schema_version") ==
        "sentientos.windows_appcontainer_baseline_worker_once:v1"
        and result.get("requests_processed") == 1
        and result.get("operation") == "inspect_baseline"
        and result.get("response_status") in {"completed", "rejected"}) else 1


if __name__ == "__main__":
    raise SystemExit(main())

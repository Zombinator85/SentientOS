"""Executable AppContainer profile-state preflight worker entrypoint."""
from __future__ import annotations

from .durable_learning_condition_worker_backend import (
    run_condition_worker_access_probe_from_environment)


def main() -> int:
    result = run_condition_worker_access_probe_from_environment()
    return 0 if (result.get("schema_version") ==
        "sentientos.windows_appcontainer_profile_state_worker_once:v1"
        and result.get("requests_processed") == 2
        and result.get("operation") == "profile_state_preflight"
        and result.get("response_status") == "completed"
        and isinstance(result.get("registry_inventory_digest"), str)) else 1


if __name__ == "__main__":
    raise SystemExit(main())

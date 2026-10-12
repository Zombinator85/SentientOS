from __future__ import annotations

import json
from pathlib import Path

from sentientos.integrity_incident import inspect_quarantine_incident_custody
from sentientos.integrity_quarantine import (
    QuarantineStateError,
    load_state_with_status,
)


def main() -> int:
    root = Path.cwd().resolve()
    try:
        loaded = load_state_with_status(root)
    except QuarantineStateError as exc:
        # Unknown protective state stays unknown. Never print a default inactive
        # object or attempt to repair custody from this status-only command.
        print(json.dumps({
            "quarantine": None,
            "quarantine_active": None,
            "quarantine_custody_status": "invalid:" + exc.code,
            "incident_custody": {
                "status": "not_checked",
                "attack_established": False,
                "defensive_consequence_established": False,
            },
        }, indent=2, sort_keys=True))
        return 2

    state = loaded.state
    incident_custody = inspect_quarantine_incident_custody(
        root,
        incident_id=state.last_incident_id,
        activated_at=state.activated_at,
    )
    print(json.dumps({
        "quarantine": state.to_dict(),
        "quarantine_active": state.active,
        "quarantine_custody_status": loaded.custody_status.value,
        "incident_custody": incident_custody,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

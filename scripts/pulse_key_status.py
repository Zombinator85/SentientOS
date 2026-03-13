from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from sentientos.federated_enforcement_policy import resolve_policy
from sentientos.pulse_trust_epoch import get_manager


def _git_sha() -> str:
    try:
        c = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], check=True, capture_output=True, text=True)
    except Exception:
        return ""
    return c.stdout.strip()


state = get_manager().load_state()
payload = {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "captured_by": _git_sha(),
    "active_epoch_id": state.get("active_epoch_id"),
    "revoked_epochs": state.get("revoked_epochs", []),
    "epochs": state.get("epochs", {}),
    "enforcement_policy": resolve_policy().to_dict(),
    "pulse_trust_posture": resolve_policy().pulse_trust_epoch,
}
out = Path("glow/contracts/pulse_key_epoch_status.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
print(json.dumps(payload, sort_keys=True))

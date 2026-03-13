from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from nacl.signing import SigningKey

from sentientos.pulse_trust_epoch import get_manager


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _git_sha() -> str:
    try:
        c = subprocess.run(["git", "rev-parse", "--verify", "HEAD"], check=True, capture_output=True, text=True)
    except Exception:
        return ""
    return c.stdout.strip()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def rotate(*, dry_run: bool, reason: str, actor: str) -> dict[str, object]:
    manager = get_manager()
    state = manager.load_state()
    current = str(state.get("active_epoch_id") or "epoch-0001")
    transition_counter = int(state.get("transition_counter", 0)) + 1
    new_epoch = f"epoch-{transition_counter+1:04d}"
    key_root = Path("/vow/keys") if Path("/vow").exists() else Path("vow/keys")
    priv = key_root / f"ed25519_private_{new_epoch}.key"
    pub = key_root / f"ed25519_public_{new_epoch}.key"

    report = {
        "schema_version": 1,
        "generated_at": _now(),
        "dry_run": dry_run,
        "actor": actor,
        "reason": reason,
        "captured_by": _git_sha(),
        "from_epoch": current,
        "to_epoch": new_epoch,
        "verify_key_path": str(pub),
        "signing_key_path": str(priv),
    }
    if not dry_run:
        key = SigningKey.generate()
        key_root.mkdir(parents=True, exist_ok=True)
        priv.write_bytes(key.encode())
        pub.write_bytes(key.verify_key.encode())
        manager.transition_epoch(
            new_epoch_id=new_epoch,
            verify_key_path=str(pub),
            signing_key_path=str(priv),
            actor=actor,
            reason=reason,
            compromise_response_mode=False,
        )
        report["rotated"] = True
    else:
        report["rotated"] = False

    status_state = manager.load_state()
    status = {
        "schema_version": 1,
        "generated_at": _now(),
        "captured_by": _git_sha(),
        "active_epoch_id": status_state.get("active_epoch_id"),
        "revoked_epochs": status_state.get("revoked_epochs", []),
        "replay_allowance_seconds": int(__import__("os").getenv("SENTIENTOS_PULSE_RETIRED_REPLAY_SECONDS", "0") or "0"),
        "epochs": status_state.get("epochs", {}),
    }
    _write_json(Path("glow/contracts/pulse_key_rotation_report.json"), report)
    _write_json(Path("glow/contracts/pulse_key_epoch_status.json"), status)
    return report


def main() -> int:
    p = argparse.ArgumentParser(description="Rotate pulse signing keys with epoch provenance")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--reason", default="privileged_rotation")
    p.add_argument("--actor", default="operator")
    args = p.parse_args()
    payload = rotate(dry_run=args.dry_run, reason=args.reason, actor=args.actor)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

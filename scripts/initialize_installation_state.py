"""Initialize and verify canonical machine-scoped installation custody."""
from __future__ import annotations

import argparse
import json
from typing import Sequence

from sentientos.installation_state import (
    InstallationIdentity,
    InstallationStateError,
    InstallationStateRegistry,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Initialize canonical SentientOS installation state; this grants no authority."
    )
    parser.add_argument("--installation-identity", required=True)
    args = parser.parse_args(argv)

    try:
        identity = InstallationIdentity.parse(args.installation_identity)
        registry = InstallationStateRegistry.system()
        created = registry.open(identity, create=True)
        reopened = InstallationStateRegistry.system().open(identity)
        if created.root != reopened.root or created.identity != reopened.identity:
            raise InstallationStateError("installation_reopen_mismatch")
    except (ValueError, InstallationStateError) as exc:
        reason = exc.code if isinstance(exc, InstallationStateError) else "invalid_installation_identity"
        print(json.dumps({"reason_code": reason, "status": "blocked"}, sort_keys=True))
        return 2

    print(json.dumps({
        "authority_granted": False,
        "canonical_state_root": str(reopened.root),
        "installation_identity": reopened.identity.value,
        "status": "installation_state_initialized",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

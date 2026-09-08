"""Deterministically verify canonical deployed catalog custody without effects."""
from __future__ import annotations

import argparse
import json

from sentientos.installation_state import InstallationIdentity, InstallationStateError, InstallationStateRegistry
from sentientos.local_model_catalog_consumer_custody import (
    CatalogConsumerCustodyError, construct_authoritative_catalog_consumer_proof,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--installation-identity", required=True)
    args = parser.parse_args(argv)
    try:
        handle = InstallationStateRegistry.system().open(InstallationIdentity.parse(args.installation_identity))
        snapshot = construct_authoritative_catalog_consumer_proof(handle)
    except (ValueError, InstallationStateError, CatalogConsumerCustodyError) as exc:
        reason = exc.code if hasattr(exc, "code") else "installation_identity_invalid"
        print(json.dumps({"reason_code": reason, "status": "blocked"}, sort_keys=True))
        return 2
    print(json.dumps({"proof": snapshot.proof, "status": "verified"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

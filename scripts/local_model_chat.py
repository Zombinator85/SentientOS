"""Explicit operator composition for hardened local production chat."""
from __future__ import annotations

import argparse

from sentientos.chat_service import configure_production_chat, run


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--installation-identity", required=True)
    parser.add_argument("--serving-operation-id", required=True)
    parser.add_argument("--expected-activation-state-digest")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    args = parser.parse_args()
    configure_production_chat(installation_identity=args.installation_identity,
                              serving_operation_id=args.serving_operation_id,
                              expected_activation_state_digest=args.expected_activation_state_digest)
    run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()

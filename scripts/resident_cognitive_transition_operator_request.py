from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.resident_cognitive_transition_operator import build_request, persist_request


def _load(path: str) -> dict[str, object]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("artifact_must_be_object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Persist one non-authoritative resident transition request")
    parser.add_argument("--installation-root", required=True)
    parser.add_argument("--installation-identity", required=True)
    parser.add_argument("--protocol", required=True); parser.add_argument("--stage-approval", required=True)
    parser.add_argument("--subordinate-approval", action="append", default=[])
    parser.add_argument("--requested-stage", required=True); parser.add_argument("--expected-prior-phase", required=True)
    parser.add_argument("--expected-journal-head", required=True); parser.add_argument("--operation-id", required=True)
    parser.add_argument("--correlation-id", required=True); parser.add_argument("--operator-identity", required=True)
    parser.add_argument("--operator-provenance", required=True); parser.add_argument("--created-at", required=True)
    parser.add_argument("--expires-at", required=True)
    args = parser.parse_args()
    request = build_request(installation_identity=args.installation_identity, protocol=_load(args.protocol),
        requested_stage=args.requested_stage, expected_prior_phase=args.expected_prior_phase,
        expected_journal_head=args.expected_journal_head, stage_approval=_load(args.stage_approval),
        subordinate_approvals=[_load(path) for path in args.subordinate_approval], operation_id=args.operation_id,
        correlation_id=args.correlation_id, operator_identity=args.operator_identity,
        operator_provenance=_load(args.operator_provenance), created_at=args.created_at, expires_at=args.expires_at)
    path = persist_request(Path(args.installation_root), request)
    print(json.dumps({"status": "operator_request_persisted", "request_id": request["request_id"],
                      "request_digest": request["request_digest"], "path": path.as_posix(),
                      "authority_granted": False}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

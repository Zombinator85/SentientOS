from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from sentientos.epistemic_qualification_cohort import MAX_REPORT_BYTES
from sentientos.epistemic_revision_assessment_attestation import (
    compose_assessment_attested_revision_suite,
    revision_case_from_dict,
)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("epistemic_assessment_duplicate_json_key")
        result[key] = value
    return result


def _read_json(path: Path) -> Any:
    raw = path.read_bytes()
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError("epistemic_assessment_report_limit_exceeded")
    return json.loads(raw, object_pairs_hook=_unique_object)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Verify a signed assessor statement alongside v3 persistent revision evidence.")
    parser.add_argument("revision_suite_v2", type=Path)
    parser.add_argument("revision_suite_v3", type=Path)
    parser.add_argument("correction_case", type=Path,
        help="private exact RevisionCase JSON used by the evaluator")
    parser.add_argument("series_reports", nargs="+", type=Path)
    parser.add_argument("--pressure-control", required=True, type=Path)
    parser.add_argument("--attestation", type=Path,
        help="signed assessor statement; omission produces an explicit insufficient result")
    parser.add_argument("--assessor-public-key", type=Path,
        help="base64url raw Ed25519 public key pinned for this assessment")
    parser.add_argument("--expected-protocol-digest")
    parser.add_argument("--expected-assessor-key-fingerprint")
    args = parser.parse_args(argv)
    if len(args.series_reports) > 96:
        parser.error("epistemic_assessment_report_count_invalid")
    try:
        attestation = _read_json(args.attestation) if args.attestation else None
        public_key = args.assessor_public_key.read_text(encoding="utf-8").strip() \
            if args.assessor_public_key else None
        result = compose_assessment_attested_revision_suite(
            revision_suite_v2_report=_read_json(args.revision_suite_v2),
            revision_suite_v3_report=_read_json(args.revision_suite_v3),
            revision_reports=[_read_json(path) for path in args.series_reports],
            pressure_control_report=_read_json(args.pressure_control),
            correction_case=revision_case_from_dict(_read_json(args.correction_case)),
            attestation=attestation,
            pinned_assessor_public_key=public_key,
            expected_protocol_digest=args.expected_protocol_digest,
            expected_assessor_key_fingerprint=args.expected_assessor_key_fingerprint,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

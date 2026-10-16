"""List verified admitted consequence records for an operator strategy pilot."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

from sentientos.codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK, RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from sentientos.embodied_consequence import (
    ATTRIBUTION_SCHEMA, STRATEGY_DECISION_QUALITY_FEEDBACK_SCHEMA,
)
from sentientos.resident_developmental_cognition import CONFIG_ENV, load_config
from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionVerifier


def _inventory(completed: tuple[Any, ...]) -> dict[str, Any]:
    rows=[]
    for record, receipt in completed:
        candidate=record.candidate
        facts=candidate.get("selected_facts") if isinstance(candidate, Mapping) else None
        events=[]
        strategy_feedback=[]
        if isinstance(facts, (list, tuple)):
            for fact in facts:
                payload=fact.get("payload") if isinstance(fact, Mapping) else None
                if not isinstance(payload, Mapping):
                    continue
                if payload.get("schema_version") == ATTRIBUTION_SCHEMA:
                    events.append({"fact_id":fact.get("fact_id"),
                        "event_id":payload.get("attribution_id"),
                        "event_digest":payload.get("attribution_digest"),
                        "record_correlation_id":getattr(record, "correlation_id", None),
                        "classification":payload.get("classification"),
                        "causal_attribution_posture":payload.get("causal_attribution_posture"),
                        "evaluated_at":payload.get("evaluated_at")})
                elif payload.get("schema_version") == STRATEGY_DECISION_QUALITY_FEEDBACK_SCHEMA:
                    result=payload.get("decision_quality_result")
                    strategy_feedback.append({"fact_id":fact.get("fact_id"),
                        "feedback_id":payload.get("feedback_id"),
                        "feedback_digest":payload.get("feedback_digest"),
                        "proposal_identity":payload.get("proposal_identity"),
                        "quality_result_digest":(result.get("result_digest")
                            if isinstance(result, Mapping) else None),
                        "execution_occurred":payload.get("execution_occurred"),
                        "physical_effect_established":payload.get("physical_effect_established"),
                        "improvement_claimed":payload.get("improvement_claimed")})
        if not events and not strategy_feedback:
            continue
        rows.append({"record_id":record.record_id,"record_digest":record.record_digest,
            "record_correlation_id":getattr(record, "correlation_id", None),
            "receipt_id":receipt.receipt_id,"receipt_digest":receipt.receipt_digest,
            "admission_id":record.admission_id,
            "admission_binding_digest":record.admission_binding_digest,
            "event_count":len(events),"events":events,
            "strategy_feedback":strategy_feedback,
            "epistemic_posture":record.epistemic_posture,
            "current_truth":record.current_truth,"authority":record.authority,
            "policy":record.policy})
    rows.sort(key=lambda item:(item["record_id"],item["record_digest"]))
    return {"schema_version":"sentientos.codex_strategy_record_inventory:v1",
        "read_only":True,"verified_completed_record_count":len(completed),
        "strategy_record_count":len(rows),
        "records":rows,"limitations":[
            "The inventory verifies owner custody and source identity, not event truth or applicability.",
            "Fixture admissions and receipts are not provider inference receipts.",
            "Choose source records per situation; applicability declarations remain operator assertions."]}


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config",default=os.environ.get(CONFIG_ENV),
        help="resident developmental-cognition configuration; inspected read-only")
    parser.add_argument("--output",help="optional inventory JSON output path")
    args=parser.parse_args()
    if not args.config:
        parser.error(f"--config or {CONFIG_ENV} is required")
    config=load_config(args.config)
    ledger=AdmissionLedger(config.state_root/"runtime_admissions.json")
    writeback=ResidentDevelopmentalWritebackController(history_root=config.history_root,
        admission_verifier=RuntimeAdmissionVerifier(definitions={
            RESIDENT_DEVELOPMENTAL_WRITEBACK:RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION},
            ledger=ledger),current_sequence=ledger.current_sequence)
    report=_inventory(writeback.inspect_completed_records())
    encoded=json.dumps(report,sort_keys=True,indent=2)+"\n"
    if args.output:
        Path(args.output).write_text(encoded,encoding="utf-8")
    print(encoded,end="")
    return 0


if __name__=="__main__":
    raise SystemExit(main())

"""End-to-end rehearsal execution helpers."""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, MutableSequence, Optional, Sequence

from ..config import RuntimeConfig, load_runtime_config
from ..storage import get_data_root
from ..determinism import seed_everything
from .runtime import AutonomyRuntime, CouncilDecision, CouncilOutcome, OracleMode

LOGGER = logging.getLogger(__name__)


@dataclass
class RehearsalCycle:
    corr_id: str
    oracle_result: Mapping[str, object]
    critic_result: Mapping[str, object]
    council_decision: CouncilDecision
    peer_review: Optional[Mapping[str, object]]


def run_rehearsal(
    *,
    cycles: int,
    runtime: Optional[AutonomyRuntime] = None,
    oracle_plan: Optional[Sequence[Callable[[int], object]]] = None,
    critic_plan: Optional[Sequence[Mapping[str, object]]] = None,
) -> dict[str, object]:
    """Execute rehearsal cycles and persist provenance artefacts."""

    config = runtime.config if runtime else load_runtime_config()
    seed_everything(config)
    runtime = runtime or AutonomyRuntime(config)

    output_dir = get_data_root() / "glow" / "rehearsal" / "latest"
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "runtime.jsonl"

    peer_reviews: MutableSequence[Mapping[str, object]] = []
    cycles_ran: list[RehearsalCycle] = []

    for idx in range(cycles):
        corr_id = f"rehearsal-{idx}-{uuid.uuid4().hex[:8]}"
        oracle_callable: Callable[[], object]
        if oracle_plan and idx < len(oracle_plan) and oracle_plan[idx] is not None:
            callback = oracle_plan[idx]

            def oracle_callable(callback=callback, idx=idx) -> object:
                return callback(idx)

        else:
            oracle_callable = lambda: {"status": "ok"}

        oracle_result = runtime.oracle.execute(oracle_callable, corr_id=corr_id)

        critic_payload: Mapping[str, object] = {}
        if critic_plan and idx < len(critic_plan) and critic_plan[idx] is not None:
            critic_payload = critic_plan[idx]
        critic_result = runtime.critic.review(critic_payload, corr_id=corr_id)

        peer_entry: Optional[Mapping[str, object]] = None
        if critic_result.get("disagreement"):
            peer_entry = {
                "corr_id": corr_id,
                "reason": critic_payload.get("reason", "critic disagreement"),
                "ts": critic_result.get("ts"),
            }
            peer_reviews.append(peer_entry)

        quorum = runtime.config.council.quorum
        votes_for = quorum
        votes_against = 0
        if critic_result.get("disagreement"):
            votes_against = max(1, quorum - 1)
        if oracle_result.get("mode") == OracleMode.DEGRADED.value:
            votes_for = max(quorum - 1, 0)
        council_decision = runtime.council.vote(
            "rehearsal-cycle",
            corr_id=corr_id,
            votes_for=votes_for,
            votes_against=votes_against,
        )
        if not council_decision.quorum_met:
            council_decision = CouncilDecision(
                outcome=CouncilOutcome.TIED,
                votes_for=votes_for,
                votes_against=votes_against,
                quorum_met=False,
                notes="Quorum not met; decision deferred",
            )
        cycles_ran.append(
            RehearsalCycle(
                corr_id=corr_id,
                oracle_result=oracle_result,
                critic_result=critic_result,
                council_decision=council_decision,
                peer_review=peer_entry,
            )
        )

    with log_path.open("w", encoding="utf-8") as handle:
        for cycle in cycles_ran:
            handle.write(
                json.dumps(
                    {
                        "corr_id": cycle.corr_id,
                        "oracle": cycle.oracle_result,
                        "critic": cycle.critic_result,
                        "council": {
                            "outcome": cycle.council_decision.outcome.value,
                            "quorum": cycle.council_decision.quorum_met,
                        },
                        "peer_review": cycle.peer_review,
                    }
                )
                + "\n"
            )

    runtime.metrics.persist_prometheus()
    runtime.metrics.persist_snapshot()

    status = runtime.status()
    report = {
        "version": "v1.1.0-beta",
        "cycles": cycles,
        "oracle_mode": runtime.oracle.mode.value,
        "critic_disagreements": len(peer_reviews),
        "council_outcomes": [cycle.council_decision.outcome.value for cycle in cycles_ran],
        "status": status.modules,
    }

    integrity = {
        "quorum_met": all(c.council_decision.quorum_met for c in cycles_ran),
        "peer_reviews": peer_reviews,
        "oracle": runtime.oracle.mode.value,
    }

    report_path = output_dir / "REHEARSAL_REPORT.json"
    integrity_path = output_dir / "INTEGRITY_SUMMARY.json"
    _write_signed_json(report_path, report)
    _write_signed_json(integrity_path, integrity)

    return {
        "report": report,
        "integrity": integrity,
        "status": status.modules,
        "peer_reviews": list(peer_reviews),
    }


def _write_signed_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2, sort_keys=True)
    digest = hashlib.sha256(data.encode("utf-8")).digest()
    signature = base64.b64encode(digest).decode("ascii")
    armored = "\n".join(
        [
            "-----BEGIN SENTIENTOS SIGNATURE-----",
            signature,
            "-----END SENTIENTOS SIGNATURE-----",
        ]
    )
    path.write_text(
        json.dumps({"payload": payload, "signature": armored}, indent=2) + "\n",
        encoding="utf-8",
    )


__all__ = ["run_rehearsal"]

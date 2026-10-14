"""Bounded, separately admitted resident developmental-history writeback.

Records produced here are historical interpretations.  They are never current
World-State truth, policy, authority, goals, or canonical explicit user memory.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence

from .codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from .governed_local_model_invocation import (
    LocalModelInvoker,
    LocalModelInvocationBudget,
    LocalModelInvocationReceipt,
    RESIDENT_COGNITION_LESSON_OUTPUT_SCHEMA,
)
from .local_model_authority import digest_payload
from .canonical_memory import sentientos_memory_dir
from .private_file_custody import (
    PrivateFileCustodyError, list_bounded_json_names_at, open_private_directory,
    read_private_file_at, publish_immutable_bytes,
)
from .platform_fcntl import fcntl, require_flock
from .runtime_admission import AdmissionError, AdmissionEvidence, RuntimeAdmissionVerifier
from .world_state_board import WorldStateSnapshot, digest, to_dict, validate_snapshot
from .windows_handle_custody import WindowsHandleCustodyError, read_regular_files

SCHEMA_VERSION = "sentientos.resident_developmental_writeback:v1"
PRINCIPAL = "deterministic_resident_developmental_writeback_controller"
EFFECTS = tuple(sorted(RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION.required_effects))
PURPOSE = "resident_developmental_interpretation"
COGNITION_LESSON_PROVENANCE_KIND = "history_conditioned_cognition_conclusion:v1"
MAX_SELECTED_FACTS = 16
MAX_SELECTED_EVIDENCE_BYTES = 6000
MAX_RESOURCE_LINEAGE_SELECTED_EVIDENCE_BYTES = 8192
# A verified five-condition replacement run has a larger but still tightly
# bounded lineage vector. This allowance is limited to one v2 embodiment fact;
# all general and mixed-source selections retain the 6 KB cap.
MAX_MODEL_REPLACEMENT_SELECTED_EVIDENCE_BYTES = 8192
# A completed three-condition history-intervention run carries a bounded set
# of invocation and score identities. Keep its writeback allowance narrow to
# one explicitly projected experiment fact.
MAX_DEVELOPMENTAL_EXPERIMENT_SELECTED_EVIDENCE_BYTES = 10_240
# A single preregistered strategy-quality vector is larger than a general
# evidence fact but remains bounded to 12 KB and carries no execution claim.
MAX_STRATEGY_QUALITY_SELECTED_EVIDENCE_BYTES = 12_288
MAX_RETRIEVAL_RECORDS = 16
MAX_INTERPRETATION_CHARS = 4000
MAX_DURABLE_RECORDS = 4096
MAX_DURABLE_RECORD_BYTES = 1_048_576
MAX_DURABLE_RECORD_ROOT_BYTES = 134_217_728


class DevelopmentalWritebackError(ValueError):
    """Fail-closed runtime boundary violation."""


def _valid_optional_lower_sha256(value: Any) -> bool:
    return (value is None or (type(value) is str and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)))


def _has_bounded_integrity_controller_observation(selection: SelectedEvidence) -> bool:
    for fact in selection.facts:
        source = fact.get("source")
        subject = fact.get("subject")
        payload = fact.get("payload")
        if (not isinstance(source, Mapping)
                or source.get("kind") != "audit_trust"
                or source.get("source_id") != "integrity-controller:resident-daemon"
                or not isinstance(subject, Mapping)
                or subject.get("subject_kind") != "integrity_controller_observation"
                or fact.get("stage") != "observation"
                or fact.get("evidence_strength") not in {
                    "source_integrity_status", "integrity_controller_observation_unavailable"}
                or not isinstance(payload, Mapping)
                or payload.get("observation_schema") not in {
                    "sentientos.integrity_controller_observation:v1",
                    "sentientos.integrity_controller_observation:v2",
                }
                or payload.get("source_owner")
                    != "sentientos.integrity_controller.evaluate_integrity"
                or payload.get("controller_posture") not in {"ok", "warn", "fail", "unknown"}
                or payload.get("cause_unknown") is not True
                or payload.get("attack_established") is not False
                or payload.get("hostile_activity_established") is not False
                or payload.get("compromise_established") is not False
                or payload.get("effect_proven") is not False
                or payload.get("effect_authority") is not False
                or payload.get("authority") is not False
                or payload.get("current_truth") is not False
                or payload.get("read_only") is not True):
            continue
        gates = payload.get("gate_results")
        if (isinstance(gates, list) and len(gates) <= 32
                and type(payload.get("gate_count")) is int
                and payload["gate_count"] == len(gates)
                and all(isinstance(gate, Mapping)
                    and isinstance(gate.get("name"), str)
                    and 0 < len(gate["name"]) <= 64
                    and gate.get("status") in {"ok", "warn", "fail", "skipped"}
                    and isinstance(gate.get("reason"), str) and len(gate["reason"]) <= 160
                    and isinstance(gate.get("checked_at"), str)
                    and len(gate["checked_at"]) <= 64
                    and _valid_optional_lower_sha256(gate.get("failed_record_sha256"))
                    for gate in gates)):
            return True
    return False


def _valid_store_identity(value: Any, prefix: str) -> bool:
    marker = prefix + "-"
    return (isinstance(value, str) and len(value) == len(marker) + 24
            and value.startswith(marker)
            and all(character in "0123456789abcdef" for character in value[len(marker):]))


def _digest(value: Any) -> str:
    return "sha256:" + digest_payload(value)


def _identity(prefix: str, payload: Any) -> tuple[str, str]:
    digest = _digest(payload)
    return f"{prefix}-{digest.removeprefix('sha256:')[:24]}", digest


def _validate_candidate_source_bindings(candidate: "DevelopmentalCandidate") -> None:
    """Require one exact source row per source referenced by retained facts.

    Older records can omit selected fact payloads, so this check is limited to
    the versioned payload-bearing form. Mapping construction must not silently
    collapse duplicate source IDs: conflicting duplicates would make recovery
    depend on row order.
    """
    if not candidate.selected_facts:
        return
    if (len(candidate.selected_fact_ids) != len(set(candidate.selected_fact_ids))
            or len(candidate.selected_facts) != len(candidate.selected_fact_ids)):
        raise DevelopmentalWritebackError("candidate_source_binding_invalid")
    sources_by_id: dict[str, Mapping[str, Any]] = {}
    for source in candidate.selected_sources:
        source_id = source.get("source_id") if isinstance(source, Mapping) else None
        source_digest = source.get("digest") if isinstance(source, Mapping) else None
        if (not isinstance(source_id, str) or not source_id
                or not isinstance(source_digest, str) or len(source_digest) != 64
                or any(character not in "0123456789abcdef" for character in source_digest)
                or source_id in sources_by_id):
            raise DevelopmentalWritebackError("candidate_source_binding_invalid")
        sources_by_id[source_id] = source
    referenced_sources: dict[str, Mapping[str, Any]] = {}
    for fact in candidate.selected_facts:
        if not isinstance(fact, Mapping) or not isinstance(fact.get("source"), Mapping):
            raise DevelopmentalWritebackError("candidate_source_binding_invalid")
        source = fact["source"]
        source_id = source.get("source_id")
        if (not isinstance(source_id, str) or not source_id
                or source_id in referenced_sources
                and dict(refe
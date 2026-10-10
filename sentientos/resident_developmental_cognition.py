"""One-tick resident composition for bounded developmental history.

The owner has no cadence of its own.  ``sentientosd`` supplies an exact
World-State snapshot and tick identity.  History is non-authoritative context;
it is never canonical explicit-user retention.
"""
from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, cast

from .codex_task_authority_admission import (
    RESIDENT_DEVELOPMENTAL_WRITEBACK,
    RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
)
from .governed_local_model_invocation import LocalModelInvocationBudget, LocalModelInvoker
from .developmental_history_intervention_experiment import (
    DevelopmentalExperimentStore, make_protocol, summarize,
    PURPOSE as EXPERIMENT_PURPOSE,
)
from .local_model_authority import atomic_write_json, digest_payload
from .longitudinal_self_model import CognitiveSelfModelProjection
from .persistent_epistemic_state import EpistemicCognitiveProjection
from .resident_developmental_writeback import (
    EFFECTS,
    PRINCIPAL,
    CognitionObservation,
    DevelopmentalHistoryProjection,
    DevelopmentalWritebackError,
    ResidentDevelopmentalWritebackController,
    measure_changed_cognition,
)
from .runtime_admission import RuntimeAdmissionAuthority
from .world_state_board import WorldStateSnapshot, validate_snapshot
from .windows_handle_custody import WindowsHandleCustodyError, read_explicit_file, read_regular_files

CONFIG_ENV = "SENTIENTOS_RESIDENT_DEVELOPMENTAL_COGNITION_CONFIG"
SCHEMA = "sentientos.resident_developmental_cognition:v1"
CONFIG_SCHEMA = "sentientos.resident_developmental_cognition_config:v1"
CONFIG_SCHEMA_V2 = "sentientos.resident_developmental_cognition_config:v2"
STATE_SCHEMA = "sentientos.resident_developmental_cognition_state:v2"
LEGACY_STATE_SCHEMA = "sentientos.resident_developmental_cognition_state:v1"
COGNITION_PURPOSE = "resident_developmental_retrieval_cognition"
CURRENT_PROJECTION_POLICY = "succession_identity_then_resource_and_transition_evidence_then_source_id:v3"
EXPERIMENT_CONTEXT_INSTRUCTION = (
    "Reason over four separately typed, non-authoritative substrates. Current evidence is current external observation "
    "and outranks a conflicting prior epistemic position for current-condition reasoning. Prior self-model is earlier "
    "evidence-bound system representation. Prior epistemic state is the system's earlier position, not truth or evidence. "
    "Developmental history is earlier interpretation. Preserve contradictions; none is policy, goal, permission, admission, "
    "execution, adoption, or canonical user memory. Resource expenditure is not inherently good or bad and is not a "
    "reward signal. Historical prediction-outcome lineage records bind comparison identities and bounded field outcomes; "
    "they remain claims about their recorded sources, and contradiction is material for reconsideration rather than a "
    "command to believe or act. A missing or indeterminate field is not a satisfied prediction. "
    "Treat measured, estimated, predicted, and unknown quantities according to their source posture; "
    "never infer per-invocation CPU, GPU, energy, or token measurements from shared host use, call counts, output size, "
    "or latency."
)
MAX_FACTS = 16
MAX_HISTORY = 16
MAX_RECOVERED_TICKS = 4096
MAX_RECOVERED_FACT_IDS = 65_536
MAX_COMPOSITION_STATE_BYTES = 16_777_216
MAX_COGNITION_OBSERVATIONS = 12_288
MAX_COGNITION_OBSERVATION_BYTES = 65_536
MAX_COGNITION_OBSERVATION_ROOT_BYTES = 134_217_728
MAX_RESIDENT_COGNITION_CONFIG_BYTES = 65_536
class ResidentDevelopmentalCognitionError(ValueError):
    """Fail-closed composition/configuration violation."""


def _digest(value: Any) -> str:
    return "sha256:" + str(digest_payload(value))


@dataclass(frozen=True)
class ResidentDevelopmentalCognitionConfig:
    history_root: Path
    state_root: Path
    allowed_source_kinds: tuple[str, ...]
    max_selected_facts: int
    max_retrieved_records: int = 4
    comparison_enabled: bool = False
    enabled: bool = True
    model_replacement_artifact_root: Path | None = None


@dataclass(frozen=True)
class ResidentCognitionObservation:
    observation_id: str
    observation_digest: str
    condition_id: str
    tick_id: str
    correlation_id: str
    model_id: str
    model_artifact_digest: str | None
    request_id: str
    request_digest: str
    inference_receipt_id: str
    inference_receipt_digest: str
    output_digest: str
    authority_map_digest: str
    active_model_identity: Mapping[str, Any]
    generation_config: Mapping[str, Any]
    current_snapshot_id: str
    current_snapshot_digest: str
    current_projection_id: str
    current_projection_digest: str
    current_fact_ids: tuple[str, ...]
    retrieved_record_ids: tuple[str, ...]
    retrieved_record_digests: tuple[str, ...]
    developmental_projection_present: bool
    self_model_projection_present: bool = False
    self_model_projection_id: str | None = None
    self_model_projection_digest: str | None = None
    self_model_reconciliation_id: str | None = None
    self_model_reconciliation_digest: str | None = None
    self_model_reconciliation_generation: int | None = None
    self_model_source_tick: str | None = None
    self_model_claim_ids: tuple[str, ...] = ()
    self_model_claim_digests: tuple[str, ...] = ()
    prior_tick_proven: bool = False
    epistemic_projection_present: bool = False
    epistemic_projection_id: str | None = None
    epistemic_projection_digest: str | None = None
    epistemic_proposition_ids: tuple[str, ...] = ()
    epistemic_state_ids: tuple[str, ...] = ()
    epistemic_state_digests: tuple[str, ...] = ()
    epistemic_generations: tuple[int, ...] = ()
    epistemic_evidence_set_digests: tuple[str, ...] = ()
    historical_context_only: bool = True
    current_truth: bool = False
    authority: bool = False
    policy: bool = False
    canonical_explicit_user_retention: bool = False


@dataclass(frozen=True)
class CurrentWorldStateCognitiveProjection:
    snapshot_id: str
    snapshot_digest: str
    facts: tuple[Mapping[str, Any], ...]
    sources: tuple[Mapping[str, Any], ...]
    conflicts: tuple[Mapping[str, Any], ...]
    fact_ids: tuple[str, ...]
    selection_policy: str = CURRENT_PROJECTION_POLICY
    read_only: bool = True
    evidence_only: bool = True
    current_truth: bool = False
    authority: bool = False
    policy: bool = False
    goal: bool = False
    canonical_explicit_user_retention: bool = False
    projection_id: str = ""
    projection_digest: str = ""

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self); value.pop("projection_id"); value.pop("projection_digest"); return value


@dataclass(frozen=True)
class ResidentDevelopmentalCycleResult:
    status: str
    tick_id: str
    snapshot_id: str
    selected_fact_ids: tuple[str, ...] = ()
    prior_record_ids: tuple[str, ...] = ()
    written_record_id: str | None = None
    writeback_receipt_id: str | None = None
    cognition_observation_ids: tuple[str, ...] = ()
    changed_cognition_measurement_id: str | None = None
    same_tick_history_excluded: bool = True
    canonical_explicit_user_retention_mutated: bool = False


def load_config(path: str | Path) -> ResidentDevelopmentalCognitionConfig:
    try:
        payload = json.loads(read_explicit_file(Path(path),
            max_bytes=MAX_RESIDENT_COGNITION_CONFIG_BYTES).decode("utf-8"))
    except (WindowsHandleCustodyError, UnicodeError, OSError, json.JSONDecodeError) as exc:
        raise ResidentDevelopmentalCognitionError("configuration_unreadable_or_invalid_json") from exc
    common = {"schema", "enabled", "history_root", "state_root", "allowed_source_kinds",
              "max_selected_facts", "max_retrieved_records", "comparison_enabled"}
    schema = payload.get("schema") if isinstance(payload, dict) else None
    expected = common if schema == CONFIG_SCHEMA else common | {"model_replacement_artifact_root"}
    if not isinstance(payload, dict) or set(payload) != expected or schema not in {CONFIG_SCHEMA, CONFIG_SCHEMA_V2}:
        raise ResidentDevelopmentalCognitionError("configuration_shape_invalid")
    kinds = payload.get("allowed_source_kinds")
    maximum = payload.get("max_selected_facts")
    history_maximum = payload.get("max_retrieved_records")
    if (not isinstance(payload.get("enabled"), bool) or not isinstance(payload.get("comparison_enabled"), bool)
            or not isinstance(kinds, list) or not kinds or any(not isinstance(x, str) or not x for x in kinds)
            or len(kinds) != len(set(kinds)) or not isinstance(maximum, int) or not 1 <= maximum <= MAX_FACTS
            or not isinstance(history_maximum, int) or not 1 <= history_maximum <= MAX_HISTORY
            or not isinstance(payload.get("history_root"), str) or not payload["history_root"]
            or not isinstance(payload.get("state_root"), str) or not payload["state_root"]):
        raise ResidentDevelopmentalCognitionError("configuration_values_invalid")
    provenance_root = payload.get("model_replacement_artifact_root")
    if schema == CONFIG_SCHEMA_V2 and (not isinstance(provenance_root, str) or not provenance_root):
        raise ResidentDevelopmentalCognitionError("configuration_values_invalid")
    history_root, state_root = Path(payload["history_root"]), Path(payload["state_root"])
    if history_root == state_root:
        raise ResidentDevelopmentalCognitionError("configuration_roots_must_be_separate")
    if provenance_root is not None and Path(provenance_root) in {history_root, state_root}:
        raise ResidentDevelopmentalCognitionError("configuration_artifact_root_must_be_separate")
    return ResidentDevelopmentalCognitionConfig(history_root, state_root, tuple(sorted(kinds)), maximum,
        history_maximum, payload["comparison_enabled"], payload["enabled"],
        Path(provenance_root) if provenance_root is not None else None)


class ResidentDevelopmentalCognitionOwner:
    """Perform at most one deterministic developmental composition per call."""

    def __init__(self, *, config: ResidentDevelopmentalCognitionConfig,
                 writeback: ResidentDevelopmentalWritebackController,
                 admission_authority: RuntimeAdmissionAuthority,
                 invoker: LocalModelInvoker,
                 current_sequence: Callable[[], int]) -> None:
        self.config = config
        self.writeback = writeback
        self.admission_authority = admission_authority
        self.invoker = invoker
        self.current_sequence = current_sequence
        self.state_path = config.state_root / "composition_state.json"
        self.observations_root = config.state_root / "cognition_observations"
        self.measurements_root = config.state_root / "changed_cognition_measurements"
        self.experiments = DevelopmentalExperimentStore(config.state_root)

    def _state(self) -> dict[str, Any]:
        state_migrated = False
        state_bytes: bytes | None = None
        if os.name == "nt":
            try:
                self.state_path.parent.lstat()
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise ResidentDevelopmentalCognitionError("composition_state_unavailable") from exc
            else:
                try:
                    entries = read_regular_files(self.state_path.parent,
                        max_entries=1, max_file_bytes=MAX_COMPOSITION_STATE_BYTES,
                        max_total_bytes=MAX_COMPOSITION_STATE_BYTES,
                        suffix=self.state_path.name)
                except WindowsHandleCustodyError as exc:
                    raise ResidentDevelopmentalCognitionError("composition_state_safe_read_failed") from exc
                if len(entries) > 1:
                    raise ResidentDevelopmentalCognitionError("composition_state_identity_ambiguous")
                if entries:
                    name, state_bytes = entries[0]
                    if name != self.state_path.name:
                        raise ResidentDevelopmentalCognitionError("composition_state_identity_ambiguous")
        else:
            if self.state_path.is_symlink():
                raise ResidentDevelopmentalCognitionError("composition_state_unbounded_or_not_regular")
            if self.state_path.exists():
                descriptor: int | None = None
                try:
                    descriptor = os.open(self.state_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                                         | getattr(os, "O_NONBLOCK", 0))
                    opened = os.fstat(descriptor)
                    if not stat.S_ISREG(opened.st_mode) or opened.st_size > MAX_COMPOSITION_STATE_BYTES:
                        raise ResidentDevelopmentalCognitionError("composition_state_unbounded_or_not_regular")
                    chunks: list[bytes] = []
                    remaining = MAX_COMPOSITION_STATE_BYTES + 1
                    while remaining:
                        chunk = os.read(descriptor, min(65_536, remaining))
                        if not chunk:
                            break
                        chunks.append(chunk); remaining -= len(chunk)
                    state_bytes = b"".join(chunks)
                    after = os.fstat(descriptor)
                    if (len(state_bytes) > MAX_COMPOSITION_STATE_BYTES or len(state_bytes) != opened.st_size
                            or after.st_size != opened.st_size or after.st_mtime_ns != opened.st_mtime_ns
                            or after.st_dev != opened.st_dev or after.st_ino != opened.st_ino):
                        raise ResidentDevelopmentalCognitionError("composition_state_unbounded_or_not_regular")
                except (OSError, ValueError) as exc:
                    raise ResidentDevelopmentalCognitionError("composition_state_corrupt") from exc
                finally:
                    if descriptor is not None:
                        os.close(descriptor)
        if state_bytes is None:
            semantic = {"schema": STATE_SCHEMA, "processed_selection_ids": [], "completed_ticks": [],
                "incomplete_ticks": []}
            state = {**semantic, "state_digest": _digest(semantic)}
        else:
            try:
                value = json.loads(state_bytes.decode("utf-8"))
                if (not isinstance(value, dict)
                        or json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n" != state_bytes):
                    raise ResidentDevelopmentalCognitionError("composition_state_noncanonical")
                claimed = value.pop("state_digest")
            except (UnicodeError, json.JSONDecodeError, KeyError, AttributeError, TypeError) as exc:
                raise ResidentDevelopmentalCognitionError("composition_state_corrupt") from exc
            if value.get("schema") not in {STATE_SCHEMA, LEGACY_STATE_SCHEMA} or claimed != _digest(value):
                raise ResidentDevelopmentalCognitionError("composition_state_digest_mismatch")
            if (not isinstance(value.get("processed_selection_ids"), list)
                    or any(not isinstance(item, str) for item in value["processed_selection_ids"])
                    or not isinstance(value.get("completed_ticks"), list)
                    or any(not isinstance(item, dict) for item in value["completed_ticks"])):
                raise ResidentDevelopmentalCognitionError("composition_state_shape_invalid")
            if value.get("schema") == LEGACY_STATE_SCHEMA:
                value["schema"] = STATE_SCHEMA
                value["incomplete_ticks"] = []
                state_migrated = True
            elif (not isinstance(value.get("incomplete_ticks"), list)
                    or any(not isinstance(item, dict) for item in value["incomplete_ticks"])):
                raise ResidentDevelopmentalCognitionError("composition_state_shape_invalid")
            migrated = {key: item for key, item in value.items() if key != "state_digest"}
            claimed = _digest(migrated)
            state = {**migrated, "state_digest": claimed}
        if (len(state["processed_selection_ids"]) > MAX_RECOVERED_FACT_IDS
                or len(state["completed_ticks"]) + len(state["incomplete_ticks"]) > MAX_RECOVERED_TICKS):
            raise ResidentDevelopmentalCognitionError("composition_state_retention_limit_exceeded")
        changed = state_migrated
        # The record and receipt are the commit point. Rebuild the checkpoint
        # if a process stopped after publication but before composition_state.
        try:
            recovered = self.writeback.recover_completed_records()
        except Exception as exc:
            raise ResidentDevelopmentalCognitionError("developmental_history_recovery_failed") from exc
        def recovery_order(item: tuple[Any, Any]) -> tuple[float, str]:
            record = item[0]
            try:
                created = datetime.fromisoformat(record.created_at.replace("Z", "+00:00"))
                if created.tzinfo is None:
                    raise ValueError("naive")
            except (AttributeError, TypeError, ValueError) as exc:
                raise ResidentDevelopmentalCognitionError("recovered_history_time_invalid") from exc
            return created.astimezone(timezone.utc).timestamp(), record.record_id
        recovered = tuple(sorted(recovered, key=recovery_order))
        processed = set(state["processed_selection_ids"])
        ticks: dict[str, dict[str, Any]] = {}
        for row in state["completed_ticks"]:
            saved_tick = row.get("tick_id")
            if not isinstance(saved_tick, str) or not saved_tick or saved_tick in ticks:
                raise ResidentDevelopmentalCognitionError("composition_tick_identity_ambiguous")
            ticks[saved_tick] = row
        incomplete: dict[str, dict[str, Any]] = {}
        for row in state["incomplete_ticks"]:
            saved_tick = row.get("tick_id")
            if not isinstance(saved_tick, str) or not saved_tick or saved_tick in incomplete or saved_tick in ticks:
                raise ResidentDevelopmentalCognitionError("composition_tick_identity_ambiguous")
            if row.get("status") == "in_progress":
                # The durable marker is written before any cognition call. If
                # it is still present on the next owner entry, completion was
                # interrupted; preserve that fact and never retry this tick.
                row["status"] = "interrupted_recovered"
                changed = True
            incomplete[saved_tick] = row
        for record, receipt in recovered:
            candidate = record.candidate
            fact_ids = candidate.get("selected_fact_ids", ())
            if not isinstance(fact_ids, (list, tuple)) or any(not isinstance(item, str) for item in fact_ids):
                raise ResidentDevelopmentalCognitionError("recovered_fact_identity_invalid")
            for fact_id in fact_ids:
                if fact_id not in processed:
                    state["processed_selection_ids"].append(fact_id)
                    processed.add(fact_id)
                    changed = True
            suffix = ":resident-developmental-writeback"
            correlation = record.correlation_id
            if not correlation.endswith(suffix):
                raise ResidentDevelopmentalCognitionError("recovered_tick_correlation_invalid")
            recovered_tick = correlation[:-len(suffix)]
            expected_operation = "resident-developmental-writeback:" + recovered_tick + ":" + str(candidate.get("candidate_id"))
            if not recovered_tick or record.operation_id != expected_operation:
                raise ResidentDevelopmentalCognitionError("recovered_tick_operation_binding_invalid")
            existing = ticks.get(recovered_tick)
            checkpoint = {"tick_id": recovered_tick, "snapshot_id": candidate.get("snapshot_id"),
                "snapshot_digest": candidate.get("snapshot_digest"), "record_id": record.record_id,
                "receipt_id": receipt.receipt_id}
            if existing is None:
                state["completed_ticks"].append(checkpoint)
                ticks[recovered_tick] = checkpoint
                changed = True
            elif existing.get("record_id") != record.record_id or existing.get("receipt_id") != receipt.receipt_id:
                raise ResidentDevelopmentalCognitionError("recovered_tick_record_conflict")
            if recovered_tick in incomplete:
                del incomplete[recovered_tick]
                state["incomplete_ticks"] = [row for row in state["incomplete_ticks"]
                    if row.get("tick_id") != recovered_tick]
                changed = True
        # A durable cognition observation without its enclosing tick checkpoint
        # is an interrupted tick. Preserve it and reject same-tick replay.
        for recovered_tick, observation_ids in self._recover_observation_ticks().items():
            if recovered_tick in ticks or recovered_tick in incomplete:
                continue
            item = {"tick_id": recovered_tick, "observation_ids": list(observation_ids),
                "status": "incomplete_recovered"}
            state["incomplete_ticks"].append(item)
            incomplete[recovered_tick] = item
            changed = True
        if (len(state["processed_selection_ids"]) > MAX_RECOVERED_FACT_IDS
                or len(state["completed_ticks"]) + len(state["incomplete_ticks"]) > MAX_RECOVERED_TICKS):
            raise ResidentDevelopmentalCognitionError("composition_state_retention_limit_exceeded")
        if changed:
            self._save_state(state)
        return state

    def _recover_observation_ticks(self, *, include_records: bool = False) -> Any:
        try:
            self.observations_root.lstat()
        except FileNotFoundError:
            return {}
        except OSError as exc:
            raise ResidentDevelopmentalCognitionError("cognition_observation_root_invalid") from exc
        entries: list[tuple[str, bytes]] = []
        if os.name == "nt":
            try:
                entries = read_regular_files(self.observations_root,
                    max_entries=MAX_COGNITION_OBSERVATIONS,
                    max_file_bytes=MAX_COGNITION_OBSERVATION_BYTES,
                    max_total_bytes=MAX_COGNITION_OBSERVATION_ROOT_BYTES)
            except WindowsHandleCustodyError as exc:
                raise ResidentDevelopmentalCognitionError("cognition_observation_windows_recovery_failed") from exc
            total_bytes = sum(len(raw) for _name, raw in entries)
            if total_bytes > MAX_COGNITION_OBSERVATION_ROOT_BYTES:
                raise ResidentDevelopmentalCognitionError("cognition_observation_retention_limit_exceeded")
        else:
            nofollow = getattr(os, "O_NOFOLLOW", None)
            directory_flag = getattr(os, "O_DIRECTORY", None)
            if nofollow is None or directory_flag is None or os.open not in os.supports_dir_fd:
                raise ResidentDevelopmentalCognitionError("cognition_observation_safe_reads_unsupported")
            try:
                root_fd = os.open(self.observations_root,
                    os.O_RDONLY | directory_flag | nofollow | getattr(os, "O_NONBLOCK", 0))
            except FileNotFoundError:
                return {}
            except OSError as exc:
                raise ResidentDevelopmentalCognitionError("cognition_observation_root_invalid") from exc
            total_bytes = 0
            try:
                root_stat = os.fstat(root_fd)
                if not stat.S_ISDIR(root_stat.st_mode):
                    raise ResidentDevelopmentalCognitionError("cognition_observation_root_invalid")
                names = sorted(name for name in os.listdir(root_fd) if name.endswith(".json"))
                if len(names) > MAX_COGNITION_OBSERVATIONS:
                    raise ResidentDevelopmentalCognitionError("cognition_observation_retention_limit_exceeded")
                for name in names:
                    if not name or name in {".", ".."} or "/" in name or "\\" in name:
                        raise ResidentDevelopmentalCognitionError("cognition_observation_not_regular")
                    descriptor: int | None = None
                    try:
                        descriptor = os.open(name, os.O_RDONLY | nofollow | getattr(os, "O_NONBLOCK", 0),
                                             dir_fd=root_fd)
                        opened = os.fstat(descriptor)
                        if not stat.S_ISREG(opened.st_mode) or opened.st_size > MAX_COGNITION_OBSERVATION_BYTES:
                            raise ResidentDevelopmentalCognitionError("cognition_observation_not_regular")
                        chunks: list[bytes] = []
                        remaining = MAX_COGNITION_OBSERVATION_BYTES + 1
                        while remaining:
                            chunk = os.read(descriptor, min(65_536, remaining))
                            if not chunk:
                                break
                            chunks.append(chunk)
                            remaining -= len(chunk)
                        raw = b"".join(chunks)
                        after = os.fstat(descriptor)
                        if (len(raw) > MAX_COGNITION_OBSERVATION_BYTES or len(raw) != opened.st_size
                                or after.st_size != opened.st_size or after.st_mtime_ns != opened.st_mtime_ns
                                or after.st_dev != opened.st_dev or after.st_ino != opened.st_ino):
                            raise ResidentDevelopmentalCognitionError("cognition_observation_corrupt")
                        total_bytes += len(raw)
                        if total_bytes > MAX_COGNITION_OBSERVATION_ROOT_BYTES:
                            raise ResidentDevelopmentalCognitionError("cognition_observation_retention_limit_exceeded")
                        entries.append((name, raw))
                    except ResidentDevelopmentalCognitionError:
                        raise
                    except OSError as exc:
                        raise ResidentDevelopmentalCognitionError("cognition_observation_corrupt") from exc
                    finally:
                        if descriptor is not None:
                            os.close(descriptor)
            finally:
                os.close(root_fd)
        by_tick: dict[str, list[str]] = {}
        verified_records: dict[str, dict[str, Any]] = {}
        contexts_by_tick: dict[str, tuple[set[str], tuple[str, str]]] = {}
        for name, raw in entries:
            try:
                value = json.loads(raw.decode("utf-8"))
                if (not isinstance(value, dict)
                        or json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n" != raw):
                    raise ResidentDevelopmentalCognitionError("cognition_observation_noncanonical")
                observation_id = value.pop("observation_id")
                observation_digest = value.pop("observation_digest")
            except (UnicodeError, json.JSONDecodeError, KeyError, AttributeError, TypeError) as exc:
                raise ResidentDevelopmentalCognitionError("cognition_observation_corrupt") from exc
            expected_fields = set(ResidentCognitionObservation.__dataclass_fields__) - {
                "observation_id", "observation_digest"}
            if (not isinstance(value, dict) or set(value) != expected_fields
                    or not isinstance(value.get("tick_id"), str) or not value["tick_id"]
                    or observation_digest != _digest(value)
                    or observation_id != "devcog-" + observation_digest[7:31]
                    or name != observation_id + ".json"):
                raise ResidentDevelopmentalCognitionError("cognition_observation_digest_mismatch")
            tick = value["tick_id"]
            condition = value.get("condition_id")
            snapshot_binding = (value.get("current_snapshot_id"), value.get("current_snapshot_digest"))
            allowed_conditions = {"prior-context", "with-history", "history_present",
                "history_withheld", "history_restored"}
            if (not isinstance(condition, str) or condition not in allowed_conditions
                    or value.get("correlation_id") !=
                        f"{tick}:resident_developmental_cognition:{condition}"
                    or type(value.get("prior_tick_proven")) is not bool
                    or type(value.get("self_model_projection_present")) is not bool
                    or not all(isinstance(item, str) and item for item in snapshot_binding)
                    or (value.get("prior_tick_proven") is True and (
                        value.get("self_model_projection_present") is not True
                        or not isinstance(value.get("self_model_source_tick"), str)
                        or value.get("self_model_source_tick") == tick))
                    or (value.get("self_model_projection_present") is True
                        and value.get("prior_tick_proven") is not True)):
                raise ResidentDevelopmentalCognitionError("cognition_observation_lineage_invalid")
            prior_context = contexts_by_tick.get(tick)
            if prior_context is None:
                contexts_by_tick[tick] = ({str(condition)}, snapshot_binding)
            else:
                conditions, prior_snapshot = prior_context
                if condition in conditions or snapshot_binding != prior_snapshot:
                    raise ResidentDevelopmentalCognitionError("cognition_observation_tick_conflict")
                conditions.add(str(condition))
            by_tick.setdefault(value["tick_id"], []).append(observation_id)
            verified_records[observation_id] = {
                **value, "observation_id": observation_id,
                "observation_digest": observation_digest}
        if include_records:
            return verified_records
        return {tick: tuple(sorted(ids)) for tick, ids in by_tick.items()}

    def verified_cognition_observation(self, observation_id: str,
                                       observation_digest: str | None = None) -> Mapping[str, Any]:
        """Re-read one bounded, canonical cognition observation from configured custody."""
        if (not isinstance(observation_id, str) or not observation_id.startswith("devcog-")
                or (observation_digest is not None and (not isinstance(observation_digest, str) or not observation_digest.startswith("sha256:")))):
            raise ResidentDevelopmentalCognitionError("cognition_observation_identity_invalid")
        records = self._recover_observation_ticks(include_records=True)
        observation = records.get(observation_id)
        if (not isinstance(observation, Mapping)
                or (observation_digest is not None and observation.get("observation_digest") != observation_digest)):
            raise ResidentDevelopmentalCognitionError("cognition_observation_not_verified")
        return dict(observation)

    def verify_transition_observation(self, *, stage: str, evidence: Mapping[str, Any],
                                     expected_model_identity: Mapping[str, Any],
                                     expected_serving_session: Mapping[str, Any],
                                     b_epoch_evidence: Mapping[str, Any] | None = None) -> None:
        """Qualify A/B transition observations against durable history and invocation owners."""
        if stage not in {"b_epoch_observed", "post_restoration_observed"}:
            raise ResidentDevelopmentalCognitionError("transition_observation_stage_invalid")
        allowed_fields = ({"b_tick_id", "b_observation_id", "b_observation_digest",
            "b_record_id", "b_record_digest", "b_writeback_receipt_id",
            "b_writeback_receipt_digest", "operator_request"} if stage == "b_epoch_observed" else
            {"restored_a_tick_id", "restored_a_observation_id", "restored_a_observation_digest",
            "restored_a_inference_receipt_id", "restored_a_inference_receipt_digest",
            "retrieved_record_ids", "retrieved_record_digests", "operator_request"})
        if not isinstance(evidence, Mapping) or set(evidence) - allowed_fields:
            raise ResidentDevelopmentalCognitionError("transition_observation_evidence_shape_invalid")
        if not isinstance(expected_serving_session, Mapping):
            raise ResidentDevelopmentalCognitionError("transition_serving_session_missing")
        session_binding = expected_serving_session.get("binding")
        session_id = expected_serving_session.get("session_id")
        if (not isinstance(session_binding, Mapping) or not isinstance(session_id, str)
                or not session_id):
            raise ResidentDevelopmentalCognitionError("transition_serving_session_invalid")
        observation_id = evidence.get("b_observation_id") if stage == "b_epoch_observed" else evidence.get("restored_a_observation_id")
        observation_digest = evidence.get("b_observation_digest") if stage == "b_epoch_observed" else evidence.get("restored_a_observation_digest")
        observation = self.verified_cognition_observation(str(observation_id or ""), str(observation_digest or ""))
        tick_id = evidence.get("b_tick_id") if stage == "b_epoch_observed" else evidence.get("restored_a_tick_id")
        if (not isinstance(tick_id, str) or not tick_id or observation.get("tick_id") != tick_id
                or observation.get("active_model_identity") != dict(expected_model_identity)):
            raise ResidentDevelopmentalCognitionError("transition_observation_model_or_tick_mismatch")
        verify_invocation = getattr(self.invoker, "verify_persisted_invocation_receipt", None)
        if not callable(verify_invocation):
            raise ResidentDevelopmentalCognitionError("transition_invocation_receipt_verifier_unavailable")

        def verify_observation_invocation() -> Mapping[str, Any]:
            receipt = verify_invocation(
                str(observation.get("inference_receipt_id", "")),
                str(observation.get("inference_receipt_digest", "")),
                expected_request_id=str(observation.get("request_id", "")),
                expected_request_digest=str(observation.get("request_digest", "")),
                expected_session_id=session_id,
                expected_session_binding=session_binding,
                expected_active_model_identity=expected_model_identity)
            request = receipt.get("request")
            if (not isinstance(request, Mapping)
                    or receipt.get("status") not in {"admitted_completed", "admitted_simulation"}
                    or not isinstance(receipt.get("output_digest"), str)
                    or request.get("model_id") != observation.get("model_id")
                    or request.get("model_artifact_digest") != observation.get("model_artifact_digest")
                    or receipt.get("output_digest") != observation.get("output_digest")):
                raise ResidentDevelopmentalCognitionError("transition_observation_invocation_model_mismatch")
            return receipt

        observed_invocation = verify_observation_invocation()
        if (stage == "post_restoration_observed"
                and (evidence.get("restored_a_inference_receipt_id") != observed_invocation.get("receipt_id")
                     or evidence.get("restored_a_inference_receipt_digest") != observed_invocation.get("receipt_digest"))):
            raise ResidentDevelopmentalCognitionError("transition_restoration_invocation_binding_mismatch")
        if stage == "b_epoch_observed":
            record_id = evidence.get("b_record_id")
            record_digest = evidence.get("b_record_digest")
            receipt_id = evidence.get("b_writeback_receipt_id")
            receipt_digest = evidence.get("b_writeback_receipt_digest")
            try:
                record = self.writeback.store.get(str(record_id))
                receipt = self.writeback.store.get_receipt(str(receipt_id))
            except Exception as exc:
                raise ResidentDevelopmentalCognitionError("transition_b_epoch_writeback_missing_or_invalid") from exc
            candidate = record.candidate
            if (record.record_digest != record_digest
                    or receipt.receipt_digest != receipt_digest
                    or receipt.record_id != record.record_id
                    or receipt.record_digest != record.record_digest
                    or receipt.candidate_id != candidate.get("candidate_id")
                    or receipt.candidate_digest != candidate.get("candidate_digest")
                    or receipt.storage_verified is not True
                    or record.correlation_id != tick_id + ":resident-developmental-writeback"
                    or record.operation_id != "resident-developmental-writeback:" + tick_id + ":" + str(candidate.get("candidate_id"))
                    or candidate.get("snapshot_id") != observation.get("current_snapshot_id")
                    or candidate.get("snapshot_digest") != observation.get("current_snapshot_digest")):
                raise ResidentDevelopmentalCognitionError("transition_b_epoch_writeback_lineage_mismatch")
            candidate_receipt = verify_invocation(
                str(candidate.get("inference_receipt_id", "")),
                str(candidate.get("inference_receipt_digest", "")),
                expected_request_id=str(candidate.get("request_id", "")),
                expected_request_digest=str(candidate.get("request_digest", "")),
                expected_session_id=session_id,
                expected_active_model_identity=expected_model_identity)
            candidate_request = candidate_receipt.get("request")
            if (not isinstance(candidate_request, Mapping)
                    or candidate_receipt.get("status") not in {"admitted_completed", "admitted_simulation"}
                    or candidate_request.get("purpose") != "resident_developmental_interpretation"
                    or candidate_request.get("correlation_id") != tick_id + ":resident-developmental_interpretation"
                    or candidate.get("model_id") != candidate_request.get("model_id")
                    or candidate.get("model_artifact_digest") != candidate_request.get("model_artifact_digest")
                    or candidate_receipt.get("output_digest") != candidate.get("output_digest")):
                raise ResidentDevelopmentalCognitionError("transition_b_epoch_candidate_invocation_mismatch")
            return
        if not isinstance(b_epoch_evidence, Mapping):
            raise ResidentDevelopmentalCognitionError("transition_b_epoch_evidence_missing")
        b_record_id = b_epoch_evidence.get("b_record_id")
        b_record_digest = b_epoch_evidence.get("b_record_digest")
        retrieved_ids = evidence.get("retrieved_record_ids")
        retrieved_digests = evidence.get("retrieved_record_digests")
        if (not isinstance(retrieved_ids, (list, tuple))
                or not isinstance(retrieved_digests, (list, tuple))
                or len(retrieved_ids) != len(retrieved_digests)
                or list(retrieved_ids) != list(observation.get("retrieved_record_ids", ()))
                or list(retrieved_digests) != list(observation.get("retrieved_record_digests", ()))
                or len(retrieved_ids) > MAX_HISTORY
                or len(set(retrieved_ids)) != len(retrieved_ids)
                or not all(isinstance(item, str) and item.startswith("sha256:") for item in retrieved_digests)
                or not any(record_id == b_record_id and record_digest == b_record_digest
                           for record_id, record_digest in zip(retrieved_ids, retrieved_digests))):
            raise ResidentDevelopmentalCognitionError("transition_restoration_history_binding_mismatch")
        for record_id, expected_digest in zip(retrieved_ids, retrieved_digests):
            try:
                record = self.writeback.store.get(str(record_id))
            except Exception as exc:
                raise ResidentDevelopmentalCognitionError("transition_retrieved_history_not_durable") from exc
            if record.record_digest != expected_digest:
                raise ResidentDevelopmentalCognitionError("transition_retrieved_history_digest_mismatch")

    def _save_state(self, state: Mapping[str, Any]) -> None:
        if os.name != "posix":
            raise ResidentDevelopmentalCognitionError("composition_state_publication_unsupported_platform")
        semantic = {k: v for k, v in state.items() if k != "state_digest"}
        if (len(semantic.get("processed_selection_ids", ())) > MAX_RECOVERED_FACT_IDS
                or len(semantic.get("completed_ticks", ())) + len(semantic.get("incomplete_ticks", ())) > MAX_RECOVERED_TICKS):
            raise ResidentDevelopmentalCognitionError("composition_state_retention_limit_exceeded")
        if len(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode("utf-8")) > MAX_COMPOSITION_STATE_BYTES:
            raise ResidentDevelopmentalCognitionError("composition_state_unbounded")
        atomic_write_json(self.state_path, {**semantic, "state_digest": _digest(semantic)})

    def _prior_projection(self, state: Mapping[str, Any], tick_id: str) -> DevelopmentalHistoryProjection:
        try:
            current_tick = datetime.fromisoformat(tick_id.replace("Z", "+00:00"))
        except (OverflowError, OSError, ValueError):
            current_tick = None
        if current_tick is not None and (current_tick.tzinfo is None or current_tick.utcoffset() is None):
            current_tick = None
        if current_tick is not None:
            current_tick = current_tick.astimezone(timezone.utc)
        ids: list[str] = []
        for completed in state["completed_ticks"]:
            try:
                completed_tick = datetime.fromisoformat(
                    str(completed.get("tick_id", "")).replace("Z", "+00:00"))
            except (OverflowError, OSError, ValueError):
                completed_tick = None
            if completed_tick is not None and (
                    completed_tick.tzinfo is None or completed_tick.utcoffset() is None):
                completed_tick = None
            if (current_tick is not None and completed_tick is not None
                    and completed.get("tick_id") != tick_id
                    and completed_tick.astimezone(timezone.utc) < current_tick
                    and completed.get("record_id")):
                ids.append(str(completed["record_id"]))
        ids = ids[-self.config.max_retrieved_records:]
        return self.writeback.retrieve(ids, limit=self.config.max_retrieved_records)

    def _select_fact_ids(self, snapshot: WorldStateSnapshot, processed: set[str]) -> tuple[str, ...]:
        allowed = set(self.config.allowed_source_kinds)
        source_kinds = {source.source_id: source.kind for source in snapshot.sources}
        candidates = sorted(
            (fact for fact in snapshot.facts if source_kinds.get(fact.source.source_id) in allowed),
            key=lambda fact: self._fact_selection_key(fact, source_kinds[fact.source.source_id]),
        )
        selected: list[str] = []
        for fact in candidates:
            trial = self.writeback.select_evidence(snapshot, fact_ids=(fact.fact_id,))
            # Fact IDs remain stable when the same immutable source is observed
            # in a later snapshot. Selection IDs include snapshot identity and
            # are accepted only for compatibility with pre-recovery state files.
            if fact.fact_id not in processed and trial.selection_id not in processed:
                selected.append(fact.fact_id)
            if len(selected) == self.config.max_selected_facts:
                break
        return tuple(selected)

    @staticmethod
    def _fact_selection_key(fact: Any, source_kind: str) -> tuple[Any, ...]:
        """Keep current identities and qualified causal evidence ahead of journal volume."""
        subject_kind = str(fact.subject.subject_kind)
        payload = fact.payload
        resource_lineage_verified = (
            source_kind == "resource_governor"
            and subject_kind == "causal_resource_consumption"
            and fact.disposition == "recorded"
            and payload.get("lineage_posture") == "verified"
            and payload.get("recovery_posture") == "reconciled_or_restored"
            and payload.get("attribution_posture") == "receipt_bound_only"
        )
        strategy_resource_lineage_verified = (
            source_kind == "resource_governor"
            and subject_kind in {"strategy_invocation_resource_lineage",
                "model_replacement_invocation_resource_lineage"}
            and fact.disposition == "verified"
            and isinstance(payload.get("resource_linkage"), Mapping)
            and bool(payload.get("principal_binding_digest"))
            and payload.get("lineage_findings") == []
        )
        chat_process_generation_verified = (
            source_kind == "resource_governor"
            and subject_kind == "chat_process_software_generation_invocation"
            and fact.disposition == "recorded"
            and payload.get("attribution_posture")
                == "invocation_receipt_and_historical_chat_handoff_verified"
            and isinstance(payload.get("chat_process_handoff"), Mapping)
            and isinstance(payload.get("invocation_receipt_digest"), str)
        )
        chat_process_recovery_lineage = (
            source_kind == "runtime_supervisor"
            and subject_kind == "chat_process_recovery_transition"
            and isinstance(payload.get("chat_process_recovery_transition"), Mapping)
            and payload["chat_process_recovery_transition"].get("phase_evidence_posture")
                == "canonical_installation_custody_and_digest_chain_checked_not_independently_signed"
            and payload["chat_process_recovery_transition"].get("effect_authority") is False
            and payload["chat_process_recovery_transition"].get("inference_performed") is False
        )
        if subject_kind in {"observed_running_model", "observed_running_software_generation"}:
            priority = 0
        elif payload.get("activated_model_identity") is not None or payload.get("serving_binding_digest"):
            priority = 1
        elif (isinstance(payload.get("proposed_successor_model_development_provenance"), Mapping)
                and payload["proposed_successor_model_development_provenance"].get("identity_binding_verified") is True):
            priority = 2
        elif resource_lineage_verified:
            priority = 3
        elif strategy_resource_lineage_verified or chat_process_generation_verified:
            priority = 3
        elif (source_kind == "runtime_supervisor"
                and subject_kind in {"resident_model_transition", "software_generation_transition"}
                and payload.get("stage_semantically_verified") is True):
            priority = 4
        elif chat_process_recovery_lineage:
            priority = 4
        elif subject_kind in {"resident_model_transition", "software_generation_transition",
                              "resident_model_transition_recovery", "software_generation_transition_recovery"}:
            priority = 6
        elif (source_kind == "embodiment"
                and subject_kind == "developmental_model_replacement_experiment"):
            priority = 4
        elif (source_kind == "embodiment" and subject_kind in {
                "embodied_consequence_chain", "embodied_consequence_attribution",
                "embodied_prediction_comparison"}):
            priority = 4
        elif subject_kind in {"embodied_strategy_proposal", "embodied_strategy_proposal_review",
                              "embodied_proposal_fulfillment_receipt"}:
            priority = 5
        else:
            priority = 6
        return priority, source_kind, fact.source.source_id, fact.fact_id

    def _current_projection(self, snapshot: WorldStateSnapshot) -> CurrentWorldStateCognitiveProjection:
        """Select current context independently of developmental-writeback deduplication."""
        allowed = set(self.config.allowed_source_kinds)
        source_kinds = {source.source_id: source.kind for source in snapshot.sources}
        facts = sorted((fact for fact in snapshot.facts if source_kinds.get(fact.source.source_id) in allowed),
                       key=lambda fact: self._fact_selection_key(fact, source_kinds[fact.source.source_id]))[:self.config.max_selected_facts]
        selected = self.writeback.select_evidence(snapshot, fact_ids=tuple(f.fact_id for f in facts))
        raw = CurrentWorldStateCognitiveProjection(snapshot.snapshot_id, snapshot.digest, selected.facts,
                                                    selected.sources, selected.conflicts,
                                                    tuple(str(x["fact_id"]) for x in selected.facts))
        digest = _digest(raw.semantic_payload())
        return replace(raw, projection_id="current-world-state-" + digest[7:31], projection_digest=digest)

    def _cognize(self, *, snapshot: WorldStateSnapshot, current: CurrentWorldStateCognitiveProjection, tick_id: str,
                  projection: DevelopmentalHistoryProjection, with_history: bool,
                  prior_self_model: CognitiveSelfModelProjection | None = None,
                  prior_epistemic_state: EpistemicCognitiveProjection | None = None,
                  condition_id: str, purpose: str = COGNITION_PURPOSE,
                  protocol: Any | None = None) -> ResidentCognitionObservation:
        records = projection.records if with_history else ()
        record_ids = projection.requested_record_ids if with_history else ()
        record_digests = tuple(str(record["record_digest"]) for record in records)
        context = {
            "instruction": EXPERIMENT_CONTEXT_INSTRUCTION if protocol is not None else (
                EXPERIMENT_CONTEXT_INSTRUCTION + " Prior context can inform interpretation but does not grant authority."),
            "current_evidence": current.semantic_payload(),
            "prior_self_model": asdict(prior_self_model) if prior_self_model is not None else None,
            "prior_epistemic_state": asdict(prior_epistemic_state) if prior_epistemic_state is not None else None,
            "developmental_history": list(records),
            "developmental_history_posture": "historical_interpretation_not_current_truth",
        }
        correlation = f"{tick_id}:resident_developmental_cognition:{condition_id}"
        request = self.invoker.build_request(
            purpose=purpose, prompt=json.dumps(context, sort_keys=True), caller=PRINCIPAL,
            correlation_id=correlation, expected_output_format="text",
            budget=LocalModelInvocationBudget(max_input_chars=16000, max_output_chars=4000, max_new_tokens=512,
                                              timeout_seconds=30, max_calls_per_correlation=1),
            upstream_evidence={"snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest,
                               "current_projection_id": current.projection_id,
                               "current_projection_digest": current.projection_digest,
                               "current_fact_ids": list(current.fact_ids),
                               "self_model_projection_present": prior_self_model is not None,
                               "self_model_projection_id": prior_self_model.projection_id if prior_self_model else None,
                               "self_model_projection_digest": prior_self_model.projection_digest if prior_self_model else None,
                               "self_model_reconciliation_id": prior_self_model.source_reconciliation_id if prior_self_model else None,
                               "self_model_reconciliation_digest": prior_self_model.source_reconciliation_digest if prior_self_model else None,
                               "self_model_reconciliation_generation": prior_self_model.source_reconciliation_generation if prior_self_model else None,
                               "self_model_source_tick": prior_self_model.source_tick if prior_self_model else None,
                               "self_model_claim_ids": list(prior_self_model.selected_claim_ids) if prior_self_model else [],
                               "self_model_claim_digests": list(prior_self_model.selected_claim_digests) if prior_self_model else [],
                               "epistemic_projection_id": prior_epistemic_state.projection_id if prior_epistemic_state else None,
                               "epistemic_projection_digest": prior_epistemic_state.projection_digest if prior_epistemic_state else None,
                               "epistemic_proposition_ids": list(prior_epistemic_state.proposition_ids) if prior_epistemic_state else [],
                               "epistemic_state_ids": list(prior_epistemic_state.state_ids) if prior_epistemic_state else [],
                               "epistemic_state_digests": list(prior_epistemic_state.state_digests) if prior_epistemic_state else [],
                               "epistemic_generations": list(prior_epistemic_state.generations) if prior_epistemic_state else [],
                               "epistemic_evidence_set_digests": list(prior_epistemic_state.evidence_set_digests) if prior_epistemic_state else [],
                               "record_ids": list(record_ids), "record_digests": list(record_digests)},
            linkage={"condition_group": f"{tick_id}:retrieval-comparison", "condition_id": condition_id,
                     "history_present": with_history},
        )
        if protocol is not None and (
            request.model_id != protocol.model_id
            or request.model_artifact_digest != protocol.model_artifact_digest
            or str(getattr(request, "authority_map_digest", "test-authority-map")) != protocol.authority_map_digest
            or dict(getattr(request, "active_model_identity", {})) != dict(protocol.active_model_identity)
            or request.budget.to_dict() != dict(protocol.inference_budget)
            or protocol.instruction_template_digest != _digest({"instruction": EXPERIMENT_CONTEXT_INSTRUCTION})
            or snapshot.snapshot_id != protocol.snapshot_id
            or snapshot.digest != protocol.snapshot_digest
            or current.projection_id != protocol.current_projection_id
            or current.projection_digest != protocol.current_projection_digest
            or tuple(current.fact_ids) != protocol.current_fact_ids
            or (prior_self_model.projection_id if prior_self_model else None) != protocol.self_model_projection_id
            or (prior_self_model.projection_digest if prior_self_model else None) != protocol.self_model_projection_digest
            or (prior_self_model.source_reconciliation_id if prior_self_model else None) != protocol.self_model_reconciliation_id
            or (prior_self_model.source_reconciliation_digest if prior_self_model else None) != protocol.self_model_reconciliation_digest
            or (prior_self_model.source_reconciliation_generation if prior_self_model else None) != protocol.self_model_reconciliation_generation
            or (prior_self_model.source_tick if prior_self_model else None) != protocol.self_model_source_tick
            or (prior_self_model.selected_claim_ids if prior_self_model else ()) != protocol.self_model_claim_ids
            or (prior_self_model.selected_claim_digests if prior_self_model else ()) != protocol.self_model_claim_digests
        ):
            raise ResidentDevelopmentalCognitionError("experiment_control_drift")
        if protocol is not None:
            expected_ids = protocol.record_ids if with_history else ()
            expected_digests = protocol.record_digests if with_history else ()
            if tuple(record_ids) != tuple(expected_ids) or tuple(record_digests) != tuple(expected_digests):
                raise ResidentDevelopmentalCognitionError("experiment_history_binding_drift")
        receipt = self.invoker.invoke(request, persist=True, include_output_in_receipt=False)
        if receipt.status not in {"admitted_completed", "admitted_simulation"} or receipt.output_digest is None:
            raise ResidentDevelopmentalCognitionError("retrieval_cognition_not_completed")
        if protocol is not None and dict(receipt.generation_config).get("actual_generation_parameters", {}).get("temperature") != 0:
            raise ResidentDevelopmentalCognitionError("experiment_generation_configuration_drift")
        req = dict(receipt.request)
        semantic = {
            "condition_id": condition_id, "tick_id": tick_id, "correlation_id": correlation,
            "model_id": str(req["model_id"]), "model_artifact_digest": req.get("model_artifact_digest"),
            "request_id": str(req["request_id"]), "request_digest": str(req["request_digest"]),
            "inference_receipt_id": receipt.receipt_id, "inference_receipt_digest": receipt.receipt_digest,
            "output_digest": receipt.output_digest,
            "authority_map_digest":str(getattr(request, "authority_map_digest", "test-authority-map")),
            "active_model_identity":dict(getattr(request, "active_model_identity", {})),
            "generation_config":dict(receipt.generation_config), "current_snapshot_id": snapshot.snapshot_id,
            "current_snapshot_digest": snapshot.digest, "current_projection_id":current.projection_id,
            "current_projection_digest":current.projection_digest, "current_fact_ids":current.fact_ids,
            "retrieved_record_ids": record_ids,
            "retrieved_record_digests": record_digests, "developmental_projection_present": with_history,
            "self_model_projection_present": prior_self_model is not None,
            "self_model_projection_id": prior_self_model.projection_id if prior_self_model else None,
            "self_model_projection_digest": prior_self_model.projection_digest if prior_self_model else None,
            "self_model_reconciliation_id": prior_self_model.source_reconciliation_id if prior_self_model else None,
            "self_model_reconciliation_digest": prior_self_model.source_reconciliation_digest if prior_self_model else None,
            "self_model_reconciliation_generation": prior_self_model.source_reconciliation_generation if prior_self_model else None,
            "self_model_source_tick": prior_self_model.source_tick if prior_self_model else None,
            "self_model_claim_ids": prior_self_model.selected_claim_ids if prior_self_model else (),
            "self_model_claim_digests": prior_self_model.selected_claim_digests if prior_self_model else (),
            "prior_tick_proven": prior_self_model is not None and prior_self_model.source_tick != tick_id,
            "epistemic_projection_present": prior_epistemic_state is not None,
            "epistemic_projection_id": prior_epistemic_state.projection_id if prior_epistemic_state else None,
            "epistemic_projection_digest": prior_epistemic_state.projection_digest if prior_epistemic_state else None,
            "epistemic_proposition_ids": prior_epistemic_state.proposition_ids if prior_epistemic_state else (),
            "epistemic_state_ids": prior_epistemic_state.state_ids if prior_epistemic_state else (),
            "epistemic_state_digests": prior_epistemic_state.state_digests if prior_epistemic_state else (),
            "epistemic_generations": prior_epistemic_state.generations if prior_epistemic_state else (),
            "epistemic_evidence_set_digests": prior_epistemic_state.evidence_set_digests if prior_epistemic_state else (),
        }
        digest = _digest(semantic)
        observation = ResidentCognitionObservation(
            "devcog-" + digest[7:31], digest, condition_id, tick_id, correlation,
            str(req["model_id"]), req.get("model_artifact_digest"), str(req["request_id"]),
            str(req["request_digest"]), receipt.receipt_id, receipt.receipt_digest,
            receipt.output_digest, str(getattr(request, "authority_map_digest", "test-authority-map")),
            dict(getattr(request, "active_model_identity", {})), dict(receipt.generation_config),
            snapshot.snapshot_id, snapshot.digest, current.projection_id,
            current.projection_digest, current.fact_ids, record_ids,
            record_digests, with_history,
            prior_self_model is not None, prior_self_model.projection_id if prior_self_model else None,
            prior_self_model.projection_digest if prior_self_model else None,
            prior_self_model.source_reconciliation_id if prior_self_model else None,
            prior_self_model.source_reconciliation_digest if prior_self_model else None,
            prior_self_model.source_reconciliation_generation if prior_self_model else None,
            prior_self_model.source_tick if prior_self_model else None,
            prior_self_model.selected_claim_ids if prior_self_model else (),
            prior_self_model.selected_claim_digests if prior_self_model else (),
            prior_self_model is not None and prior_self_model.source_tick != tick_id,
            prior_epistemic_state is not None,
            prior_epistemic_state.projection_id if prior_epistemic_state else None,
            prior_epistemic_state.projection_digest if prior_epistemic_state else None,
            prior_epistemic_state.proposition_ids if prior_epistemic_state else (),
            prior_epistemic_state.state_ids if prior_epistemic_state else (),
            prior_epistemic_state.state_digests if prior_epistemic_state else (),
            prior_epistemic_state.generations if prior_epistemic_state else (),
            prior_epistemic_state.evidence_set_digests if prior_epistemic_state else (),
        )
        atomic_write_json(self.observations_root / f"{observation.observation_id}.json", asdict(observation))
        return observation

    def run_tick(self, *, snapshot: WorldStateSnapshot, tick_id: str,
                 prior_self_model: CognitiveSelfModelProjection | None = None,
                 prior_epistemic_state: EpistemicCognitiveProjection | None = None) -> ResidentDevelopmentalCycleResult:
        if not self.config.enabled:
            return ResidentDevelopmentalCycleResult("disabled", tick_id, snapshot.snapshot_id)
        if os.name != "posix":
            raise ResidentDevelopmentalCognitionError("composition_publication_unsupported_platform")
        validation = validate_snapshot(snapshot)
        if not validation.valid:
            raise ResidentDevelopmentalCognitionError("invalid_world_state_snapshot")
        state = self._state()
        if (any(row.get("tick_id") == tick_id for row in state["completed_ticks"])
                or any(row.get("tick_id") == tick_id for row in state["incomplete_ticks"])):
            raise ResidentDevelopmentalCognitionError("tick_already_completed")
        if len(state["completed_ticks"]) + len(state["incomplete_ticks"]) >= MAX_RECOVERED_TICKS:
            raise ResidentDevelopmentalCognitionError("composition_state_retention_limit_exceeded")

        # Publish the exact snapshot/tick intent before any local-model call.
        # A crash before the first durable cognition observation must remain
        # distinguishable from a tick that never began, and the same tick may
        # not be replayed after restart. A future tick can continue normally.
        state["incomplete_ticks"].append({"tick_id": tick_id,
            "snapshot_id": snapshot.snapshot_id, "snapshot_digest": snapshot.digest,
            "status": "in_progress"})
        self._save_state(state)

        # Capture prior history before any candidate from this tick can exist.
        prior = self._prior_projection(state, tick_id)
        current = self._current_projection(snapshot)
        observations: list[ResidentCognitionObservation] = []
        measurement_id: str | None = None
        has_developmental_history = bool(prior.requested_record_ids)
        has_prior_self_model = prior_self_model is not None
        has_prior_epistemic_state = prior_epistemic_state is not None
        should_cognize = (has_developmental_history or has_prior_self_model
                          or has_prior_epistemic_state)
        should_run_history_comparison = (self.config.comparison_enabled
                                         and has_developmental_history)
        if should_cognize:
            if not should_run_history_comparison:
                observations.append(self._cognize(snapshot=snapshot, current=current, tick_id=tick_id,
                                    projection=prior, with_history=has_developmental_history,
                                    condition_id="with-history" if has_developmental_history else "prior-context",
                                    prior_self_model=prior_self_model, prior_epistemic_state=prior_epistemic_state))
            else:
                records = tuple(self.writeback.store.get(rid) for rid in prior.requested_record_ids)
                record_digests = tuple(r.record_digest for r in records)
                record_set_digest = _digest({"record_ids":list(prior.requested_record_ids), "record_digests":list(record_digests)})
                budget = LocalModelInvocationBudget(max_input_chars=16000, max_output_chars=4000,
                    max_new_tokens=512, timeout_seconds=30, max_calls_per_correlation=1)
                probe = self.invoker.build_request(purpose=EXPERIMENT_PURPOSE, prompt="protocol-control-probe",
                    caller=PRINCIPAL, correlation_id=f"{tick_id}:developmental-experiment:protocol",
                    budget=budget, upstream_evidence={"control_probe":True}, linkage={"protocol_only":True})
                protocol = make_protocol(snapshot_id=snapshot.snapshot_id, snapshot_digest=snapshot.digest,
                    current_projection_id=current.projection_id, current_projection_digest=current.projection_digest,
                    current_fact_ids=current.fact_ids, record_ids=prior.requested_record_ids,
                    record_digests=record_digests, record_set_digest=record_set_digest, model_id=probe.model_id,
                    model_artifact_digest=probe.model_artifact_digest,
                    active_model_identity=dict(getattr(probe, "active_model_identity", {})),
                    active_model_identity_digest=_digest(dict(getattr(probe, "active_model_identity", {}))),
                    authority_map_digest=str(getattr(probe, "authority_map_digest", "test-authority-map")),
                    inference_budget=budget.to_dict(), generation_posture={"temperature":0, "hardware_determinism_claimed":False},
                    epistemic_projection_id=prior_epistemic_state.projection_id if prior_epistemic_state else None,
                    epistemic_projection_digest=prior_epistemic_state.projection_digest if prior_epistemic_state else None,
                    epistemic_state_digests=prior_epistemic_state.state_digests if prior_epistemic_state else (),
                    epistemic_evidence_set_digests=prior_epistemic_state.evidence_set_digests if prior_epistemic_state else (),
                    self_model_projection_id=prior_self_model.projection_id if prior_self_model else None,
                    self_model_projection_digest=prior_self_model.projection_digest if prior_self_model else None,
                    self_model_reconciliation_id=prior_self_model.source_reconciliation_id if prior_self_model else None,
                    self_model_reconciliation_digest=prior_self_model.source_reconciliation_digest if prior_self_model else None,
                    self_model_reconciliation_generation=prior_self_model.source_reconciliation_generation if prior_self_model else None,
                    self_model_source_tick=prior_self_model.source_tick if prior_self_model else None,
                    self_model_claim_ids=prior_self_model.selected_claim_ids if prior_self_model else (),
                    self_model_claim_digests=prior_self_model.selected_claim_digests if prior_self_model else (),
                    instruction_template_digest=_digest({"instruction":EXPERIMENT_CONTEXT_INSTRUCTION}))
                self.experiments.persist_protocol(protocol)  # preregistration precedes the first inference
                present = self._cognize(snapshot=snapshot, current=current, tick_id=tick_id, projection=prior,
                    with_history=True, condition_id="history_present", purpose=EXPERIMENT_PURPOSE, protocol=protocol,
                    prior_self_model=prior_self_model, prior_epistemic_state=prior_epistemic_state)
                withheld = self._cognize(snapshot=snapshot, current=current, tick_id=tick_id, projection=prior,
                    with_history=False, condition_id="history_withheld", purpose=EXPERIMENT_PURPOSE, protocol=protocol,
                    prior_self_model=prior_self_model, prior_epistemic_state=prior_epistemic_state)
                restored_records = tuple(self.writeback.store.get(rid) for rid in protocol.record_ids)
                if tuple(r.record_digest for r in restored_records) != protocol.record_digests:
                    raise ResidentDevelopmentalCognitionError("restored_history_digest_mismatch")
                restored_projection = self.writeback.retrieve(protocol.record_ids, limit=self.config.max_retrieved_records)
                restored = self._cognize(snapshot=snapshot, current=current, tick_id=tick_id,
                    projection=restored_projection, with_history=True, condition_id="history_restored",
                    purpose=EXPERIMENT_PURPOSE, protocol=protocol, prior_self_model=prior_self_model,
                    prior_epistemic_state=prior_epistemic_state)
                observations.extend((present, withheld, restored))
                summary = summarize(protocol, observations)
                measurement_id = self.experiments.persist_run({"protocol":asdict(protocol),
                    "conditions":[asdict(x) for x in observations], "summary":summary,
                    "validity":"valid_controlled_observation", "contamination_reasons":[]})

        fact_ids = self._select_fact_ids(snapshot, set(state["processed_selection_ids"]))
        if len(set(state["processed_selection_ids"]) | set(fact_ids)) > MAX_RECOVERED_FACT_IDS:
            raise ResidentDevelopmentalCognitionError("composition_state_retention_limit_exceeded")
        record_id = receipt_id = None
        if fact_ids:
            selection = self.writeback.select_evidence(snapshot, fact_ids=fact_ids)
            if selection.selection_id not in set(state["processed_selection_ids"]):
                candidate = self.writeback.infer_candidate(
                    selection, invoker=self.invoker,
                    correlation_id=f"{tick_id}:resident_developmental_interpretation")
                operation_id = f"resident-developmental-writeback:{tick_id}:{candidate.candidate_id}"
                config_digest = self.writeback.admission_configuration_digest(candidate, operation_id=operation_id)
                sequence = self.current_sequence()
                admission = self.admission_authority.issue(
                    admission_id=f"resident-admission-{candidate.candidate_id}-{sequence}",
                    capability_id=RESIDENT_DEVELOPMENTAL_WRITEBACK, definition_version=1,
                    subsystem_kind="memory_context_reflection", principal_id=PRINCIPAL,
                    principal_kind=PRINCIPAL, effects=EFFECTS, subject_id=candidate.candidate_id,
                    request_configuration_digest=config_digest,
                    provenance=f"configured-resident-control-plane:{tick_id}", issued_sequence=sequence,
                    valid_through_sequence=sequence,
                    affirmative_preconditions=RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION.approval_requirements,
                )
                record, receipt = self.writeback.append(candidate, admission=admission,
                                                        operation_id=operation_id,
                                                        correlation_id=f"{tick_id}:resident-developmental-writeback")
                record_id, receipt_id = record.record_id, receipt.receipt_id
                # Persist each exact fact-evidence identity so changing the batch
                # bound cannot make an already interpreted fact eligible again.
                state["processed_selection_ids"].extend(fact_ids)
        state["incomplete_ticks"] = [row for row in state["incomplete_ticks"]
                                      if row.get("tick_id") != tick_id]
        state["completed_ticks"].append({"tick_id": tick_id, "snapshot_id": snapshot.snapshot_id,
                                         "snapshot_digest": snapshot.digest, "record_id": record_id,
                                         "receipt_id": receipt_id})
        self._save_state(state)
        return ResidentDevelopmentalCycleResult(
            "completed", tick_id, snapshot.snapshot_id, fact_ids, prior.requested_record_ids,
            record_id, receipt_id, tuple(item.observation_id for item in observations), measurement_id,
        )

"""Bounded repeated attribution above one-shot post-adoption evaluations.

This owner records observational control evidence; it does not infer experimental
causation and has no mutation, adoption, scheduling, rollback, or provider authority.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence

from sentientos.maintenance_post_adoption_evaluation import Evaluation, FALSE_AUTHORITY

PROTOCOL_SCHEMA = "sentientos.maintenance_post_adoption_attribution_campaign_protocol:v1"
CONTROL_SCHEMA = "sentientos.maintenance_attribution_control_observation:v1"
TRIAL_SCHEMA = "sentientos.maintenance_attribution_campaign_trial:v1"
RESULT_SCHEMA = "sentientos.maintenance_post_adoption_attribution_campaign_result:v1"
ATTRIBUTION_POSTURE = "repeated_controlled_association_not_experimental_causation"
CONTROL_DESIGNS = frozenset({"observed_environmental_stability", "matched_repeated_conditions", "independently_replayed_workload", "contemporaneous_reference_observation", "randomized_experimental_intervention"})
SOURCE_CLASSES = frozenset({"world_state_evidence", "host_observation", "external_instrument", "operator_attested_observation", "independent_workload_replay", "contemporaneous_reference"})
RESULTS = frozenset({"repeated_association_under_matched_controls", "repeated_target_contradiction_under_matched_controls", "environmental_confound_detected", "heterogeneous_repeated_outcome", "no_detectable_target_change", "insufficient_target_evidence", "insufficient_control_evidence", "measurement_failure", "interrupted_or_invalid_trial", "protected_regression_observed", "indeterminate"})
TERMINAL_STATUSES = frozenset({"completed", "interrupted", "invalid"})
MAX_ARTIFACT_BYTES = 131_072
MAX_RECORDS_PER_KIND = 2_048
WORLD_STATE_PROJECTION_SCHEMA = "sentientos.post_adoption_attribution_world_state_projection:v1"


class AttributionCampaignError(ValueError):
    """Fail-closed campaign custody or admission error."""


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def _identity(prefix: str, payload: Mapping[str, Any]) -> tuple[str, str]:
    value = digest(payload)
    return f"{prefix}:{value[7:31]}", value


def validate_world_state_projection_config(value: Mapping[str, Any]) -> dict[str, Any]:
    config = dict(value)
    expected = {"schema_version", "enabled", "store_root", "campaign_ids", "config_digest"}
    if (set(config) != expected or config.get("schema_version") != WORLD_STATE_PROJECTION_SCHEMA
            or type(config.get("enabled")) is not bool
            or config.get("config_digest") != digest({key:item for key,item in config.items() if key != "config_digest"})):
        raise AttributionCampaignError("campaign_projection_config_invalid")
    if not config["enabled"]:
        if config["store_root"] is not None or config["campaign_ids"] != []:
            raise AttributionCampaignError("disabled_campaign_projection_must_be_empty")
        return config
    root, identities = config.get("store_root"), config.get("campaign_ids")
    prefix = "attribution-campaign:"
    if (not isinstance(root, str) or not os.path.isabs(root) or not isinstance(identities, list)
            or not 1 <= len(identities) <= 32
            or any(not isinstance(item, str) or len(item) != len(prefix) + 24
                or not item.startswith(prefix)
                or any(character not in "0123456789abcdef" for character in item[len(prefix):])
                for item in identities)
            or len(identities) != len(set(identities))):
        raise AttributionCampaignError("campaign_projection_selection_invalid")
    return config


def _payload(value: Any, id_field: str, digest_field: str) -> dict[str, Any]:
    body = asdict(value); body.pop(id_field); body.pop(digest_field); return body


def _false(authority: Mapping[str, bool]) -> None:
    if dict(authority) != FALSE_AUTHORITY:
        raise AttributionCampaignError("campaign_authority_must_be_all_false")


@dataclass(frozen=True)
class ControlDefinition:
    observable_id: str
    measurement_law: str
    matching_rule: str
    source_requirement: str
    admissible_source_classes: tuple[str, ...]
    required: bool = True


@dataclass(frozen=True)
class CampaignProtocol:
    campaign_id: str; campaign_digest: str; maintenance_task_id: str; proposal_id: str
    signal_ids: tuple[str, ...]; predecessor_generation: int; predecessor_revision: str; predecessor_tree: str
    successor_generation: int; successor_revision: str; successor_tree: str; adoption_identity: str
    evaluation_protocol_ids: tuple[str, ...]; evaluation_protocol_digests: tuple[str, ...]
    target_observable_ids: tuple[str, ...]; target_measurement_laws: Mapping[str, str]
    protected_invariant_ids: tuple[str, ...]; controls: tuple[ControlDefinition, ...]
    control_design: str; attribution_rule: str; trial_ids: tuple[str, ...]
    minimum_trials: int; maximum_trials: int; evidence_class: str; created_at: str; creation_generation: int
    no_retry: bool; no_replacement: bool; no_cherry_picking: bool; authority: Mapping[str, bool]
    schema_version: str = PROTOCOL_SCHEMA
    def payload(self) -> dict[str, Any]: return _payload(self, "campaign_id", "campaign_digest")


def make_campaign_protocol(**kwargs: Any) -> CampaignProtocol:
    controls = tuple(x if isinstance(x, ControlDefinition) else ControlDefinition(**x) for x in kwargs.pop("controls"))
    raw = CampaignProtocol("", "", controls=controls, authority=dict(FALSE_AUTHORITY), **kwargs)
    _false(raw.authority)
    invalid = (not 2 <= raw.minimum_trials <= raw.maximum_trials <= 32 or len(raw.trial_ids) < raw.minimum_trials
        or len(raw.trial_ids) > raw.maximum_trials or len(set(raw.trial_ids)) != len(raw.trial_ids)
        or len(raw.evaluation_protocol_ids) != len(raw.trial_ids) or len(raw.evaluation_protocol_digests) != len(raw.trial_ids)
        or raw.successor_generation != raw.predecessor_generation + 1 or raw.control_design not in CONTROL_DESIGNS
        or raw.evidence_class not in {"production", "synthetic"} or not raw.controls or not raw.target_observable_ids
        or set(raw.target_measurement_laws) != set(raw.target_observable_ids)
        or len({x.observable_id for x in raw.controls}) != len(raw.controls)
        or any(not x.measurement_law or not x.matching_rule or not x.source_requirement or not x.admissible_source_classes
               or not set(x.admissible_source_classes) <= SOURCE_CLASSES for x in raw.controls)
        or not (raw.no_retry and raw.no_replacement and raw.no_cherry_picking))
    if invalid: raise AttributionCampaignError("campaign_protocol_invalid")
    cid, cdg = _identity("attribution-campaign", raw.payload())
    return replace(raw, campaign_id=cid, campaign_digest=cdg)


@dataclass(frozen=True)
class ControlObservation:
    control_id: str; control_digest: str; campaign_id: str; campaign_digest: str; trial_id: str
    observable_id: str; measurement_law: str; matching_rule: str; match_result: str
    before_value: Any; after_value: Any; source_identity: str; source_digest: str; source_schema: str
    source_class: str; observed_at: str; collector_identity: str; dependency_ids: tuple[str, ...]
    window_identity: str; world_state_binding: str | None; host_observation_binding: str | None
    evidence_class: str; authority: Mapping[str, bool]; schema_version: str = CONTROL_SCHEMA
    def payload(self) -> dict[str, Any]: return _payload(self, "control_id", "control_digest")


def make_control_observation(protocol: CampaignProtocol, **kwargs: Any) -> ControlObservation:
    raw = ControlObservation("", "", campaign_id=protocol.campaign_id, campaign_digest=protocol.campaign_digest,
                             authority=dict(FALSE_AUTHORITY), **kwargs)
    definition = next((x for x in protocol.controls if x.observable_id == raw.observable_id), None)
    if (definition is None or raw.trial_id not in protocol.trial_ids or raw.measurement_law != definition.measurement_law
        or raw.matching_rule != definition.matching_rule or raw.source_class not in definition.admissible_source_classes
        or raw.match_result not in {"matched", "out_of_envelope", "unmeasurable"}
        or not raw.source_identity or not raw.source_digest.startswith("sha256:") or not raw.source_schema
        or not raw.observed_at or not raw.collector_identity or not raw.window_identity
        or raw.evidence_class != protocol.evidence_class):
        raise AttributionCampaignError("control_observation_invalid")
    cid, cdg = _identity("control-observation", raw.payload())
    return replace(raw, control_id=cid, control_digest=cdg)


@dataclass(frozen=True)
class CampaignTrial:
    trial_record_id: str; trial_digest: str; campaign_id: str; campaign_digest: str; trial_id: str; trial_order: int
    terminal_status: str; evaluation_id: str | None; evaluation_digest: str | None; evaluation_protocol_id: str
    evaluation_protocol_digest: str; evaluation_result: str | None; evaluation_lineage: tuple[str, ...]
    control_ids: tuple[str, ...]; control_digests: tuple[str, ...]; outcome: str; completed_at: str
    authority: Mapping[str, bool]; schema_version: str = TRIAL_SCHEMA
    def payload(self) -> dict[str, Any]: return _payload(self, "trial_record_id", "trial_digest")


@dataclass(frozen=True)
class CampaignResult:
    result_id: str; result_digest: str; campaign_id: str; campaign_digest: str; ordered_trial_ids: tuple[str, ...]
    trial_record_ids: tuple[str, ...]; trial_digests: tuple[str, ...]; evaluation_ids: tuple[str, ...]
    evaluation_digests: tuple[str, ...]; control_ids: tuple[str, ...]; control_digests: tuple[str, ...]
    classification: str; attribution_posture: str; production_ready: bool; evidence_class: str
    completed_at: str; reconstruction_lineage: tuple[str, ...]; authority: Mapping[str, bool]
    schema_version: str = RESULT_SCHEMA
    def payload(self) -> dict[str, Any]: return _payload(self, "result_id", "result_digest")


def _evaluation_valid(value: Evaluation) -> bool:
    return bool(digest(value.payload()) == value.evaluation_digest and value.attribution_posture == "controlled_before_after_correlation_not_experimental_causation")


def _classification(outcomes: set[str]) -> str:
    if "protected_regression_observed" in outcomes: return "protected_regression_observed"
    if "interrupted_or_invalid_trial" in outcomes: return "interrupted_or_invalid_trial"
    if "measurement_failure" in outcomes: return "measurement_failure"
    if "insufficient_target_evidence" in outcomes: return "insufficient_target_evidence"
    if "insufficient_control_evidence" in outcomes: return "insufficient_control_evidence"
    if "environmental_confound_detected" in outcomes: return "environmental_confound_detected"
    if len(outcomes) > 1: return "heterogeneous_repeated_outcome"
    return next(iter(outcomes), "indeterminate")


def _trial_outcome(evaluation: Evaluation | None, controls: Sequence[ControlObservation], status: str, definitions: Sequence[ControlDefinition]) -> str:
    if status != "completed": return "interrupted_or_invalid_trial"
    if evaluation is None or not _evaluation_valid(evaluation): return "insufficient_target_evidence"
    present = {x.observable_id for x in controls}
    if any(x.required and x.observable_id not in present for x in definitions): return "insufficient_control_evidence"
    if any(x.match_result == "unmeasurable" for x in controls): return "insufficient_control_evidence"
    if any(x.match_result == "out_of_envelope" for x in controls): return "environmental_confound_detected"
    return {"target_expectation_satisfied":"repeated_association_under_matched_controls",
        "target_expectation_contradicted":"repeated_target_contradiction_under_matched_controls",
        "new_regression_observed":"protected_regression_observed", "no_detectable_change":"no_detectable_target_change",
        "insufficient_evidence":"insufficient_target_evidence", "measurement_failed":"measurement_failure",
        "mixed_outcome":"heterogeneous_repeated_outcome"}.get(evaluation.result, "indeterminate")


class MaintenancePostAdoptionAttributionCampaignOwner:
    """Immutable, explicit-root custody for preregistered ordered campaigns."""
    def __init__(self, root: str | Path, *, read_only: bool = False) -> None:
        selected = Path(os.path.abspath(os.fspath(root)))
        if selected == Path(selected.anchor):
            raise AttributionCampaignError("campaign_custody_root_invalid")
        self.root = selected
        self.read_only = read_only
        self._require_descriptor_storage()
        if not read_only:
            for kind in ("protocols", "controls", "trials", "results", "signals"):
                descriptor = self._open_kind_directory(kind, create=True)
                os.close(descriptor)
        self.verify()

    @staticmethod
    def _require_descriptor_storage() -> None:
        required = (os.open, os.mkdir, os.link, os.unlink)
        if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
                or any(function not in os.supports_dir_fd for function in required)):
            raise AttributionCampaignError("campaign_unsupported_platform")

    def _open_kind_directory(self, kind: str, *, create: bool) -> int:
        if kind not in {"protocols", "controls", "trials", "results", "signals"}:
            raise AttributionCampaignError("campaign_path_invalid")
        self._require_descriptor_storage()
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
        descriptor: int | None = None
        try:
            descriptor = os.open(os.sep, flags)
            for component in (*self.root.parts[1:], kind):
                if create:
                    try:
                        os.mkdir(component, 0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                next_descriptor = os.open(component, flags, dir_fd=descriptor)
                if not stat.S_ISDIR(os.fstat(next_descriptor).st_mode):
                    os.close(next_descriptor)
                    raise AttributionCampaignError("campaign_path_invalid")
                os.close(descriptor)
                descriptor = next_descriptor
            return descriptor
        except AttributionCampaignError:
            if descriptor is not None:
                os.close(descriptor)
            raise
        except OSError as exc:
            if descriptor is not None:
                os.close(descriptor)
            if isinstance(exc, FileNotFoundError):
                raise AttributionCampaignError("campaign_history_missing") from exc
            raise AttributionCampaignError("campaign_path_invalid") from exc

    def _write(self, kind: str, identity: str, value: Any) -> None:
        if self.read_only:
            raise AttributionCampaignError("campaign_store_read_only")
        if (not isinstance(identity, str) or not identity or len(identity) > 256
                or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789:-_" for character in identity)):
            raise AttributionCampaignError("campaign_record_identity_invalid")
        path_name = identity.replace(":", "-") + ".json"
        data = canonical_bytes(asdict(value) if not isinstance(value, Mapping) else value) + b"\n"
        if len(data) > MAX_ARTIFACT_BYTES:
            raise AttributionCampaignError("campaign_record_oversized")
        directory_fd = self._open_kind_directory(kind, create=True)
        temporary_name = ".campaign-" + secrets.token_hex(16) + ".tmp"
        temporary_created = False
        try:
            try:
                existing_fd = os.open(path_name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=directory_fd)
            except FileNotFoundError:
                existing_fd = None
            if existing_fd is not None:
                os.close(existing_fd)
                existing = self._read_named(directory_fd, path_name)
                if canonical_bytes(existing) + b"\n" != data:
                    raise AttributionCampaignError("immutable_campaign_record_conflict")
                return
            descriptor = os.open(temporary_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o600, dir_fd=directory_fd)
            temporary_created = True
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data); handle.flush(); os.fsync(handle.fileno())
            try:
                os.link(temporary_name, path_name, src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd, follow_symlinks=False)
            except FileExistsError:
                existing = self._read_named(directory_fd, path_name)
                if canonical_bytes(existing) + b"\n" != data:
                    raise AttributionCampaignError("immutable_campaign_record_conflict")
                return
            os.fsync(directory_fd)
        except AttributionCampaignError:
            raise
        except OSError as exc:
            raise AttributionCampaignError("campaign_publication_failed") from exc
        finally:
            if temporary_created:
                try:
                    os.unlink(temporary_name, dir_fd=directory_fd)
                    os.fsync(directory_fd)
                except FileNotFoundError:
                    pass
            os.close(directory_fd)

    @staticmethod
    def _read_named(directory_fd: int, name: str) -> dict[str, Any]:
        descriptor: int | None = None
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=directory_fd)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_ARTIFACT_BYTES:
                raise AttributionCampaignError("campaign_history_corrupt")
            chunks: list[bytes] = []
            remaining = metadata.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 65_536))
                if not chunk:
                    raise AttributionCampaignError("campaign_history_corrupt")
                chunks.append(chunk); remaining -= len(chunk)
            raw = b"".join(chunks)
            if len(raw) != metadata.st_size:
                raise AttributionCampaignError("campaign_history_corrupt")
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict):
                raise AttributionCampaignError("campaign_history_corrupt")
            return value
        except AttributionCampaignError:
            raise
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise AttributionCampaignError("campaign_history_corrupt") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)

    def _read(self, kind: str) -> list[dict[str, Any]]:
        directory_fd = self._open_kind_directory(kind, create=False)
        try:
            names = sorted(name for name in os.listdir(directory_fd) if name.endswith(".json"))
            if len(names) > MAX_RECORDS_PER_KIND:
                raise AttributionCampaignError("campaign_retention_limit_exceeded")
            values = []
            for name in names:
                value = self._read_named(directory_fd, name)
                identity_field = {"protocols":"campaign_id", "controls":"control_id", "trials":"trial_record_id",
                    "results":"result_id", "signals":"source_artifact"}[kind]
                identity = value.get(identity_field)
                if not isinstance(identity, str) or name != identity.replace(":", "-") + ".json":
                    raise AttributionCampaignError("campaign_history_corrupt")
                values.append(value)
            return values
        finally:
            os.close(directory_fd)

    def preregister(self, protocol: CampaignProtocol) -> CampaignProtocol:
        rebuilt = make_campaign_protocol(**{k:v for k,v in asdict(protocol).items() if k not in {"campaign_id","campaign_digest","schema_version","authority"}})
        if rebuilt != protocol: raise AttributionCampaignError("campaign_protocol_digest_mismatch")
        self._write("protocols", protocol.campaign_id, protocol); return protocol

    def protocol(self, campaign_id: str) -> CampaignProtocol:
        rows = [x for x in self._read("protocols") if x["campaign_id"] == campaign_id]
        if len(rows) != 1: raise AttributionCampaignError("campaign_protocol_not_found")
        row = dict(rows[0]); row["controls"] = tuple(ControlDefinition(**{**x, "admissible_source_classes":tuple(x["admissible_source_classes"])}) for x in row["controls"])
        for field in ("signal_ids", "evaluation_protocol_ids", "evaluation_protocol_digests", "target_observable_ids", "protected_invariant_ids", "trial_ids"):
            row[field] = tuple(row[field])
        return CampaignProtocol(**row)

    def controls_for_trial(self, campaign_id: str, trial_id: str) -> tuple[ControlObservation, ...]:
        """Return exact persisted controls for a trial after full store verification."""
        self.verify()
        rows = [row for row in self._read("controls")
            if row.get("campaign_id") == campaign_id and row.get("trial_id") == trial_id]
        values = []
        for row in rows:
            value = dict(row)
            value["dependency_ids"] = tuple(value["dependency_ids"])
            values.append(ControlObservation(**value))
        return tuple(sorted(values, key=lambda item: item.observable_id))

    def record_control(self, protocol: CampaignProtocol, control: ControlObservation) -> ControlObservation:
        """Publish one immutable control observation so an interrupted trial can resume exactly."""
        self.verify()
        if self.read_only:
            raise AttributionCampaignError("campaign_store_read_only")
        if self.protocol(protocol.campaign_id) != protocol:
            raise AttributionCampaignError("campaign_protocol_custody_mismatch")
        if control.campaign_id != protocol.campaign_id or control.campaign_digest != protocol.campaign_digest:
            raise AttributionCampaignError("control_campaign_lineage_mismatch")
        fields = {key:value for key,value in asdict(control).items()
            if key not in {"control_id", "control_digest", "campaign_id", "campaign_digest", "authority", "schema_version"}}
        fields["dependency_ids"] = tuple(fields["dependency_ids"])
        if make_control_observation(protocol, **fields) != control:
            raise AttributionCampaignError("control_digest_mismatch")
        if any(row.get("campaign_id") == protocol.campaign_id and row.get("trial_id") == control.trial_id
                for row in self._read("trials")):
            raise AttributionCampaignError("trial_already_terminal")
        existing = [row for row in self._read("controls")
            if row.get("campaign_id") == protocol.campaign_id and row.get("trial_id") == control.trial_id
            and row.get("observable_id") == control.observable_id]
        if existing:
            if len(existing) != 1 or existing[0].get("control_id") != control.control_id:
                raise AttributionCampaignError("trial_control_observation_conflict")
            stored = dict(existing[0]); stored["dependency_ids"] = tuple(stored["dependency_ids"])
            return ControlObservation(**stored)
        if any(row.get("campaign_id") == protocol.campaign_id for row in self._read("results")):
            raise AttributionCampaignError("completed_campaign_replay_forbidden")
        self._write("controls", control.control_id, control)
        return control

    def record_trial(self, protocol: CampaignProtocol, *, trial_id: str, evaluation: Evaluation | None,
                     controls: Sequence[ControlObservation], terminal_status: str, completed_at: str) -> CampaignTrial:
        self.verify()
        stored = self.protocol(protocol.campaign_id)
        if stored != protocol: raise AttributionCampaignError("campaign_protocol_custody_mismatch")
        if any(x["campaign_id"] == protocol.campaign_id for x in self._read("results")): raise AttributionCampaignError("completed_campaign_replay_forbidden")
        if trial_id not in protocol.trial_ids or terminal_status not in TERMINAL_STATUSES: raise AttributionCampaignError("trial_not_preregistered")
        if len({item.control_id for item in controls}) != len(controls) or len({item.observable_id for item in controls}) != len(controls):
            raise AttributionCampaignError("duplicate_trial_control_evidence")
        order = protocol.trial_ids.index(trial_id)
        existing = self._read("trials")
        if any(x["campaign_id"] == protocol.campaign_id and x["trial_id"] == trial_id for x in existing): raise AttributionCampaignError("trial_retry_or_replacement_forbidden")
        expected_next = len([x for x in existing if x["campaign_id"] == protocol.campaign_id])
        if order != expected_next: raise AttributionCampaignError("trial_order_or_omission_forbidden")
        if any(x.campaign_digest != protocol.campaign_digest or x.trial_id != trial_id for x in controls): raise AttributionCampaignError("control_campaign_lineage_mismatch")
        for control in controls:
            expected = make_control_observation(protocol, **{k:v for k,v in asdict(control).items() if k not in {"control_id","control_digest","campaign_id","campaign_digest","authority","schema_version"}})
            if expected != control: raise AttributionCampaignError("control_digest_mismatch")
        expected_pid = protocol.evaluation_protocol_ids[order]; expected_pdg = protocol.evaluation_protocol_digests[order]
        if evaluation is not None and (not _evaluation_valid(evaluation) or evaluation.protocol_id != expected_pid or evaluation.protocol_digest != expected_pdg
                or evaluation.predecessor_generation != protocol.predecessor_generation or evaluation.successor_generation != protocol.successor_generation
                or evaluation.predecessor_revision != protocol.predecessor_revision or evaluation.successor_revision != protocol.successor_revision):
            raise AttributionCampaignError("evaluation_campaign_lineage_mismatch")
        if terminal_status == "completed" and evaluation is None: raise AttributionCampaignError("completed_trial_requires_evaluation")
        outcome = _trial_outcome(evaluation, controls, terminal_status, protocol.controls)
        raw = CampaignTrial("", "", protocol.campaign_id, protocol.campaign_digest, trial_id, order, terminal_status,
            evaluation.evaluation_id if evaluation else None, evaluation.evaluation_digest if evaluation else None,
            expected_pid, expected_pdg, evaluation.result if evaluation else None,
            tuple(evaluation.reconstruction_lineage) if evaluation else (), tuple(x.control_id for x in controls),
            tuple(x.control_digest for x in controls), outcome, completed_at, dict(FALSE_AUTHORITY))
        tid, tdg = _identity("attribution-trial", raw.payload()); value = replace(raw, trial_record_id=tid, trial_digest=tdg)
        for control in controls: self._write("controls", control.control_id, control)
        self._write("trials", tid, value); return value

    def finalize(self, protocol: CampaignProtocol, *, completed_at: str) -> CampaignResult:
        self.verify()
        if self.protocol(protocol.campaign_id) != protocol: raise AttributionCampaignError("campaign_protocol_custody_mismatch")
        existing_results = [x for x in self._read("results") if x["campaign_id"] == protocol.campaign_id]
        if existing_results:
            existing = self.result(protocol.campaign_id)
            if existing.completed_at == completed_at:
                return existing
            raise AttributionCampaignError("campaign_already_terminal")
        trials = sorted((CampaignTrial(**x) for x in self._read("trials") if x["campaign_id"] == protocol.campaign_id), key=lambda x:x.trial_order)
        if tuple(x.trial_id for x in trials) != protocol.trial_ids: raise AttributionCampaignError("campaign_incomplete_no_selective_aggregation")
        outcomes = {x.outcome for x in trials}
        classification = _classification(outcomes)
        controls = sorted((x for x in self._read("controls") if x["campaign_id"] == protocol.campaign_id),
                          key=lambda x:(protocol.trial_ids.index(x["trial_id"]), x["observable_id"]))
        # ``evidence_class`` and collector/source identities are caller supplied;
        # this owner has no authenticated issuer verifier and cannot certify
        # production readiness from those declarations alone.
        production_ready = False
        lineage = (protocol.campaign_digest,) + tuple(x.trial_digest for x in trials) + tuple(x["control_digest"] for x in controls)
        raw = CampaignResult("", "", protocol.campaign_id, protocol.campaign_digest, protocol.trial_ids,
            tuple(x.trial_record_id for x in trials), tuple(x.trial_digest for x in trials),
            tuple(x.evaluation_id for x in trials if x.evaluation_id), tuple(x.evaluation_digest for x in trials if x.evaluation_digest),
            tuple(x["control_id"] for x in controls), tuple(x["control_digest"] for x in controls), classification,
            ATTRIBUTION_POSTURE, production_ready, protocol.evidence_class, completed_at, lineage, dict(FALSE_AUTHORITY))
        rid, rdg = _identity("attribution-result", raw.payload()); value = replace(raw, result_id=rid, result_digest=rdg)
        self._write("results", rid, value)
        signal = campaign_improvement_signal_record(value)
        if signal: self._write("signals", rid, signal)
        return value

    def result(self, campaign_id: str) -> CampaignResult:
        self.verify()
        rows = [x for x in self._read("results") if x["campaign_id"] == campaign_id]
        if len(rows) != 1: raise AttributionCampaignError("campaign_result_not_found")
        row = dict(rows[0])
        for field in ("ordered_trial_ids", "trial_record_ids", "trial_digests", "evaluation_ids", "evaluation_digests", "control_ids", "control_digests", "reconstruction_lineage"):
            row[field] = tuple(row[field])
        return CampaignResult(**row)

    def world_state_records(self, *, campaign_ids: Sequence[str]) -> list[dict[str, Any]]:
        """Project explicitly selected durable outcomes as non-authorizing context."""
        from sentientos.world_state_board import record_digest
        identities = tuple(campaign_ids)
        if (len(identities) > 32 or any(not isinstance(item, str) or not item.startswith("attribution-campaign:")
                or len(item) != len("attribution-campaign:") + 24
                or any(character not in "0123456789abcdef" for character in item[len("attribution-campaign:"):])
                for item in identities) or len(identities) != len(set(identities))):
            raise AttributionCampaignError("campaign_world_state_selection_invalid")
        records: list[dict[str, Any]] = []
        for campaign_id in identities:
            result = self.result(campaign_id)
            protocol = self.protocol(campaign_id)
            record: dict[str, Any] = {
                "source_kind": "owner_introspection",
                "source_id": "post-adoption-attribution:" + result.result_id,
                "schema_version": RESULT_SCHEMA,
                "subject_id": result.result_id,
                "subject_kind": "post_adoption_attribution_campaign",
                "stage": "observation",
                "disposition": result.classification,
                "evidence_strength": "digest_verified_campaign_custody_unverified_sources",
                "payload": {
                    "campaign_id": result.campaign_id,
                    "campaign_digest": result.campaign_digest,
                    "result_id": result.result_id,
                    "result_digest": result.result_digest,
                    "protocol_successor_generation": protocol.successor_generation,
                    "protocol_successor_revision": protocol.successor_revision,
                    "protocol_successor_tree": protocol.successor_tree,
                    "adoption_identity_declared": protocol.adoption_identity,
                    "trial_record_ids": list(result.trial_record_ids),
                    "trial_digests": list(result.trial_digests),
                    "evaluation_ids": list(result.evaluation_ids),
                    "evaluation_digests": list(result.evaluation_digests),
                    "control_ids": list(result.control_ids),
                    "control_digests": list(result.control_digests),
                    "reconstruction_lineage": list(result.reconstruction_lineage),
                    "declared_completed_at": result.completed_at,
                    "event_time_posture": "caller_declared_campaign_completion_time",
                    "source_issuer_posture": "unverified_caller_supplied_sources",
                    "production_ready": False,
                    "current_truth": False,
                    "authority": dict(FALSE_AUTHORITY),
                },
                "effect_claimed": False,
                "effect_proven": False,
            }
            record["digest"] = record_digest(record)
            if len(canonical_bytes(record)) > 65_536:
                raise AttributionCampaignError("campaign_world_state_record_oversized")
            records.append(record)
        return records

    def verify(self) -> Mapping[str, int]:
        protocols: dict[str, CampaignProtocol] = {}
        for row in self._read("protocols"):
            fields = {k:v for k,v in row.items() if k not in {"campaign_id","campaign_digest","schema_version","authority"}}
            fields["controls"] = tuple(ControlDefinition(**{**x, "admissible_source_classes":tuple(x["admissible_source_classes"])}) for x in fields["controls"])
            for name in ("signal_ids", "evaluation_protocol_ids", "evaluation_protocol_digests", "target_observable_ids", "protected_invariant_ids", "trial_ids"):
                fields[name] = tuple(fields[name])
            rebuilt = make_campaign_protocol(**fields)
            if (rebuilt.campaign_id != row.get("campaign_id") or rebuilt.campaign_digest != row.get("campaign_digest")
                    or canonical_bytes(asdict(rebuilt)) != canonical_bytes(row) or row["campaign_id"] in protocols):
                raise AttributionCampaignError("campaign_history_corrupt")
            protocols[row["campaign_id"]] = rebuilt

        control_rows = self._read("controls")
        controls: dict[str, dict[str, Any]] = {}
        control_slots: set[tuple[str, str, str]] = set()
        for row in control_rows:
            try:
                protocol = protocols[row["campaign_id"]]
                fields = {k:v for k,v in row.items() if k not in {"control_id","control_digest","campaign_id","campaign_digest","authority","schema_version"}}
                fields["dependency_ids"] = tuple(fields["dependency_ids"])
                rebuilt = make_control_observation(protocol, **fields)
            except (KeyError, TypeError, ValueError) as exc:
                raise AttributionCampaignError("campaign_history_corrupt") from exc
            if (rebuilt.control_id != row.get("control_id") or rebuilt.control_digest != row.get("control_digest")
                    or canonical_bytes(asdict(rebuilt)) != canonical_bytes(row) or row["control_id"] in controls):
                raise AttributionCampaignError("campaign_history_corrupt")
            slot = (row["campaign_id"], row["trial_id"], row["observable_id"])
            if slot in control_slots:
                raise AttributionCampaignError("campaign_history_corrupt")
            control_slots.add(slot)
            _false(row["authority"])
            controls[row["control_id"]] = row

        trial_rows = self._read("trials")
        trials: dict[str, dict[str, Any]] = {}
        campaign_trials: dict[str, list[dict[str, Any]]] = {}
        for row in trial_rows:
            try:
                protocol = protocols[row["campaign_id"]]
                fields = dict(row)
                for name in ("evaluation_lineage", "control_ids", "control_digests"):
                    fields[name] = tuple(fields[name])
                trial = CampaignTrial(**fields)
                computed_id, computed_digest = _identity("attribution-trial", trial.payload())
                order = protocol.trial_ids.index(trial.trial_id)
                linked_controls = [controls[identity] for identity in trial.control_ids]
                if (trial.campaign_digest != protocol.campaign_digest or trial.trial_order != order
                        or trial.schema_version != TRIAL_SCHEMA
                        or trial.evaluation_protocol_id != protocol.evaluation_protocol_ids[order]
                        or trial.evaluation_protocol_digest != protocol.evaluation_protocol_digests[order]
                        or trial.terminal_status not in TERMINAL_STATUSES or trial.outcome not in RESULTS
                        or len(trial.control_ids) != len(set(trial.control_ids))
                        or len({x["observable_id"] for x in linked_controls}) != len(linked_controls)
                        or tuple(x["control_digest"] for x in linked_controls) != trial.control_digests
                        or any(x["campaign_id"] != trial.campaign_id or x["trial_id"] != trial.trial_id for x in linked_controls)
                        or (trial.terminal_status != "completed" and trial.outcome != "interrupted_or_invalid_trial")
                        or (trial.terminal_status == "completed" and (not trial.evaluation_id or not trial.evaluation_digest))
                        or (trial.trial_record_id, trial.trial_digest) != (computed_id, computed_digest)
                        or trial.trial_record_id in trials):
                    raise AttributionCampaignError("campaign_history_corrupt")
            except (KeyError, TypeError, ValueError) as exc:
                raise AttributionCampaignError("campaign_history_corrupt") from exc
            _false(trial.authority)
            trials[trial.trial_record_id] = row
            campaign_trials.setdefault(trial.campaign_id, []).append(row)

        for rows in campaign_trials.values():
            orders = [row["trial_order"] for row in rows]
            trial_ids = [row["trial_id"] for row in rows]
            if len(orders) != len(set(orders)) or len(trial_ids) != len(set(trial_ids)):
                raise AttributionCampaignError("campaign_history_corrupt")

        result_rows = self._read("results")
        results: dict[str, dict[str, Any]] = {}
        for row in result_rows:
            try:
                protocol = protocols[row["campaign_id"]]
                fields = dict(row)
                for name in ("ordered_trial_ids", "trial_record_ids", "trial_digests", "evaluation_ids", "evaluation_digests", "control_ids", "control_digests", "reconstruction_lineage"):
                    fields[name] = tuple(fields[name])
                result = CampaignResult(**fields)
                ordered_trials = sorted(campaign_trials.get(result.campaign_id, []), key=lambda x:x["trial_order"])
                expected_controls = sorted((x for x in control_rows if x["campaign_id"] == result.campaign_id),
                    key=lambda x:(protocol.trial_ids.index(x["trial_id"]), x["observable_id"]))
                expected_ids = tuple(x["trial_record_id"] for x in ordered_trials)
                expected_digests = tuple(x["trial_digest"] for x in ordered_trials)
                expected_ordered_trial_ids = tuple(x["trial_id"] for x in ordered_trials)
                expected_evaluations = tuple(x["evaluation_id"] for x in ordered_trials if x["evaluation_id"])
                expected_evaluation_digests = tuple(x["evaluation_digest"] for x in ordered_trials if x["evaluation_digest"])
                expected_control_ids = tuple(x["control_id"] for x in expected_controls)
                expected_control_digests = tuple(x["control_digest"] for x in expected_controls)
                computed_id, computed_digest = _identity("attribution-result", result.payload())
                expected_lineage = (protocol.campaign_digest,) + expected_digests + expected_control_digests
                if ((result.result_id, result.result_digest) != (computed_id, computed_digest)
                        or result.schema_version != RESULT_SCHEMA
                        or result.campaign_digest != protocol.campaign_digest
                        or result.ordered_trial_ids != protocol.trial_ids
                        or expected_ordered_trial_ids != protocol.trial_ids
                        or result.trial_record_ids != expected_ids or result.trial_digests != expected_digests
                        or result.evaluation_ids != expected_evaluations or result.evaluation_digests != expected_evaluation_digests
                        or result.control_ids != expected_control_ids or result.control_digests != expected_control_digests
                        or result.reconstruction_lineage != expected_lineage
                        or result.classification != _classification({x["outcome"] for x in ordered_trials})
                        or result.attribution_posture != ATTRIBUTION_POSTURE or result.production_ready is not False
                        or result.evidence_class != protocol.evidence_class or result.result_id in results):
                    raise AttributionCampaignError("campaign_history_corrupt")
            except (KeyError, TypeError, ValueError) as exc:
                raise AttributionCampaignError("campaign_history_corrupt") from exc
            _false(result.authority)
            results[result.result_id] = row
        return {"protocols":len(protocols), "controls":len(controls), "trials":len(trials), "results":len(results), "signals":len(self._read("signals"))}


def campaign_epistemic_binding(*, proposition_id: str, result: CampaignResult,
                               owner: MaintenancePostAdoptionAttributionCampaignOwner) -> Any:
    from sentientos.persistent_epistemic_state import make_evidence_binding
    if owner.result(result.campaign_id) != result:
        raise AttributionCampaignError("campaign_result_not_recovered_from_custody")
    expected_id, expected_digest = _identity("attribution-result", result.payload())
    _false(result.authority)
    if (result.schema_version != RESULT_SCHEMA or result.attribution_posture != ATTRIBUTION_POSTURE
            or result.classification not in RESULTS
            or (result.result_id, result.result_digest) != (expected_id, expected_digest)):
        raise AttributionCampaignError("campaign_result_identity_unverified")
    # Control source identities/classes are caller supplied and have no
    # authenticated issuer in this owner. Preserve the aggregate as historical
    # context without calling it independent or fresh evidence.
    return make_evidence_binding(proposition_id=proposition_id,
        source_artifact_id=result.result_id, source_digest=result.result_digest,
        source_schema=result.schema_version, source_class="post_adoption_attribution_campaign",
        observation_time=result.completed_at, evidence_relation="contextualizes",
        dependency_kind="unknown_dependency", dependency_group=None,
        upstream_binding_ids=(), freshness="unknown",
        reliability_posture="control_source_issuers_unverified")


def developmental_evidence_record(result: CampaignResult,
                                  owner: MaintenancePostAdoptionAttributionCampaignOwner) -> Mapping[str, Any]:
    if owner.result(result.campaign_id) != result:
        raise AttributionCampaignError("campaign_result_not_recovered_from_custody")
    return {"source_kind":"post_adoption_attribution_campaign", "result_id":result.result_id,
        "result_digest":result.result_digest, "campaign_id":result.campaign_id, "campaign_digest":result.campaign_digest,
        "classification":result.classification, "evaluation_ids":result.evaluation_ids, "control_ids":result.control_ids,
        "reconstruction_lineage":result.reconstruction_lineage, "selectable_evidence_only":True,
        "interpretation_performed":False, "authority":dict(FALSE_AUTHORITY)}


def campaign_improvement_signal_record(result: CampaignResult) -> Mapping[str, Any] | None:
    kinds = {"repeated_target_contradiction_under_matched_controls":"recurring_failure",
        "protected_regression_observed":"recurring_failure", "heterogeneous_repeated_outcome":"recurring_failure",
        "environmental_confound_detected":"telemetry_gap", "insufficient_control_evidence":"telemetry_gap",
        "insufficient_target_evidence":"telemetry_gap", "measurement_failure":"telemetry_gap"}
    kind = kinds.get(result.classification)
    if kind is None: return None
    return {"source_kind":"post_adoption_attribution_campaign", "finding_kind":kind,
        "severity":"high" if result.classification == "protected_regression_observed" else "medium",
        "description":f"Campaign-level {result.classification} for {result.campaign_id}",
        "spec_id":result.campaign_id, "source_artifact":result.result_id, "source_digest":result.result_digest,
        "evidence_refs":list(result.reconstruction_lineage), "observed_at":result.completed_at,
        "declared_constraints":["proposal_only","campaign_level_distinct_finding","no_repository_mutation","no_adoption","no_rollback"],
        "signal_handoff_only":True, "repository_mutation_performed":False, "adoption_performed":False,
        "provider_or_network_or_git_operation_performed":False, "trial_performed":False}


__all__ = ["MaintenancePostAdoptionAttributionCampaignOwner", "AttributionCampaignError", "ControlDefinition",
    "CampaignProtocol", "ControlObservation", "CampaignTrial", "CampaignResult", "make_campaign_protocol",
    "make_control_observation", "campaign_epistemic_binding", "developmental_evidence_record",
    "campaign_improvement_signal_record", "ATTRIBUTION_POSTURE", "RESULTS", "SOURCE_CLASSES", "CONTROL_DESIGNS"]

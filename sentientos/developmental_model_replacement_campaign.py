"""Preregistered descriptive replication of one frozen model-replacement experiment."""
from __future__ import annotations

import json
import os
import re
import secrets
import stat
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Mapping, Sequence, cast

_fcntl: ModuleType | None
try:
    import fcntl as _fcntl
except ImportError:  # Keep imports usable on Windows; custody fails closed there.
    _fcntl = None

from .developmental_model_replacement_experiment import (
    CONDITION_ORDER, FAMILY_TASK_SCHEMA_V3, FAMILY_TASK_SCHEMA_V4, NON_CLAIMS,
    DevelopmentalModelReplacementError,
    DevelopmentalModelReplacementExperiment, _digest,
    ModelReplacementArtifactStore,
)
from .windows_handle_custody import WindowsHandleCustodyError, read_regular_files

PROTOCOL_SCHEMA = "sentientos.developmental_model_replacement_campaign_protocol:v1"
SCORED_PROTOCOL_SCHEMA = "sentientos.developmental_model_replacement_campaign_protocol:v2"
STATE_SCHEMA = "sentientos.developmental_model_replacement_campaign_state:v1"
LEGACY_REPORT_SCHEMA = "sentientos.developmental_model_replacement_campaign_report:v1"
PREVIOUS_REPORT_SCHEMA = "sentientos.developmental_model_replacement_campaign_report:v2"
REPORT_SCHEMA = "sentientos.developmental_model_replacement_campaign_report:v3"
WORLD_STATE_RECORD_SCHEMA = (
    "sentientos.developmental_model_replacement_campaign_world_state_record:v1")
MIN_TRIALS = 2
MAX_TRIALS = 32
CAMPAIGN_NON_CLAIMS = NON_CLAIMS + (
    "statistical_significance", "hypothesis_probability", "longitudinal_development",
)
MAX_CAMPAIGN_ARTIFACT_BYTES = 4_194_304
MAX_CAMPAIGN_STATE_REVISIONS = 256
_CAMPAIGN_ID = re.compile(r"model-replacement-campaign-[0-9a-f]{24}\Z")
_REPORT_ID = re.compile(r"model-replacement-campaign-report-[0-9a-f]{24}\Z")
AGGREGATION_RULES = (
    "exact_verified_trial_artifacts_only", "ordered_counting_without_inference",
    "preserve_negative_unstable_and_invalid_outcomes",
)


@dataclass(frozen=True)
class CampaignProtocol:
    campaign_id: str
    campaign_digest: str
    base_protocol_id: str
    base_protocol_digest: str
    causal_context_id: str
    causal_context_digest: str
    model_a_identity_digest: str
    model_b_identity_digest: str
    model_a_provenance_manifest_digest: str
    model_b_provenance_manifest_digest: str
    history_record_set_digest: str
    current_projection_digest: str
    inference_budget: Mapping[str, Any]
    generation_posture: Mapping[str, Any]
    condition_order: tuple[str, ...]
    planned_trial_count: int
    trial_ids: tuple[str, ...]
    aggregation_rules: tuple[str, ...] = AGGREGATION_RULES
    non_claims: tuple[str, ...] = CAMPAIGN_NON_CLAIMS
    grants_authority: bool = False
    schema_version: str = PROTOCOL_SCHEMA
    objective_task_plan_digest: str | None = None

    def semantic_payload(self) -> dict[str, Any]:
        value = asdict(self)
        value.pop("campaign_id"); value.pop("campaign_digest")
        # Keep the historical v1 identity scope unchanged.
        if self.schema_version == PROTOCOL_SCHEMA:
            value.pop("objective_task_plan_digest")
        return value

    @classmethod
    def create(cls, experiment: DevelopmentalModelReplacementExperiment,
               trial_ids: Sequence[str]) -> "CampaignProtocol":
        ids = tuple(trial_ids)
        if not MIN_TRIALS <= len(ids) <= MAX_TRIALS or len(set(ids)) != len(ids):
            raise DevelopmentalModelReplacementError("campaign_trial_inventory_invalid")
        # Reuse the experiment's validator without allowing a trial to execute.
        for trial_id in ids:
            if not trial_id or len(trial_id) > 128 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in trial_id):
                raise DevelopmentalModelReplacementError("trial_id_invalid")
        p, c = experiment.protocol, experiment.context
        plan = experiment.objective_plan
        plan_digest = str(plan["plan_digest"]) if plan is not None else None
        if plan is not None:
            # The oracle is immutable and available before campaign identity or
            # any serving worker can be constructed.
            experiment.store.persist_objective_plan(plan)
        raw = cls("", "", p.protocol_id, p.protocol_digest, c.context_id, c.context_digest,
                  p.model_a_identity.identity_digest, p.model_b_identity.identity_digest,
                  p.model_a_provenance_digest, p.model_b_provenance_digest,
                  c.history_record_set_digest, c.current_projection_digest,
                  dict(c.inference_budget), dict(c.generation_posture), p.condition_order,
                  len(ids), ids, schema_version=(SCORED_PROTOCOL_SCHEMA if plan is not None else PROTOCOL_SCHEMA),
                  objective_task_plan_digest=plan_digest)
        payload = raw.semantic_payload()
        digest = _digest(payload)
        return replace(raw, campaign_id="model-replacement-campaign-" + digest[7:31], campaign_digest=digest)

    def verify(self) -> None:
        trial_ids_valid = (
            type(self.trial_ids) is tuple
            and all(type(trial_id) is str and 0 < len(trial_id) <= 128
                and all(character in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
                    for character in trial_id)
                for trial_id in self.trial_ids)
        )
        payload = self.semantic_payload()
        digest = _digest(payload)
        if (self.campaign_digest != digest or self.campaign_id != "model-replacement-campaign-" + digest[7:31]
                or self.schema_version not in {PROTOCOL_SCHEMA, SCORED_PROTOCOL_SCHEMA}
                or type(self.grants_authority) is not bool or self.grants_authority is not False
                or self.condition_order != CONDITION_ORDER
                or type(self.condition_order) is not tuple
                or type(self.planned_trial_count) is not int
                or not MIN_TRIALS <= self.planned_trial_count <= MAX_TRIALS
                or not trial_ids_valid
                or self.planned_trial_count != len(self.trial_ids)
                or len(set(self.trial_ids)) != len(self.trial_ids)
                or type(self.aggregation_rules) is not tuple
                or self.aggregation_rules != AGGREGATION_RULES
                or type(self.non_claims) is not tuple
                or self.non_claims != CAMPAIGN_NON_CLAIMS
                or (self.schema_version == PROTOCOL_SCHEMA and self.objective_task_plan_digest is not None)
                or (self.schema_version == SCORED_PROTOCOL_SCHEMA and
                    (not isinstance(self.objective_task_plan_digest, str)
                     or len(self.objective_task_plan_digest) != 71
                     or not self.objective_task_plan_digest.startswith("sha256:")
                     or any(c not in "0123456789abcdef" for c in self.objective_task_plan_digest[7:])))):
            raise DevelopmentalModelReplacementError("campaign_protocol_invalid")


class CampaignStore:
    def __init__(self, root: Path) -> None:
        selected_root = Path(root)
        if selected_root.is_symlink() or any(parent.is_symlink() for parent in selected_root.parents):
            raise DevelopmentalModelReplacementError("campaign_store_root_symlink")
        # Preserve the caller's lexical path on Windows. Resolving it first
        # would follow a junction before the handle-bound reader can reject it.
        self.state_root = Path(os.path.abspath(selected_root))
        self.root = self.state_root / "developmental_experiments" / "model_replacement_campaigns"
        self.protocols, self.states = self.root / "protocols", self.root / "state"
        self.failures, self.reports = self.root / "failures", self.root / "reports"
        self.state_history = self.root / "state-history"

    @staticmethod
    def _require_descriptor_storage() -> None:
        required = (os.open, os.mkdir, os.link, os.rename, os.unlink)
        if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW")
                or any(function not in os.supports_dir_fd for function in required)
                or _fcntl is None):
            raise DevelopmentalModelReplacementError("campaign_store_unsupported_platform")

    def _open_kind_directory(self, kind: str, *, create: bool) -> int:
        if kind not in {"protocols", "state", "state-history", "failures", "reports"}:
            raise DevelopmentalModelReplacementError("campaign_store_path_invalid")
        self._require_descriptor_storage()
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
        descriptor: int | None = None
        try:
            descriptor = os.open(os.sep, flags)
            components = (*self.state_root.parts[1:], "developmental_experiments",
                "model_replacement_campaigns", kind)
            for component in components:
                if create:
                    try:
                        os.mkdir(component, 0o700, dir_fd=descriptor)
                    except FileExistsError:
                        pass
                next_descriptor = os.open(component, flags, dir_fd=descriptor)
                if not stat.S_ISDIR(os.fstat(next_descriptor).st_mode):
                    os.close(next_descriptor)
                    raise DevelopmentalModelReplacementError("campaign_store_path_invalid")
                os.close(descriptor)
                descriptor = next_descriptor
            return descriptor
        except DevelopmentalModelReplacementError:
            if descriptor is not None:
                os.close(descriptor)
            raise
        except OSError as exc:
            if descriptor is not None:
                os.close(descriptor)
            raise DevelopmentalModelReplacementError("campaign_store_path_invalid") from exc

    def _artifact_location(self, path: Path) -> tuple[str, str]:
        try:
            relative = path.relative_to(self.root)
        except ValueError as exc:
            raise DevelopmentalModelReplacementError("campaign_store_path_invalid") from exc
        if len(relative.parts) != 2 or relative.parts[0] not in {"protocols", "state", "state-history", "failures", "reports"}:
            raise DevelopmentalModelReplacementError("campaign_store_path_invalid")
        filename = relative.parts[1]
        if not filename or filename in {".", ".."} or "/" in filename or "\\" in filename:
            raise DevelopmentalModelReplacementError("campaign_store_path_invalid")
        return relative.parts[0], filename

    def _read_json(self, path: Path, *, missing_code: str, invalid_code: str) -> dict[str, Any]:
        kind, filename = self._artifact_location(path)
        if os.name == "nt":
            try:
                entries = read_regular_files(path.parent, max_entries=1,
                    max_file_bytes=MAX_CAMPAIGN_ARTIFACT_BYTES,
                    max_total_bytes=MAX_CAMPAIGN_ARTIFACT_BYTES,
                    selected_names=(filename,))
            except WindowsHandleCustodyError as exc:
                if str(exc) == "explicit_file_missing":
                    raise DevelopmentalModelReplacementError(missing_code) from exc
                raise DevelopmentalModelReplacementError(invalid_code) from exc
            if not entries:
                raise DevelopmentalModelReplacementError(missing_code)
            if len(entries) != 1 or entries[0][0] != filename:
                raise DevelopmentalModelReplacementError(invalid_code)
            try:
                raw = entries[0][1]
                value = json.loads(raw.decode("utf-8"))
                canonical = json.dumps(value, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=True).encode("utf-8") if isinstance(value, dict) else b""
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise DevelopmentalModelReplacementError(invalid_code) from exc
            if not isinstance(value, dict) or canonical != raw:
                raise DevelopmentalModelReplacementError(invalid_code)
            return value
        directory_fd: int | None = None
        descriptor: int | None = None
        try:
            directory_fd = self._open_kind_directory(kind, create=False)
            descriptor = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
            metadata = os.fstat(descriptor)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_CAMPAIGN_ARTIFACT_BYTES
                    or metadata.st_nlink != 1):
                raise DevelopmentalModelReplacementError(invalid_code)
            remaining = metadata.st_size
            chunks: list[bytes] = []
            while remaining:
                chunk = os.read(descriptor, min(remaining, 65536))
                if not chunk:
                    raise DevelopmentalModelReplacementError(invalid_code)
                chunks.append(chunk)
                remaining -= len(chunk)
            raw = b"".join(chunks)
            after = os.fstat(descriptor)
            value = json.loads(raw.decode("utf-8"))
            canonical = json.dumps(value, sort_keys=True, separators=(",", ":"),
                ensure_ascii=True).encode("utf-8") if isinstance(value, dict) else b""
            if not isinstance(value, dict):
                raise DevelopmentalModelReplacementError(invalid_code)
            if (canonical != raw or len(raw) != metadata.st_size
                    or after.st_dev != metadata.st_dev or after.st_ino != metadata.st_ino
                    or after.st_size != metadata.st_size or after.st_mtime_ns != metadata.st_mtime_ns):
                raise DevelopmentalModelReplacementError(invalid_code)
            return value
        except DevelopmentalModelReplacementError:
            raise
        except FileNotFoundError as exc:
            raise DevelopmentalModelReplacementError(missing_code) from exc
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DevelopmentalModelReplacementError(invalid_code) from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if directory_fd is not None:
                os.close(directory_fd)

    def _write_immutable(self, path: Path, value: Mapping[str, Any]) -> None:
        normalized = json.loads(json.dumps(dict(value), sort_keys=True))
        encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True).encode("utf-8")
        if len(encoded) > MAX_CAMPAIGN_ARTIFACT_BYTES:
            raise DevelopmentalModelReplacementError("campaign_artifact_size_limit_exceeded")
        kind, filename = self._artifact_location(path)
        directory_fd = self._open_kind_directory(kind, create=True)
        temporary_name = ".campaign-" + secrets.token_hex(16) + ".tmp"
        temporary_created = False
        try:
            try:
                prior = self._read_json(path, missing_code="campaign_artifact_missing",
                    invalid_code="campaign_artifact_tampered")
            except DevelopmentalModelReplacementError as exc:
                if str(exc) != "campaign_artifact_missing":
                    raise
                prior = None
            if prior is not None:
                if prior != normalized:
                    raise DevelopmentalModelReplacementError("campaign_artifact_identity_collision")
                return
            descriptor = os.open(temporary_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o600, dir_fd=directory_fd)
            temporary_created = True
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary_name, filename, src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd, follow_symlinks=False)
            except FileExistsError:
                prior = self._read_json(path, missing_code="campaign_artifact_missing",
                    invalid_code="campaign_artifact_tampered")
                if prior != normalized:
                    raise DevelopmentalModelReplacementError("campaign_artifact_identity_collision")
            os.fsync(directory_fd)
        except OSError as exc:
            raise DevelopmentalModelReplacementError("campaign_artifact_publication_failed") from exc
        finally:
            if temporary_created:
                try:
                    os.unlink(temporary_name, dir_fd=directory_fd)
                except FileNotFoundError:
                    pass
            os.close(directory_fd)

    def immutable(self, path: Path, value: Mapping[str, Any]) -> None:
        self._write_immutable(path, value)

    def protocol_path(self, campaign_id: str) -> Path: return self.protocols / f"{campaign_id}.json"
    def state_path(self, campaign_id: str) -> Path: return self.states / f"{campaign_id}.json"

    def state_revision_path(self, campaign_id: str, revision: int, state_digest: str) -> Path:
        if (not _CAMPAIGN_ID.fullmatch(campaign_id) or type(revision) is not int
                or revision < 0 or revision > MAX_CAMPAIGN_STATE_REVISIONS
                or not isinstance(state_digest, str) or len(state_digest) != 71
                or not state_digest.startswith("sha256:")
                or any(character not in "0123456789abcdef" for character in state_digest[7:])):
            raise DevelopmentalModelReplacementError("campaign_state_identity_invalid")
        return self.state_history / f"{campaign_id}-r{revision}-{state_digest[7:]}.json"

    def persist_protocol(self, protocol: CampaignProtocol) -> None:
        protocol.verify(); self._write_immutable(self.protocol_path(protocol.campaign_id), asdict(protocol))

    def verify_protocol(self, protocol: CampaignProtocol) -> None:
        actual = self._read_json(self.protocol_path(protocol.campaign_id),
            missing_code="campaign_protocol_custody_changed", invalid_code="campaign_protocol_custody_changed")
        if actual != json.loads(json.dumps(asdict(protocol))): raise DevelopmentalModelReplacementError("campaign_protocol_custody_changed")

    def write_state(self, protocol: CampaignProtocol, body: Mapping[str, Any]) -> dict[str, Any]:
        semantic = {key: value for key, value in body.items() if key not in {"state_digest", "campaign_id", "campaign_digest", "schema_version"}}
        semantic = {**semantic, "campaign_id": protocol.campaign_id, "campaign_digest": protocol.campaign_digest,
                    "schema_version": STATE_SCHEMA}
        if not _CAMPAIGN_ID.fullmatch(protocol.campaign_id):
            raise DevelopmentalModelReplacementError("campaign_state_identity_invalid")
        kind, filename = self._artifact_location(self.state_path(protocol.campaign_id))
        directory_fd = self._open_kind_directory(kind, create=True)
        fcntl_module = _fcntl
        if fcntl_module is None:
            os.close(directory_fd)
            raise DevelopmentalModelReplacementError("campaign_store_unsupported_platform")
        lock_fd: int | None = None
        temporary_name = ".campaign-state-" + secrets.token_hex(16) + ".tmp"
        temporary_created = False
        try:
            lock_fd = os.open(".state.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
                0o600, dir_fd=directory_fd)
            fcntl_module.flock(lock_fd, fcntl_module.LOCK_EX)
            try:
                prior = self._read_json(self.state_path(protocol.campaign_id),
                    missing_code="campaign_state_missing", invalid_code="campaign_state_tampered")
            except DevelopmentalModelReplacementError as exc:
                if str(exc) != "campaign_state_missing":
                    raise
                prior = None
            supplied_digest = body.get("state_digest")
            if prior is None:
                if supplied_digest is not None:
                    raise DevelopmentalModelReplacementError("campaign_state_stale_writer")
                semantic.update({"state_revision": 1, "previous_state_digest": None})
            else:
                self.load_state(protocol)
                prior_semantic = {key: item for key, item in prior.items() if key != "state_digest"}
                if (prior.get("state_digest") != _digest(prior_semantic)
                        or prior.get("campaign_digest") != protocol.campaign_digest):
                    raise DevelopmentalModelReplacementError("campaign_state_tampered")
                if supplied_digest != prior.get("state_digest"):
                    raise DevelopmentalModelReplacementError("campaign_state_stale_writer")
                prior_revision = prior.get("state_revision", 0)
                if type(prior_revision) is not int or not 0 <= prior_revision < MAX_CAMPAIGN_STATE_REVISIONS:
                    raise DevelopmentalModelReplacementError("campaign_state_revision_invalid")
                self._write_immutable(self.state_revision_path(protocol.campaign_id,
                    prior_revision, str(prior["state_digest"])), prior)
                semantic.update({"state_revision": prior_revision + 1,
                    "previous_state_digest": prior["state_digest"]})
            value = {**semantic, "state_digest": _digest(semantic)}
            self._write_immutable(self.state_revision_path(protocol.campaign_id,
                value["state_revision"], value["state_digest"]), value)
            encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                ensure_ascii=True).encode("utf-8")
            if len(encoded) > MAX_CAMPAIGN_ARTIFACT_BYTES:
                raise DevelopmentalModelReplacementError("campaign_state_size_limit_exceeded")
            descriptor = os.open(temporary_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                0o600, dir_fd=directory_fd)
            temporary_created = True
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.rename(temporary_name, filename, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
            os.fsync(directory_fd)
            return value
        except OSError as exc:
            raise DevelopmentalModelReplacementError("campaign_state_publication_failed") from exc
        finally:
            if temporary_created:
                try:
                    os.unlink(temporary_name, dir_fd=directory_fd)
                except FileNotFoundError:
                    pass
            if lock_fd is not None:
                try:
                    fcntl_module.flock(lock_fd, fcntl_module.LOCK_UN)
                finally:
                    os.close(lock_fd)
            os.close(directory_fd)

    def load_state(self, protocol: CampaignProtocol) -> dict[str, Any]:
        value = self._read_json(self.state_path(protocol.campaign_id),
            missing_code="campaign_state_unavailable", invalid_code="campaign_state_tampered")
        semantic = {k: v for k, v in value.items() if k != "state_digest"}
        revision = value.get("state_revision", 0)
        predecessor = value.get("previous_state_digest")
        if (value.get("state_digest") != _digest(semantic)
                or value.get("campaign_digest") != protocol.campaign_digest
                or type(revision) is not int or revision < 0
                or (revision == 0 and predecessor is not None)
                or (predecessor is not None and (not isinstance(predecessor, str)
                    or not predecessor.startswith("sha256:")))
                or (revision > 1 and predecessor is None)):
            raise DevelopmentalModelReplacementError("campaign_state_tampered")
        if revision > 0:
            current = value
            for expected_revision in range(revision, -1, -1):
                current_revision = current.get("state_revision", 0)
                current_digest = current.get("state_digest")
                if current_revision != expected_revision or not isinstance(current_digest, str):
                    raise DevelopmentalModelReplacementError("campaign_state_predecessor_invalid")
                snapshot = self._read_json(self.state_revision_path(protocol.campaign_id,
                    expected_revision, current_digest), missing_code="campaign_state_predecessor_missing",
                    invalid_code="campaign_state_predecessor_invalid")
                snapshot_semantic = {key: item for key, item in snapshot.items() if key != "state_digest"}
                if snapshot != current or current_digest != _digest(snapshot_semantic):
                    raise DevelopmentalModelReplacementError("campaign_state_predecessor_invalid")
                previous = current.get("previous_state_digest")
                if expected_revision == 0:
                    if previous is not None:
                        raise DevelopmentalModelReplacementError("campaign_state_predecessor_invalid")
                    break
                if expected_revision == 1:
                    if previous is None:
                        break
                    if not isinstance(previous, str):
                        raise DevelopmentalModelReplacementError("campaign_state_predecessor_invalid")
                    # A legacy pre-journal state is preserved as revision zero.
                    legacy = self._read_json(self.state_revision_path(protocol.campaign_id, 0, previous),
                        missing_code="campaign_state_predecessor_missing",
                        invalid_code="campaign_state_predecessor_invalid")
                    legacy_semantic = {key: item for key, item in legacy.items() if key != "state_digest"}
                    if (legacy.get("state_digest") != previous or _digest(legacy_semantic) != previous
                            or legacy.get("campaign_digest") != protocol.campaign_digest):
                        raise DevelopmentalModelReplacementError("campaign_state_predecessor_invalid")
                    break
                if not isinstance(previous, str):
                    raise DevelopmentalModelReplacementError("campaign_state_predecessor_invalid")
                current = self._read_json(self.state_revision_path(protocol.campaign_id,
                    expected_revision - 1, previous), missing_code="campaign_state_predecessor_missing",
                    invalid_code="campaign_state_predecessor_invalid")
        return value


class DevelopmentalModelReplacementCampaign:
    def __init__(self, experiment: DevelopmentalModelReplacementExperiment,
                 protocol: CampaignProtocol, store: CampaignStore, state: Mapping[str, Any]) -> None:
        self.experiment, self.protocol, self.store, self.state = experiment, protocol, store, dict(state)
        self.recovery_posture = "not_reconstructed"
        self.recovery_condition_journal: dict[str, Any] | None = None

    @classmethod
    def create(cls, *, experiment: DevelopmentalModelReplacementExperiment,
               artifact_root: Path, trial_ids: Sequence[str]) -> "DevelopmentalModelReplacementCampaign":
        # Freeze every identity, including a scored task plan, before campaign
        # publication. A later runner can only reconstruct this exact bundle.
        experiment.store.persist_context(experiment.context)
        experiment.store.persist_protocol(experiment.protocol)
        experiment.store.persist_provenance(experiment.provenance_a)
        experiment.store.persist_provenance(experiment.provenance_b)
        if experiment.objective_plan is not None:
            experiment.store.persist_objective_plan(experiment.objective_plan)
        protocol, store = CampaignProtocol.create(experiment, trial_ids), CampaignStore(artifact_root)
        store.persist_protocol(protocol)
        state = store.write_state(protocol, {"completed_trials": [], "next_trial_id": protocol.trial_ids[0],
            "in_progress_trial_id": None, "validity": "valid_incomplete", "failure_reason": None})
        return cls(experiment, protocol, store, state)

    @classmethod
    def reconstruct(cls, *, experiment: DevelopmentalModelReplacementExperiment,
                    artifact_root: Path, campaign_id: str) -> "DevelopmentalModelReplacementCampaign":
        store = CampaignStore(artifact_root)
        if not isinstance(campaign_id, str) or not _CAMPAIGN_ID.fullmatch(campaign_id):
            raise DevelopmentalModelReplacementError("campaign_protocol_identity_invalid")
        raw = store._read_json(store.protocol_path(campaign_id),
            missing_code="campaign_protocol_custody_changed", invalid_code="campaign_protocol_custody_changed")
        try:
            raw["trial_ids"] = tuple(raw["trial_ids"]); raw["condition_order"] = tuple(raw["condition_order"])
            raw["aggregation_rules"] = tuple(raw["aggregation_rules"]); raw["non_claims"] = tuple(raw["non_claims"])
            protocol = CampaignProtocol(**raw); protocol.verify(); store.verify_protocol(protocol)
        except (KeyError, TypeError, DevelopmentalModelReplacementError) as exc:
            raise DevelopmentalModelReplacementError("campaign_protocol_custody_changed") from exc
        campaign = cls(experiment, protocol, store, store.load_state(protocol))
        campaign._verify_experiment()
        if campaign.state.get("in_progress_trial_id"):
            trial_id = str(campaign.state["in_progress_trial_id"])
            if trial_id != campaign.state.get("next_trial_id"):
                raise DevelopmentalModelReplacementError("campaign_interrupted_trial_identity_conflict")
            # A campaign recovery read must never call the inference endpoint or
            # reinterpret a started condition as a completed trial. Preserve the
            # exact durable in-progress state for explicit later review.
            campaign.recovery_condition_journal = experiment.inspect_trial_custody(
                trial_id=trial_id)
            campaign.recovery_posture = "interrupted_trial_preserved_not_replayed"
        else:
            campaign.recovery_posture = "durable_state_reconstructed"
        return campaign

    @classmethod
    def inspect_custody(cls, *, artifact_root: Path, campaign_id: str) -> dict[str, Any]:
        """Verify bounded campaign protocol and state without an inference endpoint."""
        if not isinstance(campaign_id, str) or not _CAMPAIGN_ID.fullmatch(campaign_id):
            raise DevelopmentalModelReplacementError("campaign_protocol_identity_invalid")
        store = CampaignStore(artifact_root)
        raw = store._read_json(store.protocol_path(campaign_id),
            missing_code="campaign_protocol_custody_changed", invalid_code="campaign_protocol_custody_changed")
        try:
            raw["trial_ids"] = tuple(raw["trial_ids"])
            raw["condition_order"] = tuple(raw["condition_order"])
            raw["aggregation_rules"] = tuple(raw["aggregation_rules"])
            raw["non_claims"] = tuple(raw["non_claims"])
            protocol = CampaignProtocol(**raw)
            protocol.verify()
            store.verify_protocol(protocol)
            state = store.load_state(protocol)
        except (KeyError, TypeError, DevelopmentalModelReplacementError) as exc:
            raise DevelopmentalModelReplacementError("campaign_protocol_or_state_custody_changed") from exc
        interrupted = state.get("in_progress_trial_id")
        return {"status": "campaign_interrupted_trial_preserved" if interrupted else str(state.get("validity", "unknown")),
            "read_only": True, "effects_performed": [], "campaign_id": protocol.campaign_id,
            "campaign_digest": protocol.campaign_digest, "state_digest": state.get("state_digest"),
            "state_revision": state.get("state_revision"), "completed_trial_count": len(state.get("completed_trials", ())),
            "in_progress_trial_id": interrupted, "recovery_posture":
                "interrupted_trial_preserved_not_replayed" if interrupted else "durable_state_reconstructed"}

    @classmethod
    def verify_report_from_artifacts(cls, *, artifact_root: Path, experiment_state_root: Path,
                                     campaign_id: str, report_id: str,
                                     expected_report_digest: str) -> dict[str, Any]:
        """Rebuild a campaign report using saved artifacts, without model endpoints.

        This is an evidence recovery path: it verifies the frozen protocol and
        context manifests, objective plan, campaign state, and every referenced
        run artifact. It performs no inference and grants no authority.
        """
        if not isinstance(campaign_id, str) or not _CAMPAIGN_ID.fullmatch(campaign_id):
            raise DevelopmentalModelReplacementError("campaign_protocol_identity_invalid")
        campaign_store = CampaignStore(artifact_root)
        raw = campaign_store._read_json(campaign_store.protocol_path(campaign_id),
            missing_code="campaign_protocol_custody_changed",
            invalid_code="campaign_protocol_custody_changed")
        try:
            for key in ("trial_ids", "condition_order", "aggregation_rules", "non_claims"):
                raw[key] = tuple(raw[key])
            campaign_protocol = CampaignProtocol(**raw)
            campaign_protocol.verify()
            campaign_store.verify_protocol(campaign_protocol)
            state = campaign_store.load_state(campaign_protocol)
            experiment_store = ModelReplacementArtifactStore(experiment_state_root, read_only=True)
            protocol = experiment_store.load_verified_protocol(
                campaign_protocol.base_protocol_id, campaign_protocol.base_protocol_digest)
            context = experiment_store.load_verified_context(
                campaign_protocol.causal_context_id, campaign_protocol.causal_context_digest)
            plan = (experiment_store.verify_objective_plan(protocol)
                if campaign_protocol.objective_task_plan_digest is not None else None)
            if (protocol.causal_context_id != context["context_id"]
                    or protocol.causal_context_digest != context["context_digest"]
                    or campaign_protocol.objective_task_plan_digest is not None
                        and campaign_protocol.objective_task_plan_digest != plan.get("plan_digest")):
                raise DevelopmentalModelReplacementError("campaign_artifact_binding_invalid")
            context_view = SimpleNamespace(
                verify=lambda: None,
                context_id=context["context_id"], context_digest=context["context_digest"],
                history_record_set_digest=context["history_record_set_digest"],
                current_projection_digest=context["current_projection_digest"],
                inference_budget=context["inference_budget"],
                generation_posture=context["generation_posture"])
            experiment_view = SimpleNamespace(protocol=protocol, context=context_view,
                objective_plan=plan, store=experiment_store)
            campaign = cls(experiment_view, campaign_protocol, campaign_store, state)
            campaign._verify_experiment()
            return campaign.load_report(report_id,
                expected_report_digest=expected_report_digest)
        except (KeyError, TypeError, ValueError) as exc:
            raise DevelopmentalModelReplacementError(
                "campaign_artifact_reconstruction_failed") from exc

    def _verify_experiment(self) -> None:
        p, c, expected = self.experiment.protocol, self.experiment.context, self.protocol
        self.experiment.context.verify(); p.verify(); self.store.verify_protocol(expected)
        bindings = (p.protocol_id, p.protocol_digest, c.context_id, c.context_digest,
                    p.model_a_identity.identity_digest, p.model_b_identity.identity_digest,
                    p.model_a_provenance_digest, p.model_b_provenance_digest,
                    c.history_record_set_digest, c.current_projection_digest,
                    dict(c.inference_budget), dict(c.generation_posture), p.condition_order)
        registered = (expected.base_protocol_id, expected.base_protocol_digest, expected.causal_context_id,
                      expected.causal_context_digest, expected.model_a_identity_digest, expected.model_b_identity_digest,
                      expected.model_a_provenance_manifest_digest, expected.model_b_provenance_manifest_digest,
                      expected.history_record_set_digest, expected.current_projection_digest,
                      dict(expected.inference_budget), dict(expected.generation_posture), expected.condition_order)
        if bindings != registered: self._invalidate("campaign_control_drift"); raise DevelopmentalModelReplacementError("campaign_control_drift")
        experiment_plan_digest = (self.experiment.objective_plan.get("plan_digest")
            if self.experiment.objective_plan is not None else None)
        if experiment_plan_digest != expected.objective_task_plan_digest:
            self._invalidate("campaign_objective_task_drift")
            raise DevelopmentalModelReplacementError("campaign_objective_task_drift")

    def _invalidate(self, reason: str, *, failure_evidence: Mapping[str, Any] | None = None) -> None:
        self.state = self.store.write_state(self.protocol, {**self.state, "validity": "invalid_incomplete", "failure_reason": reason})
        failure: dict[str, Any] = {"campaign_id": self.protocol.campaign_id, "reason": reason}
        if failure_evidence is not None:
            failure["failure_evidence"] = dict(failure_evidence)
        self.store.immutable(self.store.failures / f"{self.protocol.campaign_id}-{reason}.json",
                             failure)

    def run_next_trial(self) -> dict[str, Any]:
        self.state = self.store.load_state(self.protocol); self._verify_experiment()
        if self.state["next_trial_id"] is None:
            raise DevelopmentalModelReplacementError("campaign_already_complete")
        if self.state["validity"] != "valid_incomplete" or self.state["in_progress_trial_id"]:
            raise DevelopmentalModelReplacementError("campaign_not_runnable")
        trial_id = self.state["next_trial_id"]
        self.state = self.store.write_state(self.protocol, {**self.state, "in_progress_trial_id": trial_id})
        try: run = self.experiment.run(trial_id=trial_id)
        except Exception:
            self._invalidate("campaign_trial_failed_no_retry")
            raise
        if run.get("experiment_completion_posture", "completed") != "completed":
            condition_statuses = run.get("condition_statuses")
            failure_code = next((evidence.get("failure_code")
                for row in condition_statuses if isinstance(row, Mapping)
                and isinstance((evidence := row.get("failure_evidence")), Mapping)
                and isinstance(evidence.get("failure_code"), str)
                and len(evidence["failure_code"]) <= 128
                and all(character.isascii() and
                    (character.isalnum() or character in "_.:-")
                    for character in evidence["failure_code"])), None) \
                if isinstance(condition_statuses, list) else None
            reason = ("campaign_trial_failed_no_retry" if failure_code is not None
                else "campaign_trial_incomplete_no_retry")
            self._invalidate(reason, failure_evidence={
                "trial_id": trial_id, "run_id": run.get("run_id"),
                "run_digest": run.get("run_digest"),
                "experiment_completion_posture": run.get("experiment_completion_posture"),
                "condition_statuses": run.get("condition_statuses"),
            })
            if failure_code is not None:
                # Keep the terminal no-retry state while preserving the
                # concrete owner reason for callers and diagnostics.
                raise DevelopmentalModelReplacementError(failure_code)
            raise DevelopmentalModelReplacementError("campaign_trial_incomplete_no_retry")
        completed = list(self.state["completed_trials"])
        completed.append({"trial_id": trial_id, "run_id": run["run_id"], "run_digest": run["run_digest"]})
        index = len(completed); next_id = self.protocol.trial_ids[index] if index < len(self.protocol.trial_ids) else None
        self.state = self.store.write_state(self.protocol, {"state_digest": self.state["state_digest"],
            "completed_trials": completed, "next_trial_id": next_id,
            "in_progress_trial_id": None, "validity": "valid_complete" if next_id is None else "valid_incomplete",
            "failure_reason": None})
        return run

    def _build_report(self) -> dict[str, Any]:
        self.state = self.store.load_state(self.protocol); self._verify_experiment()
        if self.state["validity"] != "valid_complete": raise DevelopmentalModelReplacementError("campaign_incomplete")
        runs = [self.experiment.store.load_verified_run(item["run_id"], item["run_digest"])
                for item in self.state["completed_trials"]]
        classifications: dict[str, int] = {}
        for run in runs: classifications[run["classification"]] = classifications.get(run["classification"], 0) + 1
        count = len(runs)
        conditions = {}
        for index, condition in enumerate(CONDITION_ORDER):
            digests = [run["observations"][index]["output_digest"] for run in runs]
            conditions[condition] = {"ordered_output_digests": digests, "unique_output_digest_count": len(set(digests)),
                                     "exact_baseline_repeat_count": sum(d == digests[0] for d in digests)}
        def difference_count(key: str) -> int:
            return sum(bool(run["differences"][key]) for run in runs)
        a, b = difference_count("history_effect_model_a"), difference_count("history_effect_model_b")
        restoration = difference_count("model_a_restoration")
        objective_summary: dict[str, Any] | None = None
        if self.protocol.objective_task_plan_digest is not None:
            plan = self.experiment.objective_plan
            if (not isinstance(plan, Mapping)
                    or plan.get("plan_digest") != self.protocol.objective_task_plan_digest):
                raise DevelopmentalModelReplacementError("campaign_objective_task_binding_invalid")
            self.experiment.store.verify_objective_plan(self.experiment.protocol, plan)
            by_condition: dict[str, list[dict[str, Any]]] = {name: [] for name in CONDITION_ORDER}
            for run in runs:
                rows = run.get("observations")
                if not isinstance(rows, list) or len(rows) != len(CONDITION_ORDER):
                    raise DevelopmentalModelReplacementError("campaign_objective_score_inventory_invalid")
                for condition, row in zip(CONDITION_ORDER, rows):
                    score = row.get("objective_task_score") if isinstance(row, Mapping) else None
                    if not isinstance(score, Mapping) or score.get("plan_digest") != self.protocol.objective_task_plan_digest:
                        raise DevelopmentalModelReplacementError("campaign_objective_score_binding_invalid")
                    by_condition[condition].append(dict(score))
            objective_summary = {"objective_task_plan_digest": self.protocol.objective_task_plan_digest,
                "trial_count": count, "condition_status_counts": {
                    condition: {status: sum(score.get("status") == status for score in scores)
                        for status in ("correct", "incorrect", "selective", "invalid_answer",
                            "output_unavailable", "output_truncated")}
                    for condition, scores in by_condition.items()},
                "condition_correct_count": {condition: sum(score.get("correct") is True for score in scores)
                    for condition, scores in by_condition.items()},
                "condition_scored_trial_count": {condition: sum(type(score.get("correct")) is bool for score in scores)
                    for condition, scores in by_condition.items()},
                "claim_scope": "observed_task_correctness_only",
                "independence_or_improvement_claimed": False}
            if plan.get("task", {}).get("schema_version") in {
                    "sentientos.affine_prediction_task_suite:v2",
                    FAMILY_TASK_SCHEMA_V3, FAMILY_TASK_SCHEMA_V4}:
                def answered_count(score: Mapping[str, Any]) -> int:
                    answered = score.get("answered_count")
                    if type(answered) is int:
                        return answered
                    if score.get("status") in {
                            "invalid_answer", "output_unavailable", "output_truncated"}:
                        return 0
                    count_value = score.get("correct_count")
                    return (plan["task_descriptor"].get("probe_count", 0)
                        if type(count_value) is int else 0)

                def abstained_count(score: Mapping[str, Any]) -> int:
                    value = score.get("abstained_count")
                    return value if type(value) is int else 0

                objective_summary["condition_correct_probe_count"] = {
                    condition: sum(score.get("correct_count")
                        if type(score.get("correct_count")) is int else 0
                        for score in scores)
                    for condition, scores in by_condition.items()}
                objective_summary["condition_scored_probe_count"] = {
                    condition: sum(answered_count(score) for score in scores)
                    for condition, scores in by_condition.items()}
                objective_summary["condition_answered_probe_count"] = {
                    condition: sum(answered_count(score) for score in scores)
                    for condition, scores in by_condition.items()}
                objective_summary["condition_abstained_probe_count"] = {
                    condition: sum(abstained_count(score) for score in scores)
                    for condition, scores in by_condition.items()}
                probes = plan["task"].get("probe_inputs")
                if (not isinstance(probes, list) or not probes
                        or any(type(probe) is not int for probe in probes)):
                    raise DevelopmentalModelReplacementError(
                        "campaign_objective_probe_inventory_invalid")
                comparison_pairs = {
                    "model_a_history": ("model_a_history_present",
                        "model_a_history_withheld"),
                    "model_b_history": ("model_b_history_present",
                        "model_b_history_withheld"),
                    "model_difference_with_history": (
                        "model_a_history_present", "model_b_history_present"),
                    "model_difference_without_history": (
                        "model_a_history_withheld", "model_b_history_withheld"),
                    "model_a_restoration": ("model_a_history_present",
                        "model_a_history_restored"),
                }
                probe_rows: list[dict[str, Any]] = []
                for probe_index, probe in enumerate(probes):
                    condition_counts = {condition: {
                        outcome: 0 for outcome in ("correct", "incorrect",
                            "abstained", "invalid_answer", "unscoreable")}
                        for condition in CONDITION_ORDER}
                    transition_counts = {name: {} for name in comparison_pairs}
                    comparable_trials = {name: 0 for name in comparison_pairs}
                    for run in runs:
                        rows = run["observations"]
                        outcomes: dict[str, str | None] = {}
                        for condition, row in zip(CONDITION_ORDER, rows):
                            score = row["objective_task_score"]
                            status = score.get("status")
                            if status == "invalid_answer":
                                outcome: str | None = "invalid_answer"
                            elif status in {"output_unavailable", "output_truncated"}:
                                outcome = None
                            else:
                                answer = score.get("answer")
                                if (not isinstance(answer, list)
                                        or len(answer) != len(probes)):
                                    raise DevelopmentalModelReplacementError(
                                        "campaign_objective_probe_answer_invalid")
                                actual = answer[probe_index]
                                if actual is None and plan["task"].get(
                                        "schema_version") == FAMILY_TASK_SCHEMA_V4:
                                    outcome = "abstained"
                                elif type(actual) is int:
                                    outcome = ("correct" if actual ==
                                        plan["task"]["multiplier"] * probe
                                            + plan["task"]["offset"] else "incorrect")
                                else:
                                    raise DevelopmentalModelReplacementError(
                                        "campaign_objective_probe_answer_invalid")
                            outcomes[condition] = outcome
                            condition_counts[condition][
                                outcome if outcome is not None else "unscoreable"] += 1
                        for name, (left_name, right_name) in comparison_pairs.items():
                            left, right = outcomes[left_name], outcomes[right_name]
                            if left is None or right is None:
                                continue
                            comparable_trials[name] += 1
                            transition = left + "_vs_" + right
                            transition_counts[name][transition] = (
                                transition_counts[name].get(transition, 0) + 1)
                    probe_rows.append({
                        "probe_id": _digest({"probe_input": probe}),
                        "condition_outcome_counts": condition_counts,
                        "comparison_transition_counts": {
                            name: {"comparable_trial_count": comparable_trials[name],
                                "outcomes": transition_counts[name]}
                            for name in comparison_pairs},
                    })
                for condition in CONDITION_ORDER:
                    outcome_totals = {outcome: sum(
                        row["condition_outcome_counts"][condition][outcome]
                        for row in probe_rows)
                        for outcome in ("correct", "incorrect", "abstained",
                            "invalid_answer", "unscoreable")}
                    if (outcome_totals["correct"] != objective_summary[
                            "condition_correct_probe_count"][condition]
                            or outcome_totals["correct"]
                                + outcome_totals["incorrect"]
                                != objective_summary[
                                    "condition_answered_probe_count"][condition]
                            or outcome_totals["abstained"] != objective_summary[
                                "condition_abstained_probe_count"][condition]
                            or sum(outcome_totals.values()) != count * len(probes)):
                        raise DevelopmentalModelReplacementError(
                            "campaign_objective_probe_aggregate_mismatch")
                for name in comparison_pairs:
                    for probe_row in probe_rows:
                        transitions = probe_row["comparison_transition_counts"][name]
                        if (sum(transitions["outcomes"].values())
                                != transitions["comparable_trial_count"]
                                or transitions["comparable_trial_count"] > count):
                            raise DevelopmentalModelReplacementError(
                                "campaign_objective_probe_transition_mismatch")
                objective_summary["per_probe_replication"] = probe_rows
        semantic = {"campaign_id": self.protocol.campaign_id, "campaign_digest": self.protocol.campaign_digest,
            "planned_trial_count": count, "completed_valid_trial_count": count,
            "trial_artifacts": list(self.state["completed_trials"]),
            "per_trial_classification": [{"trial_id": r["trial_id"], "classification": r["classification"]} for r in runs],
            "classification_counts": classifications, "history_effect_model_a_observed_count": a,
            "history_effect_model_b_observed_count": b,
            "history_association_under_both_models_count": sum(r["differences"]["history_effect_model_a"] and r["differences"]["history_effect_model_b"] for r in runs),
            "model_difference_with_history_observed_count": difference_count("model_difference_with_history"),
            "model_difference_without_history_observed_count": difference_count("model_difference_without_history"),
            "model_a_restoration_stable_count": restoration, "condition_output_reproducibility": conditions,
            "all_trials_same_classification": len(classifications) == 1,
            "model_a_history_effect_observed_every_trial": a == count,
            "model_b_history_effect_observed_every_trial": b == count,
            "both_model_history_association_observed_every_trial": a == b == count,
            "model_a_restoration_stable_every_trial": restoration == count,
            "all_condition_output_digests_identical_across_trials": all(v["unique_output_digest_count"] == 1 for v in conditions.values()),
            "claims_posture": "descriptive_exact_counts_only", "non_claims": list(CAMPAIGN_NON_CLAIMS),
            "validity": "valid_completed_replication_campaign", "schema_version": REPORT_SCHEMA}
        if objective_summary is not None:
            semantic["objective_evaluation"] = objective_summary
        digest = _digest(semantic); report = {**semantic, "report_id": "model-replacement-campaign-report-" + digest[7:31], "report_digest": digest}
        return report

    def summarize(self) -> dict[str, Any]:
        report = self._build_report()
        self.store.immutable(self.store.reports / f"{report['report_id']}.json", report)
        return report

    def _report_for_schema(self, report: Mapping[str, Any],
            schema_version: str) -> dict[str, Any]:
        if schema_version not in {LEGACY_REPORT_SCHEMA, PREVIOUS_REPORT_SCHEMA,
                REPORT_SCHEMA}:
            raise DevelopmentalModelReplacementError(
                "campaign_report_schema_unsupported")
        semantic = json.loads(json.dumps({key: value for key, value in report.items()
            if key not in {"report_id", "report_digest"}}, sort_keys=True))
        objective = semantic.get("objective_evaluation")
        if schema_version in {LEGACY_REPORT_SCHEMA, PREVIOUS_REPORT_SCHEMA}:
            if isinstance(objective, Mapping):
                objective = dict(objective)
                if schema_version == LEGACY_REPORT_SCHEMA:
                    objective.pop("per_probe_replication", None)
                answered = objective.get("condition_answered_probe_count")
                scored = objective.get("condition_scored_probe_count")
                status_counts = objective.get("condition_status_counts")
                plan = self.experiment.objective_plan
                task_descriptor = (plan.get("task_descriptor")
                    if isinstance(plan, Mapping) else None)
                probe_count = (task_descriptor.get("probe_count")
                    if isinstance(task_descriptor, Mapping) else None)
                if isinstance(answered, Mapping) or isinstance(scored, Mapping):
                    if (not isinstance(answered, Mapping)
                            or not isinstance(scored, Mapping)
                            or not isinstance(status_counts, Mapping)
                            or type(probe_count) is not int or probe_count < 1):
                        raise DevelopmentalModelReplacementError(
                            "campaign_report_legacy_score_summary_invalid")
                    for condition in CONDITION_ORDER:
                        condition_statuses = status_counts.get(condition)
                        if (not isinstance(condition_statuses, Mapping)
                                or type(answered.get(condition)) is not int
                                or type(scored.get(condition)) is not int
                                or type(condition_statuses.get("invalid_answer")) is not int):
                            raise DevelopmentalModelReplacementError(
                                "campaign_report_legacy_score_summary_invalid")
                        legacy_answered = answered[condition] + (
                            condition_statuses["invalid_answer"] * probe_count)
                        answered[condition] = legacy_answered
                        scored[condition] = legacy_answered
                    objective["condition_answered_probe_count"] = dict(answered)
                    objective["condition_scored_probe_count"] = dict(scored)
                semantic["objective_evaluation"] = objective
        semantic["schema_version"] = schema_version
        digest = _digest(semantic)
        return {**semantic,
            "report_id": "model-replacement-campaign-report-" + digest[7:31],
            "report_digest": digest}

    def load_report(self, report_id: str, *, expected_report_digest: str
            ) -> dict[str, Any]:
        """Reload a report only after rebuilding it from verified trial artifacts."""
        if (not isinstance(report_id, str) or not _REPORT_ID.fullmatch(report_id)
                or not isinstance(expected_report_digest, str)
                or not expected_report_digest.startswith("sha256:")
                or len(expected_report_digest) != 71
                or any(character not in "0123456789abcdef"
                    for character in expected_report_digest[7:])):
            raise DevelopmentalModelReplacementError(
                "campaign_report_identity_invalid")
        stored = self.store._read_json(
            self.store.reports / f"{report_id}.json",
            missing_code="campaign_report_missing",
            invalid_code="campaign_report_tampered")
        semantic = {key: value for key, value in stored.items()
            if key not in {"report_id", "report_digest"}}
        digest = _digest(semantic)
        if (stored.get("report_id") != report_id
                or stored.get("report_digest") != digest
                or digest != expected_report_digest
                or report_id != "model-replacement-campaign-report-" + digest[7:31]
                or stored.get("campaign_id") != self.protocol.campaign_id
                or stored.get("campaign_digest") != self.protocol.campaign_digest):
            raise DevelopmentalModelReplacementError(
                "campaign_report_identity_mismatch")
        rebuilt = self._build_report()
        expected = self._report_for_schema(rebuilt,
            str(stored.get("schema_version") or ""))
        if stored != expected:
            raise DevelopmentalModelReplacementError(
                "campaign_report_trial_binding_mismatch")
        return stored

    def world_state_records(self, *, report_refs: Sequence[tuple[str, str]]) -> list[dict[str, Any]]:
        """Project explicitly selected verified campaign reports as historical evidence."""
        from .world_state_board import record_digest

        references = tuple(report_refs)
        if (len(references) > 32 or any(not isinstance(item, tuple) or len(item) != 2
                or any(not isinstance(value, str) or not value for value in item)
                for item in references)
                or len({item[0] for item in references}) != len(references)):
            raise DevelopmentalModelReplacementError(
                "campaign_report_projection_selection_invalid")
        records: list[dict[str, Any]] = []
        for report_id, expected_report_digest in references:
            report = self.load_report(report_id,
                expected_report_digest=expected_report_digest)
            trial_refs = report.get("trial_artifacts")
            if (not isinstance(trial_refs, list) or not 2 <= len(trial_refs) <= MAX_TRIALS
                    or any(not isinstance(item, Mapping)
                        or not isinstance(item.get("run_id"), str)
                        or not isinstance(item.get("run_digest"), str)
                        for item in trial_refs)):
                raise DevelopmentalModelReplacementError(
                    "campaign_report_trial_inventory_invalid")
            run_refs = tuple((item["run_id"], item["run_digest"])
                for item in trial_refs)
            if len({run_id for run_id, _ in run_refs}) != len(run_refs):
                raise DevelopmentalModelReplacementError(
                    "campaign_report_trial_inventory_invalid")
            run_records = self.experiment.store.world_state_records(run_refs=run_refs)
            records_by_run = {item.get("subject_id"): item for item in run_records
                if isinstance(item, Mapping)}
            expected_run_digests = dict(run_refs)
            if (len(records_by_run) != len(run_records)
                    or set(records_by_run) != set(expected_run_digests)
                    or any(not isinstance(record.get("payload"), Mapping)
                        or record["payload"].get("run_digest")
                            != expected_run_digests[run_id]
                        for run_id, record in records_by_run.items())):
                # A legacy run can be score-verified yet deliberately omitted
                # from cognition projection because its task oracle commitment
                # is unsalted. Never reintroduce its score summary via a
                # campaign-level aggregate.
                raise DevelopmentalModelReplacementError(
                    "campaign_report_run_projection_ineligible")
            event_time: str | None = None
            event_time_posture = "verified_event_time_unavailable"
            trial_event_times: list[dict[str, str]] = []
            if (all(isinstance(records_by_run[run_id].get("observed_at"), str)
                        for run_id, _ in run_refs)):
                try:
                    instants = [datetime.fromisoformat(
                        records_by_run[run_id]["observed_at"].replace("Z", "+00:00"))
                        for run_id, _ in run_refs]
                except (TypeError, ValueError) as exc:
                    raise DevelopmentalModelReplacementError(
                        "campaign_report_event_time_invalid") from exc
                if any(value.tzinfo is None or value.utcoffset() is None
                        or records_by_run[run_id]["observed_at"].endswith("-00:00")
                        for value, (run_id, _) in zip(instants, run_refs)):
                    raise DevelopmentalModelReplacementError(
                        "campaign_report_event_time_invalid")
                event_time = max(instants).astimezone(timezone.utc).isoformat()
                event_time_posture = "all_trial_condition_receipt_times_verified"
                trial_event_times = [{"run_id": run_id, "run_digest": run_digest,
                    "observed_at": records_by_run[run_id]["observed_at"]}
                    for run_id, run_digest in run_refs]
            payload = {
                "campaign_id": report["campaign_id"],
                "campaign_digest": report["campaign_digest"],
                "report_id": report["report_id"],
                "report_digest": report["report_digest"],
                "report_schema_version": report["schema_version"],
                "trial_artifacts": [dict(item) for item in trial_refs],
                "trial_count": report["completed_valid_trial_count"],
                "classification_counts": report["classification_counts"],
                "model_a_identity_digest": self.protocol.model_a_identity_digest,
                "model_b_identity_digest": self.protocol.model_b_identity_digest,
                "history_record_set_digest": self.protocol.history_record_set_digest,
                "current_projection_digest": self.protocol.current_projection_digest,
                "event_time_posture": event_time_posture,
                "verified_trial_event_times": trial_event_times,
                "campaign_observed_at": event_time,
                "claims_posture": report["claims_posture"],
                "non_claims": report["non_claims"],
                "current_truth": False,
                "learning_established": False,
                "authority": False,
            }
            if "objective_evaluation" in report:
                payload["objective_evaluation"] = report["objective_evaluation"]
            if len(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False).encode("utf-8")) > 1_048_576:
                raise DevelopmentalModelReplacementError(
                    "campaign_report_projection_over_bound")
            record: dict[str, Any] = {
                "source_kind": "embodiment",
                "source_id": report_id,
                "schema_version": WORLD_STATE_RECORD_SCHEMA,
                "subject_id": report_id,
                "subject_kind": "developmental_model_replacement_campaign",
                "stage": "observation",
                "disposition": "completed_replication_campaign",
                "evidence_strength": "digest_bound_model_replacement_replication_campaign",
                "payload": payload,
                "effect_claimed": False,
                "effect_proven": False,
            }
            if event_time is not None:
                record["observed_at"] = event_time
            record["digest"] = record_digest(record)
            records.append(record)
        return records

"""Preregistered descriptive replication of one frozen model-replacement experiment."""
from __future__ import annotations

import json
import os
import re
import secrets
import stat
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

try:
    import fcntl as _fcntl
except ImportError:  # Keep imports usable on Windows; custody fails closed there.
    _fcntl = None

from .developmental_model_replacement_experiment import (
    CONDITION_ORDER, NON_CLAIMS, DevelopmentalModelReplacementError,
    DevelopmentalModelReplacementExperiment, _digest,
)

PROTOCOL_SCHEMA = "sentientos.developmental_model_replacement_campaign_protocol:v1"
STATE_SCHEMA = "sentientos.developmental_model_replacement_campaign_state:v1"
REPORT_SCHEMA = "sentientos.developmental_model_replacement_campaign_report:v1"
MIN_TRIALS = 2
MAX_TRIALS = 32
CAMPAIGN_NON_CLAIMS = NON_CLAIMS + (
    "statistical_significance", "hypothesis_probability", "longitudinal_development",
)
MAX_CAMPAIGN_ARTIFACT_BYTES = 4_194_304
MAX_CAMPAIGN_STATE_REVISIONS = 256
_CAMPAIGN_ID = re.compile(r"model-replacement-campaign-[0-9a-f]{24}\Z")
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
        raw = cls("", "", p.protocol_id, p.protocol_digest, c.context_id, c.context_digest,
                  p.model_a_identity.identity_digest, p.model_b_identity.identity_digest,
                  p.model_a_provenance_digest, p.model_b_provenance_digest,
                  c.history_record_set_digest, c.current_projection_digest,
                  dict(c.inference_budget), dict(c.generation_posture), p.condition_order,
                  len(ids), ids)
        payload = asdict(raw); payload.pop("campaign_id"); payload.pop("campaign_digest")
        digest = _digest(payload)
        return replace(raw, campaign_id="model-replacement-campaign-" + digest[7:31], campaign_digest=digest)

    def verify(self) -> None:
        payload = asdict(self); payload.pop("campaign_id"); payload.pop("campaign_digest")
        digest = _digest(payload)
        if (self.campaign_digest != digest or self.campaign_id != "model-replacement-campaign-" + digest[7:31]
                or self.schema_version != PROTOCOL_SCHEMA or self.grants_authority
                or self.condition_order != CONDITION_ORDER
                or not MIN_TRIALS <= self.planned_trial_count <= MAX_TRIALS
                or self.planned_trial_count != len(self.trial_ids) or len(set(self.trial_ids)) != len(self.trial_ids)):
            raise DevelopmentalModelReplacementError("campaign_protocol_invalid")


class CampaignStore:
    def __init__(self, root: Path) -> None:
        selected_root = Path(root)
        if selected_root.is_symlink() or any(parent.is_symlink() for parent in selected_root.parents):
            raise DevelopmentalModelReplacementError("campaign_store_root_symlink")
        self.state_root = selected_root.resolve()
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
        directory_fd: int | None = None
        descriptor: int | None = None
        try:
            directory_fd = self._open_kind_directory(kind, create=False)
            descriptor = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_CAMPAIGN_ARTIFACT_BYTES:
                raise DevelopmentalModelReplacementError(invalid_code)
            remaining = metadata.st_size
            chunks: list[bytes] = []
            while remaining:
                chunk = os.read(descriptor, min(remaining, 65536))
                if not chunk:
                    raise DevelopmentalModelReplacementError(invalid_code)
                chunks.append(chunk)
                remaining -= len(chunk)
            value = json.loads(b"".join(chunks).decode("utf-8"))
            if not isinstance(value, dict):
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
        lock_fd: int | None = None
        temporary_name = ".campaign-state-" + secrets.token_hex(16) + ".tmp"
        temporary_created = False
        try:
            lock_fd = os.open(".state.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
                0o600, dir_fd=directory_fd)
            _fcntl.flock(lock_fd, _fcntl.LOCK_EX)
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
                    _fcntl.flock(lock_fd, _fcntl.LOCK_UN)
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
                if not isinstance(previous, str):
                    raise DevelopmentalModelReplacementError("campaign_state_predecessor_invalid")
                if expected_revision == 1:
                    if previous is None:
                        break
                    # A legacy pre-journal state is preserved as revision zero.
                    legacy = self._read_json(self.state_revision_path(protocol.campaign_id, 0, previous),
                        missing_code="campaign_state_predecessor_missing",
                        invalid_code="campaign_state_predecessor_invalid")
                    legacy_semantic = {key: item for key, item in legacy.items() if key != "state_digest"}
                    if (legacy.get("state_digest") != previous or _digest(legacy_semantic) != previous
                            or legacy.get("campaign_digest") != protocol.campaign_digest):
                        raise DevelopmentalModelReplacementError("campaign_state_predecessor_invalid")
                    break
                current = self._read_json(self.state_revision_path(protocol.campaign_id,
                    expected_revision - 1, previous), missing_code="campaign_state_predecessor_missing",
                    invalid_code="campaign_state_predecessor_invalid")
        return cast(dict[str, Any], value)


class DevelopmentalModelReplacementCampaign:
    def __init__(self, experiment: DevelopmentalModelReplacementExperiment,
                 protocol: CampaignProtocol, store: CampaignStore, state: Mapping[str, Any]) -> None:
        self.experiment, self.protocol, self.store, self.state = experiment, protocol, store, dict(state)

    @classmethod
    def create(cls, *, experiment: DevelopmentalModelReplacementExperiment,
               artifact_root: Path, trial_ids: Sequence[str]) -> "DevelopmentalModelReplacementCampaign":
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
                campaign._invalidate("campaign_interrupted_trial_identity_conflict",
                    failure_evidence={"in_progress_trial_id": trial_id,
                        "next_trial_id": campaign.state.get("next_trial_id")})
                raise DevelopmentalModelReplacementError("campaign_interrupted_trial_identity_conflict")
            try:
                recovered_run = experiment.run(trial_id=trial_id)
            except Exception as exc:
                campaign._invalidate("campaign_interrupted_trial_recovery_failed",
                    failure_evidence={"trial_id": trial_id,
                        "failure_kind": type(exc).__name__})
                raise DevelopmentalModelReplacementError("campaign_interrupted_trial_recovery_failed") from exc
            if recovered_run.get("experiment_completion_posture", "completed") != "completed":
                campaign._invalidate("campaign_interrupted_trial_recovered_incomplete",
                    failure_evidence={"trial_id": trial_id,
                        "run_id": recovered_run.get("run_id"),
                        "run_digest": recovered_run.get("run_digest"),
                        "experiment_completion_posture": recovered_run.get("experiment_completion_posture"),
                        "condition_statuses": recovered_run.get("condition_statuses")})
                raise DevelopmentalModelReplacementError("campaign_interrupted_trial_recovered_incomplete")
            completed = list(campaign.state["completed_trials"])
            if any(item.get("trial_id") == trial_id for item in completed if isinstance(item, Mapping)):
                campaign._invalidate("campaign_interrupted_trial_already_completed",
                    failure_evidence={"trial_id": trial_id, "run_id": recovered_run.get("run_id"),
                        "run_digest": recovered_run.get("run_digest")})
                raise DevelopmentalModelReplacementError("campaign_interrupted_trial_already_completed")
            completed.append({"trial_id": trial_id, "run_id": recovered_run["run_id"],
                "run_digest": recovered_run["run_digest"]})
            index = len(completed)
            next_id = protocol.trial_ids[index] if index < len(protocol.trial_ids) else None
            campaign.state = store.write_state(protocol, {"completed_trials": completed,
                "next_trial_id": next_id, "in_progress_trial_id": None,
                "validity": "valid_complete" if next_id is None else "valid_incomplete",
                "failure_reason": None})
        return campaign

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

    def _invalidate(self, reason: str, *, failure_evidence: Mapping[str, Any] | None = None) -> None:
        self.state = self.store.write_state(self.protocol, {**self.state, "validity": "invalid_incomplete", "failure_reason": reason})
        failure = {"campaign_id": self.protocol.campaign_id, "reason": reason}
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
            self._invalidate("campaign_trial_incomplete_no_retry", failure_evidence={
                "trial_id": trial_id, "run_id": run.get("run_id"),
                "run_digest": run.get("run_digest"),
                "experiment_completion_posture": run.get("experiment_completion_posture"),
                "condition_statuses": run.get("condition_statuses"),
            })
            raise DevelopmentalModelReplacementError("campaign_trial_incomplete_no_retry")
        completed = list(self.state["completed_trials"])
        completed.append({"trial_id": trial_id, "run_id": run["run_id"], "run_digest": run["run_digest"]})
        index = len(completed); next_id = self.protocol.trial_ids[index] if index < len(self.protocol.trial_ids) else None
        self.state = self.store.write_state(self.protocol, {"completed_trials": completed, "next_trial_id": next_id,
            "in_progress_trial_id": None, "validity": "valid_complete" if next_id is None else "valid_incomplete",
            "failure_reason": None})
        return run

    def summarize(self) -> dict[str, Any]:
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
        digest = _digest(semantic); report = {**semantic, "report_id": "model-replacement-campaign-report-" + digest[7:31], "report_digest": digest}
        self.store.immutable(self.store.reports / f"{report['report_id']}.json", report)
        return report

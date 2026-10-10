"""Operator-directed production composition for post-adoption campaigns.

This module only reads, verifies, and composes existing custody.  In particular it
does not adopt software, replace a process, operate Git, or manufacture evidence.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

from sentientos.host_collectors import collect_basic_host_observations, validate_host_collector_result
from sentientos.maintenance_authority_continuity import GENERATION_SCHEMA, RECEIPT_SCHEMA as CONTINUITY_SCHEMA
from sentientos.maintenance_post_adoption_attribution_campaign import (
    CampaignProtocol, ControlObservation, MaintenancePostAdoptionAttributionCampaignOwner,
    campaign_epistemic_binding, campaign_improvement_signal_record, developmental_evidence_record,
    make_control_observation,
)
from sentientos.maintenance_post_adoption_evaluation import (
    Baseline, EvaluationProtocol, MaintenancePostAdoptionEvaluationOwner, SuccessorQualification,
)
from sentientos.maintenance_resident_runtime_adoption import EVENT_SCHEMA, PROVENANCE_SCHEMA, RECEIPT_SCHEMA as ADOPTION_SCHEMA

SCHEMA = "sentientos.maintenance_production_post_adoption_campaign_custody:v1"
READINESS_SCHEMA = "sentientos.maintenance_production_post_adoption_campaign_readiness:v1"
BUNDLE_SCHEMA = "sentientos.maintenance_production_post_adoption_campaign_bundle:v1"
QUALIFICATION_SCHEMA = "sentientos.maintenance_production_post_adoption_campaign_qualification:v1"
HOST_SCHEMA = "sentientos.host_collector_result:v1"
FALSE_EFFECTS = {"git": False, "repository_mutation": False, "software_adoption": False,
    "process_replacement": False, "rollback": False, "provider_network": False,
    "host_actuation": False, "grant": False, "authority_widening": False}
MAX_CAMPAIGN_ARTIFACT_BYTES = 1_048_576


class ProductionCampaignError(ValueError):
    pass


def _bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _digest(value: Any, omitted: str | None = None) -> str:
    body = {k: v for k, v in value.items() if k != omitted} if omitted else value
    return "sha256:" + hashlib.sha256(_bytes(body)).hexdigest()


def _open_directory(path: Path, *, create: bool) -> int:
    selected = Path(os.path.abspath(os.fspath(path)))
    if selected == Path(selected.anchor):
        raise ProductionCampaignError("production_campaign_path_invalid")
    if (os.name != "posix" or not hasattr(os, "O_NOFOLLOW") or os.open not in os.supports_dir_fd
            or (create and os.mkdir not in os.supports_dir_fd)):
        raise ProductionCampaignError("production_campaign_unsupported_platform")
    descriptor: int | None = None
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_NOFOLLOW
    try:
        descriptor = os.open(os.sep, flags)
        for component in selected.parts[1:]:
            if create:
                try:
                    os.mkdir(component, 0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            next_descriptor = os.open(component, flags, dir_fd=descriptor)
            if not stat.S_ISDIR(os.fstat(next_descriptor).st_mode):
                os.close(next_descriptor)
                raise ProductionCampaignError("production_campaign_path_invalid")
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except ProductionCampaignError:
        if descriptor is not None:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise ProductionCampaignError("production_campaign_path_invalid") from exc


def _read_bytes(path: Path) -> bytes:
    selected = Path(os.path.abspath(os.fspath(path)))
    if selected == Path(selected.anchor) or selected.name in {"", ".", ".."}:
        raise ProductionCampaignError("production_campaign_path_invalid")
    directory_fd = _open_directory(selected.parent, create=False)
    descriptor: int | None = None
    try:
        descriptor = os.open(selected.name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_NONBLOCK", 0), dir_fd=directory_fd)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_CAMPAIGN_ARTIFACT_BYTES:
            raise ProductionCampaignError("production_campaign_artifact_invalid")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 65_536))
            if not chunk:
                raise ProductionCampaignError("production_campaign_artifact_invalid")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    except ProductionCampaignError:
        raise
    except OSError as exc:
        raise ProductionCampaignError("production_campaign_artifact_unavailable") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(directory_fd)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(_read_bytes(path).decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ProductionCampaignError("production_campaign_artifact_invalid") from exc


def _write_once(path: Path, value: Mapping[str, Any], *, read_only: bool = False) -> None:
    if read_only:
        raise ProductionCampaignError("production_campaign_store_read_only")
    data = _bytes(value) + b"\n"
    if len(data) > MAX_CAMPAIGN_ARTIFACT_BYTES:
        raise ProductionCampaignError("production_campaign_artifact_oversized")
    path = Path(os.path.abspath(os.fspath(path)))
    if path == Path(path.anchor) or path.name in {"", ".", ".."}:
        raise ProductionCampaignError("production_campaign_path_invalid")
    if (os.link not in os.supports_dir_fd or os.unlink not in os.supports_dir_fd
            or os.link not in os.supports_follow_symlinks):
        raise ProductionCampaignError("production_campaign_unsupported_platform")
    directory_fd = _open_directory(path.parent, create=True)
    temporary_name = ".campaign-custody-" + secrets.token_hex(16) + ".tmp"
    temporary_created = False
    try:
        try:
            existing = _read_bytes(path)
        except ProductionCampaignError as exc:
            if str(exc) != "production_campaign_artifact_unavailable":
                raise
        else:
            if existing != data:
                raise ProductionCampaignError("immutable_production_campaign_custody_conflict")
            return
        descriptor = os.open(temporary_name, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
            0o600, dir_fd=directory_fd)
        temporary_created = True
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        try:
            os.link(temporary_name, path.name, src_dir_fd=directory_fd,
                dst_dir_fd=directory_fd, follow_symlinks=False)
        except FileExistsError:
            if _read_bytes(path) != data:
                raise ProductionCampaignError("immutable_production_campaign_custody_conflict")
        os.fsync(directory_fd)
    except ProductionCampaignError:
        raise
    except OSError as exc:
        raise ProductionCampaignError("production_campaign_publication_failed") from exc
    finally:
        if temporary_created:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd); os.fsync(directory_fd)
            except FileNotFoundError:
                pass
        os.close(directory_fd)


def _record_valid(value: Mapping[str, Any], schema: str, digest_key: str) -> bool:
    return (value.get("schema_version") == schema and isinstance(value.get(digest_key), str)
            and value.get(digest_key) == _digest(value, digest_key))


class MaintenanceProductionPostAdoptionCampaign:
    """Thin persistent coordinator over the existing evaluation/campaign owners."""

    def __init__(self, root: str | Path, *, read_only: bool = False) -> None:
        self.root = Path(os.path.abspath(os.fspath(root)))
        if self.root == Path(self.root.anchor):
            raise ProductionCampaignError("production_campaign_custody_unsafe")
        self.read_only = read_only
        if not read_only:
            descriptor = _open_directory(self.root, create=True)
            os.close(descriptor)
        self.evaluations = MaintenancePostAdoptionEvaluationOwner(self.root / "evaluations", read_only=read_only)
        self.campaigns = MaintenancePostAdoptionAttributionCampaignOwner(self.root / "campaigns", read_only=read_only)

    def prepare(self, protocol: CampaignProtocol, evaluations: Sequence[EvaluationProtocol],
                baselines: Sequence[Baseline]) -> Mapping[str, Any]:
        """Seal predecessor-created protocol and baseline custody before adoption."""
        if self.read_only:
            raise ProductionCampaignError("production_campaign_store_read_only")
        if protocol.evidence_class != "production":
            raise ProductionCampaignError("production_campaign_protocol_required")
        if tuple(x.protocol_id for x in evaluations) != protocol.evaluation_protocol_ids or \
                tuple(x.protocol_digest for x in evaluations) != protocol.evaluation_protocol_digests:
            raise ProductionCampaignError("campaign_evaluation_protocol_mismatch")
        if len(baselines) != len(evaluations):
            raise ProductionCampaignError("baseline_inventory_incomplete")
        self.campaigns.preregister(protocol)
        for evaluation, baseline in zip(evaluations, baselines):
            if (evaluation.landed_commit != protocol.successor_revision or evaluation.landed_tree != protocol.successor_tree
                    or evaluation.predecessor_generation != protocol.predecessor_generation
                    or evaluation.expected_successor_generation != protocol.successor_generation
                    or baseline.protocol_id != evaluation.protocol_id
                    or baseline.source_revision != protocol.predecessor_revision
                    or baseline.source_tree != protocol.predecessor_tree):
                raise ProductionCampaignError("predecessor_custody_lineage_mismatch")
            for observable_id in (x.observable_id for x in evaluation.measurements):
                record = baseline.source_records.get(observable_id, {})
                path = Path(str(record.get("source_path", "")))
                if not path.is_absolute():
                    raise ProductionCampaignError("baseline_source_not_production")
                try: source_value = _read_json(path)
                except ProductionCampaignError as exc: raise ProductionCampaignError("baseline_source_not_production") from exc
                if (record.get("source_digest") != _digest(source_value)
                        or not record.get("source_schema")):
                    raise ProductionCampaignError("baseline_source_not_production")
            self.evaluations.preregister(evaluation); self.evaluations.capture_baseline(evaluation, baseline)
        body: dict[str, Any] = {"schema_version": SCHEMA, "campaign_id": protocol.campaign_id,
            "campaign_digest": protocol.campaign_digest, "evaluation_protocol_ids": list(protocol.evaluation_protocol_ids),
            "evaluation_protocol_digests": list(protocol.evaluation_protocol_digests),
            "baseline_ids": [x.baseline_id for x in baselines], "baseline_digests": [x.baseline_digest for x in baselines],
            "expected_successor": {"generation": protocol.successor_generation, "commit": protocol.successor_revision,
                                   "tree": protocol.successor_tree, "adoption_identity": protocol.adoption_identity},
            "sealed_before_adoption": True, "effects": FALSE_EFFECTS}
        body["custody_digest"] = _digest(body)
        _write_once(self.root / "custody.json", body, read_only=self.read_only)
        return cast(Mapping[str, Any], body)

    def reconstruct(self, campaign_id: str) -> Mapping[str, Any]:
        try: body = _read_json(self.root / "custody.json")
        except ProductionCampaignError as exc: raise ProductionCampaignError("campaign_custody_unavailable") from exc
        if not isinstance(body, dict):
            raise ProductionCampaignError("campaign_custody_tampered")
        supplied = dict(body); actual = supplied.pop("custody_digest", None)
        if actual != _digest(supplied) or body.get("schema_version") != SCHEMA or body.get("campaign_id") != campaign_id:
            raise ProductionCampaignError("campaign_custody_tampered")
        protocol = self.campaigns.protocol(campaign_id)
        if protocol.campaign_digest != body["campaign_digest"]: raise ProductionCampaignError("campaign_custody_tampered")
        if (body.get("evaluation_protocol_ids") != list(protocol.evaluation_protocol_ids)
                or body.get("evaluation_protocol_digests") != list(protocol.evaluation_protocol_digests)
                or len(body.get("baseline_ids", [])) != len(protocol.trial_ids)
                or len(body.get("baseline_digests", [])) != len(protocol.trial_ids)):
            raise ProductionCampaignError("campaign_custody_tampered")
        for index, identity in enumerate(body["evaluation_protocol_ids"]):
            evaluation = self.evaluations.protocol(identity); baseline = self.evaluations.baseline(identity)
            if (evaluation.protocol_digest != body["evaluation_protocol_digests"][index]
                    or evaluation.predecessor_generation != protocol.predecessor_generation
                    or evaluation.expected_successor_generation != protocol.successor_generation
                    or evaluation.landed_commit != protocol.successor_revision
                    or evaluation.landed_tree != protocol.successor_tree
                    or baseline.baseline_id != body["baseline_ids"][index]
                    or baseline.baseline_digest != body["baseline_digests"][index]
                    or baseline.source_revision != protocol.predecessor_revision
                    or baseline.source_tree != protocol.predecessor_tree):
                raise ProductionCampaignError("campaign_custody_tampered")
        return cast(Mapping[str, Any], body)

    def _qualification(self, campaign_id: str) -> Mapping[str, Any]:
        try:
            body = _read_json(self.root / "qualification.json")
        except ProductionCampaignError as exc:
            raise ProductionCampaignError("campaign_qualification_unavailable") from exc
        if not isinstance(body, dict):
            raise ProductionCampaignError("campaign_qualification_corrupt")
        supplied = dict(body)
        actual = supplied.pop("qualification_digest", None)
        if (body.get("schema_version") != QUALIFICATION_SCHEMA
                or body.get("campaign_id") != campaign_id
                or actual != _digest(supplied)
                or not isinstance(body.get("evidence"), Mapping)
                or not isinstance(body.get("request_digest"), str)
                or not body.get("request_digest", "").startswith("sha256:")
                or not _record_valid(body.get("readiness", {}), READINESS_SCHEMA, "readiness_digest")):
            raise ProductionCampaignError("campaign_qualification_corrupt")
        return cast(Mapping[str, Any], body)

    def _verify_evaluation_lineage(self, campaign_id: str) -> Mapping[str, int]:
        """Reconcile trial claims with the exact independent evaluation custody."""
        protocol = self.campaigns.protocol(campaign_id)
        evaluation_counts = self.evaluations.verify()
        campaign_counts = self.campaigns.verify()
        selected_protocols = set(protocol.evaluation_protocol_ids)
        evaluation_rows = [row for row in self.evaluations._read("evaluations")
            if row.get("protocol_id") in selected_protocols]
        evaluation_by_id = {}
        for row in evaluation_rows:
            try:
                evaluation = self.evaluations.evaluation(str(row["evaluation_id"]), str(row["evaluation_digest"]))
                order = protocol.evaluation_protocol_ids.index(evaluation.protocol_id)
            except (KeyError, ValueError) as exc:
                raise ProductionCampaignError("campaign_evaluation_protocol_unselected") from exc
            if (evaluation.protocol_digest != protocol.evaluation_protocol_digests[order]
                    or evaluation.predecessor_generation != protocol.predecessor_generation
                    or evaluation.successor_generation != protocol.successor_generation
                    or evaluation.predecessor_revision != protocol.predecessor_revision
                    or evaluation.successor_revision != protocol.successor_revision
                    or evaluation.evaluation_id in evaluation_by_id):
                raise ProductionCampaignError("campaign_evaluation_lineage_substitution")
            evaluation_by_id[evaluation.evaluation_id] = evaluation
        trial_rows = [row for row in self.campaigns._read("trials")
            if row.get("campaign_id") == campaign_id]
        linked_evaluations: set[str] = set()
        for trial in trial_rows:
            order = protocol.trial_ids.index(trial["trial_id"])
            expected_protocol_id = protocol.evaluation_protocol_ids[order]
            expected_protocol_digest = protocol.evaluation_protocol_digests[order]
            if (trial["evaluation_protocol_id"] != expected_protocol_id
                    or trial["evaluation_protocol_digest"] != expected_protocol_digest):
                raise ProductionCampaignError("campaign_evaluation_protocol_lineage_invalid")
            if trial.get("evaluation_id") is None:
                if trial.get("evaluation_digest") is not None:
                    raise ProductionCampaignError("campaign_evaluation_lineage_incomplete")
                continue
            evaluation = evaluation_by_id.get(str(trial["evaluation_id"]))
            if (evaluation is None or evaluation.evaluation_digest != trial.get("evaluation_digest")
                    or evaluation.protocol_id != expected_protocol_id
                    or evaluation.protocol_digest != expected_protocol_digest
                    or evaluation.predecessor_generation != protocol.predecessor_generation
                    or evaluation.successor_generation != protocol.successor_generation
                    or evaluation.predecessor_revision != protocol.predecessor_revision
                    or evaluation.successor_revision != protocol.successor_revision
                    or trial.get("evaluation_result") != evaluation.result
                    or tuple(trial.get("evaluation_lineage", ())) != evaluation.reconstruction_lineage):
                raise ProductionCampaignError("campaign_evaluation_lineage_substitution")
            if evaluation.evaluation_id in linked_evaluations:
                raise ProductionCampaignError("campaign_evaluation_reused")
            linked_evaluations.add(evaluation.evaluation_id)
        # Unlinked durable evaluations are allowed only as a recoverable crash point.
        return {"evaluation_records":evaluation_counts["evaluations"],
            "campaign_trials":len(trial_rows), "linked_evaluations":len(linked_evaluations),
            "campaign_records":campaign_counts["results"],
            "evaluation_inventory":evaluation_counts, "campaign_inventory":campaign_counts}

    def readiness(self, campaign_id: str, evidence: Mapping[str, Mapping[str, Any]], *,
                  artifact_path: str | Path | None = None) -> Mapping[str, Any]:
        """Derive production posture from exact real records, never a caller label."""
        custody = self.reconstruct(campaign_id); protocol = self.campaigns.protocol(campaign_id)
        self._verify_evaluation_lineage(campaign_id)
        generation = evidence.get("generation", {}); continuity = evidence.get("continuity", {})
        adoption = evidence.get("adoption", {}); provenance = evidence.get("launch_provenance", {})
        adoption_event = evidence.get("adoption_completion_event", {})
        journal_path = Path(str(evidence.get("resident_journal", {}).get("path", "")))
        journal_bound = False
        try:
            journal_bytes = _read_bytes(journal_path) if journal_path.is_absolute() else b""
            try:
                journal_bound = any(json.loads(line) == adoption_event for line in journal_bytes.decode("utf-8").splitlines())
            except (UnicodeError, json.JSONDecodeError):
                journal_bound = False
        except ProductionCampaignError:
            journal_bound = False
        target_sources = evidence.get("target_sources", {}).get("records", [])
        target_sources_valid = isinstance(target_sources, list) and bool(target_sources)
        for source in target_sources if isinstance(target_sources, list) else []:
            path = Path(str(source.get("path", "")))
            if not path.is_absolute():
                target_sources_valid = False
                continue
            try:
                value = _read_json(path)
                target_sources_valid = target_sources_valid and source.get("digest") == _digest(value) \
                    and bool(source.get("schema")) and bool(source.get("observable_id"))
            except ProductionCampaignError: target_sources_valid = False
        host_controls_valid = True
        host_results = {x.collector_id: x for x in collect_basic_host_observations()}
        for definition in protocol.controls:
            collector_id, _, value_key = definition.observable_id.partition(".")
            result = host_results.get(collector_id)
            host_controls_valid = host_controls_valid and result is not None and validate_host_collector_result(result).ok \
                and result.status in {"available", "partial"} and result.to_dict()["values"].get(value_key) is not None \
                and "host_observation" in definition.admissible_source_classes
        evaluation_protocol_ids = set(protocol.evaluation_protocol_ids)
        observations = [x for x in self.evaluations._read("observations")
            if x.get("protocol_id") in evaluation_protocol_ids]
        evaluations = [x for x in self.evaluations._read("evaluations")
            if x.get("protocol_id") in evaluation_protocol_ids]
        evaluation_by_protocol = {x.get("protocol_id") for x in evaluations}
        unresolved_observation = any(x.get("protocol_id") not in evaluation_by_protocol for x in observations)
        adoption_event_time = adoption_event.get("event_time") if isinstance(adoption_event, Mapping) else None
        checks = {
            "successor_generation_sealed": _record_valid(generation, GENERATION_SCHEMA, "generation_digest"),
            "successor_generation_exact": generation.get("ordinal") == protocol.successor_generation and generation.get("base_sha") == protocol.successor_revision,
            "successor_tree_exact": evidence.get("repository", {}).get("tree_sha") == protocol.successor_tree,
            "continuity_custody_valid": _record_valid(continuity, CONTINUITY_SCHEMA, "receipt_digest"),
            "resident_adoption_completed": _record_valid(adoption, ADOPTION_SCHEMA, "receipt_digest") and adoption.get("status") == "resident_ready",
            "adoption_completion_event_valid": _record_valid(adoption_event, EVENT_SCHEMA, "event_digest") and adoption_event.get("phase") == "resident_adoption_completed" and isinstance(adoption_event_time, str) and bool(adoption_event_time) and journal_bound,
            "launch_provenance_valid": _record_valid(provenance, PROVENANCE_SCHEMA, "provenance_digest"),
            "resident_readiness_exact": adoption.get("successor_generation_digest") == generation.get("generation_digest"),
            "continuity_exact": adoption.get("continuity_receipt_digest") == continuity.get("receipt_digest"),
            "launch_provenance_exact": adoption.get("successor_launch_provenance_digest") == provenance.get("provenance_digest"),
            "baseline_inventory_complete": len(custody["baseline_ids"]) == len(protocol.trial_ids),
            "target_collector_available": target_sources_valid,
            "independent_control_available": host_controls_valid,
            "no_unresolved_observation_attempt": not unresolved_observation,
        }
        blockers = tuple(key for key, passed in checks.items() if not passed)
        terminal = False
        try: self.campaigns.result(campaign_id); terminal = True
        except ValueError: pass
        trials = [x for x in self.campaigns._read("trials") if x["campaign_id"] == campaign_id]
        status = "production_campaign_complete" if terminal else ("production_campaign_interrupted" if unresolved_observation else
                 "production_campaign_in_progress" if trials else
                 "production_campaign_ready" if not blockers else "production_campaign_not_ready")
        body: dict[str, Any] = {"schema_version": READINESS_SCHEMA, "campaign_id": campaign_id,
            "campaign_digest": protocol.campaign_digest, "status": status, "checks": checks,
            "missing_prerequisites": list(blockers), "production_posture_derived": not blockers,
            "caller_declared_evidence_class_trusted": False, "effects": FALSE_EFFECTS}
        body["readiness_digest"] = _digest(body)
        if artifact_path is not None: _write_once(Path(artifact_path), body, read_only=self.read_only)
        return body

    def collect_host_control(self, campaign_id: str, trial_id: str, observable_id: str, *,
                             before_value: Any, matching_result: str, window_identity: str,
                             observed_at: str | None = None) -> ControlObservation:
        """Collect one control with the canonical read-only host collector."""
        if self.read_only:
            raise ProductionCampaignError("production_campaign_store_read_only")
        protocol = self.campaigns.protocol(campaign_id)
        definition = next((x for x in protocol.controls if x.observable_id == observable_id), None)
        if definition is None or "host_observation" not in definition.admissible_source_classes:
            raise ProductionCampaignError("control_definition_not_host_collectable")
        now = datetime.now(timezone.utc)
        stamp = now.isoformat()
        if observed_at is not None:
            try:
                requested = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
            except (TypeError, ValueError) as exc:
                raise ProductionCampaignError("host_control_observation_time_invalid") from exc
            if (requested.tzinfo is None
                    or abs((now - requested.astimezone(timezone.utc)).total_seconds()) > 30):
                raise ProductionCampaignError("host_control_observation_time_not_current")
        results = {x.collector_id: x for x in collect_basic_host_observations(observed_at=stamp)}
        collector_id, _, value_key = observable_id.partition(".")
        result = results.get(collector_id)
        if result is None or not validate_host_collector_result(result).ok or result.status not in {"available", "partial"}:
            raise ProductionCampaignError("production_host_control_unavailable")
        payload = result.to_dict(); after = payload["values"].get(value_key)
        if after is None: raise ProductionCampaignError("production_host_control_value_unavailable")
        source_digest = _digest(payload)
        return make_control_observation(protocol, trial_id=trial_id, observable_id=observable_id,
            measurement_law=definition.measurement_law, matching_rule=definition.matching_rule,
            match_result=matching_result, before_value=before_value, after_value=after,
            source_identity=f"host-collector:{collector_id}:{stamp}", source_digest=source_digest,
            source_schema=HOST_SCHEMA, source_class="host_observation", observed_at=stamp,
            collector_identity=f"sentientos.host_collectors:{collector_id}", dependency_ids=(),
            window_identity=window_identity, world_state_binding=None,
            host_observation_binding=source_digest, evidence_class="production")

    def observe_next(self, campaign_id: str, evidence: Mapping[str, Mapping[str, Any]], *,
                     target_observations: Mapping[str, Any], target_source_records: Mapping[str, Mapping[str, str]],
                     target_measurement_laws: Mapping[str, str], control_before_values: Mapping[str, Any],
                     control_match_results: Mapping[str, str], window_identity: str, observed_at: str,
                     evaluated_at: str, completed_at: str) -> Mapping[str, Any]:
        """Run the next exact trial once after independently deriving readiness."""
        if self.read_only:
            raise ProductionCampaignError("production_campaign_store_read_only")
        ready = self.readiness(campaign_id, evidence)
        protocol = self.campaigns.protocol(campaign_id)
        prior = [x for x in self.campaigns._read("trials") if x["campaign_id"] == campaign_id]
        if len(prior) >= len(protocol.trial_ids): raise ProductionCampaignError("campaign_already_terminal")
        index = len(prior); trial_id = protocol.trial_ids[index]
        evaluation_protocol = self.evaluations.protocol(protocol.evaluation_protocol_ids[index])
        baseline = self.evaluations.baseline(evaluation_protocol.protocol_id)
        recovered_observation = self.evaluations.observation_if_present(evaluation_protocol.protocol_id)
        recoverable_interruption = (ready["status"] == "production_campaign_interrupted"
            and recovered_observation is not None
            and ready["missing_prerequisites"] == ["no_unresolved_observation_attempt"])
        if (ready["status"] not in {"production_campaign_ready", "production_campaign_in_progress"}
                and not recoverable_interruption) or (ready["missing_prerequisites"] and not recoverable_interruption):
            raise ProductionCampaignError("production_campaign_not_ready")
        request_digest = _digest({"target_observations":target_observations,
            "target_source_records":target_source_records, "target_measurement_laws":target_measurement_laws,
            "control_before_values":control_before_values, "control_match_results":control_match_results,
            "window_identity":window_identity, "observed_at":observed_at,
            "evaluated_at":evaluated_at, "completed_at":completed_at})
        qualification_path = self.root / "qualification.json"
        try:
            qualification = self._qualification(campaign_id)
        except ProductionCampaignError as exc:
            if str(exc) != "campaign_qualification_unavailable":
                raise
            qualification_body: dict[str, Any] = {"schema_version": QUALIFICATION_SCHEMA,
                "campaign_id": campaign_id, "evidence": evidence, "readiness": ready,
                "request_digest":request_digest}
            qualification_body["qualification_digest"] = _digest(qualification_body)
            _write_once(qualification_path, qualification_body, read_only=self.read_only)
            qualification = qualification_body
        if canonical_bytes(qualification.get("evidence")) != canonical_bytes(evidence):
            raise ProductionCampaignError("campaign_qualification_conflict")
        if qualification.get("request_digest") != request_digest:
            raise ProductionCampaignError("campaign_qualification_conflict")
        manifests = {x["observable_id"]: x for x in evidence["target_sources"]["records"]}
        for observable_id, record in target_source_records.items():
            manifest = manifests.get(observable_id)
            if (manifest is None or not Path(str(manifest.get("path", ""))).is_absolute()
                    or record.get("source_digest") != manifest["digest"] or record.get("source_schema") != manifest["schema"]):
                raise ProductionCampaignError("target_source_record_mismatch")
        generation, continuity, adoption, provenance = (evidence[x] for x in ("generation", "continuity", "adoption", "launch_provenance"))
        journal_path = Path(str(evidence["resident_journal"]["path"]))
        adoption_time = str(evidence["adoption_completion_event"]["event_time"])
        qualification = SuccessorQualification(protocol.successor_generation, protocol.successor_revision,
            protocol.successor_tree, str(generation["generation_digest"]), str(continuity["receipt_digest"]),
            str(adoption["receipt_digest"]), str(provenance["provenance_digest"]),
            str(adoption["receipt_digest"]), adoption_time, "resident_adoption_completed")
        observation = recovered_observation or self.evaluations.observe(evaluation_protocol, baseline, qualification,
            observations=target_observations, source_records=target_source_records,
            measurement_laws=target_measurement_laws, observed_at=observed_at,
            collector_id="maintenance-production-post-adoption-campaign")
        evaluation = self.evaluations.evaluation_if_present(evaluation_protocol.protocol_id)
        if evaluation is None:
            evaluation = self.evaluations.evaluate(evaluation_protocol, baseline, observation, evaluated_at=evaluated_at)
        controls_by_observable = {item.observable_id:item for item in
            self.campaigns.controls_for_trial(campaign_id, trial_id)}
        controls = []
        for definition in protocol.controls:
            stored = controls_by_observable.get(definition.observable_id)
            if stored is not None:
                if stored.window_identity != window_identity:
                    raise ProductionCampaignError("campaign_control_window_conflict")
                controls.append(stored)
                continue
            control = self.collect_host_control(campaign_id, trial_id, definition.observable_id,
                before_value=control_before_values[definition.observable_id],
                matching_result=control_match_results[definition.observable_id], window_identity=window_identity)
            controls.append(self.campaigns.record_control(protocol, control))
        trial = self.campaigns.record_trial(protocol, trial_id=trial_id, evaluation=evaluation,
            controls=controls, terminal_status="completed", completed_at=completed_at)
        return {"trial": asdict(trial), "observation": asdict(observation), "evaluation": asdict(evaluation),
                "controls": [asdict(x) for x in controls], "effects": FALSE_EFFECTS}

    def interrupt_next(self, campaign_id: str, *, completed_at: str) -> Mapping[str, Any]:
        if self.read_only:
            raise ProductionCampaignError("production_campaign_store_read_only")
        protocol = self.campaigns.protocol(campaign_id)
        prior = [x for x in self.campaigns._read("trials") if x["campaign_id"] == campaign_id]
        if len(prior) >= len(protocol.trial_ids): raise ProductionCampaignError("campaign_already_terminal")
        order = len(prior)
        trial_id = protocol.trial_ids[order]
        evaluation_protocol = self.evaluations.protocol(protocol.evaluation_protocol_ids[order])
        evaluation = self.evaluations.evaluation_if_present(evaluation_protocol.protocol_id)
        controls = self.campaigns.controls_for_trial(campaign_id, trial_id)
        trial = self.campaigns.record_trial(protocol, trial_id=trial_id, evaluation=evaluation,
            controls=controls, terminal_status="interrupted", completed_at=completed_at)
        return asdict(trial)

    def finalize(self, campaign_id: str, *, completed_at: str) -> Mapping[str, Any]:
        if self.read_only:
            raise ProductionCampaignError("production_campaign_store_read_only")
        self.reconstruct(campaign_id)
        self._verify_evaluation_lineage(campaign_id)
        return asdict(self.campaigns.finalize(self.campaigns.protocol(campaign_id), completed_at=completed_at))

    def report(self, campaign_id: str, *, proposition_id: str | None = None) -> Mapping[str, Any]:
        custody = self.reconstruct(campaign_id)
        self._verify_evaluation_lineage(campaign_id)
        try:
            qualification = self._qualification(campaign_id)
            readiness = self.readiness(campaign_id, qualification["evidence"])
        except (ProductionCampaignError, KeyError):
            readiness = self.readiness(campaign_id, {})
        try: result = self.campaigns.result(campaign_id)
        except ValueError: result = None
        body: dict[str, Any] = {"schema_version": BUNDLE_SCHEMA, "custody": custody,
            "readiness": readiness, "campaign_result": asdict(result) if result else None,
            "epistemic_binding_candidate": asdict(campaign_epistemic_binding(proposition_id=proposition_id, result=result, owner=self.campaigns)) if result and proposition_id else None,
            "developmental_evidence": developmental_evidence_record(result, owner=self.campaigns) if result else None,
            "improvement_signal": campaign_improvement_signal_record(result) if result else None,
            "production_evidence_collected": bool(result and result.production_ready and readiness["production_posture_derived"]),
            "effects": FALSE_EFFECTS}
        body["bundle_digest"] = _digest(body); return body

    def verify(self, campaign_id: str) -> Mapping[str, Any]:
        custody = self.reconstruct(campaign_id)
        linkage = self._verify_evaluation_lineage(campaign_id)
        return {"status": "production_campaign_custody_verified", "custody_digest": custody["custody_digest"],
                "evaluation_records":linkage["evaluation_inventory"],
                "campaign_records":linkage["campaign_inventory"],
                "lineage":{key:value for key,value in linkage.items()
                    if key not in {"evaluation_inventory", "campaign_inventory"}},
                "effects": FALSE_EFFECTS}


__all__ = ["MaintenanceProductionPostAdoptionCampaign", "ProductionCampaignError", "FALSE_EFFECTS"]

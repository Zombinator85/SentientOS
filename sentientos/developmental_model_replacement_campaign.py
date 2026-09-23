"""Preregistered descriptive replication of one frozen model-replacement experiment."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Mapping, Sequence, cast

from .developmental_model_replacement_experiment import (
    CONDITION_ORDER, NON_CLAIMS, DevelopmentalModelReplacementError,
    DevelopmentalModelReplacementExperiment, _digest,
)
from .local_model_authority import atomic_write_json

PROTOCOL_SCHEMA = "sentientos.developmental_model_replacement_campaign_protocol:v1"
STATE_SCHEMA = "sentientos.developmental_model_replacement_campaign_state:v1"
REPORT_SCHEMA = "sentientos.developmental_model_replacement_campaign_report:v1"
MIN_TRIALS = 2
MAX_TRIALS = 32
CAMPAIGN_NON_CLAIMS = NON_CLAIMS + (
    "statistical_significance", "hypothesis_probability", "longitudinal_development",
)
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
        self.root = Path(root) / "developmental_experiments" / "model_replacement_campaigns"
        self.protocols, self.states = self.root / "protocols", self.root / "state"
        self.failures, self.reports = self.root / "failures", self.root / "reports"

    @staticmethod
    def immutable(path: Path, value: Mapping[str, Any]) -> None:
        if path.exists():
            try: prior = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc: raise DevelopmentalModelReplacementError("campaign_artifact_tampered") from exc
            if prior != dict(value): raise DevelopmentalModelReplacementError("campaign_artifact_identity_collision")
        else: atomic_write_json(path, value)

    def protocol_path(self, campaign_id: str) -> Path: return self.protocols / f"{campaign_id}.json"
    def state_path(self, campaign_id: str) -> Path: return self.states / f"{campaign_id}.json"

    def persist_protocol(self, protocol: CampaignProtocol) -> None:
        protocol.verify(); self.immutable(self.protocol_path(protocol.campaign_id), asdict(protocol))

    def verify_protocol(self, protocol: CampaignProtocol) -> None:
        try: actual = json.loads(self.protocol_path(protocol.campaign_id).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise DevelopmentalModelReplacementError("campaign_protocol_custody_changed") from exc
        if actual != json.loads(json.dumps(asdict(protocol))): raise DevelopmentalModelReplacementError("campaign_protocol_custody_changed")

    def write_state(self, protocol: CampaignProtocol, body: Mapping[str, Any]) -> dict[str, Any]:
        semantic = {key: value for key, value in body.items() if key not in {"state_digest", "campaign_id", "campaign_digest", "schema_version"}}
        semantic = {**semantic, "campaign_id": protocol.campaign_id, "campaign_digest": protocol.campaign_digest,
                    "schema_version": STATE_SCHEMA}
        value = {**semantic, "state_digest": _digest(semantic)}
        atomic_write_json(self.state_path(protocol.campaign_id), value)
        return value

    def load_state(self, protocol: CampaignProtocol) -> dict[str, Any]:
        try: value = json.loads(self.state_path(protocol.campaign_id).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise DevelopmentalModelReplacementError("campaign_state_unavailable") from exc
        semantic = {k: v for k, v in value.items() if k != "state_digest"}
        if value.get("state_digest") != _digest(semantic) or value.get("campaign_digest") != protocol.campaign_digest:
            raise DevelopmentalModelReplacementError("campaign_state_tampered")
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
        try: raw = json.loads(store.protocol_path(campaign_id).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise DevelopmentalModelReplacementError("campaign_protocol_custody_changed") from exc
        try:
            raw["trial_ids"] = tuple(raw["trial_ids"]); raw["condition_order"] = tuple(raw["condition_order"])
            raw["aggregation_rules"] = tuple(raw["aggregation_rules"]); raw["non_claims"] = tuple(raw["non_claims"])
            protocol = CampaignProtocol(**raw); protocol.verify(); store.verify_protocol(protocol)
        except (KeyError, TypeError, DevelopmentalModelReplacementError) as exc:
            raise DevelopmentalModelReplacementError("campaign_protocol_custody_changed") from exc
        campaign = cls(experiment, protocol, store, store.load_state(protocol))
        campaign._verify_experiment()
        if campaign.state.get("in_progress_trial_id"):
            campaign._invalidate("campaign_interrupted_during_trial")
            raise DevelopmentalModelReplacementError("campaign_interrupted_during_trial")
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

    def _invalidate(self, reason: str) -> None:
        self.state = self.store.write_state(self.protocol, {**self.state, "validity": "invalid_incomplete", "failure_reason": reason})
        self.store.immutable(self.store.failures / f"{self.protocol.campaign_id}-{reason}.json",
                             {"campaign_id": self.protocol.campaign_id, "reason": reason})

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

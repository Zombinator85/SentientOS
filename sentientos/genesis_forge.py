"""GenesisForge — Autonomous capability expansion pipeline.

This module implements the GenesisForge flow described by the cathedral
charter.  When the existing SentientOS daemons are unable to honour a vow or
handle a new telemetry stream, GenesisForge can draft the scaffolding for a new
daemon, probe it for covenant violations, execute sandbox trials, and finally
bind the daemon into the covenant lineage if the review board approves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
import random
import re
import uuid
from pathlib import Path
from typing import Callable, Mapping, MutableMapping, Sequence

from codex.integrity_daemon import IntegrityDaemon
from codex.proposal_router import CandidateResult, choose_candidate, score_evaluation, top_violation_codes
from sentientos.codex_healer import Anomaly, RecoveryLedger, RepairAction
from sentientos.codex_startup_guard import enforce_codex_startup


# ---------------------------------------------------------------------------
# Shared dataclasses


@dataclass(slots=True, frozen=True)
class TelemetryStream:
    """Description of an incoming telemetry stream."""

    name: str
    capability: str
    description: str
    handled_by: frozenset[str] = field(default_factory=frozenset)
    sample_payload: Mapping[str, object] = field(default_factory=dict)


@dataclass(slots=True, frozen=True)
class CovenantVow:
    """Represents a covenant requirement that must be honoured."""

    capability: str
    description: str


@dataclass(slots=True, frozen=True)
class DaemonManifest:
    """Known daemon with its declared capabilities."""

    name: str
    capabilities: frozenset[str]
    telemetry_streams: frozenset[str] = field(default_factory=frozenset)


@dataclass(slots=True)
class GenesisNeed:
    """A capability gap identified by :class:`NeedSeer`."""

    capability: str
    description: str
    source: str
    telemetry: TelemetryStream | None = None
    vow: CovenantVow | None = None


@dataclass(slots=True)
class TestCase:
    """Single sandbox expectation executed during :class:`TrialRun`."""

    name: str
    input_payload: Mapping[str, object]
    validator: Callable[[Mapping[str, object], Mapping[str, object]], bool]
    failure_message: str


@dataclass(slots=True)
class DaemonBlueprint:
    """Scaffolding for the daemon produced by :class:`ForgeEngine`."""

    name: str
    objective: str
    directives: list[str]
    testing_requirements: list[str]
    handler: Callable[[Mapping[str, object]], Mapping[str, object]]
    test_cases: list[TestCase]


@dataclass(slots=True)
class ForgeProposal:
    """Proposal submitted to the IntegrityDaemon."""

    proposal_id: str
    spec_id: str
    summary: str
    need: GenesisNeed
    blueprint: DaemonBlueprint
    original_spec: Mapping[str, object]
    proposed_spec: Mapping[str, object]
    deltas: Mapping[str, object]

    def to_dict(self) -> Mapping[str, object]:
        return {
            "proposal_id": self.proposal_id,
            "spec_id": self.spec_id,
            "summary": self.summary,
            "need": {
                "capability": self.need.capability,
                "description": self.need.description,
                "source": self.need.source,
            },
            "original_spec": dict(self.original_spec),
            "proposed_spec": dict(self.proposed_spec),
            "deltas": dict(self.deltas),
        }


@dataclass(slots=True)
class TrialReport:
    """Result of sandbox simulation executed by :class:`TrialRun`."""

    passed: bool
    results: list[dict[str, object]]
    failures: list[str]


@dataclass(slots=True)
class GenesisOutcome:
    """Narrates the result for a single :class:`GenesisNeed`."""

    need: GenesisNeed
    status: str
    details: Mapping[str, object]


class GenesisForgeError(RuntimeError):
    """Raised when GenesisForge cannot complete a stage."""


# ---------------------------------------------------------------------------
# NeedSeer


class NeedSeer:
    """Scans telemetry, amendments, and covenant gaps for missing coverage."""

    def __init__(self, *, daemons: Sequence[DaemonManifest] | None = None) -> None:
        self._daemons: dict[str, DaemonManifest] = {}
        if daemons:
            for manifest in daemons:
                self._daemons[manifest.name] = manifest

    def register_daemon(self, manifest: DaemonManifest) -> None:
        self._daemons[manifest.name] = manifest

    def scan(
        self,
        telemetry_streams: Sequence[TelemetryStream],
        vows: Sequence[CovenantVow],
    ) -> list[GenesisNeed]:
        """Return unmet covenant needs based on telemetry + vows."""

        existing_capabilities = {
            capability
            for manifest in self._daemons.values()
            for capability in manifest.capabilities
        }
        handled_streams = {
            stream
            for manifest in self._daemons.values()
            for stream in manifest.telemetry_streams
        }

        needs: list[GenesisNeed] = []
        seen_capabilities: set[str] = set()

        for vow in vows:
            if vow.capability not in existing_capabilities:
                needs.append(
                    GenesisNeed(
                        capability=vow.capability,
                        description=vow.description,
                        source="vow",
                        vow=vow,
                    )
                )
                seen_capabilities.add(vow.capability)

        for stream in telemetry_streams:
            already_handled = stream.name in handled_streams or any(
                daemon_name in stream.handled_by for daemon_name in self._daemons
            )
            capability_claimed = stream.capability in existing_capabilities
            if already_handled and capability_claimed:
                continue
            if stream.capability in seen_capabilities:
                # Already covered by a missing vow entry.
                continue
            needs.append(
                GenesisNeed(
                    capability=stream.capability,
                    description=stream.description,
                    source="telemetry",
                    telemetry=stream,
                )
            )
            seen_capabilities.add(stream.capability)

        return needs


# ---------------------------------------------------------------------------
# ForgeEngine


class ForgeEngine:
    """Drafts scaffolding for a new daemon aligned with covenant law."""

    def __init__(self, *, existing_daemons: Sequence[DaemonManifest] | None = None) -> None:
        self._existing_names = {manifest.name for manifest in existing_daemons or ()}

    def _canonical_name(self, capability: str) -> str:
        words = re.findall(r"[A-Za-z0-9]+", capability)
        if not words:
            words = ["Genesis"]
        name = "".join(word.title() for word in words)
        candidate = f"{name}GenesisDaemon"
        counter = 1
        while candidate in self._existing_names:
            counter += 1
            candidate = f"{name}GenesisDaemon{counter}"
        self._existing_names.add(candidate)
        return candidate

    def _build_handler(self, need: GenesisNeed) -> Callable[[Mapping[str, object]], Mapping[str, object]]:
        def handler(payload: Mapping[str, object]) -> Mapping[str, object]:
            now = datetime.now(timezone.utc).isoformat()
            envelope: dict[str, object] = {
                "status": "ok",
                "capability": need.capability,
                "provenance": "GenesisForge",
                "received_at": now,
                "payload": dict(payload),
            }
            if need.telemetry is not None:
                envelope["telemetry_stream"] = need.telemetry.name
            if need.vow is not None:
                envelope["vow"] = need.vow.description
            return envelope

        return handler

    def _build_test_cases(self, need: GenesisNeed) -> list[TestCase]:
        sample_payload: Mapping[str, object]
        if need.telemetry is not None and need.telemetry.sample_payload:
            sample_payload = need.telemetry.sample_payload
        elif need.telemetry is not None:
            sample_payload = {"stream": need.telemetry.name, "signal": need.capability}
        else:
            sample_payload = {"signal": need.capability}

        def validator(_: Mapping[str, object], output: Mapping[str, object]) -> bool:
            if output.get("status") != "ok":
                return False
            if output.get("capability") != need.capability:
                return False
            if output.get("provenance") != "GenesisForge":
                return False
            return True

        return [
            TestCase(
                name="capability_ack",
                input_payload=sample_payload,
                validator=validator,
                failure_message="Daemon did not acknowledge capability or status",
            )
        ]

    def draft(self, need: GenesisNeed) -> ForgeProposal:
        name = self._canonical_name(need.capability)
        handler = self._build_handler(need)
        test_cases = self._build_test_cases(need)
        objective = f"Honor {need.capability} inputs discovered via {need.source}."
        directives = [
            "inherit_vows",
            "preserve_lineage",
            f"ingest_{need.capability}_telemetry",
        ]
        testing_requirements = [
            "acknowledge_capability",
            "emit_success_status",
            "record_provenance_GenesisForge",
        ]

        proposed_spec: MutableMapping[str, object] = {
            "name": name,
            "objective": objective,
            "directives": directives,
            "testing_requirements": testing_requirements,
            "lineage": {
                "provenance": "GenesisForge",
                "born_from": need.source,
                "capability": need.capability,
            },
            "ledger_required": True,
        }
        if need.telemetry is not None:
            proposed_spec["telemetry_stream"] = need.telemetry.name

        blueprint = DaemonBlueprint(
            name=name,
            objective=objective,
            directives=list(directives),
            testing_requirements=list(testing_requirements),
            handler=handler,
            test_cases=test_cases,
        )

        proposal = ForgeProposal(
            proposal_id=f"GF-{uuid.uuid4().hex}",
            spec_id=name,
            summary=f"GenesisForge scaffolding for {name}",
            need=need,
            blueprint=blueprint,
            original_spec={},
            proposed_spec=dict(proposed_spec),
            deltas={"added": [name], "capability": need.capability},
        )
        return proposal

    def draft_variants(self, need: GenesisNeed, *, k: int, seed: str) -> list[ForgeProposal]:
        """Draft deterministic, minimally perturbed variants."""

        base = self.draft(need)
        count = max(int(k), 1)
        rng_seed = int.from_bytes(hashlib.sha256(seed.encode("utf-8")).digest()[:8], "big")
        rng = random.Random(rng_seed)
        allow_directives = [
            "maintain_audit_visibility",
            "preserve_operator_accountability",
            "witness_integrity_surface",
        ]

        variants: list[ForgeProposal] = []
        seen_specs: set[str] = set()
        for index in range(count * 4):
            directives = list(base.blueprint.directives)
            testing = list(base.blueprint.testing_requirements)
            shift = index % max(len(directives), 1)
            directives = directives[shift:] + directives[:shift]
            tshift = (index // 2) % max(len(testing), 1)
            testing = testing[tshift:] + testing[:tshift]
            if index % 3 == 1:
                extra = allow_directives[rng.randrange(len(allow_directives))]
                if extra not in directives:
                    directives = directives + [extra]

            proposed_spec = dict(base.proposed_spec)
            proposed_spec["directives"] = directives
            proposed_spec["testing_requirements"] = testing
            lineage = dict(proposed_spec.get("lineage") or {})
            lineage["router_variant"] = f"{index + 1:02d}"
            proposed_spec["lineage"] = lineage
            proposed_spec["ledger_required"] = bool(base.proposed_spec.get("ledger_required", True))

            signature = json.dumps(proposed_spec, sort_keys=True)
            if signature in seen_specs:
                continue
            seen_specs.add(signature)

            blueprint = DaemonBlueprint(
                name=base.blueprint.name,
                objective=base.blueprint.objective,
                directives=list(directives),
                testing_requirements=list(testing),
                handler=base.blueprint.handler,
                test_cases=list(base.blueprint.test_cases),
            )
            variant_hash = hashlib.sha256(f"{seed}:{index}".encode("utf-8")).hexdigest()[:10]
            variants.append(
                ForgeProposal(
                    proposal_id=f"GF-{variant_hash}-V{len(variants)+1}",
                    spec_id=base.spec_id,
                    summary=f"{base.summary} [variant {len(variants)+1}]",
                    need=base.need,
                    blueprint=blueprint,
                    original_spec=dict(base.original_spec),
                    proposed_spec=proposed_spec,
                    deltas=dict(base.deltas),
                )
            )
            if len(variants) >= count:
                break

        if len(variants) < count:
            raise GenesisForgeError(f"Unable to produce {count} distinct variants")
        return variants


# ---------------------------------------------------------------------------
# TrialRun


class TrialRun:
    """Sandbox executor that validates blueprint behaviour."""

    def execute(self, blueprint: DaemonBlueprint) -> TrialReport:
        results: list[dict[str, object]] = []
        failures: list[str] = []
        for case in blueprint.test_cases:
            try:
                output = blueprint.handler(case.input_payload)
            except Exception as exc:  # pragma: no cover - defensive
                failures.append(f"{case.name}: handler raised {exc!r}")
                continue
            passed = case.validator(case.input_payload, output)
            results.append({
                "case": case.name,
                "input": dict(case.input_payload),
                "output": dict(output),
                "passed": passed,
            })
            if not passed:
                failures.append(f"{case.name}: {case.failure_message}")
        return TrialReport(passed=not failures, results=results, failures=failures)


# ---------------------------------------------------------------------------
# SpecBinder


class SpecBinder:
    """Integrates the daemon into covenant lineage mounts."""

    def __init__(self, *, lineage_root: Path, covenant_root: Path) -> None:
        self._lineage_root = Path(lineage_root)
        self._covenant_root = Path(covenant_root)
        self._lineage_root.mkdir(parents=True, exist_ok=True)
        self._covenant_root.mkdir(parents=True, exist_ok=True)
        self._daemon_dir = self._covenant_root / "daemons"
        self._daemon_dir.mkdir(parents=True, exist_ok=True)
        self._lineage_log = self._lineage_root / "lineage.jsonl"

    def integrate(self, proposal: ForgeProposal) -> Mapping[str, object]:
        spec_path = self._daemon_dir / f"{proposal.blueprint.name}.json"
        if spec_path.exists():
            raise GenesisForgeError(
                f"Daemon '{proposal.blueprint.name}' already exists; refusing to overwrite"
            )
        spec_payload = {
            "name": proposal.blueprint.name,
            "objective": proposal.blueprint.objective,
            "directives": proposal.blueprint.directives,
            "testing_requirements": proposal.blueprint.testing_requirements,
            "lineage": proposal.proposed_spec.get("lineage", {}),
        }
        spec_path.write_text(json.dumps(spec_payload, indent=2, sort_keys=True), encoding="utf-8")

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "provenance": "GenesisForge",
            "proposal_id": proposal.proposal_id,
            "spec_id": proposal.spec_id,
            "capability": proposal.need.capability,
        }
        with self._lineage_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry


# ---------------------------------------------------------------------------
# AdoptionRite


class AdoptionRite:
    """Final promotion into the live mount once governance approves."""

    def __init__(
        self,
        *,
        live_mount: Path,
        codex_index: Path,
        review_board: Callable[[ForgeProposal, TrialReport], bool],
    ) -> None:
        self._live_mount = Path(live_mount)
        self._live_mount.mkdir(parents=True, exist_ok=True)
        self._codex_index = Path(codex_index)
        self._review_board = review_board

    def promote(
        self,
        proposal: ForgeProposal,
        report: TrialReport,
        lineage_entry: Mapping[str, object],
    ) -> Mapping[str, object]:
        if not report.passed:
            raise GenesisForgeError("Cannot promote daemon with failing sandbox trials")
        approved = self._review_board(proposal, report)
        if not approved:
            return {"status": "rejected", "reason": "review_board"}

        live_path = self._live_mount / f"{proposal.blueprint.name}.json"
        if live_path.exists():
            raise GenesisForgeError(
                f"Live mount already contains '{proposal.blueprint.name}'"
            )
        live_payload = {
            "name": proposal.blueprint.name,
            "lineage": dict(lineage_entry),
            "objective": proposal.blueprint.objective,
        }
        live_path.write_text(json.dumps(live_payload, indent=2, sort_keys=True), encoding="utf-8")

        index_payload: list[dict[str, object]] = []
        if self._codex_index.exists():
            try:
                index_payload = json.loads(self._codex_index.read_text(encoding="utf-8"))
            except json.JSONDecodeError:  # pragma: no cover - defensive
                index_payload = []
        if any(entry.get("spec_id") == proposal.spec_id for entry in index_payload):
            raise GenesisForgeError(
                f"Codex index already tracks daemon '{proposal.spec_id}'"
            )
        index_payload.append(
            {
                "spec_id": proposal.spec_id,
                "proposal_id": proposal.proposal_id,
                "capability": proposal.need.capability,
                "provenance": "GenesisForge",
            }
        )
        self._codex_index.write_text(json.dumps(index_payload, indent=2, sort_keys=True), encoding="utf-8")
        return {"status": "adopted", "path": str(live_path)}


# ---------------------------------------------------------------------------
# GenesisForge orchestrator


class GenesisForge:
    """Coordinates capability expansion across all GenesisForge modules during startup."""

    def __init__(
        self,
        *,
        need_seer: NeedSeer,
        forge_engine: ForgeEngine,
        integrity_daemon: IntegrityDaemon,
        trial_run: TrialRun,
        spec_binder: SpecBinder,
        adoption_rite: AdoptionRite,
        ledger: RecoveryLedger,
    ) -> None:
        enforce_codex_startup("GenesisForge")
        self._need_seer = need_seer
        self._forge_engine = forge_engine
        self._integrity_daemon = integrity_daemon
        self._trial_run = trial_run
        self._spec_binder = spec_binder
        self._adoption_rite = adoption_rite
        self._ledger = ledger

    def expand(
        self,
        telemetry_streams: Sequence[TelemetryStream],
        vows: Sequence[CovenantVow],
    ) -> list[GenesisOutcome]:
        outcomes: list[GenesisOutcome] = []
        needs = self._need_seer.scan(telemetry_streams, vows)
        router_k = max(int(os.getenv("SENTIENTOS_ROUTER_K", "3")), 1)
        for need in needs:
            anomaly = Anomaly(kind="genesis_need", subject=need.capability)
            router_seed = f"{need.capability}:{need.source}:{router_k}"
            try:
                proposals = self._forge_engine.draft_variants(need, k=router_k, seed=router_seed)
                candidate_results: list[CandidateResult] = []
                for proposal in proposals:
                    evaluation = self._integrity_daemon.evaluate_report(proposal)
                    candidate_results.append(
                        CandidateResult(
                            candidate_id=proposal.proposal_id,
                            proposal=proposal,
                            evaluation=evaluation,
                            score=score_evaluation(evaluation),
                        )
                    )
                selected, router_status = choose_candidate(candidate_results)
                router_scorecard: dict[str, object] = {
                    "router_k": router_k,
                    "router_seed": router_seed,
                    "router_status": router_status,
                    "candidates": [
                        {
                            "candidate_id": result.candidate_id,
                            "score": result.score,
                            "rank": result.rank,
                            "valid": result.evaluation.valid,
                            "reason_codes": list(result.evaluation.reason_codes),
                            "top_violation_codes": top_violation_codes(result.evaluation.violations),
                            "evaluation_artifact": result.evaluation.ledger_entry,
                        }
                        for result in sorted(candidate_results, key=lambda item: item.rank or 999)
                    ],
                }

                if router_status != "selected":
                    router_scorecard["best_failure_id"] = selected.candidate_id
                    router_scorecard["best_failure"] = {
                        "reason_codes": list(selected.evaluation.reason_codes),
                        "score": selected.score,
                    }
                    self._ledger.log(
                        "GenesisForge routing_failed",
                        anomaly=anomaly,
                        details=router_scorecard,
                        quarantined=True,
                    )
                    raise GenesisForgeError(
                        "No admissible candidate "
                        f"({selected.candidate_id}: {','.join(selected.evaluation.reason_codes)})"
                    )

                proposal = selected.proposal
                router_scorecard["selected_candidate_id"] = selected.candidate_id
                report = self._trial_run.execute(proposal.blueprint)
                if not report.passed:
                    raise GenesisForgeError(
                        "Sandbox validation failed",
                    )
                lineage_entry = self._spec_binder.integrate(proposal)
                adoption = self._adoption_rite.promote(proposal, report, lineage_entry)
                if adoption.get("status") != "adopted":
                    raise GenesisForgeError(
                        f"Review board rejected daemon ({adoption.get('reason', 'unknown')})"
                    )
                outcome = GenesisOutcome(
                    need=need,
                    status="adopted",
                    details={
                        "proposal_id": proposal.proposal_id,
                        "spec_id": proposal.spec_id,
                        "lineage": lineage_entry,
                        "adoption": adoption,
                        "router_scorecard": router_scorecard,
                    },
                )
                self._ledger.log(
                    "GenesisForge event",
                    anomaly=anomaly,
                    action=RepairAction(
                        kind="genesis_birth",
                        subject=proposal.spec_id,
                        description="GenesisForge promoted new daemon",
                        execute=lambda: True,
                    ),
                    details=outcome.details,
                )
                outcomes.append(outcome)
            except GenesisForgeError as exc:
                self._ledger.log(
                    "GenesisForge integration_failed",
                    anomaly=anomaly,
                    details={"error": str(exc), "router_seed": router_seed, "router_k": router_k},
                    quarantined=True,
                )
                outcomes.append(
                    GenesisOutcome(
                        need=need,
                        status="failed",
                        details={"error": str(exc)},
                    )
                )
        return outcomes

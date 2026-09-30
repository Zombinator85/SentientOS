"""Acceptance proof for untrusted root-provenance forwarding through GenesisForge."""
from __future__ import annotations

import ast
import base64
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
from pathlib import Path
from collections.abc import Iterator
from typing import Mapping, cast

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from codex.integrity_daemon import IntegrityDaemon
from sentientos.causal_resource_principal import (
    CausalResourcePrincipal,
    RootPrincipalIssuance,
    RootPrincipalIssuer,
    VerifiedOperatorSponsorship,
)
from sentientos.causal_resource_principal_provenance_signer import CryptographyEd25519RootIssuerProvenanceSigner
from sentientos.causal_resource_principal_signer_custody import (
    RootIssuerPrivateKeyBackend,
    RootIssuerPrivateKeyCustody,
    RootIssuerSigningKeyReference,
)
from sentientos.codex_healer import RecoveryLedger
from sentientos.constitutional_mutation_fabric import ConstitutionalMutationRouter
from sentientos.control_plane_kernel import (
    AdmissionOutcome,
    ControlActionDecision,
    ControlActionRequest,
    ControlPlaneKernel,
    LifecyclePhase,
)
from sentientos.genesis_forge import (
    AdoptionRite,
    CovenantVow,
    ForgeEngine,
    GenesisForge,
    GenesisForgeError,
    NeedSeer,
    SpecBinder,
    TelemetryStream,
    TrialRun,
)
from sentientos.runtime_governor import GovernorDecision, PressureSnapshot

pytestmark = pytest.mark.no_legacy_skip
_SEED = bytes(range(32))


@pytest.fixture(autouse=True)  # type: ignore[untyped-decorator]
def _codex_startup(codex_startup: None) -> Iterator[None]:
    yield


class _Sponsor:
    def verify(self, evidence: object) -> VerifiedOperatorSponsorship:
        return VerifiedOperatorSponsorship("sha256:" + "1" * 64)


class _Backend:
    def __init__(self) -> None:
        self.calls = 0

    def read_configured(self, reference: RootIssuerSigningKeyReference) -> bytearray:
        self.calls += 1
        return bytearray(base64.urlsafe_b64encode(_SEED).rstrip(b"="))


def _issuance() -> tuple[RootPrincipalIssuance, _Backend]:
    public = Ed25519PrivateKey.from_private_bytes(_SEED).public_key().public_bytes_raw()
    key_id = "ed25519-sha256:" + hashlib.sha256(public).hexdigest()
    reference = RootIssuerSigningKeyReference(
        issuer_id="test-root-issuer", signing_key_id=key_id,
        algorithm="ed25519", key_reference="operator-key-v1",
    )
    backend = _Backend()
    signer = CryptographyEd25519RootIssuerProvenanceSigner(
        reference=reference,
        custody=RootIssuerPrivateKeyCustody(reference=reference, backend=cast(RootIssuerPrivateKeyBackend, backend)),
    )
    result = RootPrincipalIssuer(
        issuer_id="test-root-issuer", sponsorship_verifier=_Sponsor(), provenance_signer=signer,
    ).mint_root_with_provenance(
        sponsorship_evidence={"operator": "test"}, subject_binding_digest="sha256:" + "2" * 64,
        epoch=1, issued_at="2026-09-21T08:00:00Z", expires_at="2026-09-21T09:00:00Z",
        signed_at="2026-09-21T08:10:00Z",
    )
    return result, backend


class _Governor:
    def admit_action(self, action_type: str, actor: str, correlation_id: str,
                     metadata: Mapping[str, object] | None = None) -> GovernorDecision:
        return GovernorDecision(
            action_class=action_type, allowed=True, mode="enforce", reason="allowed",
            subject=str((metadata or {}).get("subject") or "subject"), scope="local", origin=actor,
            sampled_pressure=PressureSnapshot(cpu=.1, io=.1, thermal=.1, gpu=.1, composite=.1,
                                               sampled_at=datetime.now(timezone.utc).isoformat()),
            reason_hash="hash", correlation_id=correlation_id, action_priority=0, action_family="control",
        )


class _RecordingKernel:
    def __init__(self, path: Path) -> None:
        now = datetime(2026, 9, 21, 8, 30, tzinfo=timezone.utc).timestamp()
        self.kernel = ControlPlaneKernel(runtime_governor=_Governor(), decisions_path=path,
                                         phase=LifecyclePhase.MAINTENANCE, clock=lambda: now)
        self.requests: list[ControlActionRequest] = []
        self.decisions: list[ControlActionDecision] = []

    def admit(self, request: ControlActionRequest) -> ControlActionDecision:
        self.requests.append(request)
        decision = self.kernel.admit(request)
        self.decisions.append(decision)
        return decision


def _forge(tmp_path: Path, kernel: object) -> GenesisForge:
    return GenesisForge(
        need_seer=NeedSeer(), forge_engine=ForgeEngine(), integrity_daemon=IntegrityDaemon(tmp_path),
        trial_run=TrialRun(), spec_binder=SpecBinder(lineage_root=tmp_path / "lineage", covenant_root=tmp_path / "covenant"),
        adoption_rite=AdoptionRite(live_mount=tmp_path / "live", codex_index=tmp_path / "codex.json", review_board=lambda *_: True),
        ledger=RecoveryLedger(tmp_path / "ledger.jsonl"),
        router_factory=lambda: ConstitutionalMutationRouter(kernel_provider=lambda: kernel), kernel_provider=lambda: kernel,
    )


def _inputs() -> tuple[list[TelemetryStream], list[CovenantVow]]:
    return [TelemetryStream("vision", "vision_input", "camera", frozenset())], [CovenantVow("vision_input", "camera vow")]


def test_real_exact_pair_reaches_control_plane_without_trust_or_policy_change(tmp_path: Path) -> None:
    issuance, backend = _issuance()
    kernel = _RecordingKernel(tmp_path / "decisions.jsonl")
    forge = _forge(tmp_path, kernel)
    telemetry, vows = _inputs()

    root_outcomes = forge.propose_for_review(telemetry, vows, causal_resource_principal=issuance.principal)
    pair_outcomes = forge.propose_for_review(telemetry, vows, root_principal_issuance=issuance)

    root_request, pair_request = kernel.requests
    root_decision, pair_decision = kernel.decisions
    assert pair_request.proof_budget_context["causal_resource_principal"] == issuance.principal.to_dict()
    assert pair_request.proof_budget_context["causal_resource_principal_provenance"] == issuance.provenance.to_dict()
    assert issuance == RootPrincipalIssuance(issuance.principal, issuance.provenance)
    assert "causal_resource_principal_provenance" not in cast(Mapping[str, object], pair_request.proof_budget_context["run_context"])
    assert pair_decision.delegated_outcomes["proof_budget_context"]["causal_attribution"]["status"] == "canonical_root_binding_verified"
    assert pair_decision.outcome == root_decision.outcome == AdmissionOutcome.ALLOW
    assert pair_decision.delegated_outcomes["proof_budget_governor"] == root_decision.delegated_outcomes["proof_budget_governor"]
    assert pair_outcomes[0].status == root_outcomes[0].status == "proposal_ready_for_review"
    assert pair_outcomes[0].details["proof_budget_decision"] == root_outcomes[0].details["proof_budget_decision"]
    assert backend.calls == 1  # issuance signed once upstream; forwarding never reacquires the key


@pytest.mark.parametrize("field", ["principal_id", "principal_binding_digest", "issuer_id"])  # type: ignore[untyped-decorator]
def test_structurally_mismatched_pair_fails_before_request(tmp_path: Path, field: str) -> None:
    issuance, _ = _issuance()
    replacement = "other-issuer" if field == "issuer_id" else ("crp-sha256:" if field == "principal_id" else "sha256:") + "f" * 64
    malformed = replace(issuance, provenance=replace(issuance.provenance, **{field: replacement}))
    kernel = _RecordingKernel(tmp_path / "decisions.jsonl")
    with pytest.raises(GenesisForgeError, match="root_principal_issuance_binding_mismatch"):
        _forge(tmp_path, kernel).propose_for_review(*_inputs(), root_principal_issuance=malformed)
    assert kernel.requests == []


def test_non_exact_and_conflicting_inputs_fail_closed(tmp_path: Path) -> None:
    issuance, _ = _issuance()
    forge = _forge(tmp_path, _RecordingKernel(tmp_path / "decisions.jsonl"))
    with pytest.raises(GenesisForgeError, match="root_principal_issuance_not_canonical"):
        forge.propose_for_review(*_inputs(), root_principal_issuance=cast(RootPrincipalIssuance, object()))
    with pytest.raises(GenesisForgeError, match="causal_resource_principal_conflict"):
        forge.propose_for_review(*_inputs(), causal_resource_principal=issuance.principal, root_principal_issuance=issuance)


def test_no_root_root_only_and_multiple_need_pair_modes_are_explicit(tmp_path: Path) -> None:
    issuance, backend = _issuance()
    kernel = _RecordingKernel(tmp_path / "decisions.jsonl")
    forge = _forge(tmp_path, kernel)
    telemetry, vows = _inputs()
    forge.propose_for_review(telemetry, vows)
    forge.propose_for_review(telemetry, vows, causal_resource_principal=issuance.principal)
    multi = telemetry + [TelemetryStream("audio", "audio_input", "microphone", frozenset())]
    forge.expand(multi, vows + [CovenantVow("audio_input", "audio vow")], root_principal_issuance=issuance)
    assert "causal_resource_principal" not in kernel.requests[0].proof_budget_context
    assert "causal_resource_principal_provenance" not in kernel.requests[1].proof_budget_context
    for request in kernel.requests[2:]:
        assert request.proof_budget_context["causal_resource_principal"] == issuance.principal.to_dict()
        assert request.proof_budget_context["causal_resource_principal_provenance"] == issuance.provenance.to_dict()
    assert backend.calls == 1


def test_genesis_forwarder_has_no_issuer_verifier_trust_or_resource_authority() -> None:
    source = Path("sentientos/genesis_forge.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    calls = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    forbidden_calls = {"RootPrincipalIssuer", "RootIssuerProvenanceVerifier", "ReadOnlyTrustedIssuerCatalog",
                       "CryptographyEd25519RootIssuerProvenanceSigner", "ResourceAllocation", "EffectGrant"}
    assert calls.isdisjoint(forbidden_calls)
    assert all(term not in source for term in ("mint_root_with_provenance(", "private_key", "resource_quota", "admission_grant"))
    assert {field for field in issuance_fields() if "allocation" in field or "quota" in field} == set()


def issuance_fields() -> set[str]:
    issuance, _ = _issuance()
    return set(issuance.principal.to_dict()) | set(issuance.provenance.to_dict())

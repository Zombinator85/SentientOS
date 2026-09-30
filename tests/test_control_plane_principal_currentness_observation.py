from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from sentientos.causal_resource_principal_authentication import RootIssuerProvenanceVerifier
from sentientos.causal_resource_principal_currentness import (
    REGISTRY_SCHEMA,
    PrincipalCurrentnessError,
    PrincipalCurrentnessVerifier,
    ReadOnlyPrincipalRevocationRegistry,
    registry_digest_for,
)
from sentientos.control_plane_kernel import ControlPlaneKernel
from tests.test_control_plane_root_principal_provenance_authentication import (
    NOW,
    _attribution,
    _issuance,
    _kernel,
    _request,
    _verifier,
)

pytestmark = pytest.mark.no_legacy_skip


def _registry(
    tmp_path: Path,
    principal: object,
    *,
    generated_at: str = "2026-09-21T07:00:00Z",
    valid_until: str = "2026-09-21T10:00:00Z",
    revoked_at: str | None = None,
) -> ReadOnlyPrincipalRevocationRegistry:
    entries: list[dict[str, object]] = []
    if revoked_at is not None:
        entries.append(
            {
                "principal_id": principal.principal_id,
                "principal_binding_digest": principal.binding_digest,
                "issuer_id": principal.issuer_id,
                "epoch": principal.epoch,
                "revoked_at": revoked_at,
            }
        )
    body: dict[str, object] = {
        "schema": REGISTRY_SCHEMA,
        "registry_version": 4,
        "generated_at": generated_at,
        "valid_until": valid_until,
        "revoked_principals": entries,
    }
    digest = registry_digest_for(body)
    path = tmp_path / f"registry-{len(list(tmp_path.glob('registry-*.json')))}.json"
    path.write_text(json.dumps({**body, "registry_digest": digest}), encoding="utf-8")
    return ReadOnlyPrincipalRevocationRegistry.load(
        path, expected_registry_version=4, expected_registry_digest=digest
    )


def _current_kernel(
    tmp_path: Path,
    name: str,
    registry: ReadOnlyPrincipalRevocationRegistry,
    *,
    currentness: PrincipalCurrentnessVerifier | None = None,
    provenance: RootIssuerProvenanceVerifier | None = None,
) -> ControlPlaneKernel:
    return _kernel(
        tmp_path,
        name,
        provenance or _verifier(tmp_path),
        principal_currentness_verifier=currentness or PrincipalCurrentnessVerifier(),
        principal_revocation_registry=registry,
    )


def test_real_chain_projects_exact_process_local_currentness_evidence(tmp_path: Path) -> None:
    issuance, _, _ = _issuance()
    provenance = _verifier(tmp_path)
    registry = _registry(tmp_path, issuance.principal)
    currentness = PrincipalCurrentnessVerifier()
    decision, observed = _attribution(
        _current_kernel(tmp_path, "current.jsonl", registry, currentness=currentness, provenance=provenance),
        _request(issuance.principal.to_dict(), issuance.provenance.to_dict()),
    )
    authenticated = provenance.verify(issuance.principal, issuance.provenance, current_time=NOW)
    expected = currentness.verify(issuance.principal, authenticated, registry, current_time=NOW)
    assert decision.allowed
    assert observed["status"] == "authenticated_root_issuer_provenance_verified"
    assert observed["principal_currentness"] == "verified"
    assert observed["principal_currentness_checked_at"] == expected.checked_at
    assert observed["principal_revocation_registry_version"] == expected.revocation_registry_version
    assert observed["principal_revocation_registry_digest"] == expected.revocation_registry_digest
    assert observed["principal_revocation_registry_generated_at"] == expected.registry_generated_at
    assert observed["principal_revocation_registry_valid_until"] == expected.registry_valid_until


def test_configuration_pairing_fails_closed_and_default_remains_usable(tmp_path: Path) -> None:
    issuance, _, _ = _issuance()
    registry = _registry(tmp_path, issuance.principal)
    with pytest.raises(ValueError, match="configured together"):
        ControlPlaneKernel(principal_currentness_verifier=PrincipalCurrentnessVerifier())
    with pytest.raises(ValueError, match="configured together"):
        ControlPlaneKernel(principal_revocation_registry=registry)
    _, observed = _attribution(
        _kernel(tmp_path, "default.jsonl", _verifier(tmp_path)),
        _request(issuance.principal.to_dict(), issuance.provenance.to_dict()),
    )
    assert observed["status"] == "authenticated_root_issuer_provenance_verified"
    assert "principal_currentness" not in observed


def test_currentness_failures_are_bounded_and_do_not_change_policy_or_admission(tmp_path: Path) -> None:
    cases = [
        ("2026-09-21T07:00:00Z", "2026-09-21T10:00:00Z", NOW, "principal_revoked"),
        ("2026-09-21T07:00:00Z", NOW, None, "registry_stale"),
        ("2026-09-21T08:20:00Z", "2026-09-21T10:00:00Z", None, "registry_not_yet_valid"),
    ]
    issuance, _, _ = _issuance()
    for generated_at, valid_until, revoked_at, reason in cases:
        registry = _registry(
            tmp_path, issuance.principal, generated_at=generated_at, valid_until=valid_until, revoked_at=revoked_at
        )
        failed, observed = _attribution(
            _current_kernel(tmp_path, f"{reason}.jsonl", registry),
            _request(issuance.principal.to_dict(), issuance.provenance.to_dict(), reason),
        )
        baseline, _ = _attribution(
            _kernel(tmp_path, f"baseline-{reason}.jsonl", _verifier(tmp_path)),
            _request(issuance.principal.to_dict(), issuance.provenance.to_dict(), reason),
        )
        assert observed["status"] == "authenticated_root_issuer_provenance_verified"
        assert observed["principal_currentness"] == "failed"
        assert observed["principal_currentness_reason"] == reason
        assert failed.outcome == baseline.outcome
        assert failed.reason_codes == baseline.reason_codes
        assert failed.delegated_outcomes["runtime_governor"] == baseline.delegated_outcomes["runtime_governor"]
        assert failed.delegated_outcomes["proof_budget_governor"] == baseline.delegated_outcomes["proof_budget_governor"]


def test_future_revocation_transitions_exactly_at_revoked_at(tmp_path: Path) -> None:
    issuance, _, _ = _issuance()
    future = "2026-09-21T08:20:00Z"
    registry = _registry(tmp_path, issuance.principal, revoked_at=future)
    _, before = _attribution(
        _current_kernel(tmp_path, "before.jsonl", registry),
        _request(issuance.principal.to_dict(), issuance.provenance.to_dict(), "before"),
    )
    at_kernel = _current_kernel(tmp_path, "at.jsonl", registry)
    at_kernel._clock = lambda: 1789978800  # type: ignore[attr-defined]
    _, at = _attribution(
        at_kernel, _request(issuance.principal.to_dict(), issuance.provenance.to_dict(), "at")
    )
    assert before["principal_currentness"] == "verified"
    assert at["principal_currentness_reason"] == "principal_revoked"


def test_currentness_runs_once_only_after_authentication_and_uses_the_same_clock(tmp_path: Path) -> None:
    issuance, _, _ = _issuance()
    registry = _registry(tmp_path, issuance.principal)

    class CountingCurrentness(PrincipalCurrentnessVerifier):
        calls = 0
        seen_time: str | None = None

        def verify(self, principal, authenticated, registry, *, current_time):  # type: ignore[no-untyped-def]
            self.calls += 1
            self.seen_time = current_time
            return super().verify(principal, authenticated, registry, current_time=current_time)

    currentness = CountingCurrentness()
    clock_calls = 0
    kernel = _current_kernel(tmp_path, "counts.jsonl", registry, currentness=currentness)

    def clock() -> float:
        nonlocal clock_calls
        clock_calls += 1
        return 1789978200

    kernel._clock = clock  # type: ignore[attr-defined]
    _attribution(kernel, _request(issuance.principal.to_dict(), issuance.provenance.to_dict()))
    assert currentness.calls == 1 and currentness.seen_time == NOW and clock_calls == 1

    for index, request in enumerate(
        (
            _request(issuance.principal.to_dict(), None, "no-provenance"),
            _request({"malformed": True}, issuance.provenance.to_dict(), "bad-root"),
            _request(issuance.principal.to_dict(), {"malformed": True}, "bad-provenance"),
        )
    ):
        isolated = CountingCurrentness()
        _attribution(_current_kernel(tmp_path, f"skip-{index}.jsonl", registry, currentness=isolated), request)
        assert isolated.calls == 0

    repeated = CountingCurrentness()
    repeated_kernel = _current_kernel(tmp_path, "repeated.jsonl", registry, currentness=repeated)
    for correlation in ("genesis-need-1", "genesis-need-2"):
        _attribution(
            repeated_kernel,
            _request(issuance.principal.to_dict(), issuance.provenance.to_dict(), correlation),
        )
    assert repeated.calls == 2


def test_binding_failure_and_unavailable_verifier_are_bounded(tmp_path: Path) -> None:
    issuance, _, _ = _issuance()
    registry = _registry(tmp_path, issuance.principal)

    class Failing(PrincipalCurrentnessVerifier):
        def __init__(self, failure: BaseException) -> None:
            self.failure = failure

        def verify(self, principal, authenticated, registry, *, current_time):  # type: ignore[no-untyped-def]
            raise self.failure

    for name, failure, reason in (
        ("binding", PrincipalCurrentnessError("authenticated_principal_binding_mismatch"), "authenticated_principal_binding_mismatch"),
        ("malformed", PrincipalCurrentnessError("secret registry detail"), "currentness_configuration_unusable"),
        ("unavailable", RuntimeError("secret backend detail"), "currentness_verifier_unavailable"),
    ):
        _, observed = _attribution(
            _current_kernel(tmp_path, f"{name}.jsonl", registry, currentness=cast(PrincipalCurrentnessVerifier, Failing(failure))),
            _request(issuance.principal.to_dict(), issuance.provenance.to_dict(), name),
        )
        assert observed["principal_currentness_reason"] == reason
        assert "secret" not in str(observed)


def test_caller_currentness_and_registry_claims_are_ignored_and_success_is_policy_invariant(tmp_path: Path) -> None:
    issuance, _, _ = _issuance()
    registry = _registry(tmp_path, issuance.principal)
    request = _request(issuance.principal.to_dict(), issuance.provenance.to_dict(), "smuggling")
    assert request.proof_budget_context is not None
    request.proof_budget_context.update(
        {
            "current": True,
            "currentness_verified": True,
            "principal_revocation_registry": {"revoked_principals": []},
            "current_authenticated_root_principal_evidence": {"not_revoked": True},
        }
    )
    request.proof_budget_context["run_context"].update({"revocation_checked": True, "current": True})
    verified, observed = _attribution(_current_kernel(tmp_path, "smuggling.jsonl", registry), request)
    baseline, _ = _attribution(
        _kernel(tmp_path, "plain.jsonl", _verifier(tmp_path)),
        _request(issuance.principal.to_dict(), issuance.provenance.to_dict(), "plain"),
    )
    assert observed["principal_currentness"] == "verified"
    assert "current_authenticated_root_principal_evidence" not in observed
    assert verified.outcome == baseline.outcome
    assert verified.delegated_outcomes["proof_budget_governor"] == baseline.delegated_outcomes["proof_budget_governor"]


def test_composition_exposes_no_resource_or_authority_operations() -> None:
    forbidden = {
        "allocate", "allocator", "amount", "reservation", "entitle", "consume", "receipt",
        "admission_grant", "effect_grant", "sign", "mint", "issue", "revoke", "renew", "admin",
    }
    names = set(ControlPlaneKernel.__dict__)
    added = {name for name in names if "current" in name.lower() or "revocation" in name.lower()}
    assert not any(word in name.lower() for name in added for word in forbidden)

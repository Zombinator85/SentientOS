"""Repository-native end-to-end fixture for diagnostic execution tests."""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path

from sentientos.host_dry_run_audit_closure_runtime import HostDryRunAuditClosureRuntimeCoordinator
from sentientos.host_dry_run_execution_runtime import HostDryRunExecutionRuntimeCoordinator
from sentientos.host_fulfillment_executor_readiness_runtime import HostFulfillmentExecutorReadinessRuntimeCoordinator
from sentientos.host_local_diagnostic_execution_source_runtime import HostLocalDiagnosticExecutionSourceRuntimeCoordinator
from sentientos.host_real_effect_admission_runtime import HostRealEffectAdmissionRuntimeCoordinator
from sentientos.local_authorization_grant import build_local_authorization_grant_expiry_evaluation, build_local_authorization_grant_ledger, local_authorization_grant_digest, verify_local_authorization_grant
from sentientos.host_fulfillment_authorization_runtime import build_request_envelope, recompute_source
from tests.test_host_fulfillment_authorization_runtime import Kernel, chain, consume
from tests.test_host_fulfillment_executor_readiness_runtime import _snapshot_for, reroute_result

NOW = "2029-01-02T00:00:00+00:00"


@dataclass(frozen=True)
class DiagnosticExecutionFixture:
    source_bundle: Path
    source_digest: str
    snapshot: dict[str, object]
    verification: dict[str, object]
    target: Path


def build_diagnostic_execution_fixture(root: Path) -> DiagnosticExecutionFixture:
    """Build every persisted source rung through its public coordinator."""
    issue, grant, _verification, _ledger, _expiry, issue_source, environment = chain()
    # Diagnostic execution authority deliberately includes the separately named
    # exact-rollback scope; write authority alone never implies deletion.
    grant = replace(grant, granted_scope_labels=tuple(sorted(set(grant.granted_scope_labels) | {"local_diagnostic_exact_rollback"})), digest="")
    grant = replace(grant, digest=local_authorization_grant_digest(grant))
    issue = dict(issue) | {"grant_digest": grant.digest}
    provisional_expiry = build_local_authorization_grant_expiry_evaluation(grant, evaluated_at=NOW)
    provisional_verification = verify_local_authorization_grant(grant, checked_scope_labels=grant.granted_scope_labels, checked_time_label=NOW, expiry_evaluation=provisional_expiry)
    provisional_ledger = build_local_authorization_grant_ledger((grant,), (), (provisional_expiry,), created_at=NOW)
    issue_source = recompute_source(issue_receipt=issue, grant=grant, verification=provisional_verification, authorization_ledger=provisional_ledger, ledger_predecessor_digest="sha256:empty", expiry_evaluation=provisional_expiry)
    environment = build_request_envelope(issue_source, requested_scope_labels=grant.granted_scope_labels, requested_time=NOW)
    _verification, _ledger, _expiry = provisional_verification, provisional_ledger, provisional_expiry
    consumed = consume(root / "authorization-consumption", bundle=(issue, grant, _verification, _ledger, _expiry, issue_source, environment))
    consumed = reroute_result(consumed, "diagnostics_fulfillment_authorization")
    expiry = build_local_authorization_grant_expiry_evaluation(grant, evaluated_at=NOW)
    verification = verify_local_authorization_grant(grant, checked_scope_labels=grant.granted_scope_labels, checked_time_label=NOW, expiry_evaluation=expiry)
    ledger = build_local_authorization_grant_ledger((grant,), (), (expiry,), created_at=NOW)
    snapshot = _snapshot_for(grant, ledger, issue_source)

    readiness = HostFulfillmentExecutorReadinessRuntimeCoordinator(runtime_state_root=root / "readiness-state", kernel=Kernel(), clock=lambda: NOW).evaluate(
        consumed, output_root=root / "readiness", grant=grant, verification=verification, current_snapshot=snapshot, expiry_evaluation=expiry
    )
    assert readiness.status.startswith("ready_for_executor_contract_review")
    readiness_bundle = root / "readiness" / readiness.request.request_id
    dry_run = HostDryRunExecutionRuntimeCoordinator(runtime_state_root=root / "dry-run-state", kernel=Kernel(), clock=lambda: NOW).evaluate(readiness, output_root=root / "dry-run")
    assert dry_run.status == "dry_run_runtime_simulated"
    dry_run_bundle = root / "dry-run" / dry_run.request.request_id
    closure = HostDryRunAuditClosureRuntimeCoordinator(runtime_state_root=root / "closure-state", clock=lambda: NOW).evaluate(dry_run_runtime_bundle_root=dry_run_bundle, output_root=root / "closure")
    assert closure.status == "host_dry_run_audit_closure_runtime_closed"
    admission = HostRealEffectAdmissionRuntimeCoordinator().evaluate(
        closure_bundle_root=root / "closure" / closure.request.request_id,
        output_root=root / "admission",
        admission_domain="diagnostics_real_effect_candidate",
    )
    assert admission.status == "host_real_effect_admission_runtime_recorded" and admission.request is not None
    source = HostLocalDiagnosticExecutionSourceRuntimeCoordinator().evaluate(
        admission_bundle_root=root / "admission" / admission.request.request_id,
        dry_run_bundle_root=dry_run_bundle,
        readiness_bundle_root=readiness_bundle,
        current_snapshot=snapshot.to_dict(),
        current_verification=verification.to_dict(),
        effect_output_dir=root / "target",
        output_root=root / "execution-source",
        correlation_id="diagnostic-execution-proof",
    )
    assert source.status == "host_local_diagnostic_execution_source_ready"
    source_bundle = Path(source.bundle_root)
    source_digest = json.loads((source_bundle / "bundle_manifest.json").read_text())["bundle_digest"]
    return DiagnosticExecutionFixture(source_bundle, source_digest, snapshot.to_dict(), verification.to_dict(), root / "target")

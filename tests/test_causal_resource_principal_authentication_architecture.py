from __future__ import annotations

import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "architecture/causal_resource_principal_authentication_architecture.json"
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def test_contract_records_historical_sha_and_bounded_runtime_posture() -> None:
    assert re.fullmatch(r"[0-9a-f]{40}", CONTRACT["repository_sha"])
    assert CONTRACT["repository_sha"] == "6e07a74b4814f656aa211bfcabb90c15dc13698d"
    assert CONTRACT["schema"] == "sentientos.causal_resource_principal_authentication_architecture:v2"
    assert CONTRACT["posture"] == "bounded_runtime_verification_boundary_non_authority"
    assert CONTRACT["implementation_boundaries"]["runtime_changes_in_this_task"] is True
    assert CONTRACT["implementation_boundaries"]["changed_runtime_files"] == [
        "sentientos/causal_resource_principal_authentication.py"
    ]


def test_v1_identity_and_authentication_are_separate() -> None:
    compatibility = CONTRACT["principal_compatibility"]
    assert compatibility["schema"] == "sentientos.causal_resource_principal:v1"
    assert compatibility["decision"] == "preserve_unchanged"
    assert compatibility["identity_under_key_rotation"] == "same_principal_id"
    assert compatibility["identity_under_resigning"] == "same_principal_id"
    assert CONTRACT["current_gap"]["statement"] == "principal_self_binding_is_not_issuer_authentication"


def test_existing_mechanism_decisions_use_closed_vocabularies() -> None:
    allowed_classifications = {
        "production_cryptographic_authentication", "test_only_authentication",
        "self_binding_integrity_only", "compatibility_stub", "credential_custody",
        "artifact_signing", "authority_evidence", "unrelated",
    }
    allowed_reuse = {
        "reuse_directly", "reuse_pattern_only", "test_only", "incompatible_semantics",
        "must_not_use", "requires_refactor_before_reuse",
    }
    audit = {item["mechanism"]: item for item in CONTRACT["existing_mechanism_audit"]}
    assert all(item["classification"] in allowed_classifications for item in audit.values())
    assert all(item["reuse_decision"] in allowed_reuse for item in audit.values())
    assert audit["nacl/signing.py"]["reuse_decision"] == "must_not_use"
    assert audit["sentientos/signed_strategic.py:HmacTestStrategicSigner"]["classification"] == "test_only_authentication"
    assert CONTRACT["algorithm_policy"]["hmac"] == "test_only_never_production_asymmetric_authentication"


def test_trust_signing_and_secret_boundaries_are_non_collapsible() -> None:
    assert CONTRACT["public_key_custody"]["envelope_key_accepted"] is False
    assert CONTRACT["public_key_custody"]["runtime_callers_can_add"] is False
    assert CONTRACT["signer_boundary"]["arbitrary_bytes_api"] == "forbidden"
    assert CONTRACT["verifier_boundary"]["can_sign"] is False
    assert CONTRACT["signer_boundary"]["conceptual_interface"] != CONTRACT["verifier_boundary"]["conceptual_interfaces"]
    assert "private_key" not in CONTRACT["provenance_envelope"]["durable_fields"]
    assert "private_key" in CONTRACT["provenance_envelope"]["forbidden_fields"]


def test_identity_epochs_authority_and_allocation_remain_distinct() -> None:
    assert CONTRACT["issuer_identity"]["stable_across_rotation"] is True
    assert CONTRACT["key_identity"]["distinct_from_issuer_id"] is True
    assert CONTRACT["key_identity"]["distinct_from_principal_epoch"] is True
    assert CONTRACT["rotation_semantics"]["causal_identity_preserved"] is True
    assert CONTRACT["provenance_envelope"]["authority"] == "none"
    assert CONTRACT["verified_result_semantics"]["grants"] == []
    assert "issuer_authentication != resource_entitlement" in CONTRACT["security_invariants"]
    assert "issuer_authentication != effect_authority" in CONTRACT["security_invariants"]
    prerequisite = CONTRACT["future_allocation_prerequisite"]
    assert prerequisite["canonical_self_binding_alone_sufficient"] is False
    assert prerequisite["authentication_creates_allocation"] is False


def test_observation_only_and_verified_result_postures_are_explicit() -> None:
    observation = CONTRACT["observation_only_policy"]
    assert observation["canonical_status"] == "canonical_root_binding_verified"
    assert observation["canonical_status_meaning"] == "self_consistency_only"
    assert observation["canonical_only_may_continue"] is True
    assert observation["canonical_only_grants"] == []
    assert CONTRACT["verified_result_semantics"]["serialization"] == "not_accepted_as_verified_caller_truth"


def test_next_slice_is_one_bounded_verification_backend_task() -> None:
    next_slice = CONTRACT["next_runtime_slice"]
    assert next_slice["count"] == 1
    assert next_slice["id"] == "production_verification_only_ed25519_backend"
    assert "verification-only Ed25519 backend" in next_slice["scope"]
    assert "do not add signing" in next_slice["scope"]


def test_implemented_and_deferred_boundaries_are_exactly_separated() -> None:
    boundaries = CONTRACT["implementation_boundaries"]
    assert "root_issuer_provenance_verifier" in boundaries["implemented"]
    assert "process_local_authenticated_result" in boundaries["implemented"]
    assert "deterministic_test_only_backend" in boundaries["implemented"]
    assert "production_ed25519_backend" in boundaries["deferred"]
    assert "production_signer" in boundaries["deferred"]
    assert "resource_allocation" in boundaries["deferred"]
    assert CONTRACT["algorithm_policy"]["claim_identifier"] == "ed25519"


def test_all_evidence_sources_exist() -> None:
    assert CONTRACT["evidence_sources"]
    assert all((ROOT / path).is_file() for path in CONTRACT["evidence_sources"])


def test_top_level_contract_has_required_sections() -> None:
    required = {
        "schema", "posture", "repository_sha", "current_gap", "existing_mechanism_audit",
        "alternatives", "decision", "principal_compatibility", "provenance_envelope",
        "signed_payload", "domain_separation", "algorithm_policy", "signer_boundary",
        "verifier_boundary", "private_key_custody", "public_key_custody", "trust_anchor_rules",
        "issuer_identity", "key_identity", "rotation_semantics", "revocation_semantics",
        "replay_semantics", "durability", "producer_flow", "consumer_flow",
        "verified_result_semantics", "observation_only_policy", "future_allocation_prerequisite",
        "security_invariants", "implementation_boundaries", "forbidden_claims", "open_questions",
        "next_runtime_slice",
    }
    assert required <= CONTRACT.keys()
    assert {item["decision"] for item in CONTRACT["alternatives"]} <= {"adopt", "reject"}

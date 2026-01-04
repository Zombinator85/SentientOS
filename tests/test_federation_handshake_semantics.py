import json

from sentientos.federation.handshake_semantics import (
    CompatibilityResult,
    SemanticAttestation,
    compute_semantic_layer_hash,
    evaluate_compatibility,
)


def test_attestation_serialization_is_deterministic() -> None:
    attestation = SemanticAttestation(
        node_id="node-a",
        ontology_hash="onto",
        policy_hash="policy",
        invariant_catalog_hash="inv",
        failure_taxonomy_hash="fail",
        declared_capabilities=("read", "write"),
    )
    first = attestation.serialize()
    second = attestation.serialize()
    assert first == second
    payload = json.loads(first)
    assert payload["semantic_layer_hash"] == compute_semantic_layer_hash(
        "onto", "policy", "inv", "fail"
    )


def test_identical_semantic_layers_are_compatible() -> None:
    local = SemanticAttestation(
        node_id="node-a",
        ontology_hash="onto",
        policy_hash="policy",
        invariant_catalog_hash="inv",
        failure_taxonomy_hash="fail",
    )
    remote = SemanticAttestation(
        node_id="node-b",
        ontology_hash="onto",
        policy_hash="policy",
        invariant_catalog_hash="inv",
        failure_taxonomy_hash="fail",
    )
    result, explanation = evaluate_compatibility(local, remote)
    assert result is CompatibilityResult.COMPATIBLE
    assert explanation.semantic_divergence is False
    assert explanation.peripheral_divergence is False


def test_single_layer_divergence_is_compatible_with_divergence() -> None:
    local = SemanticAttestation(
        node_id="node-a",
        ontology_hash="onto",
        policy_hash="policy",
        invariant_catalog_hash="inv",
        failure_taxonomy_hash="fail",
    )
    remote = SemanticAttestation(
        node_id="node-b",
        ontology_hash="onto",
        policy_hash="policy-x",
        invariant_catalog_hash="inv",
        failure_taxonomy_hash="fail",
    )
    result, explanation = evaluate_compatibility(local, remote)
    assert result is CompatibilityResult.COMPATIBLE_WITH_DIVERGENCE
    assert explanation.semantic_divergence is False
    assert explanation.peripheral_divergence is True


def test_ontology_mismatch_is_parallel() -> None:
    local = SemanticAttestation(
        node_id="node-a",
        ontology_hash="onto",
        policy_hash="policy",
        invariant_catalog_hash="inv",
        failure_taxonomy_hash="fail",
    )
    remote = SemanticAttestation(
        node_id="node-b",
        ontology_hash="onto-x",
        policy_hash="policy",
        invariant_catalog_hash="inv",
        failure_taxonomy_hash="fail",
    )
    result, explanation = evaluate_compatibility(local, remote)
    assert result is CompatibilityResult.PARALLEL
    assert explanation.semantic_divergence is True
    assert explanation.peripheral_divergence is False


def test_no_mutation_or_side_effects() -> None:
    local = SemanticAttestation(
        node_id="node-a",
        ontology_hash="onto",
        policy_hash="policy",
        invariant_catalog_hash="inv",
        failure_taxonomy_hash="fail",
    )
    remote = SemanticAttestation(
        node_id="node-b",
        ontology_hash="onto",
        policy_hash="policy-x",
        invariant_catalog_hash="inv",
        failure_taxonomy_hash="fail",
    )
    local_serialized = local.serialize()
    remote_serialized = remote.serialize()
    result, _ = evaluate_compatibility(local, remote)
    assert result is CompatibilityResult.COMPATIBLE_WITH_DIVERGENCE
    assert local.serialize() == local_serialized
    assert remote.serialize() == remote_serialized

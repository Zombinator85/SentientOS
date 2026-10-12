from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime
import sys
import time
from pathlib import Path

from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.production_chat_resource_observation import ProductionChatResourceObservationOwner
from sentientos.production_chat_resource_provisioning_bundle_producer import (
    produce_production_chat_resource_provisioning_bundle,
)
from sentientos.runtime.local_model_chat_service import (
    LocalModelChatServiceAdapter, LocalModelChatStartup,
)
from sentientosd import RuntimeMaintenanceSurfaces
from tests.test_local_model_serving_inference import setup as serving_setup
from tests.test_production_chat_resource_provisioning_bundle_producer import inputs
from tests.test_resident_epistemic_development import fixture as epistemic_fixture
from sentientos.persistent_epistemic_state import PersistentEpistemicStateOwner
from sentientos.codex_task_authority_admission import (
    RESIDENT_EPISTEMIC_STATE_MUTATION,
    RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION,
)
from sentientos.resident_epistemic_state_mutation import ResidentEpistemicStateMutationController
from sentientos.runtime_admission import RuntimeAdmissionVerifier


def test_parent_child_resource_invocation_generation_reaches_world_state(
        tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Join actual adapter handoff to fixture inference, debit, observer and World-State."""
    monkeypatch.setenv("SENTIENTOS_GOVERNOR_ROOT", str(tmp_path / "governor"))
    monkeypatch.setenv("SENTIENTOS_RUNTIME_STATE_ROOT", str(tmp_path / "runtime"))
    monkeypatch.setenv("SENTIENTOS_FEDERATION_ROOT", str(tmp_path / "federation"))
    monkeypatch.setenv("SENTIENTOS_REPO_ROOT", str(tmp_path / "repo"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_ROOT", str(tmp_path / "trust"))
    monkeypatch.setenv("PULSE_TRUST_EPOCH_STATE", str(tmp_path / "trust" / "state.json"))

    registry, provisioning_inputs = inputs(tmp_path, calls=2)
    bundle = produce_production_chat_resource_provisioning_bundle(
        registry, "joined-process", **provisioning_inputs)
    result_path = tmp_path / "joined-result.json"
    release_path = tmp_path / "release-joined-child"
    monkeypatch.setenv("TEST_RESOURCE_ROOT", str(tmp_path))
    monkeypatch.setenv("TEST_JOINED_RESULT", str(result_path))
    monkeypatch.setenv("TEST_RELEASE_JOINED_CHILD", str(release_path))
    child = tmp_path / "resource-chat-child.py"
    child.write_text("""\
import json, os, sys, time
from pathlib import Path
from sentientos.chat_process_generation import ChatProcessGenerationError, verify_current_chat_process_handoff
from sentientos.governed_local_model_invocation import LocalModelInvocationBudget
from sentientos.installation_state import InstallationIdentity, InstallationStateRegistry
from sentientos.production_chat_resource_provisioning import load_production_chat_resource_context_owner
from tests.test_local_model_serving_inference import setup
from _pytest.monkeypatch import MonkeyPatch

args = dict(zip(sys.argv[1::2], sys.argv[2::2]))
resource_root = Path(os.environ['TEST_RESOURCE_ROOT'])
registry = InstallationStateRegistry._for_testing(resource_root / 'state')
handle = registry.open(InstallationIdentity.parse(args['--installation-identity']))
deadline = time.monotonic() + 5
while True:
    try:
        handoff = verify_current_chat_process_handoff(handle=handle, handoff_id=args['--runtime-handoff-id'])
        break
    except ChatProcessGenerationError as exc:
        if str(exc) != 'chat_process_handoff_unavailable' or time.monotonic() >= deadline:
            raise
        time.sleep(.01)
if handoff['software_generation_digest'] != args['--expected-software-generation-digest']:
    raise RuntimeError('expected_source_generation_mismatch')
patch = MonkeyPatch()
context = serving = None
try:
    bridge, serving, _session, model, _kernel, _current = setup(
        patch, resource_root / 'child-model',
        installation_identity=args['--installation-identity'],
        runtime_handoff_id=args['--runtime-handoff-id'], state_root=resource_root / 'state',
        serving_operation_id=args['--serving-operation-id'])
    context = load_production_chat_resource_context_owner(
        serving._handle, args['--resource-provisioning-id'],
        clock=lambda: '2026-09-21T08:30:00Z', nonce_source=lambda: 'child-attempt')
    receipt = bridge.generate(prompt='joined process and resource fixture', caller='test-operator',
        correlation_id='joined-process-invocation',
        budget=LocalModelInvocationBudget(100, 200, 20, 5.0, 2),
        resource_context=context.next_context())
    if receipt.status != 'admitted_completed' or model.calls != 1:
        raise RuntimeError('fixture_invocation_not_completed')
    output = {'status': receipt.status, 'receipt_id': receipt.receipt_id,
        'receipt_digest': receipt.receipt_digest,
        'model_id': receipt.request.get('model_id'),
        'linked_model_id': receipt.request['linkage'].get('model_id'),
        'software_generation_digest': handoff['software_generation_digest'],
        'handoff_id': handoff['handoff_id'], 'handoff_digest': handoff['handoff_digest'],
        'process_instance_id': handoff['process_instance_id']}
finally:
    if context is not None:
        context.close()
    if serving is not None:
        serving.close()
    patch.undo()
Path(os.environ['TEST_JOINED_RESULT']).write_text(json.dumps(output, sort_keys=True))
deadline = time.monotonic() + 10
while not Path(os.environ['TEST_RELEASE_JOINED_CHILD']).exists() and time.monotonic() < deadline:
    time.sleep(.01)
""", encoding="utf-8")

    identity = InstallationIdentity("production")

    def child_argv(config, *, root, runtime_handoff_id=None,
                   expected_source_generation_digest=None, **_kwargs):
        assert runtime_handoff_id is not None
        argv = (sys.executable, str(child), "--installation-identity", config.installation_identity,
            "--serving-operation-id", config.serving_operation_id,
            "--runtime-handoff-id", runtime_handoff_id)
        if expected_source_generation_digest is not None:
            argv += ("--expected-software-generation-digest", expected_source_generation_digest)
        if config.resource_provisioning_id is not None:
            argv += ("--resource-provisioning-id", config.resource_provisioning_id)
        return argv

    monkeypatch.setattr(LocalModelChatServiceAdapter, "_launcher_argv", staticmethod(child_argv))
    config = LocalModelChatStartup(enabled=True, installation_identity=identity.value,
        serving_operation_id="serve-joined", resource_provisioning_id="joined-process")
    adapter = LocalModelChatServiceAdapter(config, installation_handle=registry)
    readonly = InstallationStateRegistry(tmp_path / "state", _test_only=True).open_read_only(identity)
    try:
        adapter.start()
        parent_handoff = adapter.current_runtime_handoff()
        deadline = time.monotonic() + 10
        while not result_path.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert result_path.exists(), bytes(adapter._diagnostics).decode("utf-8", "replace")
        child_result = json.loads(result_path.read_text(encoding="utf-8"))
        assert child_result["status"] == "admitted_completed"
        assert child_result["software_generation_digest"] == parent_handoff["software_generation_digest"]
        assert child_result["handoff_digest"] == parent_handoff["handoff_digest"]

        observer = ProductionChatResourceObservationOwner(readonly, "joined-process")
        observation = observer.observe()
        assert observation.invocation_receipt_posture == "verified"
        assert observation.chat_process_generation_posture == "verified"
        assert len(observation.chat_process_generation_attributions) == 1
        attribution = observation.chat_process_generation_attributions[0]
        assert attribution["invocation_receipt_id"] == child_result["receipt_id"]
        assert attribution["invocation_receipt_digest"] == child_result["receipt_digest"]
        assert attribution["chat_process_handoff"]["process_instance_id"] == child_result[
            "process_instance_id"]
        assert attribution["chat_process_handoff"]["software_generation_digest"] == child_result[
            "software_generation_digest"]

        surfaces = RuntimeMaintenanceSurfaces(tmp_path,
            resource_observation_owner=observer,
            resource_observation_configuration_status={
                "status": "configured", "read_only": True, "effect_authority": False})
        surfaces.build_world_state_board(tick_id="2026-09-21T08:40:00Z")
        snapshot = surfaces.current_world_state_snapshot
        assert snapshot is not None
        generation_facts = [fact for fact in snapshot.facts
            if fact.subject.subject_kind == "chat_process_software_generation_invocation"]
        assert len(generation_facts) == 1
        payload = generation_facts[0].payload
        assert payload["invocation_receipt_digest"] == child_result["receipt_digest"]
        assert payload["software_generation_digest"] == child_result["software_generation_digest"]
        assert payload["process_instance_id"] == child_result["process_instance_id"]
        assert payload["loaded_code_identity_posture"] == "not_independently_attested"
        assert generation_facts[0].effect_claimed is False and generation_facts[0].effect_proven is False
        assert payload["model_id"] == child_result["model_id"]
        assert payload["model_id"]
        assert payload["resource_allocation_digest"] == bundle.allocation_digest
        resource_facts = [fact for fact in snapshot.facts
            if fact.subject.subject_kind == "causal_resource_consumption"]
        assert len(resource_facts) == 1
        assert resource_facts[0].payload["shared_host_usage_attribution"] == (
            "unknown_without_independent_observation")

        # Admit this exact recovered resource observation through the existing
        # configured epistemic owner, then reconstruct custody and enforce the
        # persisted N-to-N+1 cognition cutoff.
        epistemic_root = tmp_path / "epistemics"
        epistemic_owner, proposition, _admission_ledger, development = epistemic_fixture(
            epistemic_root)
        rule = replace(development.config.rules[0], selector={
            "source_kind": "resource_governor",
            "source_id": "governed_local_model_resource_consumption",
            "subject_kind": "causal_resource_consumption",
            "stage": "observation",
            "disposition": "recorded",
        })
        development.config = replace(development.config, rules=(rule,))
        tick_id_n = "2026-09-21T08:40:00+00:00"
        tick_n = int(datetime.fromisoformat(tick_id_n).timestamp())
        epistemic_surfaces = RuntimeMaintenanceSurfaces(
            tmp_path, resource_observation_owner=observer,
            resource_observation_configuration_status={
                "status": "configured", "read_only": True, "effect_authority": False},
            epistemic_state_owner=epistemic_owner,
            epistemic_state_config={"status": "configured",
                "cognitive_consumption_enabled": True,
                "max_cognitive_projection_count": 4},
            epistemic_development_runtime=development)
        epistemic_surfaces.build_world_state_board(tick_id=tick_id_n)
        epistemic_snapshot = epistemic_surfaces.current_world_state_snapshot
        assert epistemic_snapshot is not None
        developed = epistemic_surfaces.run_epistemic_development(tick_id=tick_id_n)
        assert developed["status"] == "state_advanced"
        assert developed["next_tick_only"] is True and developed["authority"] is False
        bindings = epistemic_owner.bindings(proposition.proposition_id)
        assert len(bindings) == 1
        assert bindings[0].observation_time == "2026-09-21T08:30:00Z"
        assert bindings[0].freshness != "current"
        assert epistemic_owner.cognitive_projection(max_states=4, current_tick=tick_n) is None

        recovered_epistemic_owner = PersistentEpistemicStateOwner(
            epistemic_root / "epistemics", allowed_namespaces=("operator",))
        ResidentEpistemicStateMutationController(
            owner=recovered_epistemic_owner,
            admission_verifier=RuntimeAdmissionVerifier(
                definitions={RESIDENT_EPISTEMIC_STATE_MUTATION:
                    RESIDENT_EPISTEMIC_STATE_MUTATION_DEFINITION},
                ledger=_admission_ledger),
            current_sequence=_admission_ledger.current_sequence,
            receipt_root=epistemic_root / "receipts")
        assert recovered_epistemic_owner.cognitive_projection(
            max_states=4, current_tick=tick_n) is None
        recovered_state = recovered_epistemic_owner.current_state(proposition.proposition_id)
        later_projection = recovered_epistemic_owner.cognitive_projection(
            max_states=4, current_tick=tick_n + 1)
        assert later_projection is not None, {
            "state": recovered_state, "verification": recovered_epistemic_owner.verify(),
            "tick_n": tick_n,
        }
        assert later_projection.source_tick == tick_n
        assert later_projection.state_ids == tuple(developed["successor_state_ids"])
    finally:
        release_path.write_text("release\n", encoding="utf-8")
        adapter.stop()

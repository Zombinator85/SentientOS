from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.local_model_authority import (
    ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_INVOCATION_PURPOSES,
    ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,
)
from sentientos.rootless_experimental_local_model import RootlessExperimentalError
from sentientos.rootless_experimental_ollama_epistemic_session import (
    MAX_NEW_TOKENS, MAX_OUTPUT_CHARS, MAX_PROMPT_CHARS,
    ROOTLESS_DEVELOPMENTAL_MAX_CALLS,
    ROOTLESS_DEVELOPMENTAL_MAX_INPUT_CHARS,
    RootlessExperimentalOllamaEpistemicSession,
)


class _Invoker:
    def build_request(self, **kwargs):
        return SimpleNamespace(**kwargs)

    def invoke(self, request, **kwargs):
        return (request, kwargs)


def _session(*, developmental):
    session = object.__new__(RootlessExperimentalOllamaEpistemicSession)
    session._closed = False
    session._correlations = set()
    session._allowed_purposes = frozenset(
        ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_INVOCATION_PURPOSES
        if developmental else (ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,))
    session._max_input_chars = (ROOTLESS_DEVELOPMENTAL_MAX_INPUT_CHARS
        if developmental else MAX_PROMPT_CHARS)
    session._max_output_chars = 4000 if developmental else MAX_OUTPUT_CHARS
    session._max_new_tokens = 512 if developmental else MAX_NEW_TOKENS
    session._max_timeout_seconds = 120
    session._max_calls = ROOTLESS_DEVELOPMENTAL_MAX_CALLS if developmental else 4
    session.session_binding = {"purpose": "test"}
    session.invoker = _Invoker()
    return session


def _kwargs(purpose, correlation, *, input_chars=128, output_chars=256,
        tokens=16, timeout=10):
    return {
        "purpose": purpose,
        "prompt": "p" * input_chars,
        "caller": "rootless-test-controller",
        "correlation_id": correlation,
        "budget": SimpleNamespace(max_input_chars=input_chars,
            max_output_chars=output_chars, max_new_tokens=tokens,
            timeout_seconds=timeout, max_calls_per_correlation=1),
        "linkage": {"source": "test"},
    }



def test_existing_companion_invoker_is_bound_to_rootless_receipt_custody(
        tmp_path, monkeypatch):
    from sentientos.local_runtime_provisioning import semantic_digest
    from sentientos.local_model import ActiveModelIdentity
    import sentientos.rootless_experimental_ollama_epistemic_session as module

    workspace = tmp_path / "workspace"
    experiment_root = workspace / "sentientos-data" / "rootless-experimental"
    session_root = experiment_root / "live-companion-sessions" / "rootless-cognition-cycle-test"
    runtime_root = session_root / "inference-custody"
    runtime_root.mkdir(parents=True)
    model_digest = "a" * 64
    identity = ActiveModelIdentity(
        engine="ollama", resolved_artifact_path=None,
        semantic_artifact_identity="sha256:" + model_digest,
        model_content_sha256=model_digest, artifact_size_bytes=1,
        sidecar_metadata_digest=None, configuration_digest="c" * 64,
        candidate_index=0, posture="development_only", fallback=False)
    identity_payload = identity.to_dict()
    model = SimpleNamespace(active_identity=identity)
    purpose = ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_INVOCATION_PURPOSES[1]

    class Authority:
        def record_for_active_identity(self, active_identity, requested):
            return object() if active_identity is identity and requested == purpose else None

    invoker = _Invoker()
    invoker.model = model
    invoker.authority_map = Authority()
    invoker.runtime_root = runtime_root
    runtime_bundle = {"backend": "ollama-loopback", "version": "test",
        "model_manifest_digest": model_digest,
        "runtime_attestation": "local_observation_only"}
    preregistration = {
        "schema_version": "sentientos.live_companion_developmental_preregistration:v1",
        "session_id": "rootless-cognition-session-test",
        "run_id": "rootless-cognition-cycle-test",
        "model_identity_digest": semantic_digest({"identity": identity_payload}),
        "runtime_bundle_digest": semantic_digest(runtime_bundle),
    }
    binding = {
        "schema_version": "sentientos.rootless_experimental_cognition_session:v1",
        "session_id": preregistration["session_id"],
        "run_id": preregistration["run_id"],
        "preregistration_digest": semantic_digest(preregistration),
        "model_manifest_digest": model_digest,
        "runtime_bundle_digest": semantic_digest(runtime_bundle),
        "active_model_identity_digest": semantic_digest({"identity": identity_payload}),
        "purpose": "rootless_experimental_developmental_cognition_cycle",
        "production_authority": False,
        "eligible_as_production_serving_evidence": False,
    }
    session = RootlessExperimentalOllamaEpistemicSession.wrap_existing_developmental_invoker(
        invoker=invoker, root=session_root, workspace_root=workspace,
        session_binding=binding, runtime_bundle=runtime_bundle,
        preregistration=preregistration)
    with pytest.raises(RootlessExperimentalError,
            match="epistemic_session_evidence_binding_mismatch"):
        RootlessExperimentalOllamaEpistemicSession.wrap_existing_developmental_invoker(
            invoker=invoker, root=session_root, workspace_root=workspace,
            session_binding=binding, runtime_bundle=runtime_bundle,
            preregistration={**preregistration, "run_id": "different-run"})
    kwargs = _kwargs(purpose, "bounded-call")
    request = session.build_request(**kwargs)
    assert request.linkage["rootless_experimental_session"] == binding
    assert session.invoke(request)[0] is request
    assert session.model is model
    session.model = model
    assert invoker.model is model
    with pytest.raises(RootlessExperimentalError,
            match="ollama_experimental_session_model_switch_out_of_scope"):
        session.model = SimpleNamespace(active_identity=SimpleNamespace(
            to_dict=lambda: {**identity_payload, "model_content_sha256": "0" * 64}))

    receipt_id = "lmrec-" + "c" * 24
    receipt_digest = "d" * 64
    receipt = {"receipt_id": receipt_id, "receipt_digest": receipt_digest,
        "status": "admitted_completed", "output_digest": "e" * 64,
        "request": {"request_id": "request-1", "request_digest": "f" * 64,
            "purpose": purpose, "active_model_identity": identity_payload,
            "linkage": {"rootless_experimental_session": binding}}}
    monkeypatch.setattr(module, "_read_json", lambda *args, **kwargs: receipt)
    monkeypatch.setattr(module, "validate_receipt", lambda value: (True, ()))
    verified = session.verify_persisted_invocation_receipt(
        receipt_id, receipt_digest, expected_request_id="request-1",
        expected_request_digest="f" * 64,
        expected_active_model_identity=identity_payload)
    assert verified is receipt

    from sentientos.resident_developmental_cognition import (
        ResidentDevelopmentalCognitionOwner,
    )
    owner = object.__new__(ResidentDevelopmentalCognitionOwner)
    owner.invoker = session
    observation = {
        "active_model_identity": identity_payload,
        "request_id": "request-1",
        "request_digest": "f" * 64,
        "inference_receipt_id": receipt_id,
        "inference_receipt_digest": receipt_digest,
        "output_digest": "e" * 64,
    }
    assert owner._verify_observation_invocation(observation) is receipt

    with pytest.raises(RootlessExperimentalError,
            match="ollama_experimental_session_request_out_of_scope"):
        session.build_request(**_kwargs("local_user_chat", "out-of-scope"))
    forged = {**receipt, "request": {**receipt["request"],
        "linkage": {"rootless_experimental_session": {**binding,
            "session_id": "rootless-cognition-session-other"}}}}
    monkeypatch.setattr(module, "_read_json", lambda *args, **kwargs: forged)
    with pytest.raises(RootlessExperimentalError,
            match="developmental_receipt_verification_failed"):
        session.verify_persisted_invocation_receipt(
            receipt_id, receipt_digest, expected_request_id="request-1",
            expected_request_digest="f" * 64)

def test_ollama_epistemic_profile_accepts_only_epistemic_authority():
    session = _session(developmental=False)
    request = session.build_request(**_kwargs(
        ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE, "epistemic-call"))
    assert request.purpose == ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE
    assert request.linkage["rootless_experimental_session"] == session.session_binding
    result = session.invoke(request)
    assert result[0] is request
    rejected = session.build_request(**_kwargs(
        ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE, "wrong-invoke"))
    rejected.purpose = ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_INVOCATION_PURPOSES[0]
    with pytest.raises(RootlessExperimentalError,
            match="ollama_experimental_session_invocation_out_of_scope"):
        session.invoke(rejected)
    with pytest.raises(RootlessExperimentalError,
            match="ollama_experimental_session_request_out_of_scope"):
        session.build_request(**_kwargs(
            ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_INVOCATION_PURPOSES[0],
            "wrong-profile"))


def test_ollama_developmental_profile_retains_developmental_authority():
    session = _session(developmental=True)
    purpose = ROOTLESS_EXPERIMENTAL_DEVELOPMENTAL_INVOCATION_PURPOSES[0]
    request = session.build_request(**_kwargs(purpose, "developmental-call",
        input_chars=ROOTLESS_DEVELOPMENTAL_MAX_INPUT_CHARS,
        output_chars=4000, tokens=512, timeout=120))
    session._correlations.clear()
    request.correlation_id = "invoke-call"
    request.linkage = {"rootless_experimental_session": session.session_binding}
    result = session.invoke(request)
    assert result[0] is request
    assert session._max_calls == ROOTLESS_DEVELOPMENTAL_MAX_CALLS


def test_ollama_epistemic_profile_enforces_epistemic_resource_envelope():
    session = _session(developmental=False)
    with pytest.raises(RootlessExperimentalError,
            match="ollama_experimental_session_request_out_of_scope"):
        session.build_request(**_kwargs(ROOTLESS_EXPERIMENTAL_EPISTEMIC_PURPOSE,
            "over-limit", input_chars=MAX_PROMPT_CHARS + 1))

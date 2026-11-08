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

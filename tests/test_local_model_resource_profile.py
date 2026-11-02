from __future__ import annotations

import pytest

from sentientos.local_model_resource_profile import (
    LLAMA_CPP_RESOURCE_PROFILE_SCHEMA,
    LocalModelResourceProfileError,
    llama_cpp_constructor_options,
    llama_cpp_resource_profile_digest,
    validate_llama_cpp_resource_profile,
)

pytestmark = pytest.mark.no_legacy_skip


def profile() -> dict[str, object]:
    return {
        "schema_version": LLAMA_CPP_RESOURCE_PROFILE_SCHEMA,
        "profile_id": "cpu-gaming-v1",
        "n_ctx": 512,
        "n_gpu_layers": 0,
        "n_threads": 4,
        "n_threads_batch": 2,
        "n_batch": 128,
        "n_ubatch": 64,
    }


def test_profile_maps_load_parameters_without_runtime_effects() -> None:
    validated = validate_llama_cpp_resource_profile(profile())

    assert llama_cpp_constructor_options(validated) == {
        "n_ctx": 512,
        "n_gpu_layers": 0,
        "n_threads": 4,
        "n_threads_batch": 2,
        "n_batch": 128,
        "n_ubatch": 64,
    }
    assert llama_cpp_resource_profile_digest(validated) == llama_cpp_resource_profile_digest(profile())


@pytest.mark.parametrize(("field", "value", "reason"), [
    ("n_ctx", True, "field_invalid:n_ctx"),
    ("n_threads_batch", 257, "field_invalid:n_threads_batch"),
    ("n_batch", 4096, "field_invalid:n_batch"),
    ("n_ubatch", 129, "microbatch_exceeds_batch"),
    ("profile_id", "../unsafe", "identity_invalid"),
])
def test_profile_rejects_invalid_or_unbounded_load_configuration(field: str,
        value: object, reason: str) -> None:
    invalid = profile()
    invalid[field] = value

    with pytest.raises(LocalModelResourceProfileError, match=reason):
        validate_llama_cpp_resource_profile(invalid)


def test_profile_rejects_open_schema_fields() -> None:
    invalid = {**profile(), "fan_control": True}

    with pytest.raises(LocalModelResourceProfileError, match="shape_invalid"):
        validate_llama_cpp_resource_profile(invalid)

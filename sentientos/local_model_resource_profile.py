"""Closed, versioned llama.cpp construction profiles.

Profiles describe model-load-time resource settings. Applying a profile requires
the ordinary commissioning and activation path; this module never loads a
model or changes a running worker.
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping


LLAMA_CPP_RESOURCE_PROFILE_SCHEMA = "sentientos.llama_cpp_resource_profile:v1"
_PROFILE_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}\Z")
_PROFILE_FIELDS = frozenset({
    "schema_version", "profile_id", "n_ctx", "n_gpu_layers", "n_threads",
    "n_threads_batch", "n_batch", "n_ubatch",
})
_LIMITS = {
    "n_ctx": (64, 131072),
    "n_gpu_layers": (0, 256),
    "n_threads": (0, 256),
    "n_threads_batch": (0, 256),
    "n_batch": (1, 2048),
    "n_ubatch": (1, 2048),
}


class LocalModelResourceProfileError(ValueError):
    """A profile is malformed or outside the supported resource bounds."""


def validate_llama_cpp_resource_profile(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a canonical copy of a bounded construction profile."""
    if not isinstance(value, Mapping) or set(value) != _PROFILE_FIELDS:
        raise LocalModelResourceProfileError("resource_profile_shape_invalid")
    if (value.get("schema_version") != LLAMA_CPP_RESOURCE_PROFILE_SCHEMA
            or not isinstance(value.get("profile_id"), str)
            or _PROFILE_ID.fullmatch(str(value.get("profile_id"))) is None):
        raise LocalModelResourceProfileError("resource_profile_identity_invalid")
    result: dict[str, Any] = {
        "schema_version": LLAMA_CPP_RESOURCE_PROFILE_SCHEMA,
        "profile_id": value["profile_id"],
    }
    for name, (minimum, maximum) in _LIMITS.items():
        number = value.get(name)
        if type(number) is not int or not minimum <= number <= maximum:
            raise LocalModelResourceProfileError("resource_profile_field_invalid:" + name)
        result[name] = number
    if result["n_ubatch"] > result["n_batch"]:
        raise LocalModelResourceProfileError("resource_profile_microbatch_exceeds_batch")
    return result


def llama_cpp_constructor_options(profile: Mapping[str, Any]) -> dict[str, int]:
    """Map a validated profile to llama.cpp model-construction keyword args."""
    value = validate_llama_cpp_resource_profile(profile)
    options = {
        "n_ctx": value["n_ctx"],
        "n_gpu_layers": value["n_gpu_layers"],
        "n_batch": value["n_batch"],
        "n_ubatch": value["n_ubatch"],
    }
    if value["n_threads"]:
        options["n_threads"] = value["n_threads"]
    if value["n_threads_batch"]:
        options["n_threads_batch"] = value["n_threads_batch"]
    return options


def llama_cpp_resource_profile_digest(profile: Mapping[str, Any]) -> str:
    value = validate_llama_cpp_resource_profile(profile)
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

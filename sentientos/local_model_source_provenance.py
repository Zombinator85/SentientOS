"""Pure syntax checks shared by curator and portable local-model metadata."""
from __future__ import annotations

import re

_IMMUTABLE_REVISION = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
_SOURCE_REPOSITORY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")


def is_immutable_source_revision(value: object) -> bool:
    return isinstance(value, str) and _IMMUTABLE_REVISION.fullmatch(value) is not None


def is_canonical_source_repository(value: object) -> bool:
    return isinstance(value, str) and value == value.strip() and _SOURCE_REPOSITORY.fullmatch(value) is not None


def is_canonical_source_artifact_filename(value: object) -> bool:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/"):
        return False
    components = value.split("/")
    return all(component not in {"", ".", ".."} for component in components) and value.lower().endswith(".gguf")

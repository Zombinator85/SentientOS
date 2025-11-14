"""Semantic validation for Cathedral amendments."""

from __future__ import annotations

from typing import Any, Iterable, List, Mapping

from .amendment import Amendment

__all__ = ["validate_amendment"]


def _is_structured_mapping(value: Any) -> bool:
    return isinstance(value, Mapping)


def _contains_raw_code(changes: Mapping[str, Any]) -> bool:
    raw_keys = {"raw_code", "code_blob", "diff_text"}
    for key, value in changes.items():
        if key in raw_keys and isinstance(value, str):
            return True
        if isinstance(value, Mapping) and _contains_raw_code(value):
            return True
        if isinstance(value, list):
            if any(isinstance(item, str) and item.strip().startswith("def ") for item in value):
                return True
    return False


def _validate_change_grammar(changes: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    allowed_roots = {"config", "registry", "persona", "world", "experiments"}
    for root, payload in changes.items():
        if root not in allowed_roots:
            errors.append(f"Unsupported change domain: {root}")
            continue
        if root == "config":
            _validate_config_domain(payload, errors)
        elif root == "persona":
            _validate_persona_domain(payload, errors)
        elif root == "world":
            _validate_world_domain(payload, errors)
        elif root == "registry":
            _validate_collection_domain(payload, errors, root, {"adapters", "demos", "personas"})
        elif root == "experiments":
            _validate_collection_domain(payload, errors, root, {"adapters", "demos"})
    return errors


def _validate_config_domain(payload: Any, errors: List[str]) -> None:
    if not isinstance(payload, Mapping):
        errors.append("config changes must be a mapping")
        return
    for section, updates in payload.items():
        if not isinstance(section, str):
            errors.append("config section keys must be strings")
            continue
        if not isinstance(updates, Mapping):
            errors.append(f"config.{section} must be a mapping of updates")
            continue
        _validate_no_forbidden(updates, f"config.{section}", errors)


def _validate_persona_domain(payload: Any, errors: List[str]) -> None:
    allowed_keys = {"tone", "tick_interval_seconds", "heartbeat_interval_seconds", "max_message_length"}
    if not isinstance(payload, Mapping):
        errors.append("persona changes must be a mapping")
        return
    for key, value in payload.items():
        if key not in allowed_keys:
            errors.append(f"persona.{key} is not an allowed field")
            continue
        _validate_no_forbidden(value, f"persona.{key}", errors)


def _validate_world_domain(payload: Any, errors: List[str]) -> None:
    allowed_keys = {"enabled", "poll_interval_seconds", "idle_pulse_interval_seconds", "sources"}
    if not isinstance(payload, Mapping):
        errors.append("world changes must be a mapping")
        return
    for key, value in payload.items():
        if key not in allowed_keys:
            errors.append(f"world.{key} is not an allowed field")
            continue
        if key == "sources":
            if not isinstance(value, Mapping):
                errors.append("world.sources must be a mapping")
                continue
            for source_key, enabled in value.items():
                if not isinstance(source_key, str):
                    errors.append("world.sources keys must be strings")
                    continue
                if not isinstance(enabled, bool):
                    errors.append(f"world.sources.{source_key} must be boolean")
        else:
            _validate_no_forbidden(value, f"world.{key}", errors)


def _validate_collection_domain(payload: Any, errors: List[str], domain: str, categories: Iterable[str]) -> None:
    if not isinstance(payload, Mapping):
        errors.append(f"{domain} changes must be a mapping")
        return
    for category, operations in payload.items():
        if category not in categories:
            errors.append(f"{domain}.{category} is not supported")
            continue
        if not isinstance(operations, Mapping):
            errors.append(f"{domain}.{category} must be a mapping of operations")
            continue
        for op, value in operations.items():
            if op not in {"add", "remove", "update"}:
                errors.append(f"{domain}.{category}.{op} operation is not supported")
                continue
            if op in {"add", "remove"}:
                if not isinstance(value, Iterable) or isinstance(value, (str, bytes, Mapping)):
                    errors.append(f"{domain}.{category}.{op} must be a list of strings")
                    continue
                for item in value:
                    if not isinstance(item, str):
                        errors.append(f"{domain}.{category}.{op} entries must be strings")
            else:
                if not isinstance(value, Mapping):
                    errors.append(f"{domain}.{category}.update must be a mapping")
                    continue
                for name, metadata in value.items():
                    if not isinstance(name, str):
                        errors.append(f"{domain}.{category}.update keys must be strings")
                        continue
                    _validate_no_forbidden(metadata, f"{domain}.{category}.update.{name}", errors)


def _validate_no_forbidden(value: Any, path: str, errors: List[str]) -> None:
    forbidden_tokens = ("import ", "exec(", "eval(", "rm -", "subprocess", "os.system", "powershell", ".py")
    if isinstance(value, Mapping):
        for key, inner in value.items():
            if not isinstance(key, str):
                errors.append(f"{path} keys must be strings")
                continue
            _validate_no_forbidden(inner, f"{path}.{key}", errors)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _validate_no_forbidden(item, f"{path}[{index}]", errors)
    elif isinstance(value, str):
        lowered = value.lower()
        for token in forbidden_tokens:
            if token in lowered:
                errors.append(f"Forbidden content detected in {path}")
                break


def validate_amendment(amendment: Amendment) -> List[str]:
    """Run structural and semantic validation rules."""

    errors: List[str] = []
    payload = amendment.to_dict()

    for key in ("summary", "reason"):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"Missing required field: {key}")

    changes = payload.get("changes")
    if not _is_structured_mapping(changes):
        errors.append("Changes must be a structured mapping")
        return errors

    if _contains_raw_code(changes):
        errors.append("Raw code blobs are not permitted in changes")

    errors.extend(_validate_change_grammar(changes))

    touches_experiments = bool(changes.get("experiments"))
    touches_world = bool(changes.get("world"))
    if (touches_experiments or touches_world) and len(amendment.reason.strip()) < 10:
        errors.append("Experiment or world changes require a detailed rationale")

    metadata = payload.get("metadata")
    if metadata and not _is_structured_mapping(metadata):
        errors.append("Metadata, when provided, must be a mapping")

    return errors

from __future__ import annotations

from typing import Dict, Mapping, TypeGuard

from .base import AdapterActionSpec, AdapterMetadata, ExternalAdapterFactory


_ADAPTERS: Dict[str, ExternalAdapterFactory] = {}


def register_adapter(adapter_id: str, adapter_cls: object) -> None:
    if not _is_adapter_factory(adapter_cls):
        raise TypeError("adapter_factory_contract_invalid")
    if adapter_cls.metadata.adapter_id != adapter_id:
        raise ValueError("adapter_factory_id_mismatch")
    _ADAPTERS[adapter_id] = adapter_cls


def _is_adapter_factory(value: object) -> TypeGuard[ExternalAdapterFactory]:
    metadata = getattr(value, "metadata", None)
    action_specs = getattr(value, "action_specs", None)
    methods = ("probe", "describe", "execute", "rollback")
    return (
        callable(value)
        and isinstance(metadata, AdapterMetadata)
        and isinstance(action_specs, Mapping)
        and all(isinstance(spec, AdapterActionSpec) for spec in action_specs.values())
        and all(callable(getattr(value, name, None)) for name in methods)
    )


def get_adapter(adapter_id: str) -> ExternalAdapterFactory:
    try:
        return _ADAPTERS[adapter_id]
    except KeyError as exc:
        available = ", ".join(sorted(_ADAPTERS))
        raise KeyError(f"unknown adapter '{adapter_id}'. Available adapters: {available}") from exc


def list_adapters() -> Mapping[str, ExternalAdapterFactory]:
    return dict(_ADAPTERS)


__all__ = ["get_adapter", "list_adapters", "register_adapter"]

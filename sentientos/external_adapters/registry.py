from __future__ import annotations

from typing import Dict, Mapping

from .base import ExternalAdapterFactory


_ADAPTERS: Dict[str, ExternalAdapterFactory] = {}


def register_adapter(adapter_id: str, adapter_cls: ExternalAdapterFactory) -> None:
    _ADAPTERS[adapter_id] = adapter_cls


def get_adapter(adapter_id: str) -> ExternalAdapterFactory:
    try:
        return _ADAPTERS[adapter_id]
    except KeyError as exc:
        available = ", ".join(sorted(_ADAPTERS))
        raise KeyError(f"unknown adapter '{adapter_id}'. Available adapters: {available}") from exc


def list_adapters() -> Mapping[str, ExternalAdapterFactory]:
    return dict(_ADAPTERS)


__all__ = ["get_adapter", "list_adapters", "register_adapter"]

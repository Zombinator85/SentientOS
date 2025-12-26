from __future__ import annotations

from typing import Dict, Mapping, Type

from .base import ExternalAdapter


_ADAPTERS: Dict[str, Type[ExternalAdapter]] = {}


def register_adapter(adapter_id: str, adapter_cls: Type[ExternalAdapter]) -> None:
    _ADAPTERS[adapter_id] = adapter_cls


def get_adapter(adapter_id: str) -> Type[ExternalAdapter]:
    try:
        return _ADAPTERS[adapter_id]
    except KeyError as exc:
        available = ", ".join(sorted(_ADAPTERS))
        raise KeyError(f"unknown adapter '{adapter_id}'. Available adapters: {available}") from exc


def list_adapters() -> Mapping[str, Type[ExternalAdapter]]:
    return dict(_ADAPTERS)


__all__ = ["get_adapter", "list_adapters", "register_adapter"]

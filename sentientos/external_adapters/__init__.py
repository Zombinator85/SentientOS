from __future__ import annotations

from .base import AdapterMetadata, ExecutionContext, ExternalAdapter
from .filesystem_adapter import FilesystemAdapter
from .registry import get_adapter, list_adapters, register_adapter
from .runtime import AdapterExecutionContext, AdapterExecutionError, execute_adapter_action, rollback_adapter_action

register_adapter(FilesystemAdapter.metadata.adapter_id, FilesystemAdapter)

__all__ = [
    "AdapterExecutionContext",
    "AdapterExecutionError",
    "AdapterMetadata",
    "ExecutionContext",
    "ExternalAdapter",
    "FilesystemAdapter",
    "execute_adapter_action",
    "get_adapter",
    "list_adapters",
    "register_adapter",
    "rollback_adapter_action",
]

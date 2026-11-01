from __future__ import annotations

import pytest

pytestmark = pytest.mark.no_legacy_skip

from sentientos.external_adapters import AdapterExecutionError, FilesystemAdapter, get_adapter


def test_filesystem_adapter_is_registered_and_scoped(tmp_path) -> None:
    adapter_type = get_adapter("filesystem")
    adapter = adapter_type(base_path=tmp_path)

    assert adapter_type is FilesystemAdapter
    assert adapter.describe().adapter_id == "filesystem"
    with pytest.raises(AdapterExecutionError, match="escapes adapter scope"):
        adapter._resolve_path({"path": "../outside.txt"})

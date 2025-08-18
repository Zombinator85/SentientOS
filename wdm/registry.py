"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from typing import Dict

class Endpoint:
    def __init__(self, id: str, adapter_name: str, enabled: bool = True):
        self.id = id
        self.adapter_name = adapter_name
        self.enabled = enabled

class Registry:
    def __init__(self) -> None:
        self._eps: Dict[str, Endpoint] = {}

    def load(self, cfg: dict) -> None:
        for e in cfg.get("allowlist", []):
            self._eps[e["id"]] = Endpoint(e["id"], e["adapter"], e.get("enabled", True))

    def get_enabled(self) -> Dict[str, Endpoint]:
        return {k: v for k, v in self._eps.items() if v.enabled}

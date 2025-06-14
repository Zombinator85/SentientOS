"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Utility class for reordering model chains."""

from typing import List


class ModelSelector:
    """Maintain an ordered list of models."""

    def __init__(self, models: List[str]) -> None:
        self.models = list(models)

    def move(self, src: int, dest: int) -> None:
        """Move item at ``src`` to ``dest``."""
        if src < 0 or src >= len(self.models):
            return
        dest = max(0, min(dest, len(self.models) - 1))
        item = self.models.pop(src)
        self.models.insert(dest, item)

    def get_models(self) -> List[str]:
        """Return the ordered model list."""
        return list(self.models)

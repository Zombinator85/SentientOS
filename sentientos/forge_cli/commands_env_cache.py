from __future__ import annotations

from sentientos.forge_env_cache import list_cache_entries, prune_cache

from .context import ForgeContext
from .types import print_json


def handle_list(context: ForgeContext) -> int:
    entries = list_cache_entries(context.forge.repo_root)
    print_json(
        {
            "command": "env-cache",
            "entries": [
                {
                    "venv_path": item.venv_path,
                    "last_used_at": item.last_used_at,
                    "created_at": item.created_at,
                    "extras_tag": item.key.extras_tag,
                    "python_version": item.key.python_version,
                }
                for item in entries
            ],
        }
    )
    return 0


def handle_prune(context: ForgeContext) -> int:
    removed = prune_cache(context.forge.repo_root)
    print_json({"command": "env-cache-prune", "removed": removed, "removed_count": len(removed)})
    return 0

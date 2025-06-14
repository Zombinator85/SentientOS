"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Experimental presence analytics logger."""

import datetime
import json
import os
from typing import Any, Dict

from logging_config import get_log_path
import presence_analytics as pa
import experimental_flags as ex

LOG_PATH = get_log_path("presence_analytics.jsonl", "PRESENCE_ANALYTICS_LOG")


def run(limit: int | None = None) -> Dict[str, Any]:
    """Run analytics and log results when enabled."""
    if not ex.enabled("presence_analytics"):
        return {"disabled": True}
    data = pa.analytics(limit)
    entry = {"timestamp": datetime.datetime.utcnow().isoformat(), "data": data}
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return data

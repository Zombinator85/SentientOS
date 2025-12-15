from __future__ import annotations

import os

SENTIENTOS_MODE = os.getenv("SENTIENTOS_MODE", "DEFAULT")
IS_LOCAL_OWNER = SENTIENTOS_MODE == "LOCAL_OWNER"

if IS_LOCAL_OWNER:
    print("SentientOS running in LOCAL_OWNER mode (semantic constraints disabled)")

__all__ = ["SENTIENTOS_MODE", "IS_LOCAL_OWNER"]

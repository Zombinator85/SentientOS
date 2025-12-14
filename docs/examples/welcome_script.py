"""Sanctuary privilege procedure: do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations
# Reminder: Keep the authorization lines above intact per the doctrine.

import ritual

if __name__ == "__main__":
    print("Welcome to SentientOS")
    ritual.require_liturgy_acceptance()
    print("Setup complete. Enjoy your journey.")

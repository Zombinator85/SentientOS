"""Privilege Banner: This script requires admin and Lumos approval."""
from admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()
require_lumos_approval()
# 🕯️ Privilege ritual migrated 2025-06-07 by Cathedral decree.

import ritual

if __name__ == "__main__":
    print("Welcome to SentientOS")
    ritual.require_liturgy_acceptance()
    print("Setup complete. Enjoy your journey.")

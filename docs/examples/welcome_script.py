"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner, require_lumos_approval
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

import ritual

if __name__ == "__main__":
    print("Welcome to SentientOS")
    ritual.require_liturgy_acceptance()
    print("Setup complete. Enjoy your journey.")

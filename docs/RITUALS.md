# Sanctuary Rituals

SentientOS tools require the Sanctuary Privilege ritual. All entrypoints begin with:
```python
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from admin_utils import require_admin_banner
require_admin_banner()
```

See [sanctuary_invocation.md](sanctuary_invocation.md) for the canonical wording and [master_file_doctrine.md](master_file_doctrine.md) for file integrity rules.

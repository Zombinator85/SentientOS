# Contributing to SentientOS

All new scripts and entrypoints **must** invoke `admin_utils.require_admin_banner()` as the very first action. This banner enforces the Sanctuary Privilege Ritual and logs each attempt.

Add the following at the top of your `main()` or `if __name__ == '__main__'` block:

```python
from admin_utils import require_admin_banner

require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
```

Pull requests lacking this call will fail CI and be rejected.

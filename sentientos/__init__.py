"""SentientOS core package."""
# Expose privilege helpers for static analyzers
from sentientos.privilege import require_admin_banner, require_lumos_approval  # noqa: F401

__version__: str = "0.1.1"

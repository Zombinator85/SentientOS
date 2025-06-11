"""Privilege hooks — enforced by Sanctuary Doctrine."""


def require_admin_banner() -> None:
    import admin_utils
    admin_utils.require_admin_banner()


def require_lumos_approval() -> None:
    import admin_utils
    admin_utils.require_lumos_approval()

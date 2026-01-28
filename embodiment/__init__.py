"""Embodiment silhouette artifacts."""

from typing import Any

__all__ = [
    "compute_daily_silhouette",
    "write_daily_silhouette",
    "load_recent_silhouettes",
    "load_silhouette",
]


def __getattr__(name: str) -> Any:
    if name in {"compute_daily_silhouette", "write_daily_silhouette"}:
        from .silhouette import compute_daily_silhouette, write_daily_silhouette

        globals()["compute_daily_silhouette"] = compute_daily_silhouette
        globals()["write_daily_silhouette"] = write_daily_silhouette
    elif name in {"load_recent_silhouettes", "load_silhouette"}:
        from .silhouette_store import load_recent_silhouettes, load_silhouette

        globals()["load_recent_silhouettes"] = load_recent_silhouettes
        globals()["load_silhouette"] = load_silhouette
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return globals()[name]

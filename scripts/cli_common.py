from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Callable


def ensure_repo_on_path(script_path: str) -> Path:
    repo_root = Path(script_path).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))
    return repo_root


def resolve_repo_root(repo_root: str | None) -> Path:
    if repo_root is None:
        return Path.cwd().resolve()
    return Path(repo_root).resolve()


def emit_payload(payload: dict[str, object], *, as_json: bool, text_renderer: Callable[[dict[str, object]], str]) -> None:
    if as_json:
        from sentientos.attestation import canonical_json_bytes

        print(canonical_json_bytes(payload).decode("utf-8"), end="")
        return
    print(text_renderer(payload))


def exit_code(payload: dict[str, object], *, default: int = 3) -> int:
    value: Any = payload.get("exit_code", default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

from __future__ import annotations

import inspect
from contextlib import contextmanager
from typing import Iterable, Iterator


class CodexStartupViolation(RuntimeError):
    """Raised when startup-only Codex governance entrypoints are used at runtime."""

    def __init__(self, symbol: str) -> None:
        super().__init__(
            (
                f"{symbol} is restricted to Codex startup orchestration; "
                "wrap construction in codex_startup_phase() or run during bootstrap."
            )
        )


_STARTUP_ACTIVE = False
_PROVENANCE_ALLOWLIST: dict[str, tuple[str, ...]] = {
    # Explicit bootstrap call sites permitted to instantiate governance entrypoints.
    # Keep this list minimal and auditable; include test namespace so fixtures remain valid.
    "CodexHealer": (
        "sentientos.codex_healer",
        "tests.",
    ),
    "GenesisForge": (
        "sentientos.genesis_forge",
        "tests.",
    ),
    "IntegrityDaemon": (
        "codex.amendments",
        "codex.integrity_daemon",
        "sentientos.genesis_forge",
        "tests.",
    ),
    "SpecAmender": (
        "codex.amendments",
        "tests.",
    ),
}


class CodexProvenanceViolation(RuntimeError):
    """Raised when a startup-only governance entrypoint is invoked by an unapproved caller."""

    def __init__(self, symbol: str, caller: str | None, allowed: Iterable[str]) -> None:
        allowed_modules = ", ".join(sorted(set(allowed)))
        caller_label = caller or "<unknown>"
        super().__init__(
            (
                f"{symbol} may only be constructed by approved Codex bootstrap modules "
                f"({allowed_modules}); observed caller: {caller_label}"
            )
        )


def enforce_codex_startup(symbol: str) -> None:
    """Abort startup-only entrypoint construction when bootstrap is not active."""

    if not _STARTUP_ACTIVE:
        raise CodexStartupViolation(symbol)
    _enforce_codex_provenance(symbol)


@contextmanager
def codex_startup_phase() -> Iterator[None]:
    """Temporarily allow Codex startup-only governance entrypoints to be constructed."""

    global _STARTUP_ACTIVE
    previous = _STARTUP_ACTIVE
    _STARTUP_ACTIVE = True
    try:
        yield
    finally:
        _STARTUP_ACTIVE = previous


def _enforce_codex_provenance(symbol: str) -> None:
    allowed_callers = _PROVENANCE_ALLOWLIST.get(symbol)
    if not allowed_callers:
        return

    caller_module = _resolve_invoker_module()
    if caller_module is None or not _is_allowed_caller(caller_module, allowed_callers):
        raise CodexProvenanceViolation(symbol, caller_module, allowed_callers)


def _resolve_invoker_module() -> str | None:
    """Return the first module outside the governance entrypoint's own module."""

    frame = inspect.currentframe()
    try:
        skip_modules = {__name__}
        caller_module: str | None = None
        while frame:
            module_name = frame.f_globals.get("__name__")
            if module_name and not module_name.startswith("importlib."):
                if module_name in skip_modules:
                    frame = frame.f_back
                    continue
                if caller_module is None:
                    caller_module = module_name
                    skip_modules.add(module_name)
                    frame = frame.f_back
                    continue
                if module_name != caller_module:
                    return module_name
            frame = frame.f_back
        return caller_module
    finally:
        del frame


def _is_allowed_caller(caller: str, allowed_callers: Iterable[str]) -> bool:
    for allowed in allowed_callers:
        if allowed.endswith(".") and caller.startswith(allowed):
            return True
        if allowed.endswith(".*") and caller.startswith(allowed[:-2]):
            return True
        if caller == allowed:
            return True
    return False

"""Central registry for optional dependencies and feature gating."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.util
import logging
import sys
from types import ModuleType
from typing import Callable, Literal

MissingBehavior = Literal["disable_feature", "warn_once", "hard_fail"]

LOGGER = logging.getLogger("sentientos.optional_deps")


class OptionalDependencyError(RuntimeError):
    """Raised when an optional dependency is required but missing."""


@dataclass(frozen=True)
class OptionalDependency:
    package: str
    module_name: str
    features: tuple[str, ...]
    import_probe: Callable[[], ModuleType | None]
    install_hint: str
    missing_behavior: MissingBehavior = "disable_feature"


def _probe_module(module_name: str) -> ModuleType | None:
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.find_spec(module_name)
    if spec is None:
        return None
    return importlib.import_module(module_name)


OPTIONAL_DEPENDENCIES: dict[str, OptionalDependency] = {
    "pyyaml": OptionalDependency(
        package="pyyaml",
        module_name="yaml",
        features=(
            "alert_rules",
            "slo_definitions",
            "runtime_config",
            "actuator_whitelist",
            "model_switcher_config",
            "ssa_selector_loader",
        ),
        import_probe=lambda: _probe_module("yaml"),
        install_hint="pip install pyyaml",
        missing_behavior="warn_once",
    ),
    "requests": OptionalDependency(
        package="requests",
        module_name="requests",
        features=("http_requests_client", "health_check", "usage_monitor", "quota_alert", "quota_reporter"),
        import_probe=lambda: _probe_module("requests"),
        install_hint="pip install requests",
        missing_behavior="warn_once",
    ),
    "fastapi": OptionalDependency(
        package="fastapi",
        module_name="fastapi",
        features=("admin_api",),
        import_probe=lambda: _probe_module("fastapi"),
        install_hint="pip install fastapi",
    ),
    "starlette": OptionalDependency(
        package="starlette",
        module_name="starlette",
        features=("asgi_middleware",),
        import_probe=lambda: _probe_module("starlette"),
        install_hint="pip install starlette",
    ),
    "pyttsx3": OptionalDependency(
        package="pyttsx3",
        module_name="pyttsx3",
        features=("voice_tts", "tts_bridge_pyttsx3"),
        import_probe=lambda: _probe_module("pyttsx3"),
        install_hint="pip install pyttsx3",
        missing_behavior="warn_once",
    ),
    "edge-tts": OptionalDependency(
        package="edge-tts",
        module_name="edge_tts",
        features=("tts_bridge_edge",),
        import_probe=lambda: _probe_module("edge_tts"),
        install_hint="pip install edge-tts",
        missing_behavior="warn_once",
    ),
    "playwright": OptionalDependency(
        package="playwright",
        module_name="playwright",
        features=("oracle_playwright",),
        import_probe=lambda: _probe_module("playwright"),
        install_hint="pip install playwright",
        missing_behavior="warn_once",
    ),
    "transformers": OptionalDependency(
        package="transformers",
        module_name="transformers",
        features=("local_model_transformers",),
        import_probe=lambda: _probe_module("transformers"),
        install_hint="pip install transformers",
    ),
    "torch": OptionalDependency(
        package="torch",
        module_name="torch",
        features=("local_model_transformers", "determinism_seed", "local_model_cuda"),
        import_probe=lambda: _probe_module("torch"),
        install_hint="pip install torch",
    ),
    "llama-cpp-python": OptionalDependency(
        package="llama-cpp-python",
        module_name="llama_cpp",
        features=("local_model_llama_cpp",),
        import_probe=lambda: _probe_module("llama_cpp"),
        install_hint="pip install llama-cpp-python",
    ),
    "numpy": OptionalDependency(
        package="numpy",
        module_name="numpy",
        features=("determinism_seed", "webcam_statistics"),
        import_probe=lambda: _probe_module("numpy"),
        install_hint="pip install numpy",
        missing_behavior="warn_once",
    ),
    "pdfrw": OptionalDependency(
        package="pdfrw",
        module_name="pdfrw",
        features=("ssa_pdf_prefill",),
        import_probe=lambda: _probe_module("pdfrw"),
        install_hint="pip install pdfrw",
        missing_behavior="warn_once",
    ),
    "sounddevice": OptionalDependency(
        package="sounddevice",
        module_name="sounddevice",
        features=("asr_sounddevice",),
        import_probe=lambda: _probe_module("sounddevice"),
        install_hint="pip install sounddevice",
    ),
    "pyaudio": OptionalDependency(
        package="pyaudio",
        module_name="pyaudio",
        features=("asr_pyaudio",),
        import_probe=lambda: _probe_module("pyaudio"),
        install_hint="pip install pyaudio",
    ),
    "pywin32": OptionalDependency(
        package="pywin32",
        module_name="win32serviceutil",
        features=("windows_service",),
        import_probe=lambda: _probe_module("win32serviceutil"),
        install_hint="pip install pywin32",
    ),
}

_import_cache: dict[str, ModuleType | None] = {}
_warned_features: set[str] = set()


def reset_optional_dependency_state() -> None:
    _import_cache.clear()
    _warned_features.clear()


def dependency_available(package: str) -> bool:
    return _load_dependency(package, feature=None, warn_missing=False) is not None


def optional_import(package: str, *, feature: str) -> ModuleType | None:
    return _load_dependency(package, feature=feature, warn_missing=True)


def _load_dependency(package: str, *, feature: str | None, warn_missing: bool) -> ModuleType | None:
    entry = OPTIONAL_DEPENDENCIES.get(package)
    if entry is None:
        raise KeyError(f"Optional dependency '{package}' is not registered")
    if package in _import_cache:
        module = _import_cache[package]
    else:
        module = entry.import_probe()
        _import_cache[package] = module
    if module is None and warn_missing:
        _handle_missing(entry, feature)
    return module


def _handle_missing(entry: OptionalDependency, feature: str | None) -> None:
    if entry.missing_behavior == "hard_fail":
        raise OptionalDependencyError(_missing_message(entry, feature))
    if entry.missing_behavior == "warn_once":
        _warn_missing_once(entry, feature)


def _warn_missing_once(entry: OptionalDependency, feature: str | None) -> None:
    feature_name = feature or entry.features[0]
    if feature_name in _warned_features:
        return
    _warned_features.add(feature_name)
    LOGGER.warning(_missing_message(entry, feature_name))


def _missing_message(entry: OptionalDependency, feature: str | None) -> str:
    feature_name = feature or entry.features[0]
    return (
        "Feature '%s' disabled: missing optional dependency '%s'. "
        "Install with: %s"
        % (feature_name, entry.package, entry.install_hint)
    )


def optional_feature_statuses() -> list[dict[str, object]]:
    statuses: list[dict[str, object]] = []
    for entry in sorted(OPTIONAL_DEPENDENCIES.values(), key=lambda item: item.package):
        available = dependency_available(entry.package)
        for feature in entry.features:
            statuses.append(
                {
                    "feature": feature,
                    "dependency": entry.package,
                    "enabled": available,
                    "missing_behavior": entry.missing_behavior,
                    "install_hint": entry.install_hint,
                }
            )
    return sorted(statuses, key=lambda row: (str(row["feature"]), str(row["dependency"])))


def optional_dependency_report() -> dict[str, object]:
    dependencies: list[dict[str, object]] = []
    critical_missing: list[str] = []
    for entry in sorted(OPTIONAL_DEPENDENCIES.values(), key=lambda item: item.package):
        available = dependency_available(entry.package)
        dependencies.append(
            {
                "dependency": entry.package,
                "features": list(entry.features),
                "available": available,
                "missing_behavior": entry.missing_behavior,
                "install_hint": entry.install_hint,
            }
        )
        if entry.missing_behavior == "hard_fail" and not available:
            critical_missing.append(entry.package)
    return {
        "dependencies": dependencies,
        "features": optional_feature_statuses(),
        "core_dependencies_ok": not critical_missing,
        "core_missing": critical_missing,
    }


def optional_dependency_for_module(module_name: str) -> OptionalDependency | None:
    for entry in OPTIONAL_DEPENDENCIES.values():
        if entry.module_name == module_name:
            return entry
    return None


__all__ = [
    "MissingBehavior",
    "OptionalDependency",
    "OptionalDependencyError",
    "OPTIONAL_DEPENDENCIES",
    "dependency_available",
    "optional_dependency_for_module",
    "optional_dependency_report",
    "optional_feature_statuses",
    "optional_import",
    "reset_optional_dependency_state",
]

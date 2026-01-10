import importlib
import inspect
import pkgutil
import sys
from types import ModuleType
from typing import Iterable, Sequence

import pytest

from tests.integrity.test_codex_public_surface import test_codex_public_surface_contract

pytestmark = pytest.mark.always_on_integrity

EXPECTED_FEDERATION_ALL = (
    "NodeId",
    "PeerConfig",
    "FederationConfig",
    "load_federation_config",
    "FederationSummary",
    "build_cathedral_index",
    "build_experiment_index",
    "build_local_summary",
    "summary_to_dict",
    "summary_from_dict",
    "summary_digest",
    "write_local_summary",
    "read_peer_summary",
    "PassiveReplay",
    "ReplayResult",
    "DeltaResult",
    "ReplaySeverity",
    "compute_delta",
    "ENABLEMENT_ENV",
    "is_enabled",
    "DriftReport",
    "DriftLevel",
    "compare_summaries",
    "FederationPoller",
    "FederationState",
    "PeerReplaySnapshot",
    "FederationWindow",
    "build_window",
    "SyncStatus",
    "CathedralSyncView",
    "ExperimentSyncView",
    "PeerSyncView",
    "compute_cathedral_sync",
    "compute_experiment_sync",
    "build_peer_sync_view",
    "FederationDigest",
    "FederationConsensusSentinel",
    "ConcordDaemon",
    "PeerSnapshot",
)

FEDERATION_MODULE_ALLOWLIST = {
    "__main__",
    "concord_daemon",
    "config",
    "consensus_sentinel",
    "delta",
    "dissent_protocol",
    "drift",
    "enablement",
    "federation_digest",
    "handshake_semantics",
    "identity",
    "poller",
    "replay",
    "summary",
    "symbol_ledger_daemon",
    "sync_view",
    "transport",
    "window",
}

FEDERATION_PUBLIC_ALLOWLIST = set(EXPECTED_FEDERATION_ALL) | (
    set(FEDERATION_MODULE_ALLOWLIST) - {"__main__"}
)

CODEX_STARTUP_MODULE_ALLOWLIST = {
    "codex_context_pruner",
    "codex_quiet_mode",
    "retraining_prep",
    "scorekeeper",
    "self_training_daemon",
}

CODEX_STARTUP_PUBLIC_ALLOWLIST = {
    "codex_context_pruner",
    "codex_quiet_mode",
    "CodexContextPruner",
    "CodexHealer",
    "CodexQuietMode",
    "ContextBlock",
    "GenesisForge",
    "IntegrityDaemon",
    "PrunePlan",
    "QuietPlan",
    "SpecAmender",
}

CODEX_STARTUP_MODULES = (
    "sentientos.codex",
    "sentientos.codex_startup_guard",
    "sentientos.codex_healer",
    "sentientos.genesis_forge",
)

EXECUTOR_CORE_MODULES = ("task_executor",)


def _public_names(module: ModuleType) -> set[str]:
    return {name for name in dir(module) if not name.startswith("_")}


def _assert_public_names(module: ModuleType, allowed: Iterable[str], label: str) -> None:
    allowed_set = set(allowed)
    public = _public_names(module)
    extras = sorted(public - allowed_set)
    missing = sorted(allowed_set - public)
    if extras or missing:
        message = [f"{label} public surface drift detected."]
        if extras:
            message.append(f"Unexpected public symbols: {extras}.")
        if missing:
            message.append(f"Missing expected symbols: {missing}.")
        message.append(
            "Remediation: add to the allowlist with justification or remove the public symbol."
        )
        raise AssertionError(" ".join(message))


def _assert_public_names_with_optional(
    module: ModuleType,
    required: Iterable[str],
    optional: Iterable[str],
    label: str,
) -> None:
    required_set = set(required)
    optional_set = set(optional)
    public = _public_names(module)
    extras = sorted(public - required_set - optional_set)
    missing = sorted(required_set - public)
    if extras or missing:
        message = [f"{label} public surface drift detected."]
        if extras:
            message.append(f"Unexpected public symbols: {extras}.")
        if missing:
            message.append(f"Missing expected symbols: {missing}.")
        message.append(
            "Remediation: add to the allowlist with justification or remove the public symbol."
        )
        raise AssertionError(" ".join(message))


def _assert_top_level_modules(package_name: str, allowed_modules: Iterable[str]) -> None:
    package = importlib.import_module(package_name)
    if not hasattr(package, "__path__"):
        raise AssertionError(f"{package_name} is not a package.")
    discovered = {module.name for module in pkgutil.iter_modules(package.__path__)}
    allowed_set = set(allowed_modules)
    extras = sorted(discovered - allowed_set)
    missing = sorted(allowed_set - discovered)
    if extras or missing:
        message = [f"{package_name} module drift detected."]
        if extras:
            message.append(f"Unexpected modules: {extras}.")
        if missing:
            message.append(f"Missing expected modules: {missing}.")
        message.append(
            "Remediation: add to the module allowlist with justification or remove the module."
        )
        raise AssertionError(" ".join(message))


def _detect_forbidden_symbols(
    module: ModuleType,
    forbidden_prefixes: Sequence[str],
    allowed_prefixes: Sequence[str] = (),
) -> list[tuple[str, str]]:
    violations: list[tuple[str, str]] = []
    for name, value in module.__dict__.items():
        if name.startswith("_"):
            continue
        module_name = None
        if inspect.ismodule(value):
            module_name = value.__name__
        else:
            module_name = getattr(value, "__module__", None)
        if not module_name:
            continue
        if any(module_name.startswith(prefix) for prefix in forbidden_prefixes) and not any(
            module_name.startswith(prefix) for prefix in allowed_prefixes
        ):
            violations.append((name, module_name))
    return violations


def _assert_no_forbidden_imports(
    module_name: str,
    forbidden_prefixes: Sequence[str],
    allowed_prefixes: Sequence[str] = (),
) -> None:
    before = set(sys.modules)
    module = importlib.import_module(module_name)
    after = set(sys.modules)
    newly_loaded = sorted(
        name
        for name in after - before
        if any(name.startswith(prefix) for prefix in forbidden_prefixes)
        and not any(name.startswith(prefix) for prefix in allowed_prefixes)
    )
    symbol_violations = _detect_forbidden_symbols(module, forbidden_prefixes, allowed_prefixes)
    if newly_loaded or symbol_violations:
        message = [f"Forbidden import drift detected in {module_name}."]
        if newly_loaded:
            message.append(f"Imported modules: {newly_loaded}.")
        if symbol_violations:
            message.append(f"Referenced symbols: {symbol_violations}.")
        message.append(
            "Remediation: remove the coupling or add an allowlist entry with justification."
        )
        raise AssertionError(" ".join(message))


def _federation_module_names() -> list[str]:
    package = importlib.import_module("sentientos.federation")
    modules = {module.name for module in pkgutil.iter_modules(package.__path__)}
    modules.discard("__main__")
    qualified = [f"sentientos.federation.{name}" for name in sorted(modules)]
    return ["sentientos.federation", *qualified]


def test_codex_public_surface_contract_tripwire() -> None:
    test_codex_public_surface_contract()


def test_federation_public_surface_contract() -> None:
    federation = importlib.import_module("sentientos.federation")
    assert tuple(federation.__all__) == EXPECTED_FEDERATION_ALL
    for symbol in EXPECTED_FEDERATION_ALL:
        assert hasattr(federation, symbol)


def test_executor_exports_no_federation_symbols() -> None:
    executor = importlib.import_module("task_executor")
    violations = _detect_forbidden_symbols(executor, ("sentientos.federation",))
    if violations:
        raise AssertionError(
            "Executor exports federation symbols. "
            f"Symbols: {violations}. "
            "Remediation: remove federation references or add an allowlist entry with justification."
        )


def test_top_level_module_tripwires() -> None:
    _assert_top_level_modules("sentientos.federation", FEDERATION_MODULE_ALLOWLIST)
    _assert_top_level_modules("sentientos.codex", CODEX_STARTUP_MODULE_ALLOWLIST)


def test_minimal_public_symbol_tripwires() -> None:
    codex_startup = importlib.import_module("sentientos.codex")
    federation = importlib.import_module("sentientos.federation")
    _assert_public_names(codex_startup, CODEX_STARTUP_PUBLIC_ALLOWLIST, "sentientos.codex")
    _assert_public_names_with_optional(
        federation,
        EXPECTED_FEDERATION_ALL,
        FEDERATION_MODULE_ALLOWLIST - {"__main__"},
        "sentientos.federation",
    )


def test_forbidden_imports_executor_to_federation() -> None:
    for module in EXECUTOR_CORE_MODULES:
        _assert_no_forbidden_imports(module, ("sentientos.federation",))


def test_forbidden_imports_codex_startup_to_federation() -> None:
    for module in CODEX_STARTUP_MODULES:
        _assert_no_forbidden_imports(module, ("sentientos.federation",))


def test_forbidden_imports_federation_to_executor() -> None:
    for module in _federation_module_names():
        _assert_no_forbidden_imports(module, ("task_executor",))

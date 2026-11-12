"""Compose installed Windows/WSL child-process profiles with signed authority.

This provider builds the existing paired supervisor from operator-installed
process specifications. Every child still passes generation and exact-command
receipt checks inside ``GamingCompanionProcessSupervisor`` before spawn.
"""
from __future__ import annotations

import platform
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Callable

from .gaming_companion_authority import CompanionAuthorityCallbacks
from .gaming_companion_bridge import CompanionBridgeError
from .gaming_companion_deployment import SCHEMA_MUTUAL_TLS_REVERSE, validate_manifest
from .gaming_companion_pair_supervisor import GamingCompanionPairSupervisor
from .gaming_companion_platform_installation import CompanionPlatformInstallation
from .gaming_companion_process_supervisor import (
    CompanionProcessLaunchSpec,
    GamingCompanionProcessSupervisor,
    HealthProbe,
    ProcessSpawner,
    validate_launch_spec,
)
from .gaming_companion_process_profile import load_companion_process_launch_profiles
from .gaming_companion_tls_transport import (
    BridgeGenerationCustodyRecord,
    BridgeGenerationPair,
)

_ROLES = frozenset({"windows_edge", "wsl_core"})
GenerationPairFactory = Callable[[BridgeGenerationPair | None], BridgeGenerationPair]
ForceStopAuthorizer = Callable[[str, int], bool]


class GamingCompanionPlatformPairProcessProvider:
    """Build a Windows-owned pair from signed launch profiles and adapters.

    The configuration contains no credentials. Launch specs must be installed
    by the platform owner; callbacks for generation loading, readiness, and
    forced-stop authority are explicit because this repository cannot infer
    those target-specific policies.
    """

    def __init__(self, *, installation: CompanionPlatformInstallation,
            launch_specs: Mapping[str, CompanionProcessLaunchSpec],
            generation_pair_factories: Mapping[str, GenerationPairFactory],
            health_probes: Mapping[str, HealthProbe],
            force_stop_authorizers: Mapping[str, ForceStopAuthorizer] | None = None,
            max_restarts: int = 3, process_poll_interval_seconds: float = 0.25,
            pair_poll_interval_seconds: float = 0.25,
            spawner: ProcessSpawner = subprocess.Popen,
            system_name: str | None = None) -> None:
        if type(installation) is not CompanionPlatformInstallation:
            raise CompanionBridgeError("companion_platform_installation_required")
        if type(installation.authority) is not CompanionAuthorityCallbacks:
            raise CompanionBridgeError("companion_platform_authority_callbacks_required")
        for name, value in (("launch_specs", launch_specs),
                ("generation_pair_factories", generation_pair_factories),
                ("health_probes", health_probes)):
            if not isinstance(value, Mapping) or set(value) != _ROLES:
                raise CompanionBridgeError("companion_pair_process_" + name + "_required")
        if force_stop_authorizers is None:
            force_stop_authorizers = {}
        if (not isinstance(force_stop_authorizers, Mapping)
                or not set(force_stop_authorizers).issubset(_ROLES)):
            raise CompanionBridgeError("companion_pair_process_force_stop_policy_invalid")
        for role in _ROLES:
            spec = launch_specs[role]
            validate_launch_spec(spec)
            if spec.role != role:
                raise CompanionBridgeError("companion_pair_process_profile_role_mismatch")
            role_flags = [index for index, argument in enumerate(spec.argv)
                          if argument == "--role"]
            manifest_flags = [index for index, argument in enumerate(spec.argv)
                              if argument == "--manifest"]
            if (spec.environment.get("SENTIENTOS_COMPANION_ROLE") != role
                    or len(role_flags) != 1 or role_flags[0] + 1 >= len(spec.argv)
                    or spec.argv[role_flags[0] + 1] != role
                    or len(manifest_flags) != 1 or manifest_flags[0] + 1 >= len(spec.argv)
                    or not spec.argv[manifest_flags[0] + 1]):
                raise CompanionBridgeError("companion_pair_process_profile_role_mismatch")
            if (not callable(generation_pair_factories[role])
                    or not callable(health_probes[role])):
                raise CompanionBridgeError("companion_pair_process_callbacks_required")
        if any(not callable(callback) for callback in force_stop_authorizers.values()):
            raise CompanionBridgeError("companion_pair_process_force_stop_policy_invalid")
        if not callable(spawner):
            raise CompanionBridgeError("companion_pair_process_spawner_required")
        if type(max_restarts) is not int or not 0 <= max_restarts <= 10:
            raise CompanionBridgeError("companion_process_restart_budget_invalid")
        if (isinstance(process_poll_interval_seconds, bool)
                or not isinstance(process_poll_interval_seconds, (int, float))
                or not 0.01 <= process_poll_interval_seconds <= 30):
            raise CompanionBridgeError("companion_process_poll_interval_invalid")
        if (isinstance(pair_poll_interval_seconds, bool)
                or not isinstance(pair_poll_interval_seconds, (int, float))
                or not 0.05 <= pair_poll_interval_seconds <= 10):
            raise CompanionBridgeError("companion_pair_poll_interval_invalid")
        self._installation = installation
        self._specs = dict(launch_specs)
        self._generation_factories = dict(generation_pair_factories)
        self._health_probes = dict(health_probes)
        self._force_stop = dict(force_stop_authorizers)
        self._max_restarts = max_restarts
        self._process_poll = float(process_poll_interval_seconds)
        self._pair_poll = float(pair_poll_interval_seconds)
        self._spawner = spawner
        self._system = system_name or platform.system()

    @classmethod
    def from_process_profile(cls, *, installation: CompanionPlatformInstallation,
            profile_path: Path | str,
            generation_pair_factories: Mapping[str, GenerationPairFactory],
            health_probes: Mapping[str, HealthProbe],
            force_stop_authorizers: Mapping[str, ForceStopAuthorizer] | None = None,
            max_restarts: int = 3, process_poll_interval_seconds: float = 0.25,
            pair_poll_interval_seconds: float = 0.25,
            spawner: ProcessSpawner = subprocess.Popen,
            system_name: str | None = None) -> GamingCompanionPlatformPairProcessProvider:
        """Load installed command profiles and compose a stopped pair owner.

        Reading the profile does not start children or grant launch authority.
        Every process still needs a fresh, verified generation pair and an
        exact-command launch receipt at spawn time.
        """
        resolved_system = system_name or platform.system()
        launch_specs = load_companion_process_launch_profiles(
            profile_path, system_name=resolved_system)
        return cls(installation=installation, launch_specs=launch_specs,
            generation_pair_factories=generation_pair_factories,
            health_probes=health_probes,
            force_stop_authorizers=force_stop_authorizers,
            max_restarts=max_restarts,
            process_poll_interval_seconds=process_poll_interval_seconds,
            pair_poll_interval_seconds=pair_poll_interval_seconds,
            spawner=spawner, system_name=resolved_system)

    def __call__(self, manifest: Mapping[str, object]) -> GamingCompanionPairSupervisor:
        """Return a stopped supervisor pair; no process starts during composition."""
        normalized = self._validate_deployment(manifest)
        roles = {role: self._build_role_supervisor(role, normalized)
                 for role in ("wsl_core", "windows_edge")}
        return GamingCompanionPairSupervisor(core=roles["wsl_core"],
            edge=roles["windows_edge"], poll_interval_seconds=self._pair_poll)

    def windows_edge_supervisor(self, manifest: Mapping[str, object]
            ) -> GamingCompanionProcessSupervisor:
        """Compose only the Windows publisher when WSL core is chat-owned.

        This reuses the exact process, generation, launch-authority, health,
        and recovery owner used by the paired deployment. It does not create
        a second WSL-core listener.
        """
        return self._build_role_supervisor("windows_edge",
            self._validate_deployment(manifest))

    def _validate_deployment(self, manifest: Mapping[str, object]) -> dict[str, object]:
        normalized = validate_manifest(dict(manifest))
        if normalized.get("schema_version") != SCHEMA_MUTUAL_TLS_REVERSE:
            raise CompanionBridgeError("companion_role_manifest_v3_required")
        for field in ("installation_identity_ref", "runtime_handoff_ref",
                      "software_generation_digest"):
            if not isinstance(normalized.get(field), str) or not normalized[field].strip():
                raise CompanionBridgeError("companion_role_authority_reference_missing")
        if self._system != "Windows":
            raise CompanionBridgeError("companion_pair_windows_host_required")
        return normalized

    def _build_role_supervisor(self, role: str, deployment: Mapping[str, object]
            ) -> GamingCompanionProcessSupervisor:
        spec = self._specs[role]
        generation_factory = self._generation_factories[role]

        def process_factory(previous: BridgeGenerationPair | None
                ) -> tuple[CompanionProcessLaunchSpec, BridgeGenerationPair]:
            generation = generation_factory(previous)
            if type(generation) is not BridgeGenerationPair:
                raise CompanionBridgeError("bridge_generation_pair_record_invalid")
            return spec, generation

        def authorize_process_launch(launch_role: str, command_digest: str,
                generation: BridgeGenerationPair) -> bool:
            return self._installation.authority.authorize_process_launch(
                launch_role, command_digest, generation, deployment)

        return GamingCompanionProcessSupervisor(
            process_factory=process_factory,
            authority_receipt_verifier=self._verify_generation,
            launch_authorizer=authorize_process_launch,
            health_probe=self._health_probes[role],
            expected_role=role,
            force_stop_authorizer=self._force_stop.get(role),
            max_restarts=self._max_restarts,
            poll_interval_seconds=self._process_poll,
            spawner=self._spawner,
        )

    def _verify_generation(self, receipt_digest: str, record: object) -> bool:
        if type(record) is not BridgeGenerationCustodyRecord:
            return False
        return self._installation.authority.verify_generation(receipt_digest, record)


__all__ = ["GamingCompanionPlatformPairProcessProvider"]

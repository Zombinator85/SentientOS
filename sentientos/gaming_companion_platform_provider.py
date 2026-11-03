"""Compose platform custody and signed authority into companion role owners.

The provider binds repository-owned role factories to the installed platform's
custody catalog and the application-level admission/verifier hooks. It does
not install services, create trust anchors, or issue launch authority.
"""
from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any, Callable, Mapping

from avatar_state import AvatarStateEmitter

from .gaming_companion_authority import CompanionAuthorityCallbacks
from .gaming_companion_avatar_output import WindowsGodotAvatarStateQueue
from .gaming_companion_bridge import CompanionBridgeError
from .gaming_companion_core_runtime import (
    WSLCoreGamingCompanionRuntime,
    build_wsl_core_gaming_companion_runtime,
)
from .gaming_companion_deployment import validate_manifest
from .gaming_companion_edge_runtime import (
    WindowsEdgeAvatarRuntime,
    build_windows_edge_avatar_runtime,
)
from .gaming_companion_platform_custody import CompanionPlatformCustodyResolver
from .gaming_companion_platform_installation import CompanionPlatformInstallation
from .gaming_companion_receipt_replay import AdmissionReceiptReplayGuard
from .gaming_companion_tls_transport import BridgeGenerationCustodyRecord

AdmissionReceiptBuilder = Callable[[Any], Mapping[str, str]]
CommandReceiptVerifier = Callable[[str, str, object], bool]


class GamingCompanionPlatformRoleProvider:
    """Concrete custody/authority composition for the split-host role owners.

    The Windows installation supplies its state-file path and command receipt
    verifier. The WSL application supplies its governed admission receipt
    builder. These are explicit application authorities; no permissive default
    is substituted when either callback is absent.
    """

    def __init__(self, *, custody: CompanionPlatformCustodyResolver,
                 authority: CompanionAuthorityCallbacks,
                 windows_avatar_state_path: Path | str | None = None,
                 admission_receipt_builder: AdmissionReceiptBuilder | None = None,
                 command_receipt_verifier: CommandReceiptVerifier | None = None,
                 receipt_replay_guard: AdmissionReceiptReplayGuard | None = None,
                 system_name: str | None = None,
                 is_wsl2: bool | None = None) -> None:
        if type(custody) is not CompanionPlatformCustodyResolver:
            raise CompanionBridgeError("companion_platform_custody_resolver_required")
        if type(authority) is not CompanionAuthorityCallbacks:
            raise CompanionBridgeError("companion_platform_authority_callbacks_required")
        self._custody = custody
        self._authority = authority
        self._avatar_state_path = (Path(windows_avatar_state_path)
            if windows_avatar_state_path is not None else None)
        self._admission_builder = admission_receipt_builder
        self._command_verifier = command_receipt_verifier
        self._receipt_replay_guard = receipt_replay_guard
        self._system = system_name or platform.system()
        self._is_wsl2 = _detect_wsl2() if is_wsl2 is None else is_wsl2

    @classmethod
    def from_installation(cls, installation: CompanionPlatformInstallation, *,
            windows_avatar_state_path: Path | str | None = None,
            admission_receipt_builder: AdmissionReceiptBuilder | None = None,
            command_receipt_verifier: CommandReceiptVerifier | None = None,
            receipt_replay_guard: AdmissionReceiptReplayGuard | None = None,
            system_name: str | None = None,
            is_wsl2: bool | None = None) -> GamingCompanionPlatformRoleProvider:
        """Compose custody and authority from the same verified installation."""
        if type(installation) is not CompanionPlatformInstallation:
            raise CompanionBridgeError("companion_platform_installation_required")
        return cls(custody=installation.custody, authority=installation.authority,
            windows_avatar_state_path=windows_avatar_state_path,
            admission_receipt_builder=admission_receipt_builder,
            command_receipt_verifier=command_receipt_verifier,
            receipt_replay_guard=receipt_replay_guard,
            system_name=system_name, is_wsl2=is_wsl2)

    def __call__(self, role: str, manifest: Mapping[str, Any]) -> (
            WindowsEdgeAvatarRuntime | WSLCoreGamingCompanionRuntime):
        return self.create_runtime(role, manifest)

    def authorize_pair_launch(self, manifest: Mapping[str, Any]) -> bool:
        normalized = validate_manifest(manifest)
        return self._authority.authorize_pair_launch(normalized)

    def authorize_role_launch(self, role: str, manifest: Mapping[str, Any]) -> bool:
        normalized = validate_manifest(manifest)
        return self._authority.authorize_role_launch(role, normalized)

    def create_runtime(self, role: str, manifest: Mapping[str, Any]) -> (
            WindowsEdgeAvatarRuntime | WSLCoreGamingCompanionRuntime):
        if role not in {"windows_edge", "wsl_core"}:
            raise CompanionBridgeError("companion_platform_role_invalid")
        normalized = validate_manifest(manifest)
        if self.authorize_role_launch(role, normalized) is not True:
            raise CompanionBridgeError("companion_role_launch_authority_denied")
        if role == "windows_edge":
            self._require_windows_edge()
            if self._avatar_state_path is None:
                raise CompanionBridgeError("companion_windows_avatar_state_path_required")
            if self._command_verifier is None:
                raise CompanionBridgeError("companion_avatar_command_verifier_required")
            renderer = WindowsGodotAvatarStateQueue(
                state_emitter=AvatarStateEmitter(self._avatar_state_path))
            return build_windows_edge_avatar_runtime(
                manifest=normalized,
                generation_pair_loader=self._custody.load_generation_pair,
                bridge_key_reader=self._custody.read_bridge_key,
                server_tls_context_factory=self._custody.server_tls_context,
                generation_receipt_verifier=self._verify_generation,
                command_receipt_verifier=self._command_verifier,
                renderer_sink=renderer.enqueue,
                receipt_replay_guard=self._receipt_replay_guard,
            )
        self._require_wsl_core()
        if self._admission_builder is None:
            raise CompanionBridgeError("companion_core_admission_receipt_builder_required")
        return build_wsl_core_gaming_companion_runtime(
            manifest=normalized,
            generation_pair_loader=self._custody.load_generation_pair,
            bridge_key_reader=self._custody.read_bridge_key,
            server_tls_context_factory=self._custody.server_tls_context,
            client_tls_context_factory=self._custody.client_tls_context,
            generation_receipt_verifier=self._verify_generation,
            admission_receipt_builder=self._admission_builder,
        )

    def _require_windows_edge(self) -> None:
        if self._system != "Windows":
            raise CompanionBridgeError("companion_platform_windows_required")

    def _require_wsl_core(self) -> None:
        if self._system != "Linux":
            raise CompanionBridgeError("companion_platform_linux_required")
        if self._is_wsl2 is not True:
            raise CompanionBridgeError("companion_platform_wsl2_required")

    def _verify_generation(self, receipt_digest: str, record: object) -> bool:
        if type(record) is not BridgeGenerationCustodyRecord:
            return False
        return self._authority.verify_generation(receipt_digest, record)


def _detect_wsl2() -> bool:
    marker = os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP")
    try:
        release = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8").lower()
    except OSError:
        release = ""
    return os.name == "posix" and bool(marker or "microsoft" in release)


__all__ = ["GamingCompanionPlatformRoleProvider"]

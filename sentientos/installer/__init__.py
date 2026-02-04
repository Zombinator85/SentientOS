"""Application installer facade for the SentientOS desktop shell."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Protocol

from logging_config import get_log_path
from log_utils import append_json
from sentientos.daemons import pulse_bus
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

REPO_ROOT = Path(__file__).resolve().parents[2]


class ActionLogger(Protocol):
    """Protocol describing the shell event logger dependency."""

    def record(
        self,
        event_type: str,
        payload: Mapping[str, object] | None = None,
        *,
        priority: str = "info",
    ) -> Mapping[str, object]:
        ...


class InstallError(RuntimeError):
    """Raised when an installation cannot be completed."""


@dataclass
class InstallResult:
    """Canonical response structure for app installations."""

    app_name: str
    package_path: str
    method: str
    ci_passed: bool
    timestamp: str

    def to_payload(self) -> dict[str, object]:
        return {
            "app_name": self.app_name,
            "package_path": self.package_path,
            "method": self.method,
            "ci_passed": self.ci_passed,
            "timestamp": self.timestamp,
        }


def _default_ci_runner() -> bool:
    """Run the test runner quietly as a lightweight safety check."""

    try:
        proc = subprocess.run(
            [sys.executable, "-m", "scripts.run_tests", "-q"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        return proc.returncode == 0
    except FileNotFoundError:
        return False


class AppInstaller:
    """Handle package verification and install logging for desktop apps."""

    SUPPORTED_EXTENSIONS = {".deb", ".appimage"}

    def __init__(
        self,
        *,
        action_logger: ActionLogger,
        ci_runner: Callable[[], bool] | None = None,
        install_log_path: Path | None = None,
        pulse_publisher: Callable[[Mapping[str, object]], Mapping[str, object]] | None = None,
    ) -> None:
        self._logger = action_logger
        self._ci_runner = ci_runner or _default_ci_runner
        self._log_path = install_log_path or get_log_path("app_installer_log.jsonl")
        self._pulse_publisher = pulse_publisher or pulse_bus.publish

    def double_click(self, package: Path) -> Mapping[str, object]:
        return self._install(package, method="double_click")

    def install_via_button(self, package: Path) -> Mapping[str, object]:
        return self._install(package, method="install_button")

    def drag_and_drop(self, package: Path) -> Mapping[str, object]:
        return self._install(package, method="drag_drop", tolerate_browser_alias=True)

    def _install(
        self,
        package: Path,
        *,
        method: str,
        tolerate_browser_alias: bool = False,
    ) -> Mapping[str, object]:
        package = package.expanduser()
        if not package.exists():
            raise FileNotFoundError(package)
        extension = package.suffix.lower()
        if extension not in self.SUPPORTED_EXTENSIONS:
            if not (tolerate_browser_alias and self._looks_like_browser(package.name)):
                raise InstallError(f"Unsupported package format: {package.suffix}")
        app_name = self._derive_app_name(package)
        timestamp = datetime.now(timezone.utc).isoformat()
        ci_passed = bool(self._ci_runner())
        result = InstallResult(
            app_name=app_name,
            package_path=package.as_posix(),
            method=method,
            ci_passed=ci_passed,
            timestamp=timestamp,
        )
        append_json(self._log_path, result.to_payload())
        status = "verified" if ci_passed else "ci_failed"
        payload = {**result.to_payload(), "status": status}
        self._logger.record("app_install", payload)
        try:
            self._pulse_publisher(
                {
                    "timestamp": timestamp,
                    "source_daemon": "AppInstaller",
                    "event_type": "app_install",
                    "priority": "info" if ci_passed else "warning",
                    "payload": payload,
                }
            )
        except Exception:
            # shell logger already stored the event; pulse errors here are tolerated
            pass
        if not ci_passed:
            raise InstallError("CI safety checks failed")
        return payload

    @staticmethod
    def _derive_app_name(package: Path) -> str:
        name = package.stem.replace("_", " ").replace("-", " ")
        return " ".join(part.capitalize() for part in name.split()) or package.stem

    @staticmethod
    def _looks_like_browser(name: str) -> bool:
        lowered = name.lower()
        return "chrome" in lowered or "brave" in lowered


__all__ = ["AppInstaller", "InstallError", "InstallResult"]

#!/usr/bin/env python3
"""Run the loopback-only, GPU-backed local companion development service.

Requires SENTIENTOS_MODEL_CONFIG to point at one digest-pinned Ollama candidate
or an ordered normal/gaming pair. All transcripts, invocation receipts, and
process coordination stay in --state-dir.
This process is a supervised development composition, never production serving.
Screen observation is disabled unless an allowlisted process and consent
lifetime are passed on the CLI. When enabled, the Windows edge captures only
on an explicit chat request, keeps raw frames local and transient, and sends
bounded observation text over the authenticated bridge; each chat message
still needs
the UI checkbox. Optional local visual summaries use an explicitly named
Ollama model on the Windows loopback interface and never send raw frames over
the bridge.
`--godot-headless` keeps the supervised edge from opening a visible Godot
window during game-screen observation.
"""
from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import hmac
import json
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, cast

ROOT = Path(__file__).resolve().parents[1]


def _build_resident_cognition_owner_pair(*, config: Any, writeback: Any,
        admission_authority: Any, invoker: Any,
        current_sequence: Callable[[], int]) -> tuple[Any, Any | None]:
    """Keep serving interactions and operator A/B/A experiments in separate owners."""
    from sentientos.resident_developmental_cognition import (
        ResidentDevelopmentalCognitionOwner,
    )

    interaction_owner = ResidentDevelopmentalCognitionOwner(
        config=replace(config, comparison_enabled=False), writeback=writeback,
        admission_authority=admission_authority, invoker=invoker,
        current_sequence=current_sequence)
    intervention_owner = None
    if config.comparison_enabled:
        intervention_owner = ResidentDevelopmentalCognitionOwner(
            config=replace(config, comparison_enabled=True), writeback=writeback,
            admission_authority=admission_authority, invoker=invoker,
            current_sequence=current_sequence)
    return interaction_owner, intervention_owner


def _build_companion_consequence_records_provider(*, config_path: str,
        read_explicit_file: Callable[..., bytes]
        ) -> Callable[[], tuple[Mapping[str, Any], ...]] | None:
    """Expose selected, digest-verified consequence history to companion cycles."""
    from sentientos.embodied_consequence import (
        ConsequenceStore, validate_world_state_projection_config,
    )

    raw = read_explicit_file(Path(config_path), max_bytes=65_536)
    config = validate_world_state_projection_config(json.loads(raw.decode("utf-8")))
    if not config["enabled"]:
        return None
    consequence_ids = tuple(config["consequence_chain_ids"])
    if not consequence_ids:
        return None
    store = ConsequenceStore(Path(config["store_root"]), create_root=False)

    def provide() -> tuple[Mapping[str, Any], ...]:
        # A prediction-comparison record carries exact expected/observed
        # fields and the result while retaining its chain-bound digest.
        # Project one concise record per selected verified chain so current
        # screen/proprioception evidence can still fit cognition selection.
        records = store.world_state_records(consequence_chain_ids=consequence_ids)
        comparisons = tuple(item for item in records
            if item.get("subject_kind") == "embodied_prediction_comparison")
        if len(comparisons) != len(consequence_ids):
            raise ValueError("companion_consequence_comparison_selection_invalid")
        if len(comparisons) > 32:
            raise ValueError("companion_consequence_projection_record_bound_exceeded")
        return comparisons

    # Fail at startup if the selected custody cannot be read and verified.
    provide()
    return provide


def _normalize_windows_edge_executable(
        executable: str, *, convert_wsl_path: Callable[[Path], str]) -> str:
    """Convert an explicit mounted Windows executable path for the Windows edge."""
    if not isinstance(executable, str) or not executable:
        raise ValueError("screen_observation_ocr_executable_invalid")
    if executable.startswith("/"):
        if not executable.startswith("/mnt/"):
            raise ValueError("screen_observation_ocr_windows_path_required")
        return convert_wsl_path(Path(executable))
    return executable
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))



def _parse_edge_ready(line: str) -> tuple[int, int]:
    parts = line.split()
    if len(parts) != 3 or parts[0] != "READY":
        raise RuntimeError("temporary_windows_edge_ready_missing_godot_pid")
    port, godot_pid = int(parts[1]), int(parts[2])
    if not 1 <= port <= 65535 or godot_pid <= 0:
        raise RuntimeError("temporary_windows_edge_invalid_ready_values")
    return port, godot_pid


def _wait_for_edge_ready(
        lines: queue.Queue[str], process: Any,
        *, timeout_seconds: float = 45.0) -> str:
    """Wait for READY while allowing bounded startup diagnostics before it."""
    deadline = time.monotonic() + timeout_seconds
    diagnostics: list[str] = []
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            state = "temporary_windows_edge_ready_timeout"
            break
        try:
            line = lines.get(timeout=min(0.25, remaining))
        except queue.Empty:
            if process.poll() is not None:
                state = "temporary_windows_edge_exited_before_ready"
                break
            continue
        if line.startswith("READY "):
            return line
        diagnostics.append(line)
    process_status = process.poll()
    if process_status is None:
        diagnostics.append("edge_process_still_running")
    else:
        diagnostics.append(f"edge_process_exit_code={process_status}")
    detail = " | ".join(diagnostics[-8:])[:768]
    return_error = state + (":" + detail if detail else "")
    raise RuntimeError(return_error)


def _kill_windows_process_tree(pid: int) -> None:
    if pid <= 0:
        raise ValueError("pid must be positive")
    taskkill = shutil.which("taskkill.exe") or "/mnt/c/Windows/System32/taskkill.exe"
    try:
        subprocess.run(
            [taskkill, "/T", "/F", "/PID", str(pid)],
            check=False, capture_output=True, timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _stage_windows_edge_source(repo_root: Path, destination: Path) -> Path:
    """Stage reviewed Python source only as one isolated Windows import archive."""
    import os
    import zipfile

    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / "windows_edge_source.zip"
    excluded = {
        ".git", ".venv", ".pytest_cache", ".mypy_cache", "__pycache__",
        "glow", "tests", "docs", "artifacts", "audio_logs", "logs",
        "sentientos_data", ".codex_task",
    }
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as bundle:
        for current, directories, filenames in os.walk(repo_root):
            directories[:] = [
                name for name in directories
                if name not in excluded and not name.startswith(".")
            ]
            current_path = Path(current)
            for filename in filenames:
                if filename.endswith(".py"):
                    source = current_path / filename
                    bundle.write(source, source.relative_to(repo_root).as_posix())
        helper = repo_root / "scripts/terminate_owned_process_tree.py"
        bundle.write(helper, "terminate_owned_process_tree.py")
    return archive


class _LatestForegroundObservation:
    """Drain verified bridge samples continuously and expose only a fresh latest value."""
    def __init__(self, *, detector: Any, process_names: tuple[str, ...]) -> None:
        from sentientos.foreground_game_detection import normalize_game_process_names
        self._detector = detector
        self._process_names = normalize_game_process_names(process_names)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._sample = None
        self._sampled_monotonic = 0.0
        self._thread = threading.Thread(target=self._run,
            name="sentientos-dev-foreground-drain", daemon=True)
        self._thread.start()

    def observe(self, process_names: tuple[str, ...] | list[str]):
        from sentientos.foreground_game_detection import ForegroundGameObservation
        from sentientos.foreground_game_detection import normalize_game_process_names
        requested = normalize_game_process_names(process_names)
        now = time.monotonic()
        with self._lock:
            sample = self._sample
            sampled = self._sampled_monotonic
        if requested != self._process_names or sample is None or now - sampled > 2.5:
            return ForegroundGameObservation("observation_unavailable", None, None,
                datetime.now(timezone.utc).isoformat())
        return sample

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                sample = self._detector.observe(self._process_names)
            except Exception:
                sample = None
            with self._lock:
                self._sample = sample
                self._sampled_monotonic = time.monotonic()
            self._stop.wait(0.25)

    def close(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)
        if self._thread.is_alive():
            raise RuntimeError("foreground_observation_drain_shutdown_timeout")
        self._detector.close()



def _host_resource_log_payload(evaluation: Any, summary: Mapping[str, Any]) -> dict[str, Any]:
    """Expose bounded read-only utilization data with its collection timestamp."""
    snapshot = evaluation.snapshot
    epoch = evaluation.epoch
    return {
        "event": "host_resource_observation",
        "evaluation_id": summary["evaluation_id"],
        "status": summary["status"],
        "observed_at": epoch.observed_at,
        "pressure_labels": list(evaluation.pressure_report.pressure_labels),
        "collectors_called": epoch.collectors_called,
        "collector_status_counts": dict(epoch.status_counts),
        "cpu_utilization_percent": snapshot.cpu_utilization_percent,
        "ram_utilization_percent": snapshot.ram_utilization_percent,
        "gpu_utilization_percent": snapshot.gpu_utilization_percent,
        "vram_utilization_percent": snapshot.vram_utilization_percent,
        "gpu_telemetry_available": (
            snapshot.gpu_utilization_percent is not None
            or snapshot.vram_utilization_percent is not None
        ),
        "no_effect_authority": evaluation.no_effect_authority is True,
        "host_mutation_performed": False,
    }


# Keep roughly 15% of a 12 GiB device available for game-side peaks.
# GLORP captures kept Qwen2.5 3B near 80-81% (about 2.4 GiB free);
# other candidate trials reached 85-89% with worse frame-time tails.
# These are provisional development thresholds, not a universal GPU policy.
_VRAM_RESIDENCY_RELEASE_THRESHOLD_PERCENT = 85.0
_VRAM_RESIDENCY_RECOVERY_THRESHOLD_PERCENT = 82.0
_VRAM_RESIDENCY_PRELOAD_THRESHOLD_PERCENT = 75.0
_VRAM_TELEMETRY_STALE_AFTER_SECONDS = 45.0


class _GamingResourcePressureGuard:
    """Gate gaming inference on fresh, low-pressure VRAM observations.

    Unknown telemetry fails closed for model inference. Once pressure is seen,
    the gate stays closed until VRAM utilization falls below the recovery
    threshold, avoiding rapid load/unload oscillation in the hysteresis band.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._blocked = True
        self._pressure_latched: bool | None = None
        self._last_observed_monotonic: float | None = None
        self._last_observation: dict[str, Any] = {
            "admission_status": "deferred",
            "reason_code": "vram_telemetry_not_observed",
            "preload_admission_status": "deferred",
            "preload_reason_code": "vram_telemetry_not_observed",
            "preload_threshold_percent": _VRAM_RESIDENCY_PRELOAD_THRESHOLD_PERCENT,
            "vram_utilization_percent": None,
            "observed_at": None,
        }

    def is_blocked(self) -> bool:
        with self._lock:
            return self._blocked

    def status(self) -> dict[str, Any]:
        with self._lock:
            stale = (self._last_observed_monotonic is None
                     or time.monotonic() - self._last_observed_monotonic
                        > _VRAM_TELEMETRY_STALE_AFTER_SECONDS)
            if stale and self._last_observation.get("reason_code") not in {
                    "vram_telemetry_unavailable", "vram_telemetry_not_observed"}:
                self._blocked = True
                self._last_observation = {
                    **self._last_observation,
                    "admission_status": "deferred",
                    "reason_code": "vram_telemetry_stale",
                    "preload_admission_status": "deferred",
                    "preload_reason_code": "vram_telemetry_stale",
                }
            return dict(self._last_observation)

    def observe(self, vram_utilization_percent: float | None,
                observed_at: str | None) -> dict[str, Any]:
        valid = (isinstance(vram_utilization_percent, (int, float))
                 and not isinstance(vram_utilization_percent, bool)
                 and 0.0 <= float(vram_utilization_percent) <= 100.0)
        with self._lock:
            if (not valid
                    or not isinstance(vram_utilization_percent, (int, float))
                    or isinstance(vram_utilization_percent, bool)):
                self._blocked = True
                reason = "vram_telemetry_unavailable"
                utilization = None
            else:
                self._last_observed_monotonic = time.monotonic()
                utilization = float(vram_utilization_percent)
                if self._pressure_latched is None:
                    self._pressure_latched = (
                        utilization >= _VRAM_RESIDENCY_RELEASE_THRESHOLD_PERCENT)
                elif utilization >= _VRAM_RESIDENCY_RELEASE_THRESHOLD_PERCENT:
                    self._pressure_latched = True
                elif utilization < _VRAM_RESIDENCY_RECOVERY_THRESHOLD_PERCENT:
                    self._pressure_latched = False
                self._blocked = self._pressure_latched
                reason = ("vram_pressure" if self._blocked
                          else "headroom_available")
            self._last_observation = {
                "admission_status": "deferred" if self._blocked else "available",
                "reason_code": reason,
                "preload_admission_status": (
                    "available" if not self._blocked and utilization is not None
                    and utilization < _VRAM_RESIDENCY_PRELOAD_THRESHOLD_PERCENT
                    else "deferred"),
                "preload_reason_code": (
                    "preload_headroom_available" if not self._blocked
                    and utilization is not None
                    and utilization < _VRAM_RESIDENCY_PRELOAD_THRESHOLD_PERCENT
                    else "preload_vram_headroom_insufficient" if valid
                    else reason),
                "preload_threshold_percent": _VRAM_RESIDENCY_PRELOAD_THRESHOLD_PERCENT,
                "vram_utilization_percent": utilization,
                "observed_at": observed_at,
                "release_threshold_percent": _VRAM_RESIDENCY_RELEASE_THRESHOLD_PERCENT,
                "recovery_threshold_percent": _VRAM_RESIDENCY_RECOVERY_THRESHOLD_PERCENT,
                "stale_after_seconds": _VRAM_TELEMETRY_STALE_AFTER_SECONDS,
            }
            return dict(self._last_observation)


def _apply_gaming_resource_observation(
        guard: _GamingResourcePressureGuard,
        utilization_percent: float | None,
        observed_at: str | None,
        release: Callable[[str], Mapping[str, Any] | None] | None,
        ) -> Mapping[str, Any]:
    """Update the gaming admission gate and release resident VRAM if blocked."""
    state = guard.observe(utilization_percent, observed_at)
    if state["admission_status"] == "deferred" and release is not None:
        reason = state["reason_code"]
        release_reason = ("vram_pressure_observed" if reason == "vram_pressure"
                          else "vram_telemetry_unavailable")
        receipt = release(release_reason)
        if receipt is not None:
            state["residency_release"] = dict(receipt)
    return state


class _LatestRendererObservation:
    """Expose only a fresh, explicitly unverified Godot body self-report."""
    def __init__(self, *, max_age_seconds: float = 5.0) -> None:
        if not 0 < max_age_seconds <= 30:
            raise ValueError("renderer_observation_cache_ttl_invalid")
        self._max_age = float(max_age_seconds)
        self._lock = threading.Lock()
        self._observation: Any | None = None
        self._sampled_monotonic = 0.0

    def update(self, report: Mapping[str, Any]) -> None:
        from sentientos.avatar_renderer_report_ingress import renderer_report_observation
        try:
            observation = renderer_report_observation(report)
        except Exception:
            observation = None
        with self._lock:
            self._observation = observation
            self._sampled_monotonic = time.monotonic() if observation is not None else 0.0

    def __call__(self) -> tuple[Any, ...]:
        now = time.monotonic()
        with self._lock:
            observation = self._observation
            sampled = self._sampled_monotonic
            if observation is None:
                return ()
            if now - sampled > self._max_age:
                self._observation = None
                self._sampled_monotonic = 0.0
                return ()
            return (observation,)


class _HostResourceSampler:
    """Feed host telemetry to the live governor and gaming inference gate."""

    def __init__(self, *, interval_seconds: float = 15.0,
                 on_vram_observation: Callable[
                     [float | None, str | None], Mapping[str, Any] | None
                 ] | None = None) -> None:
        from sentientos.control_plane_kernel import get_control_plane_kernel
        from sentientos.host_resource_runtime import (
            HostObservationBudget, HostResourceRuntimeCoordinator,
            build_observation_plan, default_collector_specs, summary_for_evaluation,
        )

        specs = tuple(spec for spec in default_collector_specs()
                      if spec.collector_id in {"platform", "cpu", "memory", "nvidia_gpu"})
        plan = build_observation_plan(specs=specs, budget=HostObservationBudget(
            max_collectors=4, per_collector_timeout_seconds=1.0,
            total_deadline_seconds=3.0, max_workers=4, retry_count=0,
            max_serialized_result_bytes=65536))
        self._coordinator = HostResourceRuntimeCoordinator(
            kernel=get_control_plane_kernel(),
            runtime_state_root=Path(os.environ["SENTIENTOS_RUNTIME_STATE_ROOT"]),
            plan=plan)
        self._interval = interval_seconds
        self._on_vram_observation = on_vram_observation
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run,
            name="sentientos-dev-host-resource-sampler", daemon=True)
        self._summary = summary_for_evaluation
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            correlation_id = "companion-host-observation-" + uuid.uuid4().hex
            try:
                evaluation = self._coordinator.run_cycle(correlation_id=correlation_id)
                if evaluation is not None:
                    report = self._summary(evaluation)
                    payload = _host_resource_log_payload(evaluation, report)
                    try:
                        if self._on_vram_observation is not None:
                            resource_state = self._on_vram_observation(
                                evaluation.snapshot.vram_utilization_percent,
                                evaluation.epoch.observed_at)
                            if resource_state is not None:
                                payload["gaming_resource_state"] = dict(resource_state)
                    except Exception as exc:
                        payload["gaming_resource_state"] = {
                            "status": "error",
                            "error_type": type(exc).__name__,
                        }
                    print(json.dumps(payload), flush=True)
                else:
                    resource_state = None
                    if self._on_vram_observation is not None:
                        try:
                            resource_state = self._on_vram_observation(None, None)
                        except Exception as exc:
                            resource_state = {"status": "error",
                                "error_type": type(exc).__name__}
                    print(json.dumps({"event": "host_resource_observation",
                                      "status": "admission_deferred",
                                      "gaming_resource_state": resource_state}), flush=True)
            except Exception as exc:
                resource_state = None
                if self._on_vram_observation is not None:
                    try:
                        resource_state = self._on_vram_observation(None, None)
                    except Exception as state_exc:
                        resource_state = {"status": "error",
                            "error_type": type(state_exc).__name__}
                print(json.dumps({"event": "host_resource_observation",
                                  "status": "error",
                                  "error_type": type(exc).__name__,
                                  "gaming_resource_state": resource_state}), flush=True)
            self._stop.wait(self._interval)

    def close(self) -> None:
        self._stop.set()
        timeout = max(5.0, self._coordinator.plan.budget.total_deadline_seconds + 2.0)
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            raise RuntimeError("host_resource_sampler_shutdown_timeout")


class _TemporaryCompanionEdge:
    """Own test-only Windows mTLS edge, Godot process, and sender."""

    def __init__(self, *, windows_python: Path,
                 godot_executable: Path, godot_project: Path,
                 godot_headless: bool = False,
                 game_process_names: tuple[str, ...] = (),
                 screen_observation_process_names: tuple[str, ...] = (),
                 screen_observation_consent_minutes: int = 60,
                 screen_observation_foreground_wait_seconds: int = 5,
                 screen_observation_tesseract_executable: str | None = None,
                 screen_observation_vision_model: str | None = None,
                 delivery_event_file: Path | None = None) -> None:
        from scripts.gaming_companion_cross_host_smoke import (
            _addresses, _contexts, _test_identities, _win_path, _win_temp,
            _secret_free_environment,
        )
        from sentientos.gaming_companion_avatar_output import (
            BridgeChatAvatarOutputEmitter, MutualTLSAvatarCommandSender,
        )
        from sentientos.gaming_companion_bridge import CompanionBridgeReceiver
        from sentientos.gaming_companion_bridge_runtime import CompanionBridgeLoopbackRuntime
        from sentientos.foreground_game_bridge import BridgeForegroundGameDetector
        from sentientos.foreground_game_detection import normalize_game_process_names
        from sentientos.screen_observation_bridge import (
            BridgeScreenObservationProvider, RequestDrivenScreenObservation,
            ScreenCaptureRequestSender,
        )
        from sentientos.avatar_consequence_bridge import (
            AvatarConsequenceMeasurementRequestSender, RemoteAvatarConsequenceObserver,
        )
        from sentientos.embodied_consequence import AuthenticatedBridgeIndependentObserver
        from sentientos.gaming_companion_tls_transport import (
            CompanionBridgeMutualTLSClient,
        )

        self._temporary = tempfile.TemporaryDirectory(
            prefix="sentientos-companion-dev-", dir=_win_temp())
        root = Path(self._temporary.name)
        self._edge_process: subprocess.Popen[str] | None = None
        self._godot_pid: int | None = None
        self._sender: Any | None = None
        self._foreground_runtime: Any | None = None
        self.foreground_game_detector: Any | None = None
        self._screen_runtime: Any | None = None
        self.screen_observer: Any | None = None
        self._avatar_consequence_runtime: Any | None = None
        self.avatar_consequence_observer: Any | None = None
        self._avatar_consequence_request_material: tuple[Any, ...] | None = None
        self._lines: queue.Queue[str] = queue.Queue()
        self._report_file: Path | None = None
        self._delivery_event_file = delivery_event_file
        if type(godot_headless) is not bool:
            raise ValueError("godot_headless_must_be_boolean")
        self.godot_headless = godot_headless
        if delivery_event_file is not None:
            delivery_event_file.parent.mkdir(parents=True, exist_ok=True)
        self.proprioception_observations = _LatestRendererObservation()
        try:
            identities = _test_identities(root)
            wsl, edge, ca = identities["wsl"], identities["windows"], identities["ca"]
            wsl_ip, windows_ip = _addresses()
            avatar_key, avatar_ack, receipt_key = (
                secrets.token_bytes(32) for _ in range(3))
            windows_source = _stage_windows_edge_source(ROOT, root)
            worker = root / "local_companion_edge_dev_worker.py"
            shutil.copyfile(ROOT / "scripts/local_companion_edge_dev_worker.py", worker)
            config = {
                "bind": windows_ip,
                "peer_pin": wsl["pin"],
                "ca": _win_path(ca),
                "cert": _win_path(edge["cert"]),
                "key": _win_path(edge["key"]),
                "avatar_key": base64.b64encode(avatar_key).decode("ascii"),
                "avatar_ack": base64.b64encode(avatar_ack).decode("ascii"),
                "receipt_key": base64.b64encode(receipt_key).decode("ascii"),
                "runtime_root": _win_path(root / "edge-runtime"),
                "godot_executable": _win_path(godot_executable),
                "godot_project": _win_path(godot_project),
                "godot_headless": godot_headless,
            }
            if game_process_names:
                observer_source_key = secrets.token_bytes(32)
                observer_ack_key = secrets.token_bytes(32)
                observer_source_id = "windows-game-observer"
                observer_source_generation = "windows-game-observer-dev-1"
                observer_ack_id = "wsl-game-observer-ack"
                observer_ack_generation = "wsl-game-observer-ack-dev-1"
                self._foreground_runtime = CompanionBridgeLoopbackRuntime(
                    receiver=CompanionBridgeReceiver(
                        source_keys={observer_source_id: observer_source_key},
                        expected_generations={observer_source_id: observer_source_generation}),
                    acknowledgment_source_id=observer_ack_id,
                    acknowledgment_generation_id=observer_ack_generation,
                    acknowledgment_key=observer_ack_key, queue_capacity=8,
                    socket_timeout_seconds=1.5)
                observation_port = self._foreground_runtime.start()
                bridge_detector = BridgeForegroundGameDetector(
                    runtime=self._foreground_runtime, source_id=observer_source_id,
                    # The bridge envelope admits up to 30 seconds of wall-clock
                    # skew; keep this detector aligned with that bound. The
                    # pump samples every second and stale data still fails to
                    # conservative gaming mode when the bounded window expires.
                    generation_id=observer_source_generation, max_observation_age_seconds=30.0)
                self.foreground_game_detector = _LatestForegroundObservation(
                    detector=bridge_detector, process_names=game_process_names)
                config["foreground_observation"] = {
                    "port": observation_port,
                    "source_key": base64.b64encode(observer_source_key).decode("ascii"),
                    "ack_key": base64.b64encode(observer_ack_key).decode("ascii"),
                    "source_id": observer_source_id,
                    "source_generation_id": observer_source_generation,
                    "ack_source_id": observer_ack_id,
                    "ack_generation_id": observer_ack_generation,
                    "process_names": list(game_process_names),
                }
            if screen_observation_process_names:
                allowed_screen_processes = normalize_game_process_names(
                    screen_observation_process_names)
                if (type(screen_observation_consent_minutes) is not int
                        or not 1 <= screen_observation_consent_minutes <= 240):
                    raise ValueError("screen_observation_consent_minutes_out_of_range")
                screen_source_key = secrets.token_bytes(32)
                screen_request_key = secrets.token_bytes(32)
                screen_ack_key = secrets.token_bytes(32)
                screen_source_id = "windows-game-screen"
                screen_source_generation = "windows-game-screen-dev-1"
                screen_ack_id = "wsl-game-screen-ack"
                screen_ack_generation = "wsl-game-screen-ack-dev-1"
                self._screen_runtime = CompanionBridgeLoopbackRuntime(
                    receiver=CompanionBridgeReceiver(
                        source_keys={screen_source_id: screen_source_key},
                        expected_generations={screen_source_id: screen_source_generation}),
                    acknowledgment_source_id=screen_ack_id,
                    acknowledgment_generation_id=screen_ack_generation,
                    acknowledgment_key=screen_ack_key, queue_capacity=8,
                    socket_timeout_seconds=1.5)
                screen_port = self._screen_runtime.start()
                screen_provider = BridgeScreenObservationProvider(
                    runtime=self._screen_runtime, source_id=screen_source_id,
                    generation_id=screen_source_generation,
                    # Windows and WSL clocks showed ~8s skew; capture remains request-driven.
                    max_observation_age_seconds=15.0)
                screen_request_material = (screen_provider, screen_request_key)
                consent_expires = (datetime.now(timezone.utc)
                    + timedelta(minutes=screen_observation_consent_minutes))
                if (type(screen_observation_foreground_wait_seconds) is not int
                        or not 0 <= screen_observation_foreground_wait_seconds <= 10):
                    raise ValueError("screen_observation_foreground_wait_out_of_range")
                config["screen_observation"] = {
                    "port": screen_port,
                    "foreground_wait_seconds": screen_observation_foreground_wait_seconds,
                    "source_key": base64.b64encode(screen_source_key).decode("ascii"),
                    "ack_key": base64.b64encode(screen_ack_key).decode("ascii"),
                    "source_id": screen_source_id,
                    "source_generation_id": screen_source_generation,
                    "request_key": base64.b64encode(screen_request_key).decode("ascii"),
                    "request_source_id": "wsl-screen-request-dev",
                    "request_generation_id": "wsl-screen-request-dev-1",
                    "ack_source_id": screen_ack_id,
                    "ack_generation_id": screen_ack_generation,
                    "process_names": list(allowed_screen_processes),
                    "consent_id": "chat-screen-" + uuid.uuid4().hex,
                    "consent_expires_at": consent_expires.isoformat().replace("+00:00", "Z"),
                }
                if screen_observation_vision_model is not None:
                    if (not isinstance(screen_observation_vision_model, str)
                            or re.fullmatch(
                                r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}",
                                screen_observation_vision_model) is None):
                        raise ValueError("screen_observation_vision_model_invalid")
                    config["screen_observation"]["vision_model"] = (
                        screen_observation_vision_model)
                    avatar_request_key = secrets.token_bytes(32)
                    avatar_source_key = secrets.token_bytes(32)
                    avatar_ack_key = secrets.token_bytes(32)
                    avatar_request_id = "wsl-avatar-consequence-request"
                    avatar_request_generation = "wsl-avatar-consequence-request-dev-1"
                    avatar_source_id = "windows-avatar-consequence"
                    avatar_source_generation = "windows-avatar-consequence-dev-1"
                    avatar_ack_id = "wsl-avatar-consequence-ack"
                    avatar_ack_generation = "wsl-avatar-consequence-ack-dev-1"
                    self._avatar_consequence_runtime = CompanionBridgeLoopbackRuntime(
                        receiver=CompanionBridgeReceiver(
                            source_keys={avatar_source_id: avatar_source_key},
                            expected_generations={avatar_source_id: avatar_source_generation}),
                        acknowledgment_source_id=avatar_ack_id,
                        acknowledgment_generation_id=avatar_ack_generation,
                        acknowledgment_key=avatar_ack_key, queue_capacity=8,
                        socket_timeout_seconds=1.5)
                    avatar_consequence_port = self._avatar_consequence_runtime.start()
                    avatar_cfg = {
                        "request_source_id": avatar_request_id,
                        "request_generation_id": avatar_request_generation,
                        "request_key": base64.b64encode(avatar_request_key).decode("ascii"),
                        "port": avatar_consequence_port,
                        "source_id": avatar_source_id,
                        "source_generation_id": avatar_source_generation,
                        "source_key": base64.b64encode(avatar_source_key).decode("ascii"),
                        "ack_source_id": avatar_ack_id,
                        "ack_generation_id": avatar_ack_generation,
                        "ack_key": base64.b64encode(avatar_ack_key).decode("ascii"),
                    }
                    config["screen_observation"]["avatar_consequence"] = avatar_cfg
                    # The Windows listener chooses an ephemeral port; construct the
                    # authenticated request sender after EDGE_READY reports it.
                    self._avatar_consequence_request_material = (
                        avatar_request_key, avatar_request_id, avatar_request_generation,
                        avatar_source_id, avatar_source_generation)
                if screen_observation_tesseract_executable is not None:
                    executable = screen_observation_tesseract_executable
                    if (not isinstance(executable, str) or not executable
                            or len(executable) > 1024 or "\0" in executable):
                        raise ValueError("screen_observation_ocr_executable_invalid")
                    config["screen_observation"]["tesseract_executable"] = (
                        _normalize_windows_edge_executable(
                            executable, convert_wsl_path=_win_path))
            self._edge_process = subprocess.Popen(
                [str(windows_python), _win_path(worker), _win_path(windows_source)],
                cwd=str(ROOT), env=_secret_free_environment(), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                encoding="utf-8", errors="replace", bufsize=1)
            assert self._edge_process.stdin is not None
            assert self._edge_process.stdout is not None
            self._edge_process.stdin.write(json.dumps(config, separators=(",", ":")) + "\n")
            self._edge_process.stdin.flush()
            self._report_file = root / "renderer-reports.jsonl"
            self.report_file = self._report_file
            threading.Thread(target=self._forward_lines,
                args=(self._edge_process.stdout, self._lines, self._report_file,
                      self._delivery_event_file,
                      self.proprioception_observations.update),
                daemon=True).start()
            if self._edge_process is None:
                raise RuntimeError("temporary_windows_edge_process_unavailable")
            ready = _wait_for_edge_ready(
                self._lines, self._edge_process, timeout_seconds=45.0)
            port, self._godot_pid = _parse_edge_ready(ready)
            print(f"WINDOWS_EDGE READY port={port} godot_pid={self._godot_pid}", flush=True)
            _server_context, client_context = _contexts(ca, wsl["cert"], wsl["key"])
            client = CompanionBridgeMutualTLSClient(
                address=windows_ip, port=port, server_hostname="windows-edge.test",
                tls_context=client_context,
                acknowledgment_receiver=CompanionBridgeReceiver(
                    source_keys={"windows-edge-dev": avatar_ack},
                    expected_generations={"windows-edge-dev":
                        "windows-avatar-ack-dev-1"}),
                expected_server_certificate_sha256=edge["pin"],
                timeout_seconds=4.0)
            def receipt_builder(_authorization: Any) -> dict[str, str]:
                receipt_id = "dev-" + uuid.uuid4().hex
                digest = hmac.new(receipt_key, receipt_id.encode("utf-8"),
                                  hashlib.sha256).hexdigest()
                return {"receipt_id": receipt_id, "semantic_digest": digest}
            if screen_observation_process_names:
                screen_provider, screen_request_key = screen_request_material
                screen_request_client = CompanionBridgeMutualTLSClient(
                    address=windows_ip, port=port, server_hostname="windows-edge.test",
                    tls_context=client_context,
                    acknowledgment_receiver=CompanionBridgeReceiver(
                        source_keys={"windows-edge-dev": avatar_ack},
                        expected_generations={"windows-edge-dev":
                            "windows-avatar-ack-dev-1"}),
                    expected_server_certificate_sha256=edge["pin"],
                    timeout_seconds=4.0)
                request_sender = ScreenCaptureRequestSender(
                    client=screen_request_client,
                    source_id="wsl-screen-request-dev",
                    session_id="wsl-screen-request-dev",
                    generation_id="wsl-screen-request-dev-1",
                    source_key=screen_request_key)
                self.screen_observer = RequestDrivenScreenObservation(
                    request_sender=request_sender, provider=screen_provider,
                    timeout_seconds=30.0,
                    consent_expires_at=config["screen_observation"]["consent_expires_at"],
                    foreground_wait_seconds=config["screen_observation"][
                        "foreground_wait_seconds"])
                if self._avatar_consequence_runtime is not None:
                    request_material = self._avatar_consequence_request_material
                    if request_material is None:
                        raise RuntimeError("avatar_consequence_request_material_unavailable")
                    (avatar_request_key, avatar_request_id, avatar_request_generation,
                     avatar_source_id, avatar_source_generation) = request_material
                    avatar_request_client = CompanionBridgeMutualTLSClient(
                        address=windows_ip, port=port, server_hostname="windows-edge.test",
                        tls_context=client_context,
                        acknowledgment_receiver=CompanionBridgeReceiver(
                            source_keys={"windows-edge-dev": avatar_ack},
                            expected_generations={"windows-edge-dev":
                                "windows-avatar-ack-dev-1"}),
                        expected_server_certificate_sha256=edge["pin"],
                        timeout_seconds=4.0)
                    avatar_sender = AvatarConsequenceMeasurementRequestSender(
                        client=avatar_request_client, source_id=avatar_request_id,
                        session_id="wsl-avatar-consequence-request",
                        generation_id=avatar_request_generation,
                        source_key=avatar_request_key)
                    authenticated_observer = AuthenticatedBridgeIndependentObserver(
                        runtime=self._avatar_consequence_runtime,
                        observer_id=avatar_source_id,
                        generation_id=avatar_source_generation,
                        max_observation_age_seconds=30.0,
                        receive_timeout_seconds=30.0)
                    self.avatar_consequence_observer = RemoteAvatarConsequenceObserver(
                        request_sender=avatar_sender, observer=authenticated_observer)
            self._sender = MutualTLSAvatarCommandSender(
                client=client, source_id="wsl-core-dev", session_id=None,
                generation_id="wsl-avatar-dev-1", source_key=avatar_key,
                admission_receipt_builder=receipt_builder)
            self.emitter = BridgeChatAvatarOutputEmitter(self._sender)
            self.state_file = root / "edge-runtime" / "avatar_state.json"
            self.identity_posture = "temporary_test_mtls_identities"
        except Exception:
            self.close()
            raise

    @staticmethod
    def _forward_lines(stream, target: queue.Queue[str], report_file: Path,
                       delivery_event_file: Path | None = None,
            renderer_observation_sink: Callable[[Mapping[str, Any]], None] | None = None) -> None:
        ready_seen = False
        delivery_file = (delivery_event_file
                         if delivery_event_file is not None
                         else report_file.with_name("avatar-delivery-events.jsonl"))
        def persist_delivery_event(event: Mapping[str, Any]) -> None:
            delivery_file.parent.mkdir(parents=True, exist_ok=True)
            with delivery_file.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event, separators=(",", ":")))
                handle.write(chr(10))
                handle.flush()
        for line in stream:
            rendered = line.rstrip()
            if rendered.startswith("READY "):
                ready_seen = True
            if rendered.startswith("RENDERER_REPORT "):
                try:
                    report = json.loads(rendered[len("RENDERER_REPORT "):])
                    with report_file.open("a", encoding="utf-8") as handle:
                        handle.write(json.dumps(report, separators=(",", ":")))
                        handle.write(chr(10))
                        handle.flush()
                    if callable(renderer_observation_sink):
                        renderer_observation_sink(report)
                except (OSError, ValueError, TypeError):
                    pass
            if rendered.startswith("AVATAR_DISPATCH "):
                try:
                    outcome = json.loads(rendered[len("AVATAR_DISPATCH "):])
                    if (not isinstance(outcome, dict)
                            or outcome.get("schema_version")
                                != "sentientos.avatar_dispatch_outcome:v1"
                            or not isinstance(outcome.get("message_id"), str)
                            or not isinstance(outcome.get("session_id"), str)
                            or outcome.get("kind") != "avatar_command"
                            or type(outcome.get("accepted")) is not bool
                            or outcome.get("renderer_effect_proven") is not False
                            or ("failure_code" in outcome
                                and not isinstance(outcome.get("failure_code"), str))):
                        raise ValueError("avatar_dispatch_outcome_invalid")
                    event = {
                        "event": "windows_edge_avatar_command_dispatch",
                        "observed_at": datetime.now(timezone.utc).isoformat(),
                        **outcome,
                    }
                    persist_delivery_event(event)
                except (OSError, ValueError, TypeError):
                    pass
            if rendered.startswith("AVATAR_ACCEPTED "):
                try:
                    accepted = json.loads(rendered[len("AVATAR_ACCEPTED "):])
                    if (not isinstance(accepted, dict)
                            or not isinstance(accepted.get("session_id"), str)
                            or not isinstance(accepted.get("output_digest"), str)):
                        raise ValueError("avatar_acceptance_event_invalid")
                    event = {
                        "event": "windows_edge_avatar_state_accepted",
                        "observed_at": datetime.now(timezone.utc).isoformat(),
                        **accepted,
                    }
                    persist_delivery_event(event)
                except (OSError, ValueError, TypeError):
                    pass
            if rendered.startswith("FOREGROUND_PUMP "):
                print("WINDOWS_EDGE "+rendered,flush=True)
                continue
            if rendered.startswith(("SCREEN_CAPTURE_READY ", "EDGE_STARTUP ")):
                print("WINDOWS_EDGE "+rendered,flush=True)
            elif ready_seen and rendered and not rendered.startswith("READY "):
                # Keep post-startup edge diagnostics visible. The queue is only
                # consumed while waiting for READY, so otherwise worker errors
                # disappear and bridge failures look like unexplained timeouts.
                print("WINDOWS_EDGE "+rendered,flush=True)
            target.put(rendered)

    def close(self) -> None:
        process = self._edge_process
        self._edge_process = None
        if self._sender is not None:
            self._sender.close()
            self._sender = None
        if process is not None:
            try:
                if process.stdin is not None:
                    process.stdin.write("STOP\n")
                    process.stdin.flush()
                    process.stdin.close()
                process.wait(timeout=10)
            except Exception:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        # The worker can be force-stopped before its Python finally block has
        # finished. Kill only the exact Windows Godot PID it reported at READY,
        # before deleting the temporary profile that Godot holds open.
        godot_pid = self._godot_pid
        self._godot_pid = None
        if godot_pid is not None:
            _kill_windows_process_tree(godot_pid)
        try:
            if self.foreground_game_detector is not None:
                self.foreground_game_detector.close()
                self.foreground_game_detector = None
            elif self._foreground_runtime is not None:
                self._foreground_runtime.close()
                self._foreground_runtime = None
        finally:
            try:
                if self.screen_observer is not None:
                    self.screen_observer.close()
                    self.screen_observer = None
            finally:
                try:
                    if self._screen_runtime is not None:
                        self._screen_runtime.close()
                        self._screen_runtime = None
                    if self._avatar_consequence_runtime is not None:
                        self._avatar_consequence_runtime.close()
                        self._avatar_consequence_runtime = None
                finally:
                    self._temporary.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--initial-workload-mode", choices=("normal", "gaming", "automatic"),
                        default="normal")
    parser.add_argument("--game-process-name", action="append", default=[],
                        help="Allowlisted Windows game executable basename for automatic mode")
    parser.add_argument(
        "--gaming-keep-alive", choices=("0", "5s", "5m", "15m", "-1"), default="0",
        help=("Development experiment: unload immediately, retain the gaming model "
              "for 5 seconds, 5 minutes, 15 minutes, or until released by the "
              "development runner VRAM pressure monitor."),
    )
    parser.add_argument("--enable-resident-cognition", action="store_true",
        help=("Opt in to the configured resident cognition owner; inference is "
              "serialized with chat and disabled while automatic gaming mode is active"))
    parser.add_argument("--windows-python", type=Path)
    parser.add_argument("--godot-exe", type=Path)
    parser.add_argument("--godot-project", type=Path)
    parser.add_argument("--godot-headless", action="store_true",
                        help="Run the supervised development edge without opening a Godot window")
    parser.add_argument("--local-speech-output", action="store_true",
                        help=("Expose opt-in local pyttsx3 speech; playback remains disabled "
                              "until approved for a conversation in the chat UI"))
    parser.add_argument("--screen-observation-process", action="append", default=[],
                        metavar="GAME.exe",
                        help=("Configure launch-scoped consent for per-message local OCR on "
                              "this allowlisted foreground game"))
    parser.add_argument("--screen-observation-consent-minutes", type=int, default=60,
                        help="Expire opt-in screen OCR consent after 1 to 240 minutes")
    parser.add_argument("--screen-observation-foreground-wait-seconds",
                        type=int, default=5,
                        help=("After a per-message request, wait up to 0-10 seconds for "
                              "the allowlisted game to become foreground"))
    parser.add_argument("--screen-observation-tesseract-executable",
                        help="Use an explicit local Tesseract executable for screen OCR")
    parser.add_argument("--screen-observation-vision-model",
                        help=("Optionally add one-sentence visual descriptions using the "
                              "named Ollama model over loopback; frame data stays local and "
                              "the model is not kept resident"))
    args = parser.parse_args()
    if args.host != "127.0.0.1" or not 1 <= args.port <= 65535:
        parser.error("development chat must bind only to 127.0.0.1")
    edge_args = (args.windows_python, args.godot_exe, args.godot_project)
    if any(value is not None for value in edge_args) and not all(
            value is not None for value in edge_args):
        parser.error("the temporary edge requires Windows Python, Godot, and project")
    if args.screen_observation_process and not all(
            value is not None for value in edge_args):
        parser.error("screen observation requires the supervised Windows edge")
    if args.godot_headless and not all(value is not None for value in edge_args):
        parser.error("headless Godot requires the supervised Windows edge")
    if (args.screen_observation_tesseract_executable is not None
            and not args.screen_observation_process):
        parser.error("a Tesseract executable requires screen observation opt-in")
    if (args.screen_observation_vision_model is not None
            and not args.screen_observation_process):
        parser.error("a local vision model requires screen observation opt-in")
    if (args.screen_observation_vision_model is not None
            and re.fullmatch(
                r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}",
                args.screen_observation_vision_model) is None):
        parser.error("screen observation vision model name is invalid")
    if not 1 <= args.screen_observation_consent_minutes <= 240:
        parser.error("screen observation consent minutes must be between 1 and 240")
    if not 0 <= args.screen_observation_foreground_wait_seconds <= 10:
        parser.error("screen observation foreground wait must be between 0 and 10 seconds")
    config_path = os.environ.get("SENTIENTOS_MODEL_CONFIG")
    if not config_path or not Path(config_path).is_file():
        parser.error("SENTIENTOS_MODEL_CONFIG must identify the pinned local Ollama model")
    if args.initial_workload_mode == "automatic":
        if not args.game_process_name:
            parser.error("automatic mode requires at least one --game-process-name allowlist entry")
        if not all(value is not None for value in edge_args):
            parser.error("automatic mode requires the supervised Windows foreground observer edge")
    if args.enable_resident_cognition:
        if (args.initial_workload_mode != "automatic"
                or not args.game_process_name or not all(value is not None for value in edge_args)):
            parser.error("resident cognition requires automatic workload mode and an allowlisted foreground observer")
        if not os.environ.get("SENTIENTOS_RESIDENT_DEVELOPMENTAL_COGNITION_CONFIG"):
            parser.error("resident cognition requires SENTIENTOS_RESIDENT_DEVELOPMENTAL_COGNITION_CONFIG")
    state = args.state_dir.expanduser().resolve()
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(state, 0o700)
    lock_path = state / "active-chat.lock"
    lock_handle = lock_path.open("a+", encoding="utf-8")
    os.chmod(lock_path, 0o600)
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        parser.error("another local companion development process holds this state directory")

    runtime = state / "runtime"
    chat_state = state / "chat"
    memory = state / "memory"
    for directory in (runtime, chat_state, memory):
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
    os.environ["SENTIENTOS_DATA_DIR"] = str(runtime)
    os.environ["MEMORY_DIR"] = str(memory)
    os.environ["SENTIENTOS_RUNTIME_STATE_ROOT"] = str(state / "runtime-state")
    os.environ["SENTIENTOS_CONTROL_KERNEL_ROOT"] = str(state / "control-kernel")
    os.environ["SENTIENTOS_GOVERNOR_ROOT"] = str(state / "governor")
    os.environ["SENTIENTOS_FEDERATION_ROOT"] = str(state / "federation")
    os.environ["SENTIENTOS_REPO_ROOT"] = str(ROOT)
    pulse_root = state / "pulse-trust"
    pulse_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    private_key = pulse_root / "ed25519_private.key"
    public_key = pulse_root / "ed25519_public.key"
    if not private_key.is_file() or not public_key.is_file():
        from nacl.signing import SigningKey
        signing_key = SigningKey.generate()
        for path, value in ((private_key, signing_key.encode()),
                            (public_key, signing_key.verify_key.encode())):
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(value)
                stream.flush()
                os.fsync(stream.fileno())
    os.environ["PULSE_TRUST_EPOCH_ROOT"] = str(pulse_root)
    os.environ["PULSE_TRUST_EPOCH_STATE"] = str(pulse_root / "epoch_state.json")
    os.environ["PULSE_SIGNING_KEY"] = str(private_key)
    os.environ["PULSE_VERIFY_KEY"] = str(public_key)
    # Persistent, machine-local development trust keys only; no commissioning or
    # production authority. Control-plane evidence stays outside the repository.
    os.environ["CONTROL_PLANE_LOG"] = str(state / "control-plane.jsonl")

    from sentientos.chat_service import configure_development_chat, run
    from sentientos.config import load_model_config
    from sentientos.governed_local_model_invocation import (
        GovernedLocalModelInvoker, LocalModelInvoker)
    from sentientos.local_model import LocalModel
    from sentientos.local_model_authority import (
        atomic_write_json, build_local_model_authority_map,
        build_developmental_companion_authority_map,
    )

    config = load_model_config()
    if not 1 <= len(config.candidates) <= 2 or any(
            item.engine != "ollama" or item.path is None
            for item in config.candidates):
        parser.error("development composition requires one model or normal+gaming Ollama candidates")
    allowed_roots = sorted({item.path.parent for item in config.candidates
                             if item.path is not None}, key=str)
    authority = (build_developmental_companion_authority_map(
            config, allowed_roots=allowed_roots)
        if args.enable_resident_cognition else
        build_local_model_authority_map(config, allowed_roots=allowed_roots))
    expected_purposes = (("local_user_chat",
        "resident_developmental_retrieval_cognition")
        if args.enable_resident_cognition else ("local_user_chat",))
    for record in authority.records:
        expected_disposition = ("development_companion_candidate"
            if args.enable_resident_cognition else "development_only")
        if (record.disposition != expected_disposition
                or record.runtime_eligibility_status != "eligible"
                or record.allowed_invocation_purposes != expected_purposes
                or record.tool_posture != "blocked"
                or record.memory_posture != "blocked"
                or record.action_posture != "blocked"):
            parser.error("Ollama model authority is not eligible for the selected local development purposes")
    models = [LocalModel.load_candidate(index, config=config)
              for index in range(len(config.candidates))]
    for model in models:
        if model.active_identity.posture != "development_only" or model.active_identity.fallback:
            parser.error("the exact local development model did not load")
        for purpose in expected_purposes:
            if authority.record_for_active_identity(model.active_identity, purpose) is None:
                parser.error("loaded model does not match its local development authority record")
    model = models[0]
    model_profiles = {"normal": models[0], "gaming": models[-1]}
    atomic_write_json(state / "model-authority-map.json", authority.to_dict())
    invoker = GovernedLocalModelInvoker(model=model, authority_map=authority,
        runtime_root=state / "invocations")
    resident_cognition_owner = None
    resident_history_intervention_owner = None
    self_model_owner = None
    self_model_config = None
    epistemic_state_owner = None
    epistemic_state_config = None
    consequence_records_provider = None
    if args.enable_resident_cognition:
        from sentientos.codex_task_authority_admission import (
            RESIDENT_DEVELOPMENTAL_WRITEBACK,
            RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION,
        )
        from sentientos.longitudinal_self_model import (
            LongitudinalSelfModelOwner, load_runtime_config as load_self_model_config,
        )
        from sentientos.persistent_epistemic_state import PersistentEpistemicStateOwner
        from sentientos.resident_developmental_cognition import (
            CONFIG_ENV as RESIDENT_COGNITION_CONFIG_ENV,
            load_config as load_resident_cognition_config,
        )
        from sentientos.resident_developmental_writeback import ResidentDevelopmentalWritebackController
        from sentientos.runtime_admission import AdmissionLedger, RuntimeAdmissionAuthority, RuntimeAdmissionVerifier
        from sentientos.windows_handle_custody import read_explicit_file

        consequence_projection_path = os.environ.get(
            "SENTIENTOS_EMBODIED_CONSEQUENCE_PROJECTION_CONFIG")
        if consequence_projection_path:
            try:
                consequence_records_provider = (
                    _build_companion_consequence_records_provider(
                        config_path=consequence_projection_path,
                        read_explicit_file=read_explicit_file))
            except Exception as exc:
                parser.error(
                    "embodied consequence projection configuration is invalid: "
                    + type(exc).__name__)

        cognition_config = load_resident_cognition_config(
            os.environ[RESIDENT_COGNITION_CONFIG_ENV])
        if (not cognition_config.enabled
                or "embodiment" not in cognition_config.allowed_source_kinds):
            parser.error("configured resident cognition must be enabled and admit embodiment evidence")
        ledger = AdmissionLedger(cognition_config.state_root / "runtime_admissions.json")
        definitions = {RESIDENT_DEVELOPMENTAL_WRITEBACK:
            RESIDENT_DEVELOPMENTAL_WRITEBACK_DEFINITION}
        writeback = ResidentDevelopmentalWritebackController(
            history_root=cognition_config.history_root,
            admission_verifier=RuntimeAdmissionVerifier(
                definitions=definitions, ledger=ledger),
            current_sequence=ledger.current_sequence)
        resident_cognition_owner, resident_history_intervention_owner = (
            _build_resident_cognition_owner_pair(
                config=cognition_config, writeback=writeback,
                admission_authority=RuntimeAdmissionAuthority(
                    definitions=definitions, ledger=ledger),
                # GovernedLocalModelInvoker uses stricter typed request/receipt objects
                # than the legacy structural protocol; runtime behavior is compatible.
                invoker=cast(LocalModelInvoker, invoker),
                current_sequence=ledger.current_sequence))

        self_model_path = os.environ.get("SENTIENTOS_LONGITUDINAL_SELF_MODEL_CONFIG")
        if self_model_path:
            self_model_config = load_self_model_config(self_model_path)
            if self_model_config.enabled:
                self_model_owner = LongitudinalSelfModelOwner(
                    self_model_config.custody_root)
                self_model_owner.history()

        epistemic_path = os.environ.get("SENTIENTOS_EPISTEMIC_STATE_CONFIG")
        if epistemic_path:
            try:
                epistemic_payload = json.loads(
                    read_explicit_file(Path(epistemic_path), max_bytes=65_536).decode("utf-8"))
            except Exception as exc:
                parser.error(f"epistemic state configuration is unreadable: {type(exc).__name__}")
            expected_epistemic_config = {"schema", "custody_root",
                "allowed_proposition_namespaces", "max_cognitive_projection_count",
                "cognitive_consumption_enabled"}
            if (not isinstance(epistemic_payload, dict)
                    or set(epistemic_payload) != expected_epistemic_config
                    or epistemic_payload.get("schema") != "sentientos.epistemic_runtime_config:v1"
                    or not isinstance(epistemic_payload.get("custody_root"), str)
                    or not Path(epistemic_payload["custody_root"]).is_absolute()
                    or not isinstance(epistemic_payload.get("allowed_proposition_namespaces"), list)
                    or not epistemic_payload["allowed_proposition_namespaces"]
                    or any(not isinstance(item, str) or not item
                        for item in epistemic_payload["allowed_proposition_namespaces"])
                    or len(set(epistemic_payload["allowed_proposition_namespaces"]))
                        != len(epistemic_payload["allowed_proposition_namespaces"])
                    or not isinstance(epistemic_payload.get("cognitive_consumption_enabled"), bool)
                    or not isinstance(epistemic_payload.get("max_cognitive_projection_count"), int)
                    or isinstance(epistemic_payload.get("max_cognitive_projection_count"), bool)
                    or not 1 <= epistemic_payload["max_cognitive_projection_count"] <= 128):
                parser.error("epistemic state configuration is invalid")
            epistemic_state_owner = PersistentEpistemicStateOwner(
                epistemic_payload["custody_root"],
                allowed_namespaces=epistemic_payload["allowed_proposition_namespaces"])
            epistemic_state_config = {
                "cognitive_consumption_enabled":
                    epistemic_payload["cognitive_consumption_enabled"],
                "max_cognitive_projection_count":
                    epistemic_payload["max_cognitive_projection_count"],
            }
    edge: _TemporaryCompanionEdge | None = None
    host_resource_sampler: _HostResourceSampler | None = None
    try:
        if all(value is not None for value in edge_args):
            if (not args.windows_python.is_file()
                    or not args.godot_exe.is_file()
                    or not (args.godot_project / "project.godot").is_file()):
                parser.error("a temporary companion edge executable or project is missing")
            edge = _TemporaryCompanionEdge(
                windows_python=args.windows_python, godot_executable=args.godot_exe,
                godot_project=args.godot_project,
                godot_headless=args.godot_headless,
                game_process_names=tuple(args.game_process_name),
                screen_observation_process_names=tuple(args.screen_observation_process),
                screen_observation_consent_minutes=args.screen_observation_consent_minutes,
                screen_observation_foreground_wait_seconds=(
                    args.screen_observation_foreground_wait_seconds),
                screen_observation_tesseract_executable=(
                    args.screen_observation_tesseract_executable),
                screen_observation_vision_model=args.screen_observation_vision_model,
                delivery_event_file=state / "evidence" / "avatar-delivery-events.jsonl")
        gaming_vram_guard = _GamingResourcePressureGuard()
        development_inference = configure_development_chat(
            invoker=invoker, data_root=chat_state,
            avatar_output_emitter=edge.emitter if edge else None,
            model_profiles=model_profiles,
            gaming_resource_status_provider=gaming_vram_guard.status,
            initial_workload_mode=args.initial_workload_mode,
            foreground_game_detector=(edge.foreground_game_detector if edge else None),
            game_process_names=tuple(args.game_process_name),
            gaming_keep_alive=args.gaming_keep_alive,
            screen_observer=edge.screen_observer if edge else None,
            proprioception_provider=(edge.proprioception_observations if edge else None),
            consequence_records_provider=consequence_records_provider,
            screen_capture_policy=("allowlisted_session_polling"
                if args.screen_observation_process else "request_driven"),
            local_speech_output=args.local_speech_output,
            resident_cognition_owner=resident_cognition_owner,
            resident_history_intervention_owner=resident_history_intervention_owner,
            self_model_owner=self_model_owner, self_model_config=self_model_config,
            epistemic_state_owner=epistemic_state_owner,
            epistemic_state_config=epistemic_state_config)
        def release_model_for_gaming_resource_pressure(
                reason_code: str) -> Mapping[str, Any] | None:
            if not invoker.model.is_resident():
                return None
            return invoker.release_model_residency(
                reason_code=reason_code, cancel_active=False).to_dict()

        def observe_gaming_vram(
                utilization_percent: float | None,
                observed_at: str | None) -> Mapping[str, Any]:
            resource_state = _apply_gaming_resource_observation(
                gaming_vram_guard, utilization_percent, observed_at,
                release_model_for_gaming_resource_pressure)
            try:
                workload_state = development_inference.reconcile_workload_state()
                result = dict(resource_state)
                result["effective_workload_mode"] = workload_state.get("effective_mode")
                result["foreground_game"] = workload_state.get("game_foreground")
                if isinstance(workload_state.get("residency_preload"), Mapping):
                    result["residency_preload"] = dict(workload_state["residency_preload"])
                return result
            except Exception as exc:
                return {**dict(resource_state), "workload_reconciliation": {
                    "status": "error", "error_type": type(exc).__name__}}

        host_resource_sampler = _HostResourceSampler(
            on_vram_observation=observe_gaming_vram)
        initial_profile = ("gaming" if args.initial_workload_mode == "automatic"
                           else args.initial_workload_mode)
        initial_model = model_profiles[initial_profile]
        print(json.dumps({
            "state": "running",
            "posture": "development_only",
            "host": args.host,
            "port": args.port,
            "engine": initial_model.active_identity.engine,
            "model": initial_model.active_identity.semantic_artifact_identity,
            "model_profiles": {
                name: profile.active_identity.semantic_artifact_identity
                for name, profile in model_profiles.items()},
            "initial_workload_mode": args.initial_workload_mode,
            "initial_effective_profile": initial_profile,
            "resident_cognition": ("configured_existing_owner_normal_workload_only"
                if resident_cognition_owner is not None else "disabled"),
            "resident_history_intervention": ("separate_operator_confirmed_owner"
                if resident_history_intervention_owner is not None else "disabled"),
            "companion_output": ("temporary_mtls_windows_edge_and_godot"
                                 if edge else "not_configured"),
            "godot_headless": bool(edge and edge.godot_headless),
            "screen_observation_configured": bool(edge and edge.screen_observer),
            "companion_identity_posture": (
                edge.identity_posture if edge else "unavailable"),
            "production_serving": False,
            "transcript_directory": str(chat_state / "conversations"),
            "godot_state_file": str(edge.state_file) if edge else None,
            "renderer_report_capture": str(edge.report_file) if edge else None,
        }), flush=True)
        run(host=args.host, port=args.port)
    finally:
        try:
            from sentientos.chat_service import close_production_chat
            close_production_chat()
        finally:
            try:
                if host_resource_sampler is not None:
                    host_resource_sampler.close()
            finally:
                try:
                    if edge is not None:
                        edge.close()
                finally:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                    lock_handle.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

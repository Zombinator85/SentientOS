#  _____  _             _
# |  __ \| |           (_)
# | |__) | |_   _  __ _ _ _ __   __ _
# |  ___/| | | | |/ _` | | '_ \ / _` |
# | |    | | |_| | (_| | | | | | (_| |
# |_|    |_\__,_|\__, |_|_| |_|\__, |
#                  __/ |         __/ |
#                 |___/         |___/
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from godot_avatar_receiver import AvatarStateForwarder, DEFAULT_HOST, DEFAULT_INTERVAL, DEFAULT_PORT
from sentientos.storage import get_state_file

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_DIR = REPO_ROOT / "tools" / "avatar_runtime"
DEFAULT_DEMO_DIR = RUNTIME_DIR / "demo"
FALLBACK_DEMO_DIR = REPO_ROOT / "godot_avatar_demo"
DEFAULT_SCENE = "res://scenes/avatar_demo.tscn"


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the Godot avatar demo and forward state updates")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Godot listener host for avatar packets")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Godot listener port for avatar packets")
    parser.add_argument("--interval", type=float, default=DEFAULT_INTERVAL, help="Polling interval for state changes")
    parser.add_argument("--state-file", type=Path, default=None, help="Override avatar_state.json path")
    parser.add_argument(
        "--project-dir", type=Path, default=None, help="Path to the Godot demo project (auto-detected by default)"
    )
    parser.add_argument("--godot-bin", type=Path, default=None, help="Explicit Godot binary to launch")
    parser.add_argument(
        "--no-godot", action="store_true", help="Skip launching Godot and only run the UDP forwarder"
    )
    parser.add_argument("--renderer-report-relay-port", type=int, default=None,
                        help="Opt in to sending renderer self-reports to a loopback-only edge relay")
    args = parser.parse_args(argv)
    if (args.renderer_report_relay_port is not None
            and not 1 <= args.renderer_report_relay_port <= 65535):
        parser.error("--renderer-report-relay-port must be from 1 to 65535")
    return args


def resolve_project_dir(candidate: Optional[Path]) -> Optional[Path]:
    for path in (candidate, DEFAULT_DEMO_DIR, FALLBACK_DEMO_DIR):
        if path and path.exists():
            return path
    return None


def resolve_godot_binary(candidate: Optional[Path]) -> Optional[Path]:
    for path in (candidate, RUNTIME_DIR / "godot"):
        if path and path.exists():
            return path
    system = shutil.which("godot")
    return Path(system) if system else None


def launch_godot(project_dir: Path, godot_bin: Optional[Path], *,
                 renderer_report_relay_port: int | None = None) -> Optional[subprocess.Popen[bytes]]:
    binary = resolve_godot_binary(godot_bin)
    if binary is None:
        print("Godot binary not found; run the installer with --with-avatar or set --godot-bin.")
        return None

    args = [str(binary), "--path", str(project_dir), "--scene", DEFAULT_SCENE]
    print(f"Launching Godot demo from {project_dir} using {binary}")
    try:
        child_environment = os.environ.copy()
        if renderer_report_relay_port is not None:
            if not 1 <= renderer_report_relay_port <= 65535:
                raise ValueError("renderer_report_relay_port_invalid")
            child_environment["SENTIENTOS_RENDERER_REPORT_RELAY_PORT"] = str(
                renderer_report_relay_port)
        return subprocess.Popen(args, env=child_environment)
    except FileNotFoundError:
        print("Failed to spawn Godot; ensure the binary is executable.")
    return None


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    state_path = args.state_file or get_state_file("avatar_state.json")
    project_dir = resolve_project_dir(args.project_dir)

    if project_dir is None:
        print("Godot demo project not found. Install the avatar runtime or set --project-dir.")

    forwarder = AvatarStateForwarder(state_path, host=args.host, port=args.port, poll_interval=args.interval)
    forwarder.start()

    godot_proc: Optional[subprocess.Popen[bytes]] = None
    if not args.no_godot and project_dir:
        godot_proc = launch_godot(project_dir, args.godot_bin,
            renderer_report_relay_port=args.renderer_report_relay_port)

    try:
        while True:
            if godot_proc is not None and godot_proc.poll() is not None:
                break
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        forwarder.stop()
        if godot_proc is not None and godot_proc.poll() is None:
            godot_proc.terminate()
            godot_proc.wait(timeout=5)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())

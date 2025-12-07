"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval
from sentientos import __version__

require_admin_banner()
require_lumos_approval()

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import shutil
import venv
from pathlib import Path
import webbrowser
import time
from typing import Dict, Mapping, Optional

import requests
import tkinter.messagebox as messagebox

from logging_config import get_log_path
from cathedral_const import PUBLIC_LOG, log_json

try:
    from sentientos.consciousness.integration import run_consciousness_cycle
except Exception:  # pragma: no cover - optional dependency path
    run_consciousness_cycle = None

MIN_VERSION = (3, 11)
CATHEDRAL_LOG = get_log_path("cathedral.log")
UPDATES_DIR = Path(".updates")
HARDWARE_PROFILE = Path("config/hardware_profile.json")
MODEL_PREFERENCE = Path("config/model_preference.txt")

EXIT_OK = 0
EXIT_ENVIRONMENT = 2
EXIT_DEPENDENCY = 3
EXIT_RUNTIME = 4

REQUIRED_MODULES = ["llama_cpp", "python_multipart", "pygments", "cpuinfo", "requests"]
CUDA_SEARCH_PATHS = [
    Path("C:/Windows/System32"),
    Path("C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.8/bin"),
]


def log_event(event: str, *, level: str = "INFO", data: Optional[Dict[str, object]] = None) -> None:
    payload = {"event": event, "level": level, "data": data or {}}
    log_json(CATHEDRAL_LOG, payload)


def optional_consciousness_cycle(system_context: Mapping[str, object]) -> Optional[Dict[str, object]]:
    """Expose the Consciousness Layer integration without scheduling it."""

    if run_consciousness_cycle is None:
        return None
    if not isinstance(system_context, Mapping):
        return None
    return run_consciousness_cycle(system_context)


def ensure_venv_active() -> bool:
    marker = os.environ.get("VIRTUAL_ENV") or ""
    active = Path(marker).name == ".venv" or Path(sys.prefix).name == ".venv"
    if not active:
        print("[FATAL] .venv is not active. Please activate .\\.venv before launching.")
        log_event("venv_missing", level="ERROR")
    return active


def ensure_required_modules() -> bool:
    missing: list[str] = []
    for module in REQUIRED_MODULES:
        try:
            __import__(module)
        except Exception as exc:
            log_event("module_missing", level="ERROR", data={"module": module, "error": str(exc)})
            missing.append(module)
    if missing:
        print("[FATAL] Missing modules: " + ", ".join(missing))
        print("Run `pip install -r requirements.txt` inside the .venv to self-heal.")
        return False
    return True


def check_self_update() -> None:
    """Check GitHub Releases for a newer version."""
    repo_api = "https://api.github.com/repos/OpenAI/SentientOS/releases/latest"
    try:
        resp = requests.get(repo_api, timeout=5)
        resp.raise_for_status()
        latest = resp.json().get("tag_name", "")
        if latest and latest != __version__:
            print(f"Update available: {latest} (current {__version__})")
            log_event("update_available", data={"version": latest})
        else:
            log_event("up_to_date")
    except Exception as e:  # pragma: no cover - network dependent
        log_event("update_check_failed", level="WARNING", data={"error": str(e)})


def _download(url: str, dest: Path) -> None:
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    dest.write_bytes(resp.content)


def install_update(src: Path, tag: str) -> None:
    backup = UPDATES_DIR / f"backup_{__version__}"
    if backup.exists():
        shutil.rmtree(backup)
    backup.mkdir(parents=True, exist_ok=True)
    for item in Path(".").iterdir():
        if item.name == ".updates":
            continue
        dest = backup / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
    for item in src.iterdir():
        dest = Path(item.name)
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)
    log_json(PUBLIC_LOG, {"event": "update_installed", "data": {"version": tag}})


def rollback_update(version: str) -> None:
    backup = UPDATES_DIR / f"backup_{version}"
    if not backup.exists():
        messagebox.showerror("Rollback failed", "Backup missing")
        log_json(
            PUBLIC_LOG,
            {"event": "rollback_failed", "data": {"version": version}},
        )
        return
    for item in Path(".").iterdir():
        if item.name == ".updates":
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    for item in backup.iterdir():
        dest = Path(item.name)
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
    log_json(
        PUBLIC_LOG,
        {"event": "rollback_complete", "data": {"version": version}},
    )


def check_updates() -> None:
    repo_api = "https://api.github.com/repos/OpenAI/SentientOS/releases/latest"
    try:
        resp = requests.get(repo_api, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        tag = data.get("tag_name", "")
        if not tag or tag == __version__:
            log_event("up_to_date")
            return
        assets = data.get("assets", [])
        archive_url = ""
        sig_url = ""
        for a in assets:
            name = a.get("name", "")
            if name.endswith(".tar.gz"):
                archive_url = a.get("browser_download_url", "")
            if name.endswith(".asc") or name.endswith(".sig"):
                sig_url = a.get("browser_download_url", "")
        if not archive_url or not sig_url:
            log_json(
                PUBLIC_LOG,
                {"event": "update_verify_failed", "data": {"version": tag}},
            )
            return
        update_dir = UPDATES_DIR / tag
        update_dir.mkdir(parents=True, exist_ok=True)
        archive = update_dir / archive_url.split("/")[-1]
        sig = update_dir / sig_url.split("/")[-1]
        _download(archive_url, archive)
        _download(sig_url, sig)
        res = subprocess.run(
            ["gpg", "--verify", str(sig), str(archive)],
            capture_output=True,
        )
        if res.returncode != 0:
            log_json(
                PUBLIC_LOG,
                {"event": "update_verify_failed", "data": {"version": tag}},
            )
            return
        shutil.unpack_archive(str(archive), update_dir)
        log_json(
            PUBLIC_LOG,
            {"event": "update_downloaded", "data": {"version": tag}},
        )
        if messagebox.askyesno("Install Update", f"Install version {tag}?"):
            install_update(update_dir, tag)
            if messagebox.askyesno("Rollback", "Restore previous version?"):
                rollback_update(__version__)
    except Exception as e:  # pragma: no cover - network dependent
        log_event("update_check_failed", level="WARNING", data={"error": str(e)})


def check_gpu() -> tuple[bool, bool]:
    runtime_present = detect_cuda_runtime()
    try:
        import torch  # type: ignore

        has = torch.cuda.is_available() or runtime_present
        log_event("gpu_available", data={"available": has})
        return bool(has), runtime_present
    except Exception as exc:
        log_event("gpu_check_failed", level="WARNING", data={"error": str(exc)})
        return runtime_present, runtime_present


def prompt_cloud_inference(env_path: Path) -> None:
    """Ask the user whether to use cloud inference and persist the answer."""
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    if "MODEL_REMOTE_ONLY=" in text:
        return
    resp = input("GPU not detected. Use cloud inference? [y/N] ")
    use_cloud = resp.strip().lower() in {"y", "yes"}
    set_remote_only(env_path, use_cloud)


def check_python_version() -> bool:
    if sys.version_info < MIN_VERSION:
        log_event(
            "python_version_unsupported",
            level="ERROR",
            data={"found": platform.python_version(), "required": "3.11+"},
        )
        print("Python 3.11+ is required")
        return False
    return True


def ensure_pip() -> None:
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "--version"], stdout=subprocess.DEVNULL)
    except subprocess.CalledProcessError:
        subprocess.check_call([sys.executable, "-m", "ensurepip", "--upgrade"])
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])


def ensure_virtualenv() -> None:
    if sys.prefix == sys.base_prefix and os.getenv("VIRTUAL_ENV") is None:
        venv_dir = Path(".venv")
        log_event("virtualenv_creating")
        venv.create(venv_dir, with_pip=True)
        print(f"Virtual environment created at {venv_dir}")


def install_requirements() -> None:
    req = Path("requirements.txt")
    if req.exists():
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", str(req)])


def ensure_env_file() -> Path:
    env = Path(".env")
    if not env.exists():
        example = Path(".env.example")
        if example.exists():
            env.write_text(example.read_text())
        else:
            env.touch()
        log_event("env_created")
    return env


def ensure_log_dir() -> Path:
    path = get_log_path("dummy").parent
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_hardware_profile(gpu_ok: bool, cuda_ok: bool, avx_ok: bool) -> None:
    profile = {
        "gpu": gpu_ok,
        "cuda_runtime": cuda_ok,
        "avx": avx_ok,
        "model_precision": "Q4_K_M" if avx_ok else "Q4_K",
        "mode": "gpu" if (gpu_ok and cuda_ok) else "cpu",
    }
    HARDWARE_PROFILE.parent.mkdir(parents=True, exist_ok=True)
    HARDWARE_PROFILE.write_text(json.dumps(profile, indent=2))
    log_json(PUBLIC_LOG, {"event": "hardware_profile", "data": profile})


def detect_avx() -> bool:
    try:
        from cpuinfo import get_cpu_info

        flags = get_cpu_info().get("flags", [])
        has_avx = "avx" in flags or "avx2" in flags
        log_event("avx_detected", data={"supported": has_avx})
        if not has_avx:
            print("[WARN] AVX not detected; CPU inference will be slower.")
        return bool(has_avx)
    except Exception as exc:  # pragma: no cover - detection best-effort
        log_event("avx_detection_failed", level="WARNING", data={"error": str(exc)})
        return False


def detect_cuda_runtime() -> bool:
    for path in CUDA_SEARCH_PATHS:
        if not path.exists():
            continue
        if any(path.glob("cudart64*.dll")):
            if os.name == "nt" and hasattr(os, "add_dll_directory"):
                try:
                    os.add_dll_directory(str(path))
                except OSError:
                    pass
            log_event("cuda_runtime_found", data={"path": str(path)})
            return True
    log_event("cuda_runtime_missing", level="WARNING")
    return False

def check_llama_server(host: str, port: int, endpoint: str = "/completion") -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        print(f"llama.cpp server not reachable at {host}:{port}{endpoint}")
        log_event("llama_unreachable", level="WARNING", data={"host": host, "port": port})
        return False


def set_remote_only(env_path: Path, use_cloud: bool) -> None:
    """Persist remote-only preference to ``env_path``."""
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    updated = False
    for i, line in enumerate(lines):
        if line.startswith("MODEL_REMOTE_ONLY"):
            lines[i] = f"MODEL_REMOTE_ONLY={'1' if use_cloud else '0'}"
            updated = True
            break
    if not updated:
        lines.append(f"MODEL_REMOTE_ONLY={'1' if use_cloud else '0'}")
    env_path.write_text("\n".join(lines))
    log_event("remote_only", data={"enabled": use_cloud})


def load_model_preferences() -> Dict[str, str]:
    if not MODEL_PREFERENCE.exists():
        MODEL_PREFERENCE.parent.mkdir(parents=True, exist_ok=True)
        MODEL_PREFERENCE.write_text(
            "# model_preference.txt\n"
            "# mode=auto|cpu|gpu|remote\n"
            "# model_path=/absolute/path/to/model.gguf\n"
            "# precision=Q4_K_M\n",
            encoding="utf-8",
        )
        log_event("model_preference_created")
        return {}

    prefs: Dict[str, str] = {}
    for line in MODEL_PREFERENCE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        prefs[key.strip().lower()] = value.strip()
    log_event("model_preference_loaded", data={"keys": sorted(prefs.keys())})
    return prefs


def apply_model_preferences(env: Dict[str, str], env_path: Path) -> tuple[Dict[str, str], Dict[str, str]]:
    prefs = load_model_preferences()
    model_path = prefs.get("model_path")
    if model_path:
        env["SENTIENTOS_MODEL_PATH"] = model_path
        env["LOCAL_MODEL_PATH"] = model_path
        env["SENTIENTOS_ALLOW_MODEL_OVERRIDE"] = "1"
    mode = prefs.get("mode", "").lower()
    if mode:
        env["MODEL_MODE"] = mode
        if mode == "remote":
            set_remote_only(env_path, True)
        elif mode in {"cpu", "gpu", "auto"}:
            set_remote_only(env_path, False)
    precision = prefs.get("precision")
    if precision:
        env["MODEL_PRECISION"] = precision
    if prefs:
        log_event("model_preferences_applied", data=prefs)
    return env, prefs


def wait_for_relay_health(host: str, port: int, *, path: str = "/health/status", timeout: int = 60) -> bool:
    url = f"http://{host}:{port}{path}"
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            resp = requests.get(url, timeout=5)
            if resp.status_code < 500:
                log_event("relay_healthy", data={"status": resp.status_code})
                return True
            last_error = f"status={resp.status_code}"
        except Exception as exc:  # pragma: no cover - runtime networking
            last_error = str(exc)
        time.sleep(2)
    log_event("relay_health_failed", level="ERROR", data={"url": url, "error": last_error})
    return False


def launch_background(
    cmd: list[str],
    stdout: Optional[int] = subprocess.DEVNULL,
    env: Optional[Dict[str, str]] = None,
) -> subprocess.Popen[bytes]:
    """Launch *cmd* in the background with optional environment."""
    return subprocess.Popen(cmd, stdout=stdout, stderr=stdout, env=env)


def main(argv: Optional[list[str]] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SentientOS Launcher")
    parser.add_argument(
        "--log-level",
        choices=["INFO", "DEBUG"],
        default="INFO",
        help="Relay log verbosity",
    )
    parser.add_argument(
        "--check-updates",
        action="store_true",
        help="Check GitHub for new releases and exit",
    )
    parser.add_argument(
        "--relay-port",
        type=int,
        default=int(os.getenv("RELAY_PORT", "3928")),
        help="Port for relay_app.py (env: RELAY_PORT)",
    )
    parser.add_argument(
        "--relay-host",
        default=os.getenv("RELAY_HOST", "127.0.0.1"),
        help="Host/interface for relay_app.py (env: RELAY_HOST)",
    )
    parser.add_argument(
        "--relay-health-path",
        default=os.getenv("RELAY_HEALTH_PATH", "/health/status"),
        help="Health endpoint path for the relay (env: RELAY_HEALTH_PATH)",
    )
    parser.add_argument(
        "--health-timeout",
        type=int,
        default=int(os.getenv("RELAY_HEALTH_TIMEOUT", "60")),
        help="Seconds to wait for relay health (env: RELAY_HEALTH_TIMEOUT)",
    )
    parser.add_argument(
        "--webui-port",
        type=int,
        default=int(os.getenv("WEBUI_PORT", os.getenv("STREAMLIT_SERVER_PORT", "8501"))),
        help="Web UI port (env: WEBUI_PORT or STREAMLIT_SERVER_PORT)",
    )
    parser.add_argument(
        "--model-host",
        default=os.getenv("MODEL_HOST", "127.0.0.1"),
        help="Model server host (env: MODEL_HOST)",
    )
    parser.add_argument(
        "--model-port",
        type=int,
        default=int(os.getenv("MODEL_PORT", "8080")),
        help="Model server port (env: MODEL_PORT)",
    )
    args = parser.parse_args(argv)

    env_path = ensure_env_file()
    ensure_log_dir()
    if args.check_updates:
        check_updates()
        return EXIT_OK

    check_updates()

    log_event(
        "launcher_start",
        data={"relay_port": args.relay_port, "webui_port": args.webui_port, "model_port": args.model_port},
    )
    print(
        f"Starting Cathedral Launcher on relay {args.relay_host}:{args.relay_port} "
        f"(web UI port {args.webui_port})..."
    )

    if not check_python_version():
        return EXIT_ENVIRONMENT
    if not ensure_venv_active():
        return EXIT_ENVIRONMENT
    ensure_pip()
    ensure_virtualenv()
    try:
        install_requirements()
    except subprocess.CalledProcessError as exc:
        print(f"Dependency installation failed: {exc}")
        log_event("pip_install_failed", level="ERROR", data={"error": str(exc)})
        return EXIT_DEPENDENCY

    if not ensure_required_modules():
        return EXIT_DEPENDENCY

    gpu_ok, cuda_runtime = check_gpu()
    avx_ok = detect_avx()
    save_hardware_profile(gpu_ok, cuda_runtime, avx_ok)

    env = os.environ.copy()
    env["MODEL_PORT"] = str(args.model_port)
    env["MODEL_HOST"] = args.model_host
    env["WEBUI_PORT"] = str(args.webui_port)
    env["STREAMLIT_SERVER_PORT"] = str(args.webui_port)
    env["RELAY_PORT"] = str(args.relay_port)
    env["RELAY_HOST"] = args.relay_host
    env["RELAY_LOG_LEVEL"] = args.log_level
    env, prefs = apply_model_preferences(env, env_path)

    if not gpu_ok and prefs.get("mode") != "remote":
        prompt_cloud_inference(env_path)

    if not check_llama_server(args.model_host, args.model_port, env.get("MODEL_ENDPOINT", "/completion")):
        log_event(
            "llama_unreachable", level="WARNING", data={"host": args.model_host, "port": args.model_port}
        )

    relay_script = Path("sentientos_relay.py")
    if not relay_script.exists():
        relay_script = Path("relay_app.py")

    log_event(
        "relay_launching",
        data={"script": str(relay_script), "host": args.relay_host, "port": args.relay_port},
    )
    relay_proc = launch_background(
        [sys.executable, str(relay_script)],
        env={**env, "RELAY_PORT": str(args.relay_port), "RELAY_HOST": args.relay_host},
    )

    if not wait_for_relay_health(args.relay_host, args.relay_port, path=args.relay_health_path, timeout=args.health_timeout):
        log_event("relay_health_timeout", level="ERROR", data={"port": args.relay_port})
        print("[FATAL] Relay failed health check; see logs/cathedral.log for details.")
        relay_proc.terminate()
        return EXIT_RUNTIME

    for bridge in ["bio_bridge.py", "tts_bridge.py", "haptics_bridge.py"]:
        path = Path(bridge)
        if path.exists():
            log_event("bridge_launching", data={"bridge": bridge})
            launch_background([sys.executable, bridge], env=env)

    webbrowser.open(f"http://localhost:{args.webui_port}")
    print(
        "Cathedral Launcher complete. Components supervised; configure your process "
        "manager for optional auto-restarts if desired."
    )
    log_event("launcher_complete")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())

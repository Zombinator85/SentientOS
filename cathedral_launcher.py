"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import platform
import subprocess
import sys
import shutil
import venv
from pathlib import Path
import webbrowser
from typing import Optional

from logging_config import get_log_path

MIN_VERSION = (3, 11)
LOG_PATH = get_log_path("cathedral_launcher.log")


def log(msg: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def check_python_version() -> bool:
    if sys.version_info < MIN_VERSION:
        log("Python 3.11+ required")
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
        log("Creating virtual environment")
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
        log("Created .env from example")
    return env


def ensure_log_dir() -> Path:
    path = get_log_path("dummy").parent
    path.mkdir(parents=True, exist_ok=True)
    return path


def check_gpu() -> bool:
    try:
        import torch  # type: ignore
        has = torch.cuda.is_available()
        log(f"gpu_available={has}")
        return bool(has)
    except Exception as exc:
        log(f"gpu_check_failed: {exc}")
        return False


def prompt_cloud_inference(env_path: Path) -> None:
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    if "MIXTRAL_CLOUD_ONLY=1" in text:
        return
    resp = input("GPU not detected. Use cloud inference? [y/N] ")
    if resp.strip().lower() in {"y", "yes"}:
        enable_cloud_only(env_path)


def check_ollama() -> bool:
    if shutil.which("ollama") is not None:
        return True
    print("Ollama binary not found. Install from https://ollama.com")
    log("Ollama binary missing")
    return False


def install_ollama() -> None:
    system = platform.system().lower()
    if system in {"linux", "darwin"}:
        cmd = "curl -fsSL https://ollama.com/install.sh | sh"
        subprocess.call(cmd, shell=True)
    elif system == "windows":
        subprocess.call("winget install Ollama.Ollama -s winget", shell=True)
    else:
        print("Please install Ollama from https://ollama.com")
        log("Ollama missing")


def pull_mixtral_model() -> bool:
    try:
        subprocess.check_call(["ollama", "pull", "mixtral"])
        return True
    except FileNotFoundError:
        print("Cannot pull Mixtral model: ollama not found")
        log("mixtral pull failed: ollama missing")
    except subprocess.CalledProcessError as exc:
        print(f"Failed to pull Mixtral model: {exc}")
        log("mixtral pull failed")
    except Exception as exc:  # pragma: no cover - unexpected
        print(f"Unexpected error pulling Mixtral model: {exc}")
        log("mixtral pull unexpected")
    return False


def enable_cloud_only(env_path: Path) -> None:
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    updated = False
    for i, line in enumerate(lines):
        if line.startswith("MIXTRAL_CLOUD_ONLY"):
            lines[i] = "MIXTRAL_CLOUD_ONLY=1"
            updated = True
            break
    if not updated:
        lines.append("MIXTRAL_CLOUD_ONLY=1")
    env_path.write_text("\n".join(lines))
    log("Enabled Mixtral cloud-only mode")


def launch_background(cmd: list[str], stdout: Optional[int] = subprocess.DEVNULL) -> subprocess.Popen[bytes]:
    return subprocess.Popen(cmd, stdout=stdout, stderr=stdout)


def main() -> int:
    env_path = ensure_env_file()
    ensure_log_dir()
    if not check_python_version():
        return 1
    ensure_pip()
    ensure_virtualenv()
    try:
        install_requirements()
    except subprocess.CalledProcessError as exc:
        print(f"Dependency installation failed: {exc}")
        log("pip install failed")

    if not check_gpu():
        prompt_cloud_inference(env_path)

    if not check_ollama():
        install_ollama()

    ollama_ok = check_ollama()
    if ollama_ok and check_gpu():
        if not pull_mixtral_model():
            enable_cloud_only(env_path)
            print("Using Mixtral cloud-only mode")
    else:
        enable_cloud_only(env_path)
        if not ollama_ok:
            log("Ollama unavailable")

    launch_background(["ollama", "serve"])
    relay_script = Path("sentientos_relay.py")
    if not relay_script.exists():
        relay_script = Path("relay_app.py")
    launch_background([sys.executable, str(relay_script)])

    for bridge in ["bio_bridge.py", "tts_bridge.py", "haptics_bridge.py"]:
        path = Path(bridge)
        if path.exists():
            launch_background([sys.executable, bridge])

    webbrowser.open("http://localhost:8501")
    print("Cathedral Launcher complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

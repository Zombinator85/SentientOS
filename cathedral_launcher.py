"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval
from sentientos import __version__

require_admin_banner()
require_lumos_approval()

import os
import platform
import socket
import subprocess
import sys
import shutil
import venv
from pathlib import Path
import webbrowser
from typing import Optional, Dict
import argparse
import requests

from logging_config import get_log_path
from cathedral_const import PUBLIC_LOG, log_json
import tkinter.messagebox as messagebox

MIN_VERSION = (3, 11)
LOG_PATH = get_log_path("cathedral_launcher.log")
UPDATES_DIR = Path(".updates")


def log(msg: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")


def check_self_update() -> None:
    """Check GitHub Releases for a newer version."""
    repo_api = "https://api.github.com/repos/OpenAI/SentientOS/releases/latest"
    try:
        resp = requests.get(repo_api, timeout=5)
        resp.raise_for_status()
        latest = resp.json().get("tag_name", "")
        if latest and latest != __version__:
            print(f"Update available: {latest} (current {__version__})")
            log(f"update_available:{latest}")
        else:
            log("up_to_date")
    except Exception as e:  # pragma: no cover - network dependent
        log(f"update_check_failed:{e}")


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
            log("up_to_date")
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
        log(f"update_check_failed:{e}")


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
    """Ask the user whether to use cloud inference and persist the answer."""
    text = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    if "MODEL_REMOTE_ONLY=" in text:
        return
    resp = input("GPU not detected. Use cloud inference? [y/N] ")
    use_cloud = resp.strip().lower() in {"y", "yes"}
    set_remote_only(env_path, use_cloud)


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

def check_llama_server() -> bool:
    host = os.getenv("MODEL_HOST", "127.0.0.1")
    port = int(os.getenv("MODEL_PORT", "8080"))
    endpoint = os.getenv("MODEL_ENDPOINT", "/completion")
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        print(f"llama.cpp server not reachable at {host}:{port}{endpoint}")
        log("llama.cpp server unreachable")
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
    log("remote_only=" + ("1" if use_cloud else "0"))


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
    args = parser.parse_args(argv)

    env_path = ensure_env_file()
    ensure_log_dir()
    if args.check_updates:
        check_updates()
        return 0
    check_updates()

    if not check_python_version():
        return 1
    ensure_pip()
    ensure_virtualenv()
    try:
        install_requirements()
    except subprocess.CalledProcessError as exc:
        print(f"Dependency installation failed: {exc}")
        log("pip install failed")

    gpu_ok = check_gpu()
    if not gpu_ok:
        prompt_cloud_inference(env_path)
    if not check_llama_server():
        log("llama.cpp backend not reachable; awaiting manual launch")

    relay_script = Path("sentientos_relay.py")
    if not relay_script.exists():
        relay_script = Path("relay_app.py")

    env = os.environ.copy()
    env["RELAY_LOG_LEVEL"] = args.log_level
    launch_background([sys.executable, str(relay_script)], env=env)

    for bridge in ["bio_bridge.py", "tts_bridge.py", "haptics_bridge.py"]:
        path = Path(bridge)
        if path.exists():
            launch_background([sys.executable, bridge])

    webbrowser.open("http://localhost:8501")
    print("Cathedral Launcher complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

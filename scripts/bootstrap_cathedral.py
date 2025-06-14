"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
"""Bootstrap helper to set up SentientOS with minimal fuss."""

import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

LOG_DIR = Path("logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
BOOT_LOG = LOG_DIR / "bootstrap_run.jsonl"
ENV_LOG = LOG_DIR / "env_autofill_log.jsonl"


def warn_version() -> None:
    ver = sys.version_info
    if ver < (3, 11) or ver > (3, 12):
        print(f"[bootstrap] Warning: Python {ver.major}.{ver.minor}.{ver.micro} may not be fully supported")


def _install_package(pkg: str) -> bool:
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", pkg, "--no-build-isolation"])
        return True
    except subprocess.CalledProcessError:
        return False


def install_requirements() -> None:
    req_file = Path("requirements.txt")
    lines = req_file.read_text().splitlines()
    patched: list[str] = []
    for line in lines:
        pkg = line.strip()
        if not pkg or pkg.startswith("#"):
            continue
        if pkg.startswith("pandas") and sys.version_info >= (3, 12):
            pkg = "pandas==2.3.0"
        if pkg.startswith("TTS") and sys.version_info >= (3, 12):
            print("[bootstrap] Skipping TTS install on Python 3.12")
            continue
        patched.append(pkg)
    for pkg in patched:
        ok = _install_package(pkg)
        if not ok:
            if pkg.startswith("playsound") or pkg.startswith("streamlit"):
                print(f"[bootstrap] Warning: failed to install {pkg}, continuing...")
            elif pkg.startswith("pandas"):
                subprocess.run([sys.executable, "-m", "pip", "install", "pandas==2.3.0"], check=False)
            else:
                print(f"[bootstrap] Failed to install {pkg}")

    if not _install_package("Cython"):
        print("Cython fallback failed, continuing...")


def autofill_env() -> None:
    env_path = Path(".env")
    if env_path.exists():
        text = env_path.read_text(encoding="utf-8")
        lines = text.splitlines()
    else:
        lines = []
    data = {}
    mapping = {
        "OPENAI_API_KEY": "",
        "MODEL_SLUG": "openai/gpt-4o",
        "SYSTEM_PROMPT": "You are Lumos...",
        "ENABLE_TTS": "true",
        "TTS_ENGINE": "pyttsx3",
    }
    keys = {ln.split("=", 1)[0] for ln in lines if "=" in ln and not ln.strip().startswith("#")}
    for k, v in mapping.items():
        if k not in keys:
            lines.append(f"{k}={v}")
            data[k] = v
    if data:
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        entry = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "added": data,
        }
        with ENV_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")


def check_files() -> list[str]:
    required = [
        "gui/cathedral_gui.py",
        "scripts/test_cathedral_boot.py",
        "model_bridge.py",
        "launch_sentientos.bat",
    ]
    missing = []
    for path in required:
        if not Path(path).exists():
            missing.append(path)
    if missing:
        print("[bootstrap] Missing files detected:")
        for m in missing:
            print(f" - {m}")
        print("Restore from templates if needed.")
    return missing


def log_result(status: str) -> None:
    entry = {
        "event_type": "bootstrap",
        "status": status,
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }
    with BOOT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def main() -> None:  # pragma: no cover - CLI
    warn_version()
    install_requirements()
    autofill_env()
    check_files()
    log_result("completed")
    print("Bootstrap completed.")


if __name__ == "__main__":
    main()

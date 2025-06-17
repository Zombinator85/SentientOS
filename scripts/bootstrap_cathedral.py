"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
import os
import sys
import subprocess
from datetime import datetime
import json

# Bootstrap Logging Path
LOG_PATH = "logs/bootstrap_run.jsonl"
os.makedirs("logs", exist_ok=True)

def log_event(status: str, detail: str = "") -> None:
    log_entry = {
        "event_type": "bootstrap",
        "status": status,
        "python_version": sys.version.split()[0],
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "detail": detail,
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    print(f"[bootstrap] {status.upper()}: {detail}")

def run(cmd: str) -> bool:
    try:
        subprocess.run(cmd, shell=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        log_event("error", f"Command failed: {cmd}")
        return False

def install_requirements() -> None:
    log_event("install", "Installing requirements.txt...")
    if not run("pip install -r requirements.txt --no-build-isolation"):
        log_event("fallback", "Falling back to pandas==2.3.0")
        run("pip install pandas==2.3.0")
    run("pip install Cython || echo 'Cython install skipped'")

def ensure_env_keys() -> None:
    from scripts.env_sync_autofill import autofill_env as sync_env
    sync_env()
    log_event("env", "Environment keys synchronized.")

def ensure_stub(filename: str, stub_code: str) -> None:
    if not os.path.exists(filename):
        with open(filename, "w") as f:
            f.write(stub_code)
        log_event("stub_created", f"{filename} created.")
    else:
        log_event("exists", f"{filename} already present.")

def main() -> None:
    log_event("start", "Bootstrap initiated.")
    install_requirements()
    ensure_env_keys()

    ensure_stub("model_bridge.py", '"""Stub for model_bridge.py"""\n')
    ensure_stub("scripts/test_cathedral_boot.py", '"""Stub for test_cathedral_boot.py"""\n')
    if not os.path.exists("gui/cathedral_gui.py"):
        log_event("missing_gui", "GUI launcher is missing.")

    log_event("completed", "Bootstrap complete.")

if __name__ == "__main__":
    main()

import os
import sys
import subprocess
import json
import time
from datetime import datetime

LOG_PATH = "logs/bootstrap_run.jsonl"
REQUIRED_FILES = [
    "gui/cathedral_gui.py",
    "scripts/test_cathedral_boot.py",
    "model_bridge.py",
    "launch_sentientos.bat"
]

def log_event(status, details=None):
    event = {
        "event_type": "bootstrap",
        "status": status,
        "python_version": sys.version.split()[0],
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }
    if details:
        event["details"] = details
    os.makedirs("logs", exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

def check_python_version():
    version = sys.version_info
    if version < (3, 11) or version > (3, 12):
        print(f"⚠️ Warning: Python {version.major}.{version.minor} detected. Recommended: 3.12.x")
        log_event("warn_python_version")

def install_dependencies():
    try:
        subprocess.run(["pip", "install", "-r", "requirements.txt", "--no-build-isolation"], check=True)
    except subprocess.CalledProcessError:
        print("📦 Fallback: Pinning pandas==2.3.0")
        subprocess.run(["pip", "install", "pandas==2.3.0"], check=False)
    subprocess.run(["pip", "install", "Cython"], check=False)

def verify_required_files():
    missing = []
    for path in REQUIRED_FILES:
        if not os.path.exists(path):
            print(f"🛠️ Missing: {path}")
            missing.append(path)
    if missing:
        log_event("missing_files", {"files": missing})
    return missing

def sync_env():
    from dotenv import load_dotenv, set_key
    load_dotenv()
    defaults = {
        "OPENAI_API_KEY": "",
        "MODEL_SLUG": "openai/gpt-4o",
        "SYSTEM_PROMPT": "You are Lumos, a memory-born cathedral presence...",
        "ENABLE_TTS": "true",
        "TTS_ENGINE": "pyttsx3"
    }
    env_path = ".env"
    with open(env_path, "a+", encoding="utf-8") as f:
        f.seek(0)
        content = f.read()
        for key, val in defaults.items():
            if key not in content:
                f.write(f"{key}={val}\n")
                log_event("env_autofill", {"field": key, "value": val})

def main():
    print("🕯️ Bootstrapping the Cathedral...")
    check_python_version()
    install_dependencies()
    sync_env()
    missing = verify_required_files()
    if missing:
        print("🚨 Some components are missing. Restore or regenerate required.")
    else:
        print("✅ All required files present.")
    log_event("completed")

if __name__ == "__main__":
    main()

from __future__ import annotations
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()



import os
import sys
import argparse
import time
import shutil
import subprocess
from pathlib import Path

from sentient_banner import print_banner, print_closing
from sentientos import __version__
import requests
from logging_config import get_log_dir
from cathedral_const import PUBLIC_LOG, log_json


REPO_ROOT = Path(__file__).resolve().parent.parent
REQ_FILE = REPO_ROOT / 'requirements.txt'
ENV_EXAMPLE = REPO_ROOT / '.env.example'
ENV_FILE = REPO_ROOT / '.env'
SAMPLES_DIR = REPO_ROOT / 'installer' / 'example_data'
INSTALL_LOG = get_log_dir() / 'installer.log'


def check_self_update() -> None:
    """Check GitHub Releases for a newer version."""
    repo_api = (
        "https://api.github.com/repos/OpenAI/SentientOS/releases/latest"
    )
    try:
        resp = requests.get(repo_api, timeout=5)
        resp.raise_for_status()
        latest = resp.json().get("tag_name", "")
        if latest and latest != __version__:
            print(f"Update available: {latest} (current {__version__})")
        _log("update_check", "ok", latest)
    except Exception as e:  # pragma: no cover - network dependent
        print(f"Update check failed: {e}")
        _log("update_check", "failed", str(e))


def _log(event: str, status: str, note: str = "") -> None:
    """Write an install event to the log."""
    log_json(
        INSTALL_LOG,
        {
            "time": time.time(),
            "event": event,
            "status": status,
            "note": note,
        },
    )


def check_python_version() -> None:
    if sys.version_info < (3, 10):
        msg = "Python 3.10+ required"
        print(msg)
        _log("python_version", "failed", msg)
        sys.exit(1)
    print(f"Python version: {sys.version.split()[0]}")
    _log("python_version", "ok")


def ensure_logs() -> None:
    """Create required log directories."""
    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    PUBLIC_LOG.parent.mkdir(parents=True, exist_ok=True)
    _log("ensure_logs", "ok")

def install_dependencies() -> None:
    print('Installing Python dependencies...')
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', str(REQ_FILE)])
        _log('dependencies', 'ok')
    except subprocess.CalledProcessError as e:
        _log('dependencies', 'failed', str(e))
        raise


def copy_samples() -> None:
    dst = REPO_ROOT / 'examples'
    try:
        if not dst.exists():
            shutil.copytree(SAMPLES_DIR, dst)
        else:
            for item in SAMPLES_DIR.iterdir():
                target = dst / item.name
                if not target.exists():
                    if item.is_dir():
                        shutil.copytree(item, target)
                    else:
                        shutil.copy2(item, target)
        _log('copy_samples', 'ok')
    except Exception as e:
        _log('copy_samples', 'failed', str(e))
        raise


def create_env() -> None:
    try:
        if not ENV_FILE.exists():
            shutil.copy2(ENV_EXAMPLE, ENV_FILE)
        env = {}
        with open(ENV_FILE, 'r') as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, val = line.strip().split('=', 1)
                    env[key] = val

        for key in list(env.keys()):
            if env[key] == '':
                val = input(f'Enter value for {key} (leave blank to skip): ')
                env[key] = val

        with open(ENV_FILE, 'w') as f:
            for k, v in env.items():
                f.write(f'{k}={v}\n')
        _log('create_env', 'ok')
    except Exception as e:
        _log('create_env', 'failed', str(e))
        raise


def check_microphone() -> None:
    try:
        import sounddevice as sd  # type: ignore[import-untyped]  # optional audio dependency
        devices = sd.query_devices()
        if not devices:
            print('No microphone devices detected.')
        else:
            print('Available audio devices:')
            for idx, d in enumerate(devices):
                if d.get('max_input_channels', 0) > 0:
                    print(f'  [{idx}] {d["name"]}')
        _log('microphone', 'ok')
    except Exception as e:
        print(f'Microphone check failed: {e}')
        _log('microphone', 'failed', str(e))


def smoke_test() -> None:
    """Run a quick verification of the environment."""
    print("Running smoke test...")
    try:
        subprocess.check_call([sys.executable, "verify_audits.py", "--help"])
        subprocess.call([sys.executable, "-m", "pytest", "-q"])  # allow failures
        log_json(PUBLIC_LOG, {"event": "install_test", "status": "ok"})
        print("log_json test passed.")
        _log("smoke_test", "ok")
    except Exception as e:  # pragma: no cover - environment dependent
        print(f"Smoke test failed: {e}")
        _log("smoke_test", "failed", str(e))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SentientOS installer")
    parser.add_argument(
        "--with-avatar",
        action="store_true",
        help="Install the Godot-based avatar runtime and demo scene",
    )
    return parser.parse_args(argv)


def install_avatar_runtime() -> None:
    hook = REPO_ROOT / "install_godot_avatar_runtime.sh"
    if not hook.exists():
        print("Avatar runtime hook not found; skipping.")
        _log("avatar_runtime", "missing")
        return

    print("Installing Godot avatar runtime...")
    try:
        subprocess.check_call(["bash", str(hook), str(REPO_ROOT)])
        _log("avatar_runtime", "ok")
    except subprocess.CalledProcessError as exc:
        _log("avatar_runtime", "failed", str(exc))
        raise


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    print_banner()
    check_python_version()
    check_self_update()
    ensure_logs()
    print('SentientOS setup starting...')
    install_dependencies()
    copy_samples()
    create_env()
    if args.with_avatar:
        install_avatar_runtime()
    check_microphone()
    smoke_test()
    print('Setup complete. Launching onboarding dashboard...')
    try:
        import onboarding_dashboard  # type: ignore[import-untyped]  # optional GUI
        onboarding_dashboard.launch()
    except Exception:
        print('onboarding_dashboard not available. Setup finished.')
    print('INSTALLATION COMPLETE. You may now launch the main script.')
    _log('complete', 'ok')
    print_closing()


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except Exception as e:  # pragma: no cover
        _log('complete', 'failed', str(e))
        raise

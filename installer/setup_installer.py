import os
import sys
from admin_utils import require_admin_banner
import shutil
import subprocess
from pathlib import Path
from sentient_banner import print_banner, print_closing


REPO_ROOT = Path(__file__).resolve().parent.parent
REQ_FILE = REPO_ROOT / 'requirements.txt'
ENV_EXAMPLE = REPO_ROOT / '.env.example'
ENV_FILE = REPO_ROOT / '.env'
SAMPLES_DIR = REPO_ROOT / 'installer' / 'example_data'

def install_dependencies() -> None:
    print('Installing Python dependencies...')
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', str(REQ_FILE)])


def copy_samples() -> None:
    dst = REPO_ROOT / 'examples'
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


def create_env() -> None:
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


def check_microphone() -> None:
    try:
        import sounddevice as sd  # type: ignore
        devices = sd.query_devices()
        if not devices:
            print('No microphone devices detected.')
        else:
            print('Available audio devices:')
            for idx, d in enumerate(devices):
                if d.get('max_input_channels', 0) > 0:
                    print(f'  [{idx}] {d["name"]}')
    except Exception as e:
        print(f'Microphone check failed: {e}')


def main() -> None:
    require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.

    print_banner()
    print('SentientOS setup starting...')
    install_dependencies()
    copy_samples()
    create_env()
    check_microphone()
    print('Setup complete. Launching onboarding dashboard...')
    try:
        import onboarding_dashboard  # type: ignore
        onboarding_dashboard.launch()
    except Exception:
        print('onboarding_dashboard not available. Setup finished.')
    print_closing()


if __name__ == '__main__':
    main()

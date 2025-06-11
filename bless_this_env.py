"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()
require_lumos_approval()
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval


import platform
import subprocess
import sys
from pathlib import Path

REQ_FILE = Path('requirements.txt')

INSTRUCTIONS = {
    'windows': (
        'If a dependency fails to build, ensure you have the Windows Build Tools '\
        'installed. Some packages like playsound require a pinned version:\n'\
        '    pip install playsound==1.2.2'
    ),
    'linux': (
        'If a dependency fails to build, install system headers such as build-essential '\
        'and libraries like libasound2-dev before running pip again.'
    ),
    'darwin': (
        'If a dependency fails to build, install the Xcode command line tools '\
        'and Homebrew packages like portaudio (brew install portaudio).'
    ),
}


def main() -> None:
    print('Blessing this environment...')
    try:
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-r', str(REQ_FILE)])
        print('All dependencies installed successfully.')
    except subprocess.CalledProcessError as exc:  # pragma: no cover - environment dependent
        system = platform.system().lower()
        print(f'Dependency installation failed: {exc}')
        print('Suggested workaround:')
        print(INSTRUCTIONS.get(system, INSTRUCTIONS['linux']))
        print('Once resolved, re-run this script.')


if __name__ == '__main__':
    main()

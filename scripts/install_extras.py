from __future__ import annotations

import argparse
import importlib
import subprocess
import sys
from pathlib import Path

import tomllib


def load_extras() -> dict[str, list[str]]:
    data = tomllib.loads(Path('pyproject.toml').read_text())
    return data.get('project', {}).get('optional-dependencies', {})


def _check_installed(packages: list[str]) -> list[str]:
    missing = []
    for name in packages:
        mod = name.split('[')[0].replace('-', '_')
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(name)
    return missing


def install(extra: str, soft: bool) -> int:
    extras = load_extras()
    pkgs = extras.get(extra, [])
    cmd = [sys.executable, '-m', 'pip', 'install', f'.[{extra}]']
    proc = subprocess.run(cmd)
    if proc.returncode != 0 and soft:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-binary', ':all:', f'.[{extra}]'], check=False)
    missing = _check_installed(pkgs)
    if missing:
        print('Missing packages:', ', '.join(missing))
    return 0 if soft else (1 if missing else 0)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('extra', nargs='?', default='all')
    parser.add_argument('--soft', action='store_true')
    args = parser.parse_args()
    code = install(args.extra, args.soft)
    sys.exit(code)


if __name__ == '__main__':
    main()

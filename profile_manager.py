"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import shutil
from pathlib import Path
from typing import Dict, List
import orchestrator
import sentient_banner as sb

# Profiles live under this directory. Each profile contains a `.env`, `memory/`,
# and `config.yaml` file.
PROFILES_DIR = Path('profiles')
CURRENT_FILE = PROFILES_DIR / '.current'
# Mirror of `.current` persisted in the user's home directory so the last
# profile is remembered across runs.
HOME_CURRENT = Path.home() / '.sentientos_profile'
TEMPLATE_DIR = PROFILES_DIR / 'template'


def list_profiles() -> List[str]:
    PROFILES_DIR.mkdir(exist_ok=True)
    return sorted([p.name for p in PROFILES_DIR.iterdir() if p.is_dir() and not p.name.startswith('.')])


def get_current_profile() -> str:
    for path in (CURRENT_FILE, HOME_CURRENT):
        if path.exists():
            name = path.read_text().strip()
            if name:
                return name
    names = list_profiles()
    return names[0] if names else 'default'


def _write_current(name: str) -> None:
    CURRENT_FILE.write_text(name)
    try:
        HOME_CURRENT.write_text(name)
    except Exception:
        pass


def load_env(profile: str) -> Dict[str, str]:
    env_path = PROFILES_DIR / profile / '.env'
    env: Dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.strip().startswith('#'):
                k, v = line.strip().split('=', 1)
                env[k] = v
    return env


def flush_agents() -> None:
    try:
        orchestrator.Orchestrator().stop()
    except Exception:
        pass


def restart_bridges() -> None:
    try:
        import bridge_watchdog
        bridge_watchdog._restart()  # type: ignore[attr-defined]
    except Exception:
        pass


def switch_profile(name: str) -> None:
    env = load_env(name)
    for k, v in env.items():
        os.environ[k] = v
    mem_dir = PROFILES_DIR / name / 'memory'
    os.environ['MEMORY_DIR'] = str(mem_dir.resolve())
    os.environ['CONFIG_PATH'] = str((PROFILES_DIR / name / 'config.yaml').resolve())
    os.environ['FALLBACK_EMOTION_PATH'] = str((PROFILES_DIR / name / 'fallback_emotion.yaml').resolve())
    _write_current(name)
    sb.set_current_profile(name)
    flush_agents()
    restart_bridges()


def create_profile(name: str) -> Path:
    dest = PROFILES_DIR / name
    if dest.exists():
        raise FileExistsError(name)
    if TEMPLATE_DIR.exists():
        shutil.copytree(TEMPLATE_DIR, dest)
    else:
        dest.mkdir(parents=True)
    # Ensure required files exist
    (dest / 'memory').mkdir(parents=True, exist_ok=True)
    (dest / '.env').write_text('', encoding='utf-8')
    (dest / 'config.yaml').write_text('name: ' + name, encoding='utf-8')
    (dest / 'fallback_emotion.yaml').write_text(
        'analytical: 0.4\ncurious: 0.6\n',
        encoding='utf-8',
    )
    return dest

from __future__ import annotations
import os
import shutil
from pathlib import Path
from typing import Dict, List
import orchestrator
import sentient_banner as sb

PROFILES_DIR = Path('profiles')
CURRENT_FILE = PROFILES_DIR / '.current'
TEMPLATE_DIR = PROFILES_DIR / 'template'


def list_profiles() -> List[str]:
    PROFILES_DIR.mkdir(exist_ok=True)
    return sorted([p.name for p in PROFILES_DIR.iterdir() if p.is_dir() and not p.name.startswith('.')])


def get_current_profile() -> str:
    if CURRENT_FILE.exists():
        return CURRENT_FILE.read_text().strip() or 'default'
    names = list_profiles()
    return names[0] if names else 'default'


def _write_current(name: str) -> None:
    CURRENT_FILE.write_text(name)


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
        (dest / 'memory').mkdir(parents=True, exist_ok=True)
        (dest / '.env').write_text('', encoding='utf-8')
        (dest / 'config.yaml').write_text('name: ' + name, encoding='utf-8')
        (dest / 'fallback_emotion.yaml').write_text(
            'analytical: 0.4\ncurious: 0.6\n',
            encoding='utf-8',
        )
    return dest

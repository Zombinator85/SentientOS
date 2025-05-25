import os
import json
from pathlib import Path

MEMORY_DIR = Path(os.getenv("MEMORY_DIR", "logs/memory"))
PROFILE_PATH = MEMORY_DIR / "profile.json"


def load_profile() -> dict:
    """Load the user profile from disk."""
    if PROFILE_PATH.exists():
        try:
            return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_profile(profile: dict) -> None:
    """Persist the profile to disk."""
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def update_profile(**updates) -> dict:
    """Update profile values and save."""
    profile = load_profile()
    profile.update({k: v for k, v in updates.items() if v is not None})
    save_profile(profile)
    return profile


def format_profile() -> str:
    """Return profile as formatted lines for prompt injection."""
    profile = load_profile()
    lines = [f"- {k}: {v}" for k, v in profile.items()]
    return "\n".join(lines)

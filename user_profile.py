import os
import json
from pathlib import Path
import getpass

import ritual
import relationship_log as rl

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
    profile_exists = PROFILE_PATH.exists()
    profile = load_profile()
    if not profile_exists:
        ritual.require_liturgy_acceptance()
        user = getpass.getuser()
        rl.log_event("ceremonial_welcome", user)
        rl.log_event("profile_created", user)
    profile.update({k: v for k, v in updates.items() if v is not None})
    save_profile(profile)
    return profile


def forget_keys(keys: list[str]) -> dict:
    profile = load_profile()
    for k in keys:
        profile.pop(k, None)
    save_profile(profile)
    return profile


def format_profile() -> str:
    """Return profile as formatted lines for prompt injection."""
    profile = load_profile()
    lines = [f"- {k}: {v}" for k, v in profile.items()]
    return "\n".join(lines)


def auto_update_profile(text: str) -> None:
    """Very naive fact extraction from ``text`` and update profile."""
    text_low = text.lower()
    updates = {}
    if "my name is" in text_low:
        parts = text_low.split("my name is", 1)[1].strip().split()
        if parts:
            updates["name"] = parts[0].strip(".,!")
    if "favorite animal is" in text_low:
        parts = text_low.split("favorite animal is", 1)[1].strip().split()
        if parts:
            updates["favorite_animal"] = parts[0].strip(".,!")
    if "my hobby is" in text_low:
        parts = text_low.split("my hobby is", 1)[1].strip().split()
        if parts:
            updates["hobby"] = parts[0].strip(".,!")
    if updates:
        update_profile(**updates)

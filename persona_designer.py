import json
from pathlib import Path
from typing import Any, Dict

from admin_utils import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
try:
    import streamlit as st  # type: ignore
except Exception:  # pragma: no cover - optional
    st = None

PERSONA_DIR = Path("personas")
PERSONA_DIR.mkdir(parents=True, exist_ok=True)


def save_persona(name: str, data: Dict[str, Any]) -> Path:
    path = PERSONA_DIR / f"{name}.json"
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def run_app() -> None:
    if st is None:
        print("streamlit not available")
        return
    st.set_page_config(page_title="Persona Designer", layout="centered")
    st.title("Persona Designer")
    name = st.text_input("Persona name")
    traits = st.text_area("Traits", "Friendly and helpful")
    voice = st.text_input("Voice file/path")
    seed = st.text_area("Seed memory")
    if st.button("Save") and name:
        data = {"traits": traits, "voice": voice, "seed": seed}
        path = save_persona(name, data)
        st.success(f"Saved to {path}")


if __name__ == "__main__":  # pragma: no cover - manual usage
    run_app()

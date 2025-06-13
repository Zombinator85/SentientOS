"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import os
import sys
from pathlib import Path
import streamlit as st
from sentient_banner import streamlit_banner, streamlit_closing
import profile_manager as pm
from sentientos import __version__
import ledger
import requests


def env_file() -> Path:
    return pm.PROFILES_DIR / pm.get_current_profile() / '.env'


def load_env() -> dict:
    env = {}
    fp = env_file()
    if fp.exists():
        with open(fp) as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    k, v = line.strip().split('=', 1)
                    env[k] = v
    return env


def show_help(env: dict) -> None:
    """Display environment help messages."""
    if not env.get("OPENAI_API_KEY"):
        st.error("OPENAI_API_KEY missing. Please edit the .env file.")
    try:
        import torch  # type: ignore[import-untyped]
        if not torch.cuda.is_available():
            st.warning("GPU not detected. The system may run slowly.")
    except Exception as e:
        st.warning(f"GPU check failed: {e}")
    st.info(f"Python version: {sys.version.split()[0]}")
    if st.button("Check for Updates"):
        st.write(check_updates())
    st.info("Set RELAY_LOG_LEVEL=DEBUG in .env for verbose relay logs.")


def check_updates() -> str:
    repo_api = "https://api.github.com/repos/OpenAI/SentientOS/releases/latest"
    try:
        resp = requests.get(repo_api, timeout=5)
        resp.raise_for_status()
        latest = resp.json().get("tag_name", "")
        if latest and latest != __version__:
            return f"Update available: {latest} (current {__version__})"
        return "You are up to date."
    except Exception as e:
        return f"Update check failed: {e}"


def launch() -> None:
    profiles = pm.list_profiles()
    current = pm.get_current_profile()
    st.title('SentientOS Onboarding')
    selected = st.selectbox('Persona Profile', profiles, index=profiles.index(current) if current in profiles else 0)
    new_name = st.text_input('Create profile', key='new_profile_name')
    if st.button('Create', key='create_profile') and new_name:
        pm.create_profile(new_name)
        profiles = pm.list_profiles()
        selected = new_name
        pm.switch_profile(selected)
        st.session_state.active_profile = selected
        st.experimental_rerun()
    if 'active_profile' not in st.session_state:
        st.session_state.active_profile = current
    if selected != st.session_state.active_profile:
        pm.switch_profile(selected)
        st.session_state.active_profile = selected
        st.experimental_rerun()
    env = load_env()
    streamlit_banner(st)
    ledger.streamlit_widget(st)
    show_help(env)
    st.write('Active models:')
    st.json({k: v for k, v in env.items() if k.endswith('_MODEL')})
    handle = env.get('USER_HANDLE', 'anonymous')
    st.write(f'User handle: {handle}')
    st.write('You can edit the .env file to configure additional options.')
    st.write('To be remembered in this cathedral is to be entered in the living ledger.')
    streamlit_closing(st)


if __name__ == '__main__':
    launch()

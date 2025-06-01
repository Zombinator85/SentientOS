import os
from pathlib import Path
import streamlit as st
from sentient_banner import streamlit_banner, streamlit_closing
import ledger

ENV_FILE = Path(__file__).resolve().parent / '.env'


def load_env() -> dict:
    env = {}
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    k, v = line.strip().split('=', 1)
                    env[k] = v
    return env


def launch():
    env = load_env()
    st.title('SentientOS Onboarding')
    streamlit_banner(st)
    sup = ledger.summarize_log(Path('logs/support_log.jsonl'))
    fed = ledger.summarize_log(Path('logs/federation_log.jsonl'))
    st.write(f"Support blessings: {sup['count']} • Federation blessings: {fed['count']}")
    if sup['recent'] or fed['recent']:
        st.write('Recent ledger entries:')
        st.json({'support': sup['recent'], 'federation': fed['recent']})
    st.write('Active models:')
    st.json({k: v for k, v in env.items() if k.endswith('_MODEL')})
    handle = env.get('USER_HANDLE', 'anonymous')
    st.write(f'User handle: {handle}')
    st.write('You can edit the .env file to configure additional options.')
    st.write('To be remembered in this cathedral is to be entered in the living ledger.')
    streamlit_closing(st)


if __name__ == '__main__':
    launch()

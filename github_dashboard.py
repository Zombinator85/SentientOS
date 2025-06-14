"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from pathlib import Path
import json

try:
    import streamlit as st
except Exception:  # pragma: no cover - optional
    st = None

from github_bridge import GitHubBridge
from sentient_banner import streamlit_banner, streamlit_closing
from logging_config import get_log_path

LOG_FILE = get_log_path("github_actions.jsonl", "GITHUB_ACTION_LOG")

def run_app() -> None:
    if st is None:
        print("streamlit not available")
        return
    bridge = GitHubBridge()
    st.title("GitHub Bridge Panel")
    streamlit_banner(st)

    model = st.text_input("Model name", "default")
    token = st.text_input("Token", type="password")
    scopes = st.text_input("Required Scopes", "repo")
    if st.button("Test & Save") and token:
        try:
            bridge.set_token(model, token, scopes=[s.strip() for s in scopes.split(',') if s.strip()])
        except Exception as e:
            st.error(str(e))
        else:
            st.success("Token saved")

    read_scope = st.checkbox("Allow read", value=True)
    write_scope = st.checkbox("Allow write")
    pr_scope = st.checkbox("Allow PR", value=False)

    st.header("Search Code")
    query = st.text_input("Query")
    if st.button("Search") and query:
        if not read_scope:
            st.error("Read scope disabled")
        else:
            try:
                res = bridge.search_code(query, model=model)
                st.json(res)
            except Exception as e:  # pragma: no cover - network
                st.error(str(e))

    st.header("Create Issue")
    repo = st.text_input("Repo (owner/repo)")
    title = st.text_input("Issue Title")
    body = st.text_area("Issue Body")
    if st.button("Post Issue"):
        if not write_scope:
            st.error("Write scope disabled")
        else:
            try:
                issue = bridge.create_issue(repo, title, body, model=model)
                st.write(issue.get("html_url"))
            except Exception as e:  # pragma: no cover - network
                st.error(str(e))

    st.header("Create Pull Request")
    head = st.text_input("Head Branch")
    base = st.text_input("Base Branch")
    if st.button("Open PR"):
        if not pr_scope:
            st.error("PR scope disabled")
        else:
            try:
                pr = bridge.create_pr(repo, title, body, head, base, model=model)
                st.write(pr.get("html_url"))
            except Exception as e:  # pragma: no cover - network
                st.error(str(e))

    st.header("Action Log")
    if Path(LOG_FILE).exists():
        lines = Path(LOG_FILE).read_text(encoding="utf-8").splitlines()[-50:]
        for line in reversed(lines):
            st.json(json.loads(line))
    streamlit_closing(st)

if __name__ == "__main__":  # pragma: no cover - manual
    run_app()

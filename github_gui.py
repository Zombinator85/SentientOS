"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

"""Simple GUI for creating GitHub issues and pull requests."""

try:
    import streamlit as st  # pragma: no cover - optional
except Exception:  # pragma: no cover - optional
    st = None

from github_bridge import create_issue, create_pull_request


def run_app() -> None:
    if st is None:
        print("streamlit not available")
        return

    st.title("GitHub Composer")

    action = st.radio("Action", ["Issue", "Pull Request"])
    repo = st.text_input("Repo (owner/repo)")
    token = st.text_input("Token", type="password")

    title = st.text_input("Title")
    body = st.text_area("Body")

    if action == "Pull Request":
        head = st.text_input("Head Branch")
        base = st.text_input("Base Branch")

    if st.button("Submit") and repo and title and token:
        try:
            if action == "Issue":
                issue = create_issue(repo, title, body, token=token)
                st.write(issue.get("html_url"))
            else:
                pr = create_pull_request(repo, title, body, head, base, token=token)
                st.write(pr.get("html_url"))
        except Exception as e:  # pragma: no cover - network
            st.error(str(e))


if __name__ == "__main__":  # pragma: no cover - manual
    run_app()

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from urllib import request, parse


from admin_utils import require_admin_banner
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
try:
    import streamlit as st
except Exception:  # pragma: no cover - optional
    st = None


def load_storyboard(path: str | Path) -> Dict[str, Any]:
    data_path = Path(path)
    if not data_path.exists():
        return {"chapters": []}
    try:
        return json.loads(data_path.read_text(encoding="utf-8"))
    except Exception:
        return {"chapters": []}


def save_storyboard(data: Dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(json.dumps(data, indent=2), encoding="utf-8")


def reorder_chapters(chapters: List[Dict[str, Any]], order: List[int]) -> List[Dict[str, Any]]:
    mapping = {c.get("chapter", i + 1): c for i, c in enumerate(chapters)}
    new_list: List[Dict[str, Any]] = []
    for idx in order:
        ch = mapping.get(idx)
        if ch:
            new_list.append(ch)
    # Renumber
    for i, ch in enumerate(new_list, 1):
        ch["chapter"] = i
    return new_list


class CollabClient:
    """Very small HTTP long-polling client for collaboration."""

    def __init__(self, url: str, persona: str = "Author"):
        import uuid
        self.url = url.rstrip('/')
        self.client_id = uuid.uuid4().hex
        self.updates: List[Dict[str, Any]] = []
        self.online: List[str] = []
        self.users: List[Dict[str, Any]] = []
        self.persona = persona
        try:
            data = parse.urlencode({"id": self.client_id, "persona": persona}).encode()
            request.urlopen(f"{self.url}/connect", data=data, timeout=0.1)
        except Exception:
            pass

    def poll(self) -> None:
        try:
            with request.urlopen(f"{self.url}/poll", timeout=0.1) as resp:
                data = json.loads(resp.read().decode())
                self.updates.extend(data)
            data = parse.urlencode({"id": self.client_id}).encode()
            with request.urlopen(f"{self.url}/connect", data=data, timeout=0.1) as resp:
                info = json.loads(resp.read().decode())
                self.online = info.get("online", [])
                self.users = info.get("users", [])
        except Exception:
            pass

    def send_edit(self, chapter: int, text: str) -> None:
        try:
            data = json.dumps({"id": self.client_id, "chapter": chapter, "text": text}).encode()
            req = request.Request(
                f"{self.url}/edit", data=data, headers={"Content-Type": "application/json"}
            )
            request.urlopen(req, timeout=0.1)
        except Exception:
            pass

    def send_update(self, chapter: int | None = None, persona: str | None = None) -> None:
        payload = {"id": self.client_id}
        if chapter is not None:
            payload["chapter"] = chapter
        if persona is not None:
            self.persona = persona
            payload["persona"] = persona
        try:
            req = request.Request(
                f"{self.url}/update", data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
            )
            request.urlopen(req, timeout=0.1)
        except Exception:
            pass

    def close(self) -> None:
        try:
            data = parse.urlencode({"id": self.client_id}).encode()
            request.urlopen(f"{self.url}/disconnect", data=data, timeout=0.1)
        except Exception:
            pass



def run_editor(storyboard_path: str, server: Optional[str] = None) -> None:
    if st is None:
        print("Streamlit not available. Install dependencies to run editor.")
        return
    st.set_page_config(page_title="Story Studio", layout="wide")
    st.title("Story Studio")

    if "orig_data" not in st.session_state:
        st.session_state.orig_data = load_storyboard(storyboard_path)
        st.session_state.chapters = [c.copy() for c in st.session_state.orig_data.get("chapters", [])]

    chapters: List[Dict[str, Any]] = st.session_state.chapters

    collab: Optional[CollabClient] = None
    if server:
        if "persona" not in st.session_state:
            st.session_state.persona = "Author"
        if "collab" not in st.session_state:
            try:
                st.session_state.collab = CollabClient(server, st.session_state.persona)
            except Exception as e:  # pragma: no cover - network
                st.warning(f"Collaboration disabled: {e}")
        collab = st.session_state.get("collab")
        if collab:
            collab.poll()
            st.sidebar.write(f"Online users: {len(collab.online)}")
            st.sidebar.table(collab.users)
            persona = st.sidebar.text_input("Persona", value=st.session_state.persona)
            if persona != st.session_state.persona:
                st.session_state.persona = persona
                collab.send_update(persona=persona)
            while collab.updates:
                upd = collab.updates.pop(0)
                idx = upd.get("chapter", 0) - 1
                if 0 <= idx < len(chapters):
                    chapters[idx]["text"] = upd.get("text", chapters[idx].get("text", ""))

    for i, ch in enumerate(chapters):
        st.subheader(f"Chapter {i+1}")
        cols = st.columns([10, 1])
        with cols[0]:
            text = st.text_area("Text", value=ch.get("text", ""), key=f"text_{i}")
            highlight = st.checkbox("Highlight", value=ch.get("highlight", False), key=f"hl_{i}")
            comment = st.text_input("Comment", value=ch.get("comment", ""), key=f"comment_{i}")
            ch["text"] = text
            ch["highlight"] = highlight
            ch["comment"] = comment
            if collab:
                collab.send_edit(i + 1, text)
                collab.send_update(chapter=i + 1)
        with cols[1]:
            if st.button("↑", key=f"up_{i}") and i > 0:
                chapters[i-1], chapters[i] = chapters[i], chapters[i-1]
                st.experimental_rerun()
            if st.button("↓", key=f"down_{i}") and i < len(chapters) - 1:
                chapters[i+1], chapters[i] = chapters[i], chapters[i+1]
                st.experimental_rerun()
        st.markdown("---")
    if st.button("Save"):
        for i, ch in enumerate(chapters, 1):
            ch["chapter"] = i
        save_storyboard({"chapters": chapters}, storyboard_path)
        st.session_state.orig_data = {"chapters": [c.copy() for c in chapters]}
        st.success("Saved")
    if st.button("Reset"):
        st.session_state.chapters = [c.copy() for c in st.session_state.orig_data.get("chapters", [])]
        st.experimental_rerun()
    if st.button("Export HTML"):
        from storymaker import export_web
        tmp = Path(storyboard_path).with_suffix(".studio.html")
        export_web(storyboard_path, str(tmp))
        st.write(f"Exported to {tmp}")


def main(argv: Optional[List[str]] = None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        print("Usage: story_studio.py STORYBOARD.json [--server URL]")
        return
    path = argv[0]
    server = None
    if "--server" in argv:
        idx = argv.index("--server")
        if idx + 1 < len(argv):
            server = argv[idx + 1]
    run_editor(path, server)


if __name__ == "__main__":
    main()

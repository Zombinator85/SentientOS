import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def run_editor(storyboard_path: str) -> None:
    if st is None:
        print("Streamlit not available. Install dependencies to run editor.")
        return
    st.set_page_config(page_title="Story Studio", layout="wide")
    st.title("Story Studio")
    data = load_storyboard(storyboard_path)
    chapters: List[Dict[str, Any]] = data.get("chapters", [])
    order = [ch.get("chapter", i + 1) for i, ch in enumerate(chapters)]
    new_chapters: List[Dict[str, Any]] = []
    for ch in chapters:
        idx = ch.get("chapter") or (len(new_chapters) + 1)
        st.subheader(f"Chapter {idx}")
        text = st.text_area("Text", value=ch.get("text", ""), key=f"text_{idx}")
        highlight = st.checkbox("Highlight", value=ch.get("highlight", False), key=f"hl_{idx}")
        comment = st.text_input("Comment", value=ch.get("comment", ""), key=f"comment_{idx}")
        order_idx = st.number_input("Order", min_value=1, max_value=len(chapters), value=idx, key=f"ord_{idx}")
        new_chapters.append({
            **ch,
            "text": text,
            "highlight": highlight,
            "comment": comment,
            "order": int(order_idx),
        })
        st.markdown("---")
    if st.button("Save"):
        new_chapters.sort(key=lambda c: c.get("order", c.get("chapter", 0)))
        for i, ch in enumerate(new_chapters, 1):
            ch.pop("order", None)
            ch["chapter"] = i
        data["chapters"] = new_chapters
        save_storyboard(data, storyboard_path)
        st.success("Saved")
    if st.button("Export HTML"):
        from storymaker import export_web
        tmp = Path(storyboard_path).with_suffix(".studio.html")
        export_web(storyboard_path, str(tmp))
        st.write(f"Exported to {tmp}")


def main(argv: Optional[List[str]] = None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        print("Usage: story_studio.py STORYBOARD.json")
        return
    run_editor(argv[0])


if __name__ == "__main__":
    main()

import argparse
from pathlib import Path

from story_studio import load_storyboard, save_storyboard


def annotate(path: Path, chapter: int, text: str) -> None:
    data = load_storyboard(path)
    ch = data.get("chapters", [])[chapter - 1]
    ch.setdefault("annotations", []).append(text)
    save_storyboard(data, path)


def suggest_edit(path: Path, chapter: int, text: str) -> None:
    data = load_storyboard(path)
    ch = data.get("chapters", [])[chapter - 1]
    ch.setdefault("suggestions", []).append(text)
    save_storyboard(data, path)


def resolve_comment(path: Path, chapter: int, index: int) -> None:
    data = load_storyboard(path)
    ch = data.get("chapters", [])[chapter - 1]
    ann = ch.get("annotations", [])
    if 0 <= index < len(ann):
        ann.pop(index)
    save_storyboard(data, path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("storyboard")
    parser.add_argument("--annotate")
    parser.add_argument("--suggest-edit")
    parser.add_argument("--resolve-comment", nargs=2)
    parser.add_argument("--chapter", type=int, default=1)
    args = parser.parse_args()

    path = Path(args.storyboard)
    if args.annotate:
        annotate(path, args.chapter, args.annotate)
    if args.suggest_edit:
        suggest_edit(path, args.chapter, args.suggest_edit)
    if args.resolve_comment:
        resolve_comment(path, args.chapter, int(args.resolve_comment[1]))


if __name__ == "__main__":
    main()

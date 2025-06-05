import argparse
from pathlib import Path
from sentient_banner import print_banner, print_closing
from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

from story_studio import load_storyboard, save_storyboard
import user_profile as up
import notification
import re


def annotate(path: Path, chapter: int, text: str) -> None:
    data = load_storyboard(path)
    ch = data.get("chapters", [])[chapter - 1]
    ch.setdefault("annotations", []).append(text)
    mentions = re.findall(r"@(\w+)", text)
    if mentions:
        notification.send("mention", {"chapter": chapter, "targets": mentions, "text": text})
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

def set_status(path: Path, chapter: int, status: str) -> None:
    data = load_storyboard(path)
    ch = data.get("chapters", [])[chapter - 1]
    ch["status"] = status
    save_storyboard(data, path)


def main() -> None:
    require_admin_banner()
    # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
    parser = argparse.ArgumentParser()
    parser.add_argument("storyboard")
    parser.add_argument("--annotate")
    parser.add_argument("--suggest-edit")
    parser.add_argument("--resolve-comment", nargs=2)
    parser.add_argument("--chapter", type=int, default=1)
    parser.add_argument("--set-status")
    parser.add_argument("--mention")
    parser.add_argument("--whoami", action="store_true")
    parser.add_argument("--switch-persona")
    args = parser.parse_args()
    print_banner()

    if args.whoami:
        prof = up.load_profile()
        print(f"User: {prof.get('user','')} Persona: {prof.get('persona','')}")
        return
    if args.switch_persona:
        up.update_profile(persona=args.switch_persona)
        print(f"Persona switched to {args.switch_persona}")
        return

    path = Path(args.storyboard)
    if args.annotate:
        text = args.annotate
        if args.mention:
            text = f"@{args.mention} {text}"
        annotate(path, args.chapter, text)
    if args.suggest_edit:
        suggest_edit(path, args.chapter, args.suggest_edit)
    if args.resolve_comment:
        resolve_comment(path, args.chapter, int(args.resolve_comment[1]))
    if args.set_status:
        set_status(path, args.chapter, args.set_status)
    print_closing()


if __name__ == "__main__":
    main()

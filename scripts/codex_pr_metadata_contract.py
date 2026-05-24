from __future__ import annotations

import argparse
import json
from pathlib import Path

from sentientos.codex_pr_metadata_contract import build_body_from_json_text, verify_pr_metadata


def _read_inline_or_file(inline: str | None, file_path: str | None) -> str:
    if inline is not None:
        return inline
    if file_path is not None:
        return Path(file_path).read_text(encoding="utf-8")
    return ""


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    verify = sub.add_parser("verify")
    verify.add_argument("--title")
    verify.add_argument("--title-file")
    verify.add_argument("--body")
    verify.add_argument("--body-file")
    verify.add_argument("--intended-commit-title")
    verify.add_argument("--summary", action="store_true")

    build = sub.add_parser("build")
    build.add_argument("--rollup-json")
    build.add_argument("--rollup-json-file")

    args = p.parse_args(argv)
    if args.cmd == "verify":
        title = _read_inline_or_file(args.title, args.title_file).strip()
        body = _read_inline_or_file(args.body, args.body_file)
        result = verify_pr_metadata(pr_title=title, pr_body=body, intended_commit_title=args.intended_commit_title)
        payload = result.to_dict()
        if args.summary:
            print(json.dumps({"status": payload["status"], "title_ok": payload["title_ok"], "missing_body_marker_count": len(payload["missing_body_markers"])}))
        else:
            print(json.dumps(payload, indent=2, sort_keys=True))
        return 0 if result.status == "codex_pr_metadata_contract_ready" else 1

    rollup_json = _read_inline_or_file(args.rollup_json, args.rollup_json_file)
    print(build_body_from_json_text(rollup_json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""CLI for managing gesture/persona plug-ins."""

import argparse
import json
import plugin_framework as pf


def main() -> None:
    pf.load_plugins()
    ap = argparse.ArgumentParser(prog="plugins")
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("list")
    t = sub.add_parser("test")
    t.add_argument("plugin_id")
    d = sub.add_parser("doc")
    d.add_argument("plugin_id")

    args = ap.parse_args()

    if args.cmd == "list":
        for name, desc in pf.list_plugins().items():
            print(f"{name}: {desc}")
    elif args.cmd == "test":
        out = pf.test_plugin(args.plugin_id)
        print(json.dumps(out, indent=2))
    elif args.cmd == "doc":
        info = pf.plugin_doc(args.plugin_id)
        print(json.dumps(info, indent=2))
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()

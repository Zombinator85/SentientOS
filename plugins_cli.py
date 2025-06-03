import argparse
import json
import plugin_framework as pf
from sentient_banner import print_banner, print_closing, ENTRY_BANNER
from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.


def main() -> None:
    require_admin_banner()
    # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
    pf.load_plugins()
    ap = argparse.ArgumentParser(prog="plugins", description=ENTRY_BANNER)
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("list")
    sub.add_parser("status")
    sub.add_parser("reload")
    t = sub.add_parser("test")
    t.add_argument("plugin_id")
    d = sub.add_parser("doc")
    d.add_argument("plugin_id")
    en = sub.add_parser("enable")
    en.add_argument("plugin_id")
    di = sub.add_parser("disable")
    di.add_argument("plugin_id")

    args = ap.parse_args()
    print_banner()

    if args.cmd == "list":
        for name, desc in pf.list_plugins().items():
            print(f"{name}: {desc}")
    elif args.cmd == "status":
        for name, enabled in pf.plugin_status().items():
            status = "enabled" if enabled else "disabled"
            print(f"{name}: {status}")
    elif args.cmd == "reload":
        pf.reload_plugins(user="cli")
        print("Reloaded")
    elif args.cmd == "test":
        out = pf.test_plugin(args.plugin_id)
        print(json.dumps(out, indent=2))
    elif args.cmd == "doc":
        info = pf.plugin_doc(args.plugin_id)
        print(json.dumps(info, indent=2))
    elif args.cmd == "enable":
        pf.enable_plugin(args.plugin_id, user="cli")
        print(f"Enabled {args.plugin_id}")
    elif args.cmd == "disable":
        pf.disable_plugin(args.plugin_id, user="cli")
        print(f"Disabled {args.plugin_id}")
    else:
        ap.print_help()
    print_closing()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()

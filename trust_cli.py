import argparse
import json
from pprint import pprint
import support_log as sl
from admin_utils import require_admin_banner

import trust_engine as te
from sentient_banner import print_banner, print_closing, ENTRY_BANNER
import support_log as sl

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""


def cmd_log(args) -> None:
    events = te.list_events(limit=args.last)
    for e in events:
        print(f"{e['timestamp']} {e['id']} {e['type']} -> {e['explanation']}")
        sl.add(e.get('source', 'anon'), f"analysis blessing: trust {e.get('id')}")


def cmd_explain(args) -> None:
    e = te.get_event(args.event_id)
    if not e:
        print("Event not found")
        return
    pprint(e)
    sl.add(e.get('source', 'anon'), f"analysis blessing: trust {e.get('id')}")


def cmd_diff(args) -> None:
    diff = te.diff_policy(args.policy)
    print("\n".join(diff))


def cmd_rollback(args) -> None:
    res = te.rollback_policy(args.policy)
    if res:
        print(f"Rolled back to {res}")
    else:
        print("No rollback performed")


def main() -> None:
    require_admin_banner()
    # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
    ap = argparse.ArgumentParser(prog="trust", description=ENTRY_BANNER)
    sub = ap.add_subparsers(dest="cmd")

    logp = sub.add_parser("log")
    logp.add_argument("--last", type=int, default=10)
    logp.set_defaults(func=cmd_log)

    ex = sub.add_parser("explain")
    ex.add_argument("event_id")
    ex.set_defaults(func=cmd_explain)

    df = sub.add_parser("diff")
    df.add_argument("policy")
    df.set_defaults(func=cmd_diff)

    rb = sub.add_parser("rollback")
    rb.add_argument("policy")
    rb.set_defaults(func=cmd_rollback)

    args = ap.parse_args()
    print_banner()
    sl.add("trust", f"trust_cli {args.cmd}")
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()
    print_closing()


if __name__ == "__main__":
    main()

import argparse
import os
import sys
import json
from pathlib import Path
import review_requests as rr
import final_approval


def main() -> None:
    parser = argparse.ArgumentParser(description="Policy/reflex suggestions")
    parser.add_argument(
        "--final-approvers",
        default=os.getenv("REQUIRED_FINAL_APPROVER", "4o"),
        help="Comma separated list or config file of required approvers",
    )
    parser.add_argument(
        "--final-approver-file",
        help="JSON file listing approvers to require at runtime",
    )
    sub = parser.add_subparsers(dest="cmd")

    l = sub.add_parser("list")
    l.add_argument("--status", default="pending")

    ex = sub.add_parser("explain")
    ex.add_argument("id")

    c = sub.add_parser("comment")
    c.add_argument("id")
    c.add_argument("text")
    c.add_argument("--user", required=True)

    v = sub.add_parser("vote")
    v.add_argument("id")
    v.add_argument("--user", required=True)
    v.add_argument("--down", action="store_true")

    a = sub.add_parser("assign")
    a.add_argument("id")
    a.add_argument("--agent")
    a.add_argument("--persona")

    ch = sub.add_parser("chain")
    ch.add_argument("id")

    pr = sub.add_parser("provenance")
    pr.add_argument("id")

    sub.add_parser("accept").add_argument("id")
    sub.add_parser("dismiss").add_argument("id")

    args = parser.parse_args()
    if args.final_approver_file:
        fp = Path(args.final_approver_file)
        if fp.exists():
            final_approval.override_approvers(json.loads(fp.read_text()))
        else:
            final_approval.override_approvers([])
    elif args.final_approvers:
        fp = Path(args.final_approvers)
        if fp.exists():
            final_approval.override_approvers(json.loads(fp.read_text()))
        else:
            final_approval.override_approvers(
                [a.strip() for a in args.final_approvers.split(",") if a.strip()]
            )

    if args.cmd == "list":
        for s in rr.list_requests(args.status):
            if "suggestion" in s:
                print(f"{s['id']} {s['suggestion']}")
    elif args.cmd == "explain":
        s = rr.get_request(args.id)
        if s:
            print(s.get("rationale", ""))
    elif args.cmd == "comment":
        rr.comment_request(args.id, args.user, args.text)
    elif args.cmd == "vote":
        rr.vote_request(args.id, args.user, upvote=not args.down)
    elif args.cmd == "assign":
        rr.assign_request(args.id, agent=args.agent, persona=args.persona)
    elif args.cmd == "accept":
        rr.implement_request(args.id)
    elif args.cmd == "dismiss":
        rr.dismiss_request(args.id)
    elif args.cmd == "chain":
        for item in rr.get_chain(args.id):
            print(f"{item['id']} {item.get('status')} {item.get('suggestion')}")
    elif args.cmd == "provenance":
        for entry in rr.get_provenance(args.id):
            print(json.dumps(entry))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

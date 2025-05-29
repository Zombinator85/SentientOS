import argparse
import json
import reflection_stream as rs


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reflection stream CLI")
    sub = parser.add_subparsers(dest="cmd")
    log = sub.add_parser("log", help="Show recent reflection events")
    log.add_argument("--last", type=int, default=5)
    exp = sub.add_parser("explain", help="Show details of an event")
    exp.add_argument("id")
    sub.add_parser("stats", help="Show event statistics")

    args = parser.parse_args(argv)
    if args.cmd == "log":
        print(json.dumps(rs.recent(args.last), indent=2))
    elif args.cmd == "explain":
        print(json.dumps(rs.get(args.id), indent=2))
    elif args.cmd == "stats":
        print(json.dumps(rs.stats(), indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

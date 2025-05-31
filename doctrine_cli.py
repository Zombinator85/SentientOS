import argparse
import ritual


def cmd_show(args) -> None:
    print(ritual.LITURGY_FILE.read_text())


def cmd_accept(args) -> None:
    ritual.require_liturgy_acceptance()
    print("Doctrine affirmed.")


def main() -> None:
    ap = argparse.ArgumentParser(prog="doctrine")
    sub = ap.add_subparsers(dest="cmd")

    sh = sub.add_parser("show", help="Display the SentientOS liturgy")
    sh.set_defaults(func=cmd_show)

    ac = sub.add_parser("affirm", help="Affirm the liturgy")
    ac.set_defaults(func=cmd_accept)

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()

import argparse
import daily_theme


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily theme tool")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("generate", help="Generate today's theme")
    sub.add_parser("show", help="Show latest theme")
    args = parser.parse_args()

    if args.cmd == "generate":
        theme = daily_theme.generate()
        print(theme)
    else:
        theme = daily_theme.latest()
        if theme:
            print(theme)
        else:
            print("No theme yet")


if __name__ == "__main__":
    main()

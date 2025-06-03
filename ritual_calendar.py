from __future__ import annotations
import argparse
import datetime
import json

from logging_config import get_log_path
from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

LOG_PATH = get_log_path("ritual_calendar.json", "RITUAL_CALENDAR")
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)


def _load_events() -> list[dict[str, str]]:
    if LOG_PATH.exists():
        try:
            return json.loads(LOG_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def _save_events(events: list[dict[str, str]]) -> None:
    LOG_PATH.write_text(json.dumps(events, indent=2), encoding="utf-8")


def add_event(date: str, name: str) -> dict[str, str]:
    events = _load_events()
    entry = {"date": date, "name": name}
    events.append(entry)
    _save_events(events)
    return entry


def list_events() -> list[dict[str, str]]:
    return _load_events()


def remind(days: int = 7) -> list[dict[str, str]]:
    events = _load_events()
    today = datetime.date.today()
    upcoming = []
    for e in events:
        try:
            d = datetime.date.fromisoformat(e.get("date", ""))
        except Exception:
            continue
        delta = (d - today).days
        if 0 <= delta <= days:
            upcoming.append(e)
    return upcoming


def main() -> None:  # pragma: no cover - CLI utility
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Ritual calendar reminder")
    sub = ap.add_subparsers(dest="cmd")

    ad = sub.add_parser("add", help="Add an event")
    ad.add_argument("date", help="YYYY-MM-DD")
    ad.add_argument("name")
    ad.set_defaults(func=lambda a: print(json.dumps(add_event(a.date, a.name), indent=2)))

    ls = sub.add_parser("list", help="List events")
    ls.set_defaults(func=lambda a: print(json.dumps(list_events(), indent=2)))

    rm = sub.add_parser("remind", help="List events within N days")
    rm.add_argument("--days", type=int, default=7)
    rm.set_defaults(func=lambda a: print(json.dumps(remind(a.days), indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()


if __name__ == "__main__":  # pragma: no cover
    main()

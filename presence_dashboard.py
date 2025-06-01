import json
import time
from urllib import request
from typing import List, Dict
from sentient_banner import print_banner, print_closing


def get_presence(url: str) -> List[Dict[str, str]]:
    try:
        with request.urlopen(f"{url.rstrip('/')}/presence", timeout=0.1) as r:
            data = json.loads(r.read().decode())
            return data.get("users", [])
    except Exception:
        return []


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Presence dashboard")
    parser.add_argument("server")
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    print_banner()
    while True:
        pres = get_presence(args.server)
        print(json.dumps(pres, indent=2))
        if args.once:
            break
        time.sleep(1)
    print_closing()


if __name__ == "__main__":
    main()

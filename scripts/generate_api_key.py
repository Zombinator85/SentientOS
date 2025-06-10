import argparse
import secrets
import hashlib


def main() -> None:
    ap = argparse.ArgumentParser(description="Generate API key")
    ap.add_argument("tenant")
    args = ap.parse_args()
    token = secrets.token_hex(16)
    print(f"tenant: {args.tenant}")
    print(f"token: {token}")
    print(f"hash: {hashlib.sha256(token.encode()).hexdigest()}")


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import os
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render CI remote-smoke host inventory from template")
    parser.add_argument("--template", default=".github/remote-smoke/hosts.ephemeral.yaml")
    parser.add_argument("--output", default=".github/remote-smoke/hosts.rendered.yaml")
    args = parser.parse_args(argv)

    template = Path(args.template).read_text(encoding="utf-8")
    required = ["REMOTE_SMOKE_HOST_1", "REMOTE_SMOKE_HOST_2", "REMOTE_SMOKE_USER", "REMOTE_SMOKE_RUNTIME_ROOT"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise SystemExit(f"missing required env vars: {', '.join(missing)}")

    rendered = template
    for name in required:
        rendered = rendered.replace(f"${{{name}}}", os.environ[name])

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(rendered, encoding="utf-8")
    print(str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

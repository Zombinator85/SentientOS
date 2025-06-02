from __future__ import annotations
import json
from pathlib import Path

from admin_utils import require_admin_banner
import audit_immutability as ai

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

ROOT = Path(__file__).resolve().parent
CONFIG = Path("config/master_files.json")


def _load_config() -> dict[str, str]:
    if not CONFIG.exists():
        return {}
    try:
        return json.loads(CONFIG.read_text())
    except Exception:
        return {}


def verify_audits() -> dict[str, bool]:
    results: dict[str, bool] = {}
    data = _load_config()
    for file in data.keys():
        path = Path(file)
        if not path.is_absolute():
            path = ROOT / path
        results[str(path)] = ai.verify(path)
    return results


def main() -> None:  # pragma: no cover - CLI
    require_admin_banner()
    res = verify_audits()
    for file, ok in res.items():
        status = "valid" if ok else "tampered"
        print(f"{file}: {status}")


if __name__ == "__main__":  # pragma: no cover
    main()

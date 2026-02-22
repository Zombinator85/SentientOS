from __future__ import annotations

import json
from pathlib import Path

from sentientos.orchestrator import tick


def main() -> int:
    result = tick(Path.cwd())
    print(
        json.dumps(
            {
                "mode": result.operating_mode,
                "pressure": result.integrity_pressure_level,
                "remediation": result.remediation_status,
                "index_path": result.index_path,
                "tick_report_path": result.tick_report_path,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

"""Export deterministic manual-audit issue review bundle."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

DEFAULT_OUTPUT_DIR = Path("glow/audits/manual_issues_pack")
FILES = {
    "verify_result": Path("glow/audits/verify_audits_result.json"),
    "repair_plan": Path("glow/audits/audit_repair_plan.json"),
    "convergence_report": Path("glow/audits/audit_convergence_report.json"),
    "quarantine_index": Path("glow/audits/quarantine_index.jsonl"),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def export_bundle(output_dir: Path, include_quarantined_files: bool) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict[str, Any] = {
        "generated_at": _utc_now(),
        "output_dir": str(output_dir),
        "included": {},
        "copied_quarantine_files": [],
        "missing": [],
    }

    for key, source in sorted(FILES.items(), key=lambda item: item[0]):
        destination = output_dir / source.name
        if not source.exists():
            manifest["missing"].append(str(source))
            continue
        shutil.copy2(source, destination)
        manifest["included"][key] = str(destination)

    if include_quarantined_files and FILES["quarantine_index"].exists():
        quarantine_output = output_dir / "quarantined_files"
        quarantine_output.mkdir(parents=True, exist_ok=True)

        for line in FILES["quarantine_index"].read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            source_path = Path(str(payload.get("quarantine_path", "")))
            if not source_path.exists() or not source_path.is_file():
                continue
            target = quarantine_output / source_path.name
            shutil.copy2(source_path, target)
            manifest["copied_quarantine_files"].append(str(target))

        manifest["copied_quarantine_files"] = sorted(set(manifest["copied_quarantine_files"]))

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Export manual audit issues review pack")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--include-quarantined-files", action="store_true")
    args = parser.parse_args(argv)

    manifest = export_bundle(Path(args.output_dir), include_quarantined_files=args.include_quarantined_files)
    print(
        json.dumps(
            {
                "tool": "export_manual_audit_issues",
                "output_dir": str(args.output_dir),
                "missing": len(manifest.get("missing", [])),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

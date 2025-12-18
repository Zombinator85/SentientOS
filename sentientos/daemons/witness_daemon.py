import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional

from witness.witness_rules import WitnessRules


class WitnessDaemon:
    def __init__(
        self,
        base_dir: Path | str = Path("perception"),
        audit_log: Path | str = Path("audit") / "witness_log.jsonl",
        rules: Optional[WitnessRules] = None,
    ) -> None:
        self.base_dir = Path(base_dir)
        self.incoming_dir = self.base_dir / "incoming"
        self.validated_dir = self.base_dir / "validated"
        self.suspect_dir = self.base_dir / "suspect"
        self.audit_log = Path(audit_log)
        self.rules = rules or WitnessRules()
        self._ensure_directories()

    def _ensure_directories(self) -> None:
        for directory in [self.incoming_dir, self.validated_dir, self.suspect_dir, self.audit_log.parent]:
            directory.mkdir(parents=True, exist_ok=True)

    def monitor_once(self) -> None:
        for event_file in self._incoming_files():
            self.process_event_file(event_file)

    def _incoming_files(self) -> Iterable[Path]:
        if not self.incoming_dir.exists():
            return []
        return sorted(self.incoming_dir.glob("*.json"))

    def process_event_file(self, event_file: Path) -> None:
        try:
            raw_content = event_file.read_text()
            event_data = json.loads(raw_content)
        except (OSError, json.JSONDecodeError) as exc:
            suspect_event = {"raw": raw_content if 'raw_content' in locals() else None, "error": str(exc)}
            self._mark_suspect(event_file, suspect_event, reasons=["invalid json"])
            return

        is_valid, reasons = self.rules.evaluate_event(event_data)
        if not is_valid:
            self._mark_suspect(event_file, event_data, reasons)
            return

        self._approve_event(event_file, event_data)

    def _mark_suspect(self, event_file: Path, event_data: Dict, reasons: Iterable[str]) -> None:
        event_data = dict(event_data)
        event_data["witness_suspect"] = True
        event_data["witness_reasons"] = list(reasons)
        destination = self.suspect_dir / event_file.name
        self._write_event(destination, event_data)
        self._log_decision(event_file.name, "rejected", reasons=list(reasons))
        event_file.unlink(missing_ok=True)

    def _approve_event(self, event_file: Path, event_data: Dict) -> None:
        stamped_event = dict(event_data)
        stamped_event["witness_stamp"] = datetime.utcnow().isoformat() + "Z"
        checksum = self._calculate_checksum(stamped_event)
        stamped_event["witness_checksum"] = checksum
        destination = self.validated_dir / event_file.name
        self._write_event(destination, stamped_event)
        self._log_decision(event_file.name, "approved", checksum=checksum)
        event_file.unlink(missing_ok=True)

    def _calculate_checksum(self, event_data: Dict) -> str:
        canonical = WitnessRules.canonical_event_dump(event_data)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _write_event(self, destination: Path, data: Dict) -> None:
        destination.write_text(json.dumps(data, indent=2, sort_keys=True))

    def _log_decision(self, filename: str, status: str, **details) -> None:
        log_entry = {
            "filename": filename,
            "status": status,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        log_entry.update(details)
        with self.audit_log.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(log_entry) + "\n")


__all__ = ["WitnessDaemon"]

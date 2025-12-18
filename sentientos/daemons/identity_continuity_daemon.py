from __future__ import annotations
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

try:
    from logging_config import get_log_path
except ImportError:
    def get_log_path(name: str, env_var: str | None = None) -> Path:
        return Path(name)

class IdentityContinuityDaemon:
    """Daemon to trace persona anchoring points and warn on erosion of doctrinal grounding."""
    def __init__(self, persona_path: Path | str, integration_ledger_path: Path | str | None = None, now_fn: Optional[Callable[[], datetime]] = None) -> None:
        self.persona_path = Path(persona_path)
        self.integration_ledger_path = Path(integration_ledger_path) if integration_ledger_path else Path("/integration/ledger.jsonl")
        self._now = now_fn or (lambda: datetime.now(timezone.utc))
        self.log_path = get_log_path("identity_continuity.jsonl")

    def audit_continuity(self) -> dict:
        persona_name = self.persona_path.stem
        try:
            persona_data = json.loads(self.persona_path.read_text(encoding="utf-8"))
        except Exception:
            persona_data = {}
        # Count recent violations or drift events in integration ledger
        violation_count = 0
        drift_count = 0
        cutoff_time = self._now() - timedelta(days=1)
        if self.integration_ledger_path.exists():
            with self.integration_ledger_path.open("r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    ts_str = str(event.get("timestamp") or "")
                    if ts_str.endswith("Z"):
                        ts_str = ts_str[:-1] + "+00:00"
                    try:
                        ts = datetime.fromisoformat(ts_str)
                    except ValueError:
                        continue
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    ts = ts.astimezone(timezone.utc)
                    if ts < cutoff_time:
                        continue
                    event_text = json.dumps(event).lower()
                    if "violation" in event_text:
                        violation_count += 1
                    if "drift" in event_text:
                        drift_count += 1
        issues: list[dict] = []
        if violation_count or drift_count:
            warning = {
                "timestamp": self._now().isoformat(),
                "persona": persona_name,
                "violations_detected": violation_count,
                "drift_audits_detected": drift_count,
                "issue": "doctrinal_erosion",
                "status": "warning",
            }
            issues.append(warning)
            # Append to continuity log
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as log_f:
                log_f.write(json.dumps(warning, ensure_ascii=False) + "\n")
        return {"warnings": issues, "warning_count": len(issues), "log_path": str(self.log_path)}

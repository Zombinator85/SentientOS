from __future__ import annotations

import json
import logging
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Mapping

from integration_memory import IntegrationMemory
from logging_config import get_log_path
from log_utils import append_json

DEFAULT_POLICIES: dict[str, int] = {
    "persona_contexts": 86400,
    "mood_fragments": 43200,
    "temporary_identities": 604800,
    "session_scope": 14400,
}

RENEWAL_WINDOW = timedelta(hours=1)

logger = logging.getLogger(__name__)


@dataclass
class ReaperResult:
    expired: int
    active: int
    epitaphs: list[str] = field(default_factory=list)


class NarrativeReaper:
    """Reap expired narrative contexts, fragments, and ledger entries."""

    def __init__(
        self,
        *,
        root: Path | str | None = None,
        integration_memory: IntegrationMemory | None = None,
        ttl_config_path: Path | str | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.root = Path(root) if root is not None else Path.cwd()
        self.integration_memory = integration_memory or IntegrationMemory()
        self.ttl_config_path = Path(ttl_config_path) if ttl_config_path else self.root / "config" / "narrative_ttl.json"
        self.clock = clock or (lambda: datetime.now(timezone.utc))

        self.contexts_dir = self.root / "glow" / "contexts"
        self.fragments_dir = self.root / "glow" / "fragments"
        self.archive_dir = self.root / "glow" / "archive" / "expired"
        self.expirations_log = self.root / "glow" / "expirations" / "expired_fragments.jsonl"
        self.audit_log = get_log_path("narrative_expiry_audit.jsonl")

    def run_forever(self, *, interval_hours: float = 6.0) -> None:
        interval_seconds = max(0.0, float(interval_hours) * 3600.0)
        while True:
            self.run_once()
            time.sleep(interval_seconds)

    def run_once(self) -> ReaperResult:
        policies = self._load_policies()
        now = self.clock()
        expired = 0
        total_processed = 0
        epitaphs: list[str] = []

        context_expired, context_total = self._process_directory(
            self.contexts_dir, "persona_contexts", policies, now, epitaphs
        )
        fragment_expired, fragment_total = self._process_directory(
            self.fragments_dir, "mood_fragments", policies, now, epitaphs
        )
        ledger_expired, ledger_total = self._process_ledger(policies, now, epitaphs)

        expired += context_expired + fragment_expired + ledger_expired
        total_processed += context_total + fragment_total + ledger_total
        active = max(total_processed - expired, 0)

        return ReaperResult(expired=expired, active=active, epitaphs=epitaphs)

    def _load_policies(self) -> dict[str, int]:
        if not self.ttl_config_path.exists():
            return dict(DEFAULT_POLICIES)
        try:
            data = json.loads(self.ttl_config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            logger.warning("Invalid TTL policy file at %s; using defaults", self.ttl_config_path)
            return dict(DEFAULT_POLICIES)
        merged = dict(DEFAULT_POLICIES)
        for key, value in data.items():
            try:
                merged[str(key)] = int(value)
            except (TypeError, ValueError):
                logger.debug("Ignoring non-numeric TTL for %s", key)
        return merged

    def _process_directory(
        self,
        base: Path,
        default_policy: str,
        policies: Mapping[str, int],
        now: datetime,
        epitaphs: list[str],
    ) -> tuple[int, int]:
        if not base.exists():
            return 0, 0
        expired = 0
        total = 0
        for path in base.iterdir():
            if not path.is_file():
                continue
            total += 1
            metadata = self._load_metadata(path)
            created = self._extract_created_at(metadata, path)
            ttl_key = self._resolve_policy_key(metadata, policies, default_policy)
            expires_at = created + timedelta(seconds=policies.get(ttl_key, policies[default_policy]))
            item_id = str(metadata.get("id") or metadata.get("name") or path.stem)
            epitaph = metadata.get("epitaph")

            if expires_at <= now:
                expired += 1
                self._handle_expired(
                    item_id,
                    source_path=path,
                    expires_at=expires_at,
                    reason=ttl_key,
                    epitaph=epitaph,
                )
                if epitaph:
                    epitaphs.append(epitaph)
                continue

            if expires_at - now <= RENEWAL_WINDOW:
                self._emit_warning(item_id, path, expires_at, ttl_key)
        return expired, total

    def _process_ledger(
        self, policies: Mapping[str, int], now: datetime, epitaphs: list[str]
    ) -> tuple[int, int]:
        ledger_path = self.root / "integration" / "ledger.jsonl"
        if not ledger_path.exists():
            return 0, 0
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
        kept: list[str] = []
        expired_entries: list[tuple[dict[str, object], datetime, str, str | None]] = []
        total = 0

        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                kept.append(raw)
                continue
            if self._is_internal_warning(entry):
                kept.append(raw)
                continue
            total += 1
            created = self._extract_created_at(entry, ledger_path)
            ttl_key = self._resolve_policy_key(entry, policies, "temporary_identities")
            expires_at = created + timedelta(seconds=policies.get(ttl_key, policies["temporary_identities"]))
            entry_id = str(entry.get("id") or entry.get("entry_id") or entry.get("tag") or "ledger")
            epitaph = entry.get("epitaph") if isinstance(entry.get("epitaph"), str) else None

            if expires_at <= now:
                expired_entries.append((entry, expires_at, ttl_key, epitaph))
                if epitaph:
                    epitaphs.append(epitaph)
                continue
            if expires_at - now <= RENEWAL_WINDOW:
                self._emit_warning(entry_id, ledger_path, expires_at, ttl_key)
            kept.append(raw)

        ledger_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")

        for entry, expires_at, ttl_key, epitaph in expired_entries:
            entry_id = str(entry.get("id") or entry.get("entry_id") or entry.get("tag") or "ledger")
            archive_path = self.archive_dir / "ledger" / f"{entry_id}.json"
            archive_path.parent.mkdir(parents=True, exist_ok=True)
            archive_path.write_text(json.dumps(entry, sort_keys=True), encoding="utf-8")
            self._write_summary(
                entry_id,
                source=str(ledger_path.relative_to(self.root)),
                archived_to=str(archive_path.relative_to(self.root)),
                expires_at=expires_at,
                reason=ttl_key,
                epitaph=epitaph,
            )
            self._log_audit_event(entry_id, ttl_key, archive_path)

        return len(expired_entries), total

    def _emit_warning(self, item_id: str, path: Path, expires_at: datetime, ttl_key: str) -> None:
        payload = {
            "id": item_id,
            "path": str(path),
            "expires_at": expires_at.isoformat(),
            "ttl_key": ttl_key,
        }
        try:
            self.integration_memory.record_event(
                "renewal_opportunity",
                source="narrative_reaper",
                impact="ttl_warning",
                payload=payload,
            )
        except Exception:  # pragma: no cover - defensive logging
            logger.exception("Failed to emit renewal warning for %s", item_id)

    def _handle_expired(
        self,
        item_id: str,
        *,
        source_path: Path,
        expires_at: datetime,
        reason: str,
        epitaph: str | None,
    ) -> None:
        try:
            relative_source = source_path.relative_to(self.root / "glow")
        except ValueError:
            relative_source = source_path.relative_to(self.root)
        archive_path = self.archive_dir / relative_source
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source_path), archive_path)
        self._write_summary(
            item_id,
            source=str(relative_source),
            archived_to=str(archive_path.relative_to(self.root)),
            expires_at=expires_at,
            reason=reason,
            epitaph=epitaph,
        )
        self._log_audit_event(item_id, reason, archive_path)

    def _write_summary(
        self,
        item_id: str,
        *,
        source: str,
        archived_to: str,
        expires_at: datetime,
        reason: str,
        epitaph: str | None,
    ) -> None:
        digest = f"{item_id}:{reason}:{expires_at.isoformat()}"
        record = {
            "id": item_id,
            "source": source,
            "archived_to": archived_to,
            "expires_at": expires_at.isoformat(),
            "reason": reason,
            "digest": digest,
        }
        if epitaph:
            record["epitaph"] = epitaph
        self.expirations_log.parent.mkdir(parents=True, exist_ok=True)
        with self.expirations_log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def _log_audit_event(self, item_id: str, reason: str, archive_path: Path) -> None:
        entry = {
            "event": "narrative_expiry",
            "reason": reason,
            "id": item_id,
            "archival_path": str(archive_path),
        }
        append_json(self.audit_log, entry)

    def _load_metadata(self, path: Path) -> dict[str, object]:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _extract_created_at(self, metadata: Mapping[str, object], fallback_path: Path) -> datetime:
        raw = metadata.get("created_at") or metadata.get("timestamp") or metadata.get("created")
        dt: datetime | None = None
        if isinstance(raw, str):
            try:
                dt = datetime.fromisoformat(raw)
            except ValueError:
                dt = None
        if isinstance(raw, (int, float)):
            dt = datetime.fromtimestamp(raw, tz=timezone.utc)
        if dt is None:
            dt = datetime.fromtimestamp(fallback_path.stat().st_mtime, tz=timezone.utc)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def _resolve_policy_key(self, metadata: Mapping[str, object], policies: Mapping[str, int], default: str) -> str:
        for key in ("ttl_key", "ttl_policy", "type", "context_type", "fragment_type", "category"):
            value = metadata.get(key)
            if isinstance(value, str) and value in policies:
                return value
        return default

    def _is_internal_warning(self, entry: Mapping[str, object]) -> bool:
        return entry.get("source") == "narrative_reaper" and entry.get("event_type") == "renewal_opportunity"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Narrative TTL reaper daemon")
    parser.add_argument("--interval-hours", type=float, default=6.0, help="Interval between sweeps")
    args = parser.parse_args()

    daemon = NarrativeReaper()
    daemon.run_forever(interval_hours=args.interval_hours)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    main()

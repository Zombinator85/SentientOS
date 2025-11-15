"""Rollback engine for Cathedral governance."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Iterable, Literal, Mapping, MutableMapping, Optional, Tuple

AllowedRollbackStatus = Literal["success", "partial", "error", "not_found"]

__all__ = ["RollbackEngine", "RollbackResult"]


@dataclass
class RollbackResult:
    """Structured outcome from a rollback attempt."""

    status: AllowedRollbackStatus
    reverted: Dict[str, Any] = field(default_factory=dict)
    skipped: Dict[str, str] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)


class RollbackEngine:
    """Revert Cathedral amendments using recorded rollback metadata."""

    _CONFIG_FILENAME = "runtime.json"
    _ALLOWED_DOMAINS = {"config", "persona", "world", "registry", "experiments"}

    def __init__(
        self,
        runtime_config: Mapping[str, Any],
        rollback_dir: str | Path,
        ledger: str | Path,
    ) -> None:
        self.runtime_config: Dict[str, Any] = copy.deepcopy(dict(runtime_config))
        runtime_section = self._coerce_mapping(self.runtime_config.get("runtime"))
        base_dir = runtime_section.get("root") or None
        if isinstance(base_dir, str) and base_dir:
            base_path = Path(base_dir)
        else:
            base_path = Path("C:/SentientOS")
        config_dir = runtime_section.get("config_dir")
        if isinstance(config_dir, str) and config_dir:
            config_path = Path(config_dir)
        else:
            config_path = base_path / "sentientos_data" / "config"
        self._config_dir = config_path
        self._config_path = self._config_dir / self._CONFIG_FILENAME
        self._rollback_dir = Path(rollback_dir)
        self._ledger_path = Path(ledger)
        self._rollback_dir.mkdir(parents=True, exist_ok=True)

    @property
    def rollback_dir(self) -> Path:
        return self._rollback_dir

    @property
    def ledger_path(self) -> Path:
        return self._ledger_path

    def revert(self, amendment_id: str, *, auto: bool = False) -> RollbackResult:
        metadata_path = self._rollback_dir / f"{amendment_id}.json"
        if not metadata_path.exists():
            return RollbackResult(status="not_found")

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            errors = {"metadata": "Rollback metadata corrupted"}
            self._write_ledger_error(amendment_id, errors["metadata"], auto)
            return RollbackResult(status="error", errors=errors)

        if not isinstance(metadata, Mapping):
            errors = {"metadata": "Rollback metadata malformed"}
            self._write_ledger_error(amendment_id, errors["metadata"], auto)
            return RollbackResult(status="error", errors=errors)

        original = metadata.get("original")
        digest = metadata.get("digest")

        if not isinstance(original, Mapping):
            errors = {"original": "Original snapshot missing"}
            self._write_ledger_error(amendment_id, errors["original"], auto)
            return RollbackResult(status="error", errors=errors)
        if not isinstance(digest, str) or not digest:
            errors = {"digest": "Rollback metadata missing digest"}
            self._write_ledger_error(amendment_id, errors["digest"], auto)
            return RollbackResult(status="error", errors=errors)

        ledger_digest = self._resolve_ledger_digest(amendment_id)
        if ledger_digest is None:
            errors = {"ledger": "Ledger entry not found for amendment"}
            self._write_ledger_error(amendment_id, errors["ledger"], auto)
            return RollbackResult(status="error", errors=errors)
        if ledger_digest != digest:
            errors = {"digest": "Rollback metadata digest mismatch"}
            self._write_ledger_error(amendment_id, errors["digest"], auto)
            return RollbackResult(status="error", errors=errors)

        proposed = copy.deepcopy(self.runtime_config)
        reverted: Dict[str, Any] = {}
        skipped: Dict[str, str] = {}
        errors: Dict[str, str] = {}

        for domain, snapshot in original.items():
            if domain not in self._ALLOWED_DOMAINS:
                errors[domain] = "Forbidden rollback domain"
                continue
            if not isinstance(snapshot, Mapping):
                errors[domain] = "Snapshot must be a mapping"
                continue
            domain_reverted, domain_skipped, domain_errors = self._restore_domain(
                domain, snapshot, proposed
            )
            if domain_reverted:
                reverted[domain] = domain_reverted
            skipped.update(domain_skipped)
            errors.update(domain_errors)

        status: AllowedRollbackStatus
        if errors and reverted:
            status = "partial"
        elif errors and not reverted:
            status = "error"
        elif reverted:
            status = "success"
        else:
            status = "success"

        if status in {"success", "partial"}:
            if reverted:
                self._persist_configuration(proposed)
            self.runtime_config = proposed
            self._write_ledger_success(amendment_id, reverted, skipped, auto)
        else:
            message = ", ".join(sorted(set(errors.values()))) or "Rollback failed"
            self._write_ledger_error(amendment_id, message, auto)

        return RollbackResult(status=status, reverted=reverted, skipped=skipped, errors=errors)

    def _persist_configuration(self, config: Mapping[str, Any]) -> None:
        serialised = json.dumps(config, indent=2, sort_keys=True)
        self._config_dir.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", dir=self._config_dir, delete=False) as tmp:
            tmp.write(serialised)
            tmp_path = Path(tmp.name)
        tmp_path.replace(self._config_path)

    def _restore_domain(
        self,
        domain: str,
        snapshot: Mapping[str, Any],
        proposed: MutableMapping[str, Any],
    ) -> Tuple[Dict[str, Any], Dict[str, str], Dict[str, str]]:
        reverted: Dict[str, Any] = {}
        skipped: Dict[str, str] = {}
        errors: Dict[str, str] = {}

        if domain == "config":
            container: MutableMapping[str, Any] = proposed
        else:
            section = self._coerce_mapping(proposed.get(domain))
            proposed[domain] = section
            container = section

        for path, value in self._flatten_snapshot(snapshot):
            self._apply_value(
                domain,
                container,
                path,
                value,
                reverted,
                skipped,
                errors,
            )

        return reverted, skipped, errors

    def _apply_value(
        self,
        domain: str,
        container: MutableMapping[str, Any],
        path: Tuple[Any, ...],
        value: Any,
        reverted_store: MutableMapping[str, Any],
        skipped_store: MutableMapping[str, str],
        errors_store: MutableMapping[str, str],
    ) -> None:
        if not path:
            errors_store[self._path_string(domain, path)] = "Invalid rollback path"
            return

        current: MutableMapping[str, Any] | None = container
        for segment in path[:-1]:
            if not isinstance(current, MutableMapping):
                errors_store[self._path_string(domain, path)] = "Rollback path invalid"
                return
            next_value = current.get(segment)
            if not isinstance(next_value, MutableMapping):
                errors_store[self._path_string(domain, path)] = "Rollback path missing"
                return
            current = next_value

        if not isinstance(current, MutableMapping):
            errors_store[self._path_string(domain, path)] = "Rollback path invalid"
            return

        leaf = path[-1]
        previous = copy.deepcopy(current.get(leaf))
        if previous == value:
            skipped_store[self._path_string(domain, path)] = "Value already restored"
            return
        current[leaf] = copy.deepcopy(value)
        self._record_reverted(reverted_store, tuple(str(part) for part in path), previous, value)

    def _flatten_snapshot(
        self,
        snapshot: Mapping[str, Any],
        prefix: Tuple[Any, ...] = (),
    ) -> Iterable[Tuple[Tuple[Any, ...], Any]]:
        for key, value in snapshot.items():
            path = prefix + (key,)
            if isinstance(value, Mapping) and value:
                yield from self._flatten_snapshot(value, path)
            else:
                yield path, copy.deepcopy(value)

    def _record_reverted(
        self,
        store: MutableMapping[str, Any],
        path: Tuple[str, ...],
        previous: Any,
        restored: Any,
    ) -> None:
        if not path:
            return
        cursor: MutableMapping[str, Any] = store
        for segment in path[:-1]:
            cursor = cursor.setdefault(segment, {})  # type: ignore[assignment]
        cursor[path[-1]] = {
            "previous": previous,
            "restored": copy.deepcopy(restored),
        }

    def _resolve_ledger_digest(self, amendment_id: str) -> Optional[str]:
        if not self._ledger_path.exists():
            return None
        latest: Optional[str] = None
        try:
            for raw in self._ledger_path.read_text(encoding="utf-8").splitlines():
                if not raw.strip():
                    continue
                entry = json.loads(raw)
                if not isinstance(entry, Mapping):
                    continue
                if str(entry.get("amendment_id") or "") != amendment_id:
                    continue
                event = entry.get("event")
                if event and event not in {"apply", "application"}:
                    continue
                digest = entry.get("digest")
                if isinstance(digest, str) and digest:
                    latest = digest
        except (OSError, json.JSONDecodeError):
            return None
        return latest

    def _write_ledger_success(
        self,
        amendment_id: str,
        reverted: Mapping[str, Any],
        skipped: Mapping[str, str],
        auto: bool,
    ) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "rollback",
            "amendment_id": amendment_id,
            "reverted": reverted,
            "skipped": skipped,
            "auto": bool(auto),
            "auto_revert": bool(auto),
        }
        self._append_ledger(entry)

    def _write_ledger_error(self, amendment_id: str, message: str, auto: bool) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": "rollback_error",
            "amendment_id": amendment_id,
            "error": message,
            "auto": bool(auto),
            "auto_revert": bool(auto),
        }
        self._append_ledger(entry)

    def _append_ledger(self, entry: Mapping[str, Any]) -> None:
        try:
            self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
            text = json.dumps(entry, sort_keys=True, separators=(",", ":"))
            with self._ledger_path.open("a", encoding="utf-8") as stream:
                stream.write(text + "\n")
        except OSError:
            pass

    @staticmethod
    def _coerce_mapping(value: Any) -> MutableMapping[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        return {}

    def _path_string(self, domain: str, path: Iterable[Any]) -> str:
        segments = [domain]
        segments.extend(str(part) for part in path if part not in {"", None})
        return ".".join(segments)

"""Deterministic amendment application engine for Cathedral."""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Iterable, Literal, Mapping, MutableMapping, Tuple

from .amendment import Amendment, amendment_digest

__all__ = ["AmendmentApplicator", "ApplyResult"]


AllowedStatus = Literal["applied", "noop", "partial", "error"]


@dataclass
class ApplyResult:
    """Outcome of an amendment application attempt."""

    status: AllowedStatus
    applied: Dict[str, Any] = field(default_factory=dict)
    skipped: Dict[str, Any] = field(default_factory=dict)
    errors: Dict[str, str] = field(default_factory=dict)


class AmendmentApplicator:
    """Safely apply approved Cathedral amendments."""

    _CONFIG_FILENAME = "runtime.json"

    def __init__(self, runtime_config: Mapping[str, Any]):
        self.runtime_config: Dict[str, Any] = copy.deepcopy(dict(runtime_config))
        runtime_section = self._coerce_mapping(self.runtime_config.get("runtime"))
        base_dir = runtime_section.get("root") or os.getenv("SENTIENTOS_BASE_DIR")
        if not isinstance(base_dir, str) or not base_dir:
            base_dir = "C:/SentientOS"
        self._base_dir = Path(base_dir)
        config_dir = runtime_section.get("config_dir")
        if not isinstance(config_dir, str) or not config_dir:
            config_dir = str(self._base_dir / "sentientos_data" / "config")
        self._config_dir = Path(config_dir)
        self._config_path = self._config_dir / self._CONFIG_FILENAME
        cathedral_cfg = self._coerce_mapping(self.runtime_config.get("cathedral"))
        ledger_override = cathedral_cfg.get("ledger_path")
        rollback_override = cathedral_cfg.get("rollback_dir")
        cathedral_root = self._base_dir / "cathedral"
        self._ledger_path = Path(ledger_override) if isinstance(ledger_override, str) else cathedral_root / "ledger.jsonl"
        self._rollback_dir = Path(rollback_override) if isinstance(rollback_override, str) else cathedral_root / "rollback"
        self._config_dir.mkdir(parents=True, exist_ok=True)
        cathedral_root.mkdir(parents=True, exist_ok=True)
        self._rollback_dir.mkdir(parents=True, exist_ok=True)
        self._last_original: Dict[str, Any] = {}

    @staticmethod
    def _coerce_mapping(value: Any) -> MutableMapping[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        return {}

    @staticmethod
    def _ensure_json_serialisable(data: Any) -> None:
        try:
            json.dumps(data)
        except (TypeError, ValueError) as exc:  # pragma: no cover - defensive branch
            raise ValueError(f"Non-serialisable data encountered: {exc}") from exc

    def _is_safe_value(self, value: Any) -> bool:
        if isinstance(value, Mapping):
            return all(self._is_safe_value(v) for v in value.values())
        if isinstance(value, (list, tuple, set)):
            return all(self._is_safe_value(item) for item in value)
        if isinstance(value, str):
            lowered = value.lower()
            dangerous_patterns = (
                "import ",
                "exec(",
                "eval(",
                "os.system",
                "subprocess",
                "rm -",
                "powershell",
            )
            if any(pattern in lowered for pattern in dangerous_patterns):
                return False
            if ("/" in value or "\\" in value) and not value.startswith(str(self._base_dir)):
                # Treat slash-containing strings as potential paths.
                candidate = Path(value)
                try:
                    candidate = candidate.resolve()
                except OSError:
                    candidate = candidate
                if candidate.is_absolute() and not str(candidate).startswith(str(self._base_dir)):
                    return False
        return True

    def apply(self, amendment: Amendment) -> ApplyResult:
        """Deterministically apply the amendment to runtime configuration."""

        applied: Dict[str, Any] = {}
        skipped: Dict[str, Any] = {}
        errors: Dict[str, str] = {}
        self._last_original = {}

        proposed = copy.deepcopy(self.runtime_config)

        for domain, change in amendment.changes.items():
            if domain == "config":
                self._apply_config(change, proposed, applied, skipped, errors)
            elif domain == "persona":
                self._apply_persona(change, proposed, applied, skipped, errors)
            elif domain == "world":
                self._apply_world(change, proposed, applied, skipped, errors)
            elif domain == "registry":
                self._apply_registry(change, proposed, applied, skipped, errors)
            elif domain == "experiments":
                self._apply_experiments(change, proposed, applied, skipped, errors)
            else:
                errors[domain] = "Forbidden change domain"

        status: AllowedStatus
        if errors and applied:
            status = "partial"
        elif errors:
            status = "error"
        elif applied and skipped:
            status = "partial"
        elif applied:
            status = "applied"
        else:
            status = "noop"

        if status in {"applied", "partial"}:
            self._persist_configuration(proposed)
            self.runtime_config = proposed
            self._write_ledger_entry(amendment, applied, skipped)
            self._write_rollback_snapshot(amendment, applied)
        return ApplyResult(status=status, applied=applied, skipped=skipped, errors=errors)

    def _persist_configuration(self, config: Mapping[str, Any]) -> None:
        serialised = json.dumps(config, indent=2, sort_keys=True)
        self._ensure_json_serialisable(config)
        self._config_dir.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", dir=self._config_dir, delete=False) as tmp:
            tmp.write(serialised)
            tmp_path = Path(tmp.name)
        tmp_path.replace(self._config_path)

    def _write_ledger_entry(self, amendment: Amendment, applied: Mapping[str, Any], skipped: Mapping[str, Any]) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "amendment_id": amendment.id,
            "digest": amendment_digest(amendment),
            "applied": applied,
            "skipped": skipped,
        }
        text = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        self._ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with self._ledger_path.open("a", encoding="utf-8") as stream:
            stream.write(text + "\n")

    def _write_rollback_snapshot(self, amendment: Amendment, applied: Mapping[str, Any]) -> None:
        snapshot = {
            "original": self._last_original,
            "applied": applied,
        }
        snapshot_path = self._rollback_dir / f"{amendment.id}.json"
        serialised = json.dumps(snapshot, indent=2, sort_keys=True)
        snapshot_path.write_text(serialised, encoding="utf-8")

    def _record_original(self, domain: str, path: Iterable[str], value: Any) -> None:
        cursor = self._last_original.setdefault(domain, {})
        *parents, leaf = list(path)
        for segment in parents:
            cursor = cursor.setdefault(segment, {})  # type: ignore[assignment]
        if leaf is not None:
            cursor[leaf] = copy.deepcopy(value)

    def _apply_config(
        self,
        change: Any,
        proposed: MutableMapping[str, Any],
        applied: MutableMapping[str, Any],
        skipped: MutableMapping[str, Any],
        errors: MutableMapping[str, str],
    ) -> None:
        if not isinstance(change, Mapping):
            errors["config"] = "Config changes must be a mapping"
            return
        empty_sections = []
        for section, updates in change.items():
            section_path = f"config.{section}"
            current_section = proposed.get(section)
            if not isinstance(updates, Mapping):
                errors[section_path] = "Section updates must be mappings"
                continue
            if not isinstance(current_section, Mapping):
                skipped[section_path] = "Unknown configuration section"
                continue
            applied_section = applied.setdefault("config", {}).setdefault(section, {})
            for key, value in updates.items():
                target_path = f"{section_path}.{key}"
                if not self._is_safe_value(value):
                    errors[target_path] = "Unsafe value rejected"
                    continue
                if key not in current_section:
                    skipped[target_path] = "Key not present in configuration"
                    continue
                previous = copy.deepcopy(current_section[key])
                if isinstance(value, Mapping) and isinstance(current_section[key], Mapping):
                    self._record_original("config", (section, key), previous)
                    merged, record = self._deep_merge_mapping(current_section[key], value, (section, key))
                    current_section[key] = merged
                    if record:
                        applied_section[key] = record
                else:
                    if current_section[key] == value:
                        skipped[target_path] = "Value unchanged"
                        continue
                    self._record_original("config", (section, key), previous)
                    current_section[key] = value
                    applied_section[key] = {"previous": previous, "value": value}
            if not applied_section:
                empty_sections.append(section)
        for section in empty_sections:
            applied.get("config", {}).pop(section, None)
        if "config" in applied and not applied["config"]:
            applied.pop("config", None)

    def _deep_merge_mapping(
        self,
        base: Mapping[str, Any],
        updates: Mapping[str, Any],
        path: Tuple[str, ...],
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        merged = copy.deepcopy(dict(base))
        applied_record: Dict[str, Any] = {}
        for key, value in updates.items():
            current_path = path + (key,)
            target_path = ".".join(("config",) + current_path)
            if not self._is_safe_value(value):
                continue
            if key not in merged:
                continue
            previous = copy.deepcopy(merged[key])
            if isinstance(value, Mapping) and isinstance(merged[key], Mapping):
                updated, sub_record = self._deep_merge_mapping(merged[key], value, current_path)
                merged[key] = updated
                if sub_record:
                    applied_record[key] = sub_record
            else:
                if merged[key] == value:
                    continue
                merged[key] = value
                applied_record[key] = {"previous": previous, "value": value}
                self._record_original("config", current_path, previous)
        return merged, applied_record

    def _apply_persona(
        self,
        change: Any,
        proposed: MutableMapping[str, Any],
        applied: MutableMapping[str, Any],
        skipped: MutableMapping[str, Any],
        errors: MutableMapping[str, str],
    ) -> None:
        allowed_keys = {"tone", "tick_interval_seconds", "heartbeat_interval_seconds", "max_message_length"}
        if not isinstance(change, Mapping):
            errors["persona"] = "Persona changes must be a mapping"
            return
        persona_cfg = self._coerce_mapping(proposed.get("persona"))
        proposed["persona"] = persona_cfg
        record = applied.setdefault("persona", {})
        for key, value in change.items():
            target_path = f"persona.{key}"
            if key not in allowed_keys:
                skipped[target_path] = "Key not allowed"
                continue
            if not self._is_safe_value(value):
                errors[target_path] = "Unsafe value rejected"
                continue
            previous = persona_cfg.get(key)
            if previous == value:
                skipped[target_path] = "Value unchanged"
                continue
            self._record_original("persona", (key,), previous)
            persona_cfg[key] = value
            record[key] = {"previous": previous, "value": value}
        if "persona" in applied and not applied["persona"]:
            applied.pop("persona", None)

    def _apply_world(
        self,
        change: Any,
        proposed: MutableMapping[str, Any],
        applied: MutableMapping[str, Any],
        skipped: MutableMapping[str, Any],
        errors: MutableMapping[str, str],
    ) -> None:
        allowed_keys = {
            "enabled",
            "poll_interval_seconds",
            "idle_pulse_interval_seconds",
            "sources",
        }
        if not isinstance(change, Mapping):
            errors["world"] = "World changes must be a mapping"
            return
        world_cfg = self._coerce_mapping(proposed.get("world"))
        proposed["world"] = world_cfg
        record = applied.setdefault("world", {})
        for key, value in change.items():
            target_path = f"world.{key}"
            if key not in allowed_keys:
                skipped[target_path] = "Key not allowed"
                continue
            if not self._is_safe_value(value):
                errors[target_path] = "Unsafe value rejected"
                continue
            previous = copy.deepcopy(world_cfg.get(key))
            if key == "sources":
                if not isinstance(value, Mapping):
                    errors[target_path] = "Sources must be a mapping"
                    continue
                merged = world_cfg.get("sources")
                if not isinstance(merged, Mapping):
                    merged = {}
                merged_copy = dict(merged)
                sub_record: Dict[str, Any] = {}
                for source_key, enabled in value.items():
                    if not isinstance(enabled, bool):
                        errors[f"{target_path}.{source_key}"] = "Source flags must be boolean"
                        continue
                    prev_value = merged_copy.get(source_key)
                    if prev_value == enabled:
                        continue
                    merged_copy[source_key] = enabled
                    self._record_original("world", ("sources", source_key), prev_value)
                    sub_record[source_key] = {"previous": prev_value, "value": enabled}
                if sub_record:
                    world_cfg["sources"] = merged_copy
                    record.setdefault("sources", {}).update(sub_record)
                continue
            if world_cfg.get(key) == value:
                skipped[target_path] = "Value unchanged"
                continue
            self._record_original("world", (key,), previous)
            world_cfg[key] = value
            record[key] = {"previous": previous, "value": value}
        if "world" in applied and not applied["world"]:
            applied.pop("world", None)

    def _apply_registry(
        self,
        change: Any,
        proposed: MutableMapping[str, Any],
        applied: MutableMapping[str, Any],
        skipped: MutableMapping[str, Any],
        errors: MutableMapping[str, str],
    ) -> None:
        if not isinstance(change, Mapping):
            errors["registry"] = "Registry changes must be a mapping"
            return
        registry = self._coerce_mapping(proposed.get("registry"))
        proposed["registry"] = registry
        empty_categories = []
        for category, operations in change.items():
            category_path = f"registry.{category}"
            if category not in {"adapters", "demos", "personas"}:
                skipped[category_path] = "Category not allowed"
                continue
            category_store = self._coerce_mapping(registry.get(category))
            registry[category] = category_store
            record = applied.setdefault("registry", {}).setdefault(category, {})
            if not isinstance(operations, Mapping):
                errors[category_path] = "Operations must be a mapping"
                continue
            self._apply_collection_ops(category_store, operations, category_path, record, skipped, errors)
            if not record:
                empty_categories.append(category)
        for category in empty_categories:
            applied.get("registry", {}).pop(category, None)
        if "registry" in applied and not applied["registry"]:
            applied.pop("registry", None)

    def _apply_experiments(
        self,
        change: Any,
        proposed: MutableMapping[str, Any],
        applied: MutableMapping[str, Any],
        skipped: MutableMapping[str, Any],
        errors: MutableMapping[str, str],
    ) -> None:
        if not isinstance(change, Mapping):
            errors["experiments"] = "Experiments changes must be a mapping"
            return
        experiments = self._coerce_mapping(proposed.get("experiments"))
        proposed["experiments"] = experiments
        empty_categories = []
        for category, operations in change.items():
            category_path = f"experiments.{category}"
            if category not in {"adapters", "demos"}:
                skipped[category_path] = "Category not allowed"
                continue
            store = self._coerce_mapping(experiments.get(category))
            experiments[category] = store
            record = applied.setdefault("experiments", {}).setdefault(category, {})
            if not isinstance(operations, Mapping):
                errors[category_path] = "Operations must be a mapping"
                continue
            self._apply_collection_ops(store, operations, category_path, record, skipped, errors)
            if not record:
                empty_categories.append(category)
        for category in empty_categories:
            applied.get("experiments", {}).pop(category, None)
        if "experiments" in applied and not applied["experiments"]:
            applied.pop("experiments", None)

    def _apply_collection_ops(
        self,
        store: MutableMapping[str, Any],
        operations: Mapping[str, Any],
        base_path: str,
        record: MutableMapping[str, Any],
        skipped: MutableMapping[str, Any],
        errors: MutableMapping[str, str],
    ) -> None:
        domain_name, category_name = base_path.split(".", 1)
        for op, payload in operations.items():
            op_path = f"{base_path}.{op}"
            if op not in {"add", "remove", "update"}:
                skipped[op_path] = "Operation not supported"
                continue
            if op in {"add", "remove"}:
                if not isinstance(payload, Iterable) or isinstance(payload, (str, bytes, Mapping)):
                    errors[op_path] = "Add/Remove payload must be a list"
                    continue
                for name in payload:
                    if not isinstance(name, str):
                        errors[f"{op_path}.{name}"] = "Entries must be strings"
                        continue
                    if op == "add":
                        if name in store:
                            skipped[f"{base_path}.{name}"] = "Already present"
                            continue
                        self._record_original(domain_name, (category_name, name), None)
                        store[name] = {}
                        record.setdefault("added", []).append(name)
                    else:
                        if name not in store:
                            skipped[f"{base_path}.{name}"] = "Entry missing"
                            continue
                        previous = copy.deepcopy(store.pop(name))
                        self._record_original(domain_name, (category_name, name), previous)
                        record.setdefault("removed", []).append({"name": name, "previous": previous})
                continue
            if not isinstance(payload, Mapping):
                errors[op_path] = "Update payload must be a mapping"
                continue
            for name, metadata in payload.items():
                entry_path = f"{base_path}.{name}"
                if not isinstance(name, str):
                    errors[entry_path] = "Entry names must be strings"
                    continue
                if not self._is_safe_value(metadata):
                    errors[entry_path] = "Unsafe metadata rejected"
                    continue
                previous = copy.deepcopy(store.get(name))
                store[name] = copy.deepcopy(metadata)
                self._record_original(domain_name, (category_name, name), previous)
                record.setdefault("updated", []).append({"name": name, "previous": previous, "value": metadata})

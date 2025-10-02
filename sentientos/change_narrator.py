"""Natural language summaries of recent SentientOS changes."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Mapping, MutableMapping, Sequence

from .codex_healer import RecoveryLedger
from .storage import get_state_file

LOGGER = logging.getLogger(__name__)

_SINCE_PATTERN = re.compile(r"since\s+([^?.!]+)")
_DURATION_PATTERN = re.compile(
    r"(?:(?:last|past)\s+)?(\d+)\s*(minute|minutes|hour|hours|day|days|week|weeks)"
)
_MODULE_KEYWORDS = {
    "codex": {"codex", "codex healer"},
    "oracle": {"oracle", "oracle cycle"},
}
_TYPE_KEYWORDS = {
    "self_healing": {"self-healing", "self healing", "healing"},
}


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _ensure_utc(parsed)


def _ledger_entry_id(entry: Mapping[str, object]) -> str:
    timestamp = str(entry.get("timestamp", ""))
    status = str(entry.get("status", ""))
    anomaly = entry.get("anomaly")
    anomaly_subject = ""
    if isinstance(anomaly, Mapping):
        anomaly_subject = str(anomaly.get("subject", ""))
    return json.dumps({"t": timestamp, "s": status, "a": anomaly_subject}, sort_keys=True)


@dataclass(slots=True)
class LedgerRecord:
    """Structured RecoveryLedger entry."""

    timestamp: datetime
    status: str
    anomaly_type: str | None
    anomaly_id: str | None
    raw: Mapping[str, object]

    @property
    def identity(self) -> str:
        return _ledger_entry_id(self.raw)


@dataclass(slots=True)
class CommitRecord:
    """Lightweight git commit representation."""

    sha: str
    summary: str
    timestamp: datetime

    @property
    def short_sha(self) -> str:
        return self.sha[:7]


@dataclass(slots=True)
class ChangeSet:
    """Data collected for narration."""

    ledger_entries: List[LedgerRecord] = field(default_factory=list)
    commits: List[CommitRecord] = field(default_factory=list)
    collected_at: datetime = field(default_factory=_now)


@dataclass(slots=True)
class ScopeFilter:
    """Represents operator scoping instructions."""

    since: datetime | None
    modules: set[str]
    change_types: set[str]
    requested: bool

    @classmethod
    def from_text(cls, text: str, *, now: datetime | None = None) -> "ScopeFilter":
        lowered = text.lower()
        request = any(keyword in lowered for keyword in ("change", "changes", "updated", "update", "diff"))
        since = cls._extract_since(lowered, now=now)
        modules: set[str] = set()
        for module, keywords in _MODULE_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                modules.add(module)
        change_types: set[str] = set()
        for change_type, keywords in _TYPE_KEYWORDS.items():
            if any(keyword in lowered for keyword in keywords):
                change_types.add(change_type)
        return cls(since=since, modules=modules, change_types=change_types, requested=request)

    @staticmethod
    def _extract_since(text: str, *, now: datetime | None) -> datetime | None:
        now = _ensure_utc(now or _now())
        match = _SINCE_PATTERN.search(text)
        if not match:
            return None
        expression = match.group(1).strip()
        if not expression:
            return None
        if expression.startswith("yesterday"):
            return now - timedelta(days=1)
        if expression.startswith("today"):
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if expression.startswith("last week"):
            return now - timedelta(weeks=1)
        if expression.startswith("last day"):
            return now - timedelta(days=1)
        duration_match = _DURATION_PATTERN.search(expression)
        if duration_match:
            amount = int(duration_match.group(1))
            unit = duration_match.group(2)
            if unit.startswith("minute"):
                return now - timedelta(minutes=amount)
            if unit.startswith("hour"):
                return now - timedelta(hours=amount)
            if unit.startswith("day"):
                return now - timedelta(days=amount)
            if unit.startswith("week"):
                return now - timedelta(weeks=amount)
        parsed = _parse_iso_timestamp(expression)
        if parsed:
            return parsed
        return None

    def matches_commit(self, commit: CommitRecord) -> bool:
        if self.modules:
            combined = commit.summary.lower()
            if not any(module in combined for module in self.modules):
                return False
        return True

    def matches_ledger(self, entry: LedgerRecord) -> bool:
        if self.since and entry.timestamp < self.since:
            return False
        category = _classify_ledger_category(entry)
        if self.change_types and category not in self.change_types:
            return False
        if self.modules:
            haystack_parts: List[str] = []
            haystack_parts.append(entry.status.lower())
            if entry.anomaly_type:
                haystack_parts.append(entry.anomaly_type.lower())
            if entry.anomaly_id:
                haystack_parts.append(entry.anomaly_id.lower())
            haystack = " ".join(haystack_parts)
            if not any(module in haystack for module in self.modules):
                return False
        return True


def _classify_ledger_category(entry: LedgerRecord) -> str:
    status = entry.status.lower()
    if "heal" in status or "recovery" in status:
        return "self_healing"
    return "general"


class ChangeCollector:
    """Collect RecoveryLedger entries and git commits."""

    def __init__(
        self,
        ledger: RecoveryLedger | None = None,
        *,
        repo_path: Path | None = None,
        state_path: Path | None = None,
        ledger_path: Path | None = None,
    ) -> None:
        self._ledger = ledger
        self._repo_path = Path(repo_path) if repo_path else Path.cwd()
        self._state_path = state_path or get_state_file("change_narrator_state.json")
        self._ledger_path = Path(ledger_path) if ledger_path else None

    def collect(self, scope: ScopeFilter, *, now: datetime | None = None) -> ChangeSet:
        state = self._load_state()
        baseline = _parse_iso_timestamp(state.get("last_reported_at"))
        if scope.since and baseline:
            baseline = max(baseline, scope.since)
        elif scope.since:
            baseline = scope.since
        reported_ledger: set[str] = set(state.get("reported_ledger_ids", []))
        reported_commits: set[str] = set(state.get("reported_commits", []))
        ledger_entries = self._collect_ledger_entries(scope, baseline, reported_ledger)
        commits = self._collect_commits(scope, baseline, reported_commits)
        return ChangeSet(ledger_entries=ledger_entries, commits=commits, collected_at=_ensure_utc(now or _now()))

    def mark_reported(
        self,
        change_set: ChangeSet,
        *,
        scope: ScopeFilter,
        response: str,
        timestamp: datetime | None = None,
    ) -> None:
        state = self._load_state()
        ledger_ids = set(state.get("reported_ledger_ids", []))
        commit_ids = set(state.get("reported_commits", []))
        ledger_ids.update(record.identity for record in change_set.ledger_entries)
        commit_ids.update(record.sha for record in change_set.commits)
        state["reported_ledger_ids"] = sorted(ledger_ids)
        state["reported_commits"] = sorted(commit_ids)
        moment = _ensure_utc(timestamp or _now())
        state["last_reported_at"] = moment.isoformat()
        state["last_response"] = response
        if scope.modules:
            state.setdefault("module_history", []).append(sorted(scope.modules))
        if scope.change_types:
            state.setdefault("type_history", []).append(sorted(scope.change_types))
        self._save_state(state)

    def _collect_ledger_entries(
        self,
        scope: ScopeFilter,
        baseline: datetime | None,
        reported: set[str],
    ) -> List[LedgerRecord]:
        raw_entries = self._load_ledger_entries()
        records: List[LedgerRecord] = []
        for entry in raw_entries:
            timestamp = _parse_iso_timestamp(str(entry.get("timestamp", "")))
            if timestamp is None:
                continue
            record = LedgerRecord(
                timestamp=timestamp,
                status=str(entry.get("status", "")),
                anomaly_type=_extract_anomaly_field(entry, "kind"),
                anomaly_id=_extract_anomaly_field(entry, "subject"),
                raw=entry,
            )
            if not scope.matches_ledger(record):
                continue
            if baseline and record.timestamp <= baseline and record.identity in reported:
                continue
            records.append(record)
        records.sort(key=lambda record: record.timestamp)
        return records

    def _collect_commits(
        self,
        scope: ScopeFilter,
        baseline: datetime | None,
        reported: set[str],
    ) -> List[CommitRecord]:
        repo = self._repo_path
        if not (repo / ".git").exists():
            return []
        args = [
            "git",
            "-C",
            str(repo),
            "log",
            "--pretty=format:%H%x1f%ct%x1f%s%x1e",
            "--no-merges",
            "--max-count=100",
        ]
        try:
            result = subprocess.run(args, capture_output=True, text=True, check=False)
        except OSError as exc:  # pragma: no cover - git unavailable
            LOGGER.debug("Unable to execute git log: %s", exc)
            return []
        if result.returncode != 0:
            LOGGER.debug("git log failed: %s", result.stderr.strip())
            return []
        stdout = result.stdout.strip()
        commits: List[CommitRecord] = []
        if not stdout:
            return commits
        for chunk in stdout.split("\x1e"):
            chunk = chunk.strip()
            if not chunk:
                continue
            parts = chunk.split("\x1f")
            if len(parts) < 3:
                continue
            sha, timestamp_raw, summary = parts[:3]
            if sha in reported:
                continue
            try:
                timestamp_value = datetime.fromtimestamp(int(timestamp_raw), tz=timezone.utc)
            except ValueError:
                continue
            record = CommitRecord(sha=sha, summary=summary.strip(), timestamp=timestamp_value)
            if scope.since and record.timestamp < scope.since:
                continue
            if baseline and record.timestamp <= baseline and sha in reported:
                continue
            if not scope.matches_commit(record):
                continue
            commits.append(record)
        commits.sort(key=lambda record: record.timestamp)
        return commits

    def _load_ledger_entries(self) -> List[Mapping[str, object]]:
        if self._ledger is not None:
            return [dict(entry) for entry in self._ledger.entries]
        if self._ledger_path is None:
            return []
        path = self._ledger_path
        if not path.exists():
            return []
        entries: List[Mapping[str, object]] = []
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(payload, Mapping):
                        entries.append(payload)
        except OSError as exc:
            LOGGER.debug("Unable to read RecoveryLedger from %s: %s", path, exc)
        return entries

    def _load_state(self) -> MutableMapping[str, object]:
        path = self._state_path
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.debug("Unable to load change narrator state: %s", exc)
            return {}

    def _save_state(self, state: Mapping[str, object]) -> None:
        path = self._state_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
        except OSError as exc:
            LOGGER.debug("Unable to persist change narrator state: %s", exc)


def _extract_anomaly_field(entry: Mapping[str, object], field: str) -> str | None:
    anomaly = entry.get("anomaly")
    if isinstance(anomaly, Mapping):
        value = anomaly.get(field)
        if value is None:
            return None
        return str(value)
    return None


class DiffSummarizer:
    """Condense collected changes into conversational sentences."""

    def summarize(self, change_set: ChangeSet) -> List[str]:
        sentences: List[str] = []
        if change_set.commits:
            sentences.append(self._summarize_commits(change_set.commits))
        if change_set.ledger_entries:
            sentences.append(self._summarize_ledger(change_set.ledger_entries))
        return sentences

    def _summarize_commits(self, commits: Sequence[CommitRecord]) -> str:
        snippets = [f"{commit.summary} ({commit.short_sha})" for commit in commits[:3]]
        remaining = len(commits) - len(snippets)
        if remaining > 0:
            snippets.append(f"{remaining} additional commit{'s' if remaining != 1 else ''}")
        joined = ", ".join(snippets)
        return f"I merged {joined}."

    def _summarize_ledger(self, entries: Sequence[LedgerRecord]) -> str:
        statuses = Counter(entry.status.replace("_", " ") for entry in entries)
        fragments = [f"{count}× {status}" for status, count in sorted(statuses.items())]
        joined = ", ".join(fragments)
        return f"Self-healing activity recorded: {joined}."


class NarrativeFormatter:
    """Transform summaries into Lumos' conversational tone."""

    def format(self, sentences: Sequence[str]) -> str:
        if not sentences:
            return "No changes since the last update."
        preamble = sentences[0]
        if preamble.startswith("I "):
            preamble = "Since your last check-in, " + preamble[2:]
        else:
            preamble = "Since your last check-in, " + preamble
        tail = [sentence for sentence in sentences[1:]]
        return " ".join([preamble, *tail]).strip()


class ChangeNarrator:
    """High-level orchestrator for change narration."""

    def __init__(
        self,
        collector: ChangeCollector,
        *,
        summarizer: DiffSummarizer | None = None,
        formatter: NarrativeFormatter | None = None,
    ) -> None:
        self._collector = collector
        self._summarizer = summarizer or DiffSummarizer()
        self._formatter = formatter or NarrativeFormatter()

    def maybe_respond(self, message: str, *, now: datetime | None = None) -> str | None:
        scope = ScopeFilter.from_text(message, now=now)
        if not scope.requested:
            return None
        change_set = self._collector.collect(scope, now=now)
        sentences = self._summarizer.summarize(change_set)
        response = self._formatter.format(sentences)
        self._collector.mark_reported(change_set, scope=scope, response=response, timestamp=change_set.collected_at)
        return response


def build_default_change_narrator() -> ChangeNarrator:
    """Create a ChangeNarrator using runtime defaults."""

    repo_path = Path(os.getenv("SENTIENTOS_REPO_PATH", Path.cwd()))
    ledger_path_value = os.getenv("CODEX_LEDGER_PATH")
    ledger_path = Path(ledger_path_value) if ledger_path_value else None
    collector = ChangeCollector(repo_path=repo_path, ledger_path=ledger_path)
    return ChangeNarrator(collector)


__all__ = [
    "ChangeNarrator",
    "ChangeCollector",
    "ChangeSet",
    "DiffSummarizer",
    "LedgerRecord",
    "NarrativeFormatter",
    "ScopeFilter",
    "build_default_change_narrator",
]

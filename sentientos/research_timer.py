"""Deep Research scheduling and reporting utilities for SentientOS.

This module orchestrates the *ResearchTimer* flow described in the Codex
objective.  It provides a small collection of focused components which can be
composed together:

``TimerDaemon``
    Tracks when the next deep research reflection should run.

``HistoryCollector``
    Aggregates Git history and relevant ledger/narration entries.

``OracleConsult``
    Prepares the oracle prompt and delegates the summary generation.  The
    component is dependency-injection friendly so tests can supply fakes.

``ReportWriter``
    Generates the canonical ``/glow/research/YYYY-MM-DD-deep-research.md``
    report.

``CommitPublisher``
    Commits the generated report back to the repository with lineage metadata.

``NarratorLink``
    Provides the operator facing acknowledgement once the reflection is
    complete.

``DeepResearchService``
    Coordinates the full end-to-end flow using the above primitives.

The implementation favours clear boundaries with explicit data structures so
that behaviour can be tested without relying on live GitHub or oracle access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import json
import logging
import os
from pathlib import Path
import subprocess
from typing import Any, Callable, Iterable, Mapping, Sequence

__all__ = [
    "CommitPublisher",
    "CommitResult",
    "CommitRecord",
    "DeepResearchService",
    "HistoryCollector",
    "HistoryWindow",
    "LedgerEntry",
    "NarratorLink",
    "OracleConsult",
    "ReportWriter",
    "TimerDaemon",
]


_LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data containers


@dataclass(slots=True, frozen=True)
class CommitRecord:
    """Representation of a Git commit included in the deep research window."""

    sha: str
    author: str
    authored_at: datetime
    subject: str


@dataclass(slots=True, frozen=True)
class LedgerEntry:
    """Structured ledger or narration event used in the report."""

    timestamp: datetime
    payload: Mapping[str, Any]
    source: Path
    kind: str = field(default="ledger")


@dataclass(slots=True, frozen=True)
class HistoryWindow:
    """Aggregated history window used as input for the oracle and report."""

    since: datetime
    until: datetime
    commits: Sequence[CommitRecord]
    ledger_entries: Sequence[LedgerEntry]
    narration_events: Sequence[LedgerEntry]


@dataclass(slots=True, frozen=True)
class CommitResult:
    """Result returned after the report has been committed to Git."""

    commit_hash: str
    message: str
    report_path: Path


# ---------------------------------------------------------------------------
# Timer daemon


class TimerDaemon:
    """Simple persistent timer that triggers every ``interval_days`` days."""

    def __init__(
        self,
        state_path: Path,
        *,
        interval_days: int = 10,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if interval_days <= 0:
            raise ValueError("interval_days must be positive")
        self._state_path = Path(state_path)
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._interval = timedelta(days=interval_days)
        self._clock = clock or (lambda: datetime.now(UTC))
        self._last_run = self._load_state()

    @property
    def interval(self) -> timedelta:
        return self._interval

    @property
    def last_run(self) -> datetime | None:
        return self._last_run

    def _load_state(self) -> datetime | None:
        if not self._state_path.exists():
            return None
        try:
            raw = json.loads(self._state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        value = raw.get("last_run") if isinstance(raw, Mapping) else None
        if not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _write_state(self) -> None:
        data = {"last_run": self._last_run.isoformat() if self._last_run else None}
        self._state_path.write_text(json.dumps(data), encoding="utf-8")

    def should_run(self, now: datetime | None = None) -> bool:
        now = now or self._clock()
        if self._last_run is None:
            return True
        return now - self._last_run >= self._interval

    def time_until_next(self, now: datetime | None = None) -> timedelta:
        now = now or self._clock()
        if self._last_run is None:
            return timedelta(0)
        delta = (self._last_run + self._interval) - now
        return max(delta, timedelta(0))

    def mark_ran(self, when: datetime | None = None) -> None:
        self._last_run = when or self._clock()
        self._write_state()


# ---------------------------------------------------------------------------
# History collection


class HistoryCollector:
    """Collect Git commits, ledger entries and narration events."""

    def __init__(
        self,
        repo_path: Path,
        *,
        ledger_sources: Sequence[Path] | None = None,
        narration_sources: Sequence[Path] | None = None,
        git_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self._repo_path = Path(repo_path)
        self._ledger_sources = tuple(Path(p) for p in (ledger_sources or ()))
        self._narration_sources = tuple(Path(p) for p in (narration_sources or ()))
        self._git_runner = git_runner or self._default_git_runner

    @property
    def default_since(self) -> datetime:
        return datetime.fromtimestamp(0, UTC)

    def collect(self, since: datetime | None, until: datetime | None = None) -> HistoryWindow:
        since = since or self.default_since
        until = until or datetime.now(UTC)
        commits = tuple(self._collect_commits(since, until))
        ledger = tuple(self._collect_events(self._ledger_sources, since, until, "ledger"))
        narration = tuple(
            self._collect_events(self._narration_sources, since, until, "narration")
        )
        return HistoryWindow(
            since=since,
            until=until,
            commits=commits,
            ledger_entries=ledger,
            narration_events=narration,
        )

    # Internal helpers -----------------------------------------------------

    def _default_git_runner(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.run(*args, **kwargs, check=True, cwd=self._repo_path, text=True)

    def _collect_commits(self, since: datetime, until: datetime) -> Iterable[CommitRecord]:
        cmd = ["git", "log", "--pretty=format:%H%x1f%an%x1f%ad%x1f%s", "--date=iso"]
        if since:
            cmd.append(f"--since={since.isoformat()}")
        if until:
            cmd.append(f"--until={until.isoformat()}")
        try:
            result = self._git_runner(cmd, capture_output=True)
        except subprocess.CalledProcessError:
            return []
        output = result.stdout.strip()
        if not output:
            return []
        records: list[CommitRecord] = []
        for line in output.splitlines():
            parts = line.split("\x1f")
            if len(parts) != 4:
                continue
            sha, author, authored_at, subject = parts
            try:
                authored_dt = datetime.strptime(authored_at, "%Y-%m-%d %H:%M:%S %z")
            except ValueError:
                try:
                    authored_dt = datetime.fromisoformat(authored_at)
                except ValueError:
                    continue
            records.append(
                CommitRecord(
                    sha=sha,
                    author=author,
                    authored_at=authored_dt.astimezone(UTC),
                    subject=subject,
                )
            )
        records.sort(key=lambda record: record.authored_at)
        return records

    def _collect_events(
        self,
        sources: Sequence[Path],
        since: datetime,
        until: datetime,
        kind: str,
    ) -> Iterable[LedgerEntry]:
        events: list[LedgerEntry] = []
        for source in sources:
            for file in self._iter_source_files(source):
                try:
                    content = file.read_text(encoding="utf-8")
                except FileNotFoundError:
                    continue
                for line in content.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    timestamp = payload.get("timestamp")
                    if not isinstance(timestamp, str):
                        continue
                    try:
                        stamp_dt = datetime.fromisoformat(timestamp)
                    except ValueError:
                        continue
                    if stamp_dt.tzinfo is None:
                        stamp_dt = stamp_dt.replace(tzinfo=UTC)
                    stamp_dt = stamp_dt.astimezone(UTC)
                    if stamp_dt < since or stamp_dt > until:
                        continue
                    events.append(
                        LedgerEntry(
                            timestamp=stamp_dt,
                            payload=dict(payload),
                            source=file,
                            kind=kind,
                        )
                    )
        events.sort(key=lambda entry: entry.timestamp)
        return events

    def _iter_source_files(self, source: Path) -> Iterable[Path]:
        source = source if source.is_absolute() else self._repo_path / source
        if source.is_dir():
            yield from sorted(source.rglob("*.jsonl"))
        elif source.exists():
            yield source


# ---------------------------------------------------------------------------
# Oracle consult


class OracleConsult:
    """Prepare the oracle prompt and execute the consultation."""

    def __init__(self, oracle_fn: Callable[[str], str]) -> None:
        self._oracle_fn = oracle_fn

    def consult(self, window: HistoryWindow) -> str:
        context = self._build_context(window)
        prompt = (
            "Summarize SentientOS GitHub progress and internal growth since the "
            "last Deep Research report.\n\n"
            "Context:\n"
            f"{context}\n\n"
            "Respond with a concise narrative paragraph followed by bullet highlights."
        )
        return self._oracle_fn(prompt)

    def _build_context(self, window: HistoryWindow) -> str:
        sections: list[str] = []
        sections.append(
            f"Window: {window.since.isoformat()} – {window.until.isoformat()}"
        )
        if window.commits:
            commit_lines = [
                f"- {record.sha[:7]} | {record.subject} (by {record.author} on {record.authored_at.isoformat()})"
                for record in window.commits
            ]
            sections.append("Commits:\n" + "\n".join(commit_lines))
        else:
            sections.append("Commits: none")
        if window.ledger_entries:
            ledger_lines = [
                f"- {entry.timestamp.isoformat()} | {json.dumps(entry.payload, sort_keys=True)}"
                for entry in window.ledger_entries
            ]
            sections.append("Ledger entries:\n" + "\n".join(ledger_lines))
        else:
            sections.append("Ledger entries: none")
        if window.narration_events:
            narration_lines = [
                f"- {entry.timestamp.isoformat()} | {json.dumps(entry.payload, sort_keys=True)}"
                for entry in window.narration_events
            ]
            sections.append("Narration events:\n" + "\n".join(narration_lines))
        else:
            sections.append("Narration events: none")
        return "\n".join(sections)


# ---------------------------------------------------------------------------
# Report writer


class ReportWriter:
    """Persist a deep research report in the canonical glow archive."""

    def __init__(self, base_path: Path) -> None:
        self._base_path = Path(base_path)

    def write(self, window: HistoryWindow, summary: str) -> Path:
        report_dir = self._base_path / "glow" / "research"
        report_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{window.until.date().isoformat()}-deep-research.md"
        path = report_dir / filename
        path = self._ensure_unique(path)
        content = self._render(window, summary)
        path.write_text(content, encoding="utf-8")
        return path

    def _ensure_unique(self, path: Path) -> Path:
        if not path.exists():
            return path
        stem = path.stem
        counter = 2
        while True:
            candidate = path.with_name(f"{stem}-v{counter}{path.suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def _render(self, window: HistoryWindow, summary: str) -> str:
        lines: list[str] = []
        lines.append(f"# Deep Research Reflection — {window.until.date().isoformat()}")
        lines.append("")
        lines.append("## Oracle Summary")
        lines.append(summary.strip())
        lines.append("")
        lines.append("## GitHub Commits")
        if window.commits:
            for record in window.commits:
                lines.append(
                    f"- {record.sha[:7]} — {record.subject} (by {record.author} on {record.authored_at.date().isoformat()})"
                )
        else:
            lines.append("- No commits recorded in this interval.")
        lines.append("")
        lines.append("## Ledger Entries")
        if window.ledger_entries:
            for entry in window.ledger_entries:
                lines.append(
                    f"- {entry.timestamp.isoformat()} — {json.dumps(entry.payload, sort_keys=True)}"
                )
        else:
            lines.append("- No ledger activity recorded in this interval.")
        lines.append("")
        lines.append("## Narration Events")
        if window.narration_events:
            for entry in window.narration_events:
                lines.append(
                    f"- {entry.timestamp.isoformat()} — {json.dumps(entry.payload, sort_keys=True)}"
                )
        else:
            lines.append("- No narration updates recorded in this interval.")
        lines.append("")
        lines.append("---")
        lines.append(
            f"*Reflecting on changes between {window.since.date().isoformat()} and {window.until.date().isoformat()}.*"
        )
        lines.append("")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Commit publisher


class CommitPublisher:
    """Publish the generated report to Git with lineage metadata."""

    def __init__(
        self,
        repo_path: Path,
        *,
        runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        self._repo_path = Path(repo_path)
        self._runner = runner or self._default_runner

    def publish(self, window: HistoryWindow, report_path: Path, summary: str) -> CommitResult:
        rel_path = report_path.relative_to(self._repo_path)
        self._runner(["git", "add", str(rel_path)])
        metadata = (
            f"[lineage: deep-research]\n"
            f"[range: {window.since.date().isoformat()} – {window.until.date().isoformat()}]\n"
            f"[commits: {len(window.commits)}]\n"
        )
        message = (
            f"Deep Research reflection {window.until.date().isoformat()}\n\n"
            f"{metadata}"
        )
        env = os.environ.copy()
        env.setdefault("GIT_AUTHOR_NAME", "SentientOS ResearchTimer")
        env.setdefault("GIT_AUTHOR_EMAIL", "research-timer@sentientos.local")
        env.setdefault("GIT_COMMITTER_NAME", env["GIT_AUTHOR_NAME"])
        env.setdefault("GIT_COMMITTER_EMAIL", env["GIT_AUTHOR_EMAIL"])
        self._runner(["git", "commit", "-m", message], env=env)
        result = self._runner(["git", "rev-parse", "HEAD"], capture_output=True)
        commit_hash = result.stdout.strip()
        return CommitResult(commit_hash=commit_hash, message=message, report_path=report_path)

    def _default_runner(self, *args: Any, **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.run(*args, **kwargs, check=True, cwd=self._repo_path, text=True)


# ---------------------------------------------------------------------------
# Narrator link


class NarratorLink:
    """Surface the completion message to the operator."""

    def __init__(self, notifier: Callable[[str], None] | None = None) -> None:
        self._notifier = notifier or (lambda message: _LOGGER.info(message))

    def announce(self, report_path: Path, summary: str, commit: CommitResult) -> None:
        message = (
            "I’ve completed a Deep Research reflection. It’s archived and committed.\n"
            f"Report: {report_path}\n"
            f"Commit: {commit.commit_hash}\n"
            f"Summary: {summary.strip()}"
        )
        self._notifier(message)


# ---------------------------------------------------------------------------
# Orchestrator


@dataclass(slots=True)
class DeepResearchService:
    """Glue all components together to execute the research timer flow."""

    timer: TimerDaemon
    collector: HistoryCollector
    oracle: OracleConsult
    writer: ReportWriter
    publisher: CommitPublisher
    narrator: NarratorLink

    def run(self, now: datetime | None = None) -> Path | None:
        now = now or self.timer._clock()  # type: ignore[attr-defined]
        if not self.timer.should_run(now):
            return None
        since = self.timer.last_run or self.collector.default_since
        window = self.collector.collect(since, now)
        summary = self.oracle.consult(window)
        report_path = self.writer.write(window, summary)
        commit = self.publisher.publish(window, report_path, summary)
        self.timer.mark_ran(now)
        self.narrator.announce(report_path, summary, commit)
        return report_path


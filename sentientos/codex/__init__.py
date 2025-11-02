from __future__ import annotations

import json
import logging
import os
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, Iterable, List, Mapping, Optional, Sequence

from nacl.signing import SigningKey

from codex.integrity_daemon import IntegrityDaemon as CovenantIntegrityDaemon
from codex.integrity_daemon import IntegrityViolation

from ..storage import ensure_mounts, get_data_root, get_state_file
from sentientos.daemons import pulse_bus
from sentientos.daemons.hungry_eyes import (
    HungryEyesDatasetBuilder,
    HungryEyesSentinel,
)

LOGGER = logging.getLogger(__name__)
_STATE_LOCK = Lock()
_STATE_PATH = get_state_file("codex_state.json")


@dataclass(frozen=True)
class GapFinding:
    """Simple heuristic signal describing a repository gap."""

    kind: str
    description: str
    path: str | None = None
    line: int | None = None
    priority: str = "minor"

    def fingerprint(self) -> str:
        return ":".join(
            [
                self.kind,
                (self.path or "").strip(),
                str(self.line or ""),
                self.description.strip(),
            ]
        )


@dataclass
class Amendment:
    identifier: str
    summary: str
    created_at: float
    status: str = "proposed"
    committed: bool = False
    payload: Dict[str, object] = field(default_factory=dict)
    integrity_status: str = "pending"
    proof_report: Dict[str, object] | None = None
    probe_report: Dict[str, object] | None = None
    hungry_eyes: Dict[str, object] | None = None
    risk_score: float | None = None
    tests: Dict[str, object] | None = None
    last_event: str | None = None
    approved_at: float | None = None

    @classmethod
    def new(
        cls,
        summary: str,
        *,
        payload: Optional[Dict[str, object]] = None,
    ) -> "Amendment":
        now = time.time()
        return cls(
            identifier=str(uuid.uuid4()),
            summary=summary,
            created_at=now,
            payload=dict(payload or {}),
            last_event=datetime.now(timezone.utc).isoformat(),
        )

    def to_record(self) -> Dict[str, object]:
        record: Dict[str, object] = {
            "identifier": self.identifier,
            "summary": self.summary,
            "created_at": self.created_at,
            "status": self.status,
            "committed": self.committed,
            "payload": dict(self.payload),
            "integrity_status": self.integrity_status,
        }
        if self.proof_report is not None:
            record["proof_report"] = self.proof_report
        if self.probe_report is not None:
            record["probe_report"] = self.probe_report
        if self.hungry_eyes is not None:
            record["hungry_eyes"] = self.hungry_eyes
        if self.risk_score is not None:
            record["risk_score"] = self.risk_score
        if self.tests is not None:
            record["tests"] = self.tests
        if self.last_event is not None:
            record["last_event"] = self.last_event
        if self.approved_at is not None:
            record["approved_at"] = self.approved_at
        return record


class CodexState:
    """Persistence container for Codex amendments and commit cadence."""

    def __init__(
        self,
        amendments: Optional[List[Amendment]] = None,
        *,
        last_commit_at: float | None = None,
    ) -> None:
        self.amendments: List[Amendment] = amendments or []
        self.last_commit_at = last_commit_at

    def to_dict(self) -> Dict[str, object]:
        payload: Dict[str, object] = {
            "amendments": [item.to_record() for item in self.amendments]
        }
        if self.last_commit_at is not None:
            payload["last_commit_at"] = self.last_commit_at
        return payload

    @classmethod
    def from_dict(cls, raw: Dict[str, object]) -> "CodexState":
        items: List[Amendment] = []
        for entry in raw.get("amendments", []):
            if not isinstance(entry, dict):
                continue
            try:
                amendment = Amendment(
                    identifier=str(entry["identifier"]),
                    summary=str(entry.get("summary", "")),
                    created_at=float(entry.get("created_at", time.time())),
                    status=str(entry.get("status", "proposed")),
                    committed=bool(entry.get("committed", False)),
                    payload=dict(entry.get("payload", {})),
                    integrity_status=str(entry.get("integrity_status", "pending")),
                )
            except (KeyError, TypeError, ValueError):
                LOGGER.debug("Skipping malformed amendment entry: %s", entry)
                continue
            amendment.proof_report = (
                entry.get("proof_report")
                if isinstance(entry.get("proof_report"), dict)
                else None
            )
            amendment.probe_report = (
                entry.get("probe_report")
                if isinstance(entry.get("probe_report"), dict)
                else None
            )
            amendment.hungry_eyes = (
                entry.get("hungry_eyes")
                if isinstance(entry.get("hungry_eyes"), dict)
                else None
            )
            risk = entry.get("risk_score")
            amendment.risk_score = float(risk) if isinstance(risk, (int, float)) else None
            amendment.tests = (
                entry.get("tests") if isinstance(entry.get("tests"), dict) else None
            )
            last_event = entry.get("last_event")
            amendment.last_event = str(last_event) if last_event is not None else None
            approved_at = entry.get("approved_at")
            amendment.approved_at = (
                float(approved_at)
                if isinstance(approved_at, (int, float))
                else None
            )
            items.append(amendment)
        last_commit_at = raw.get("last_commit_at")
        commit_ts = (
            float(last_commit_at)
            if isinstance(last_commit_at, (int, float))
            else None
        )
        return cls(items, last_commit_at=commit_ts)

    def find(self, identifier: str) -> Amendment | None:
        for amendment in self.amendments:
            if amendment.identifier == identifier:
                return amendment
        return None


def _load_state() -> CodexState:
    ensure_mounts()
    if not _STATE_PATH.exists():
        return CodexState()
    try:
        data = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        LOGGER.warning("Unable to read codex state: %s", exc)
        return CodexState()
    if not isinstance(data, dict):
        return CodexState()
    return CodexState.from_dict(data)


def _save_state(state: CodexState) -> None:
    with _STATE_LOCK:
        try:
            _STATE_PATH.write_text(
                json.dumps(state.to_dict(), indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except OSError as exc:
            LOGGER.error("Failed to persist codex state: %s", exc)


class GapSeeker:
    """Scans the repository for lightweight capability gaps."""

    TODO_PATTERNS = ("TODO", "FIXME")
    DOC_PATTERNS = ("TODO", "TBD", "OUTDATED")
    MAX_FINDINGS = 5

    def __init__(self, root: Path | None = None) -> None:
        self._root = Path(root or Path.cwd())

    def scan(self) -> list[GapFinding]:
        findings: list[GapFinding] = []
        findings.extend(self._scan_todos())
        findings.extend(self._scan_known_failing())
        findings.extend(self._scan_docs())
        return findings[: self.MAX_FINDINGS]

    def _scan_todos(self) -> list[GapFinding]:
        candidates: list[GapFinding] = []
        source_root = self._root / "sentientos"
        if not source_root.exists():
            return candidates
        for path in sorted(source_root.rglob("*.py")):
            if len(candidates) >= self.MAX_FINDINGS:
                break
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for index, line in enumerate(lines, start=1):
                if any(token in line for token in self.TODO_PATTERNS):
                    description = line.strip()
                    candidates.append(
                        GapFinding(
                            kind="todo_marker",
                            description=description[:200],
                            path=str(path.relative_to(self._root)),
                            line=index,
                            priority="minor",
                        )
                    )
                    break
        return candidates

    def _scan_known_failing(self) -> list[GapFinding]:
        failing: list[GapFinding] = []
        manifest = self._root / "KNOWN_FAILING.txt"
        if not manifest.exists():
            return failing
        try:
            lines = manifest.read_text(encoding="utf-8").splitlines()
        except OSError:
            return failing
        for raw in lines:
            entry = raw.strip()
            if not entry or entry.startswith("#"):
                continue
            failing.append(
                GapFinding(
                    kind="failing_test",
                    description=entry,
                    path="KNOWN_FAILING.txt",
                    priority="major",
                )
            )
        return failing

    def _scan_docs(self) -> list[GapFinding]:
        docs_root = self._root / "docs"
        findings: list[GapFinding] = []
        if not docs_root.exists():
            return findings
        for path in sorted(docs_root.rglob("*.md")):
            if len(findings) >= self.MAX_FINDINGS:
                break
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for token in self.DOC_PATTERNS:
                if token in text:
                    findings.append(
                        GapFinding(
                            kind="doc_outdated",
                            description=f"{token} marker in {path.name}",
                            path=str(path.relative_to(self._root)),
                            priority="minor",
                        )
                    )
                    break
        return findings


@dataclass(frozen=True)
class CommitPlan:
    message: str
    amendment_ids: tuple[str, ...]
    priority: str
    summaries: tuple[str, ...]


class IntegrityPipeline:
    """Bridge between Codex amendments and covenantal integrity checks."""

    def __init__(self) -> None:
        mounts = ensure_mounts()
        self._data_root = get_data_root()
        self._keys_root = mounts.get("vow", self._data_root / "vow") / "keys"
        self._ensure_pulse_keys()
        self._integrity = CovenantIntegrityDaemon(self._data_root)
        threshold = float(os.getenv("HUNGRY_EYES_THRESHOLD", "0.6"))
        mode = os.getenv("HUNGRY_EYES_MODE", "observe")
        self._hungry = HungryEyesSentinel(mode=mode, threshold=threshold)
        self._processed_since_retrain = 0
        self._retrain_interval = int(os.getenv("HUNGRY_EYES_RETRAIN_INTERVAL", "10"))
        self._ledger_path = self._data_root / "daemon" / "integrity" / "ledger.jsonl"
        self._quarantine_dir = self._data_root / "daemon" / "integrity" / "quarantine"
        self._negatives_dir = self._data_root / "daemon" / "integrity" / "simulated_negatives"
        self._retrain()
        self._subscription = pulse_bus.subscribe(self._handle_event)
        self.dispatch_pending()

    def publish_amendment(self, amendment: Amendment) -> None:
        state = _load_state()
        stored = state.find(amendment.identifier)
        if stored is not None:
            amendment = stored
        amendment.integrity_status = "pending"
        amendment.status = "proposed"
        amendment.last_event = datetime.now(timezone.utc).isoformat()
        _save_state(state)
        event = {
            "timestamp": amendment.last_event,
            "source_daemon": "codex.genesis_forge",
            "event_type": "codex.amendment_proposed",
            "priority": "info",
            "payload": {
                "identifier": amendment.identifier,
                "summary": amendment.summary,
                "payload": dict(amendment.payload),
            },
        }
        try:
            pulse_bus.publish(event)
        except Exception as exc:  # pragma: no cover - fallback for missing keys
            LOGGER.warning("Pulse publish failed (%s); processing proposal synchronously", exc)
            self._handle_event(event)

    def dispatch_pending(self) -> None:
        state = _load_state()
        for amendment in state.amendments:
            if amendment.integrity_status == "pending" and amendment.status == "proposed":
                self.publish_amendment(amendment)

    def _handle_event(self, event: Mapping[str, object]) -> None:
        if event.get("event_type") != "codex.amendment_proposed":
            return
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            return
        identifier = str(payload.get("identifier", ""))
        if not identifier:
            return
        state = _load_state()
        amendment = state.find(identifier)
        if amendment is None:
            LOGGER.debug("Received integrity request for unknown amendment %s", identifier)
            return
        if amendment.integrity_status != "pending":
            return
        self._process_proposal(state, amendment)

    def _process_proposal(self, state: CodexState, amendment: Amendment) -> None:
        try:
            self._integrity.evaluate(amendment)
            ledger_entry = self._latest_ledger_entry(amendment.identifier)
            assessment = self._assess_with_hungry_eyes(ledger_entry or {})
            amendment.integrity_status = "VALID"
            amendment.status = "valid"
            amendment.proof_report = (
                ledger_entry.get("proof_report") if ledger_entry else None
            )
            amendment.probe_report = ledger_entry.get("probe") if ledger_entry else None
            amendment.hungry_eyes = assessment
            amendment.risk_score = (
                float(assessment.get("risk")) if assessment else None
            )
            amendment.last_event = (
                ledger_entry.get("timestamp") if ledger_entry else datetime.now(timezone.utc).isoformat()
            )
            _save_state(state)
            self._publish_integrity_event(amendment, ledger_entry, None)
            self._record_processed_event(ledger_entry)
        except IntegrityViolation as exc:
            ledger_entry = self._latest_ledger_entry(amendment.identifier)
            amendment.integrity_status = "QUARANTINED"
            amendment.status = "quarantined"
            amendment.proof_report = (
                ledger_entry.get("proof_report") if ledger_entry else None
            )
            amendment.probe_report = ledger_entry.get("probe") if ledger_entry else None
            amendment.last_event = (
                ledger_entry.get("timestamp") if ledger_entry else datetime.now(timezone.utc).isoformat()
            )
            _save_state(state)
            self._publish_integrity_event(amendment, ledger_entry, exc)
            self._record_processed_event(ledger_entry)
            return
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.exception("Integrity evaluation failed: %s", exc)
            amendment.integrity_status = "ERROR"
            amendment.status = "rejected"
            amendment.last_event = datetime.now(timezone.utc).isoformat()
            _save_state(state)
            self._publish_integrity_event(amendment, None, exc)
            return

        assessment = amendment.hungry_eyes or {}
        try:
            risk = float(assessment.get("risk", 1.0))
        except (TypeError, ValueError):
            risk = 1.0
        threshold = float(assessment.get("threshold", self._hungry.threshold))
        if risk >= threshold:
            amendment.status = "needs_review"
            amendment.last_event = datetime.now(timezone.utc).isoformat()
            _save_state(state)
            self._publish_test_event(
                amendment,
                success=None,
                results=[],
                reason="hungry_eyes_threshold",
            )
            return

        success, results = self._run_tests()
        amendment.tests = {
            "commands": [result["command"] for result in results],
            "results": results,
            "passed": success,
        }
        amendment.last_event = datetime.now(timezone.utc).isoformat()
        if success:
            amendment.status = "approved"
            amendment.approved_at = time.time()
        else:
            amendment.status = "failed_tests"
        _save_state(state)
        self._publish_test_event(amendment, success, results)

    def _publish_integrity_event(
        self,
        amendment: Amendment,
        ledger_entry: Mapping[str, object] | None,
        error: Exception | None,
    ) -> None:
        payload: Dict[str, object] = {
            "identifier": amendment.identifier,
            "status": amendment.integrity_status,
            "summary": amendment.summary,
        }
        if ledger_entry:
            payload["proof_report"] = ledger_entry.get("proof_report")
            payload["probe_report"] = ledger_entry.get("probe")
        if amendment.hungry_eyes:
            payload["hungry_eyes"] = amendment.hungry_eyes
        if error is not None:
            payload["error"] = str(error)
            priority = "critical"
        else:
            priority = "info"
        event = {
            "timestamp": amendment.last_event or datetime.now(timezone.utc).isoformat(),
            "source_daemon": "codex.integrity_pipeline",
            "event_type": "codex.amendment_integrity",
            "priority": priority,
            "payload": payload,
        }
        try:
            pulse_bus.publish(event)
        except Exception:
            LOGGER.debug("Unable to publish integrity result to pulse bus", exc_info=True)

    def _publish_test_event(
        self,
        amendment: Amendment,
        success: bool | None,
        results: Sequence[Mapping[str, object]],
        reason: str | None = None,
    ) -> None:
        payload: Dict[str, object] = {
            "identifier": amendment.identifier,
            "status": amendment.status,
            "summary": amendment.summary,
            "results": list(results),
        }
        if reason:
            payload["reason"] = reason
        priority = "info"
        if success is False or reason:
            priority = "warning"
        event = {
            "timestamp": amendment.last_event or datetime.now(timezone.utc).isoformat(),
            "source_daemon": "codex.integrity_pipeline",
            "event_type": "codex.amendment_tests",
            "priority": priority,
            "payload": payload,
        }
        try:
            pulse_bus.publish(event)
        except Exception:
            LOGGER.debug("Unable to publish test result to pulse bus", exc_info=True)

    def _run_tests(self) -> tuple[bool, list[dict[str, object]]]:
        results: list[dict[str, object]] = []
        success = True
        for command in _determine_ci_commands():
            try:
                proc = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError:
                result = {
                    "command": command,
                    "returncode": 127,
                    "stdout": "",
                    "stderr": "command not found",
                }
                results.append(result)
                success = False
                break
            result = {
                "command": command,
                "returncode": proc.returncode,
                "stdout": (proc.stdout or "")[-4000:],
                "stderr": (proc.stderr or "")[-4000:],
            }
            results.append(result)
            if proc.returncode != 0:
                success = False
                break
        return success, results

    def _latest_ledger_entry(self, proposal_id: str) -> dict[str, object] | None:
        if not self._ledger_path.exists():
            return None
        try:
            lines = self._ledger_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("proposal_id") == proposal_id:
                return entry if isinstance(entry, dict) else None
        return None

    def _assess_with_hungry_eyes(
        self, entry: Mapping[str, object]
    ) -> dict[str, object] | None:
        if not entry:
            return None
        try:
            return self._hungry.assess(entry)
        except Exception:
            return None

    def _record_processed_event(self, entry: Mapping[str, object] | None) -> None:
        self._processed_since_retrain += 1
        if self._processed_since_retrain >= max(self._retrain_interval, 1):
            self._retrain()
            self._processed_since_retrain = 0

    def _retrain(self) -> None:
        builder = HungryEyesDatasetBuilder()
        if self._ledger_path.exists():
            builder.load_jsonl(self._ledger_path)
        if self._quarantine_dir.exists():
            builder.load_directory(self._quarantine_dir)
        self._augment_with_simulated_negatives(builder)
        examples = builder.build()
        try:
            self._hungry.fit(examples)
        except Exception:
            LOGGER.debug("HungryEyes retraining failed", exc_info=True)

    def _augment_with_simulated_negatives(
        self, builder: HungryEyesDatasetBuilder
    ) -> None:
        if not self._negatives_dir.exists():
            return
        for entry in sorted(self._negatives_dir.glob("*.json")):
            try:
                data = json.loads(entry.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, Mapping):
                builder.add_event(data)

    def _ensure_pulse_keys(self) -> None:
        self._keys_root.mkdir(parents=True, exist_ok=True)
        private_key = self._keys_root / "ed25519_private.key"
        public_key = self._keys_root / "ed25519_public.key"
        if private_key.exists() and public_key.exists():
            os.environ.setdefault("PULSE_SIGNING_KEY", str(private_key))
            os.environ.setdefault("PULSE_VERIFY_KEY", str(public_key))
            return
        signing_key = SigningKey.generate()
        private_key.write_bytes(signing_key.encode())
        public_key.write_bytes(signing_key.verify_key.encode())
        os.environ.setdefault("PULSE_SIGNING_KEY", str(private_key))
        os.environ.setdefault("PULSE_VERIFY_KEY", str(public_key))


def _determine_ci_commands() -> list[list[str]]:
    commands: list[list[str]] = [["pytest", "-q"]]
    makefile = Path("Makefile")
    if makefile.exists():
        try:
            content = makefile.read_text(encoding="utf-8")
        except OSError:
            content = ""
        if "ci:" in content:
            commands.append(["make", "ci"])
    return commands


class GenesisForge:
    """Generate targeted Codex amendments based on repository gaps."""

    MAX_NEW_PER_CYCLE = 1

    @staticmethod
    def expand() -> None:
        state = _load_state()
        _PIPELINE.dispatch_pending()
        seeker = GapSeeker(Path.cwd())
        findings = seeker.scan()
        if not findings:
            return
        fingerprints = {
            str(item.payload.get("fingerprint"))
            for item in state.amendments
            if "fingerprint" in item.payload
        }
        created = 0
        for finding in findings:
            fingerprint = finding.fingerprint()
            if fingerprint in fingerprints:
                continue
            summary = GenesisForge._summarise_finding(finding)
            amendment = Amendment.new(
                summary,
                payload={
                    "origin": "genesis_forge",
                    "gap_kind": finding.kind,
                    "description": finding.description,
                    "path": finding.path,
                    "line": finding.line,
                    "priority": finding.priority,
                    "fingerprint": fingerprint,
                },
            )
            state.amendments.append(amendment)
            fingerprints.add(fingerprint)
            _save_state(state)
            LOGGER.info(
                "GenesisForge created amendment %s for %s",
                amendment.identifier,
                fingerprint,
            )
            _PIPELINE.publish_amendment(amendment)
            created += 1
            if created >= GenesisForge.MAX_NEW_PER_CYCLE:
                break

    @staticmethod
    def _summarise_finding(finding: GapFinding) -> str:
        if finding.kind == "failing_test":
            return f"Repair failing test: {finding.description}"
        if finding.kind == "doc_outdated":
            return f"Refresh documentation reference in {finding.path}"
        location = finding.path or "repository"
        return f"Resolve TODO marker in {location}"


class SpecAmender:
    """Manage amendment lifecycle once integrity and tests have passed."""

    @staticmethod
    def cycle() -> None:
        _PIPELINE.dispatch_pending()

    @staticmethod
    def has_new_commit() -> bool:
        return SpecAmender.next_commit() is not None

    @staticmethod
    def next_commit(now: float | None = None) -> CommitPlan | None:
        state = _load_state()
        approved = [
            amendment
            for amendment in state.amendments
            if amendment.status == "approved" and not amendment.committed
        ]
        if not approved:
            return None
        majors = [
            item
            for item in approved
            if str(item.payload.get("priority")) == "major"
        ]
        if majors:
            candidate = sorted(majors, key=lambda item: item.approved_at or item.created_at)[0]
            return CommitPlan(
                message=candidate.summary,
                amendment_ids=(candidate.identifier,),
                priority="major",
                summaries=(candidate.summary,),
            )
        now = now or time.time()
        interval_minutes = float(os.getenv("CODEX_COMMIT_INTERVAL_MINUTES", "5"))
        interval_seconds = max(interval_minutes, 1.0) * 60.0
        last_commit = state.last_commit_at or 0.0
        if now - last_commit < interval_seconds and len(approved) < 3:
            return None
        message = f"Codex maintenance batch ({len(approved)} amendments)"
        return CommitPlan(
            message=message,
            amendment_ids=tuple(item.identifier for item in approved),
            priority="minor",
            summaries=tuple(item.summary for item in approved),
        )

    @staticmethod
    def mark_committed(plan: CommitPlan) -> None:
        state = _load_state()
        updated = False
        for amendment in state.amendments:
            if amendment.identifier in plan.amendment_ids:
                amendment.committed = True
                amendment.status = "committed"
                updated = True
        if updated:
            state.last_commit_at = time.time()
            _save_state(state)


class IntegrityDaemon:
    """Compatibility wrapper delegating to the integrated pipeline."""

    @staticmethod
    def guard() -> None:
        _PIPELINE.dispatch_pending()


class CodexHealer:
    """Prune stale or unhealthy amendments from the codex state."""

    EXPIRY_SECONDS = 3600

    @classmethod
    def monitor(cls) -> None:
        state = _load_state()
        cutoff = time.time() - cls.EXPIRY_SECONDS
        survivors: list[Amendment] = []
        removed = 0
        for amendment in state.amendments:
            if amendment.status in {"committed", "approved", "valid", "needs_review"}:
                survivors.append(amendment)
                continue
            if amendment.status in {"failed_tests", "quarantined", "rejected"}:
                if amendment.created_at < cutoff:
                    removed += 1
                    continue
            survivors.append(amendment)
        if removed:
            LOGGER.info("CodexHealer removed %s stale amendments", removed)
        state.amendments = survivors
        _save_state(state)


_PIPELINE = IntegrityPipeline()

__all__ = [
    "GapSeeker",
    "GenesisForge",
    "SpecAmender",
    "IntegrityDaemon",
    "CodexHealer",
    "CommitPlan",
]

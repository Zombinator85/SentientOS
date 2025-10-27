"""CodexHealer – Autonomous self-repair primitives for SentientOS."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable, List, Mapping, Sequence


def _ensure_utc(moment: datetime | None = None) -> datetime:
    """Return ``moment`` as a timezone-aware UTC timestamp."""

    if moment is None:
        return datetime.now(timezone.utc)
    if moment.tzinfo is None:
        return moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


@dataclass(frozen=True)
class DaemonHeartbeat:
    """Represents the last observed heartbeat of a daemon."""

    name: str
    last_seen: datetime
    status: str = "ok"

    def age(self, now: datetime | None = None) -> timedelta:
        return _ensure_utc(now) - _ensure_utc(self.last_seen)


@dataclass(frozen=True)
class Anomaly:
    """Captured deviation detected by :class:`PulseWatcher`."""

    kind: str
    subject: str
    details: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload = {
            "kind": self.kind,
            "subject": self.subject,
            "details": copy.deepcopy(self.details),
        }
        return payload


@dataclass
class RepairAction:
    """Candidate remediation authored by :class:`RepairSynthesizer`."""

    kind: str
    subject: str
    description: str
    execute: Callable[[], bool]
    auto_adopt: bool = True
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload = {
            "kind": self.kind,
            "subject": self.subject,
            "description": self.description,
            "auto_adopt": self.auto_adopt,
            "metadata": copy.deepcopy(self.metadata),
        }
        return payload


class RecoveryLedger:
    """Append-only ledger narrating every self-healing attempt."""

    def __init__(self, path: Path | None = None) -> None:
        self._entries: List[dict[str, object]] = []
        self._path = Path(path) if path else None
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        status: str,
        *,
        anomaly: Anomaly,
        action: RepairAction | None = None,
        details: dict[str, object] | None = None,
        quarantined: bool = False,
    ) -> dict[str, object]:
        entry: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "narrative": f"CodexHealer event: {status}",
            "anomaly": anomaly.to_dict(),
            "quarantined": quarantined,
        }
        proof_summary: dict[str, object] | None = None
        if action is not None:
            entry["action"] = action.to_dict()
        if details:
            entry["details"] = copy.deepcopy(details)
            proof_summary = self._extract_proof_summary(details.get("proof_report"))
        if proof_summary:
            entry["proof_summary"] = proof_summary
            entry["narrative"] = (
                "Amendment validated: "
                f"{proof_summary['passed']} invariants passed, "
                f"{proof_summary['violations']} violations detected, "
                f"status = {proof_summary['status']}."
            )
        self._entries.append(entry)
        if self._path is not None:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    @property
    def entries(self) -> list[dict[str, object]]:
        return list(self._entries)

    def _extract_proof_summary(
        self, proof_report: Mapping[str, object] | None
    ) -> dict[str, object] | None:
        if not isinstance(proof_report, Mapping):
            return None
        trace = proof_report.get("trace")
        violations = proof_report.get("violations")
        total = 0
        violation_count = 0
        if isinstance(trace, Iterable) and not isinstance(trace, (str, bytes)):
            total = len(list(trace))
        if isinstance(violations, Iterable) and not isinstance(violations, (str, bytes)):
            violation_count = len(list(violations))
        passed = max(total - violation_count, 0)
        status = "VALID" if bool(proof_report.get("valid")) else "QUARANTINED"
        return {
            "status": status,
            "passed": passed,
            "violations": violation_count,
        }


class HealingEnvironment:
    """Abstraction over side effects triggered during self-repair."""

    def __init__(
        self,
        *,
        lineage_pointer: Path | None = None,
        archive_root: Path | None = None,
    ) -> None:
        self.lineage_pointer = lineage_pointer
        self.archive_root = archive_root
        self.restart_requests: list[str] = []
        self.mount_repairs: list[Path] = []
        self.lineage_repairs: list[tuple[Path, Path]] = []
        self.regenesis_restores: list[Path] = []
        self.replayed_amendments: list[list[dict[str, object]]] = []
        self.fail_rebind_once = False

    def restart_daemon(self, daemon: str) -> bool:
        self.restart_requests.append(daemon)
        return True

    def ensure_mount(self, mount: Path) -> bool:
        mount = Path(mount)
        mount.mkdir(parents=True, exist_ok=True)
        self.mount_repairs.append(mount)
        return mount.exists()

    def latest_snapshot(self) -> Path | None:
        archive = self.archive_root
        if archive is None and self.lineage_pointer is not None:
            archive = self.lineage_pointer.parent
        if archive is None or not archive.exists():
            return None
        candidates = [path for path in archive.iterdir() if path.is_file()]
        if not candidates:
            return None
        candidates.sort(key=lambda path: (path.stat().st_mtime, path.name))
        return candidates[-1]

    def rebind_lineage(self, pointer: Path | None, target: Path | None) -> bool:
        pointer = pointer or self.lineage_pointer
        if pointer is None:
            return False
        pointer.parent.mkdir(parents=True, exist_ok=True)
        target = target or self.latest_snapshot()
        if target is None or not target.exists():
            return False
        if self.fail_rebind_once:
            self.fail_rebind_once = False
            return False
        pointer.write_text(target.name, encoding="utf-8")
        self.lineage_pointer = pointer
        self.lineage_repairs.append((pointer, target))
        return True

    def restore_snapshot(self, snapshot: Path) -> bool:
        pointer = self.lineage_pointer
        if pointer is None:
            return False
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(snapshot.name, encoding="utf-8")
        self.regenesis_restores.append(snapshot)
        return True

    def _amendment_log(self) -> Path | None:
        pointer = self.lineage_pointer
        if pointer is None:
            return None
        return pointer.parent / f"{pointer.name}.amendments.jsonl"

    def load_amendments(self) -> list[dict[str, object]]:
        log_path = self._amendment_log()
        if log_path is None or not log_path.exists():
            return []
        entries: list[dict[str, object]] = []
        for line in log_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                entries.append(payload)
        return entries

    def replay_amendments(self, amendments: list[dict[str, object]]) -> bool:
        self.replayed_amendments.append(amendments)
        return True


class PulseWatcher:
    """Monitor daemon heartbeats and covenant mounts."""

    def __init__(
        self,
        *,
        heartbeat_timeout: int = 120,
        required_mounts: Sequence[Path] | None = None,
        lineage_pointer: Path | None = None,
        lineage_archive: Path | None = None,
    ) -> None:
        self._timeout = timedelta(seconds=heartbeat_timeout)
        self._required_mounts = [
            Path(mount) for mount in (required_mounts or [Path("/vow"), Path("/glow"), Path("/pulse"), Path("/daemon")])
        ]
        self._lineage_pointer = lineage_pointer
        self._lineage_archive = lineage_archive

    def scan(self, heartbeats: Iterable[DaemonHeartbeat], *, now: datetime | None = None) -> list[Anomaly]:
        now_utc = _ensure_utc(now)
        anomalies: list[Anomaly] = []
        for heartbeat in heartbeats:
            if heartbeat.age(now_utc) > self._timeout:
                anomalies.append(
                    Anomaly(
                        kind="daemon_unresponsive",
                        subject=heartbeat.name,
                        details={"heartbeat_age_seconds": int(heartbeat.age(now_utc).total_seconds())},
                    )
                )
        for mount in self._required_mounts:
            if not mount.exists():
                anomalies.append(
                    Anomaly(
                        kind="covenant_missing",
                        subject=mount.as_posix(),
                        details={"issue": "missing"},
                    )
                )
            elif not mount.is_dir():
                anomalies.append(
                    Anomaly(
                        kind="covenant_corrupt",
                        subject=mount.as_posix(),
                        details={"issue": "not_directory"},
                    )
                )
        anomalies.extend(self._check_lineage())
        return anomalies

    def _check_lineage(self) -> list[Anomaly]:
        pointer = self._lineage_pointer
        if pointer is None:
            return []
        if not pointer.exists():
            return [
                Anomaly(
                    kind="lineage_pointer_missing",
                    subject=pointer.as_posix(),
                    details={"pointer": pointer.as_posix()},
                )
            ]
        try:
            target_name = pointer.read_text(encoding="utf-8").strip()
        except OSError:
            return [
                Anomaly(
                    kind="lineage_pointer_corrupt",
                    subject=pointer.as_posix(),
                    details={"pointer": pointer.as_posix(), "issue": "unreadable"},
                )
            ]
        if not target_name:
            return [
                Anomaly(
                    kind="lineage_pointer_corrupt",
                    subject=pointer.as_posix(),
                    details={"pointer": pointer.as_posix(), "issue": "empty"},
                )
            ]
        archive = self._lineage_archive or pointer.parent
        target = archive / target_name
        if not target.exists():
            return [
                Anomaly(
                    kind="lineage_target_missing",
                    subject=target_name,
                    details={
                        "pointer": pointer.as_posix(),
                        "expected_path": target.as_posix(),
                    },
                )
            ]
        return []


class IntegrityGatekeeper:
    """Simple integrity filter used by the review board."""

    def __init__(self, allowed_signatures: Sequence[str] | None = None) -> None:
        self._allowed = set(allowed_signatures or [])

    def accept(self, action: RepairAction) -> bool:
        metadata = action.metadata
        if metadata.get("hostile"):
            return False
        signature = metadata.get("signature")
        if signature is None:
            return True
        return signature in self._allowed


@dataclass
class ReviewDecision:
    approved: bool
    quarantined: bool
    reason: str = ""


class ReviewBoard:
    """Centralized approval gate for synthesized repairs."""

    def __init__(
        self,
        *,
        trust_threshold: float = 0.6,
        integrity_gatekeeper: IntegrityGatekeeper | None = None,
    ) -> None:
        self._trust_threshold = trust_threshold
        self._gatekeeper = integrity_gatekeeper or IntegrityGatekeeper()

    def evaluate(self, action: RepairAction, anomaly: Anomaly) -> ReviewDecision:
        metadata = action.metadata
        trust = float(metadata.get("trust", 0.0))
        if trust < self._trust_threshold:
            return ReviewDecision(False, True, "insufficient_trust")
        if not self._gatekeeper.accept(action):
            return ReviewDecision(False, True, "integrity_blocked")
        return ReviewDecision(True, False, "approved")


class RepairSynthesizer:
    """Translates anomalies into concrete recovery actions."""

    def __init__(self, environment: HealingEnvironment) -> None:
        self._env = environment

    def draft(self, anomaly: Anomaly) -> RepairAction | None:
        if anomaly.kind == "daemon_unresponsive":
            return RepairAction(
                kind="restart_daemon",
                subject=anomaly.subject,
                description=f"Restart stalled daemon {anomaly.subject}",
                execute=lambda: self._env.restart_daemon(anomaly.subject),
                auto_adopt=True,
                metadata={"trust": 0.9, "origin": "CodexHealer"},
            )
        if anomaly.kind in {"covenant_missing", "covenant_corrupt"}:
            mount_path = Path(anomaly.subject)
            return RepairAction(
                kind="restore_mount",
                subject=mount_path.as_posix(),
                description=f"Rebuild covenant mount {mount_path}",
                execute=lambda: self._env.ensure_mount(mount_path),
                auto_adopt=True,
                metadata={"trust": 0.85, "origin": "CodexHealer"},
            )
        if anomaly.kind in {"lineage_pointer_missing", "lineage_pointer_corrupt", "lineage_target_missing"}:
            pointer_path = (
                Path(str(anomaly.details.get("pointer")))
                if "pointer" in anomaly.details
                else self._env.lineage_pointer
            )
            return RepairAction(
                kind="rebind_lineage",
                subject=str(pointer_path) if pointer_path else anomaly.subject,
                description="Repair lineage pointer",
                execute=lambda: self._env.rebind_lineage(pointer_path, self._env.latest_snapshot()),
                auto_adopt=False,
                metadata={"trust": 0.75, "origin": "CodexHealer"},
            )
        return None

    def apply(self, action: RepairAction) -> bool:
        try:
            return bool(action.execute())
        except Exception:  # pragma: no cover - defensive guard
            return False


class ReGenesisProtocol:
    """Fallback reconstruction when direct repair cannot proceed."""

    def __init__(self, environment: HealingEnvironment) -> None:
        self._env = environment

    def rebuild(self, anomaly: Anomaly, action: RepairAction | None) -> dict[str, object]:
        snapshot = self._env.latest_snapshot()
        if snapshot is None:
            return {"status": "no_snapshot"}
        self._env.restore_snapshot(snapshot)
        amendments = self._env.load_amendments()
        self._env.replay_amendments(amendments)
        return {
            "status": "regenesis",
            "snapshot": snapshot.name,
            "amendments_replayed": len(amendments),
        }


class CodexHealer:
    """Coordinates the self-healing flow across all components."""

    def __init__(
        self,
        watcher: PulseWatcher,
        synthesizer: RepairSynthesizer,
        review_board: ReviewBoard,
        regenesis: ReGenesisProtocol,
        ledger: RecoveryLedger,
    ) -> None:
        self._watcher = watcher
        self._synth = synthesizer
        self._board = review_board
        self._regenesis = regenesis
        self._ledger = ledger

    def run(self, heartbeats: Iterable[DaemonHeartbeat], *, now: datetime | None = None) -> list[dict[str, object]]:
        anomalies = self._watcher.scan(heartbeats, now=now)
        results: list[dict[str, object]] = []
        for anomaly in anomalies:
            results.append(self._handle_anomaly(anomaly, None))
        return results

    def review_external(self, anomaly: Anomaly, action: RepairAction) -> dict[str, object]:
        return self._handle_anomaly(anomaly, action)

    def _handle_anomaly(self, anomaly: Anomaly, forced_action: RepairAction | None) -> dict[str, object]:
        action = forced_action or self._synth.draft(anomaly)
        if action is None:
            regen_info = self._regenesis.rebuild(anomaly, None)
            return self._ledger.log(
                "auto-repair escalated",
                anomaly=anomaly,
                details={"reason": "no_repair_available", "regenesis": regen_info},
            )
        decision = self._board.evaluate(action, anomaly)
        if not decision.approved:
            regen_info = self._regenesis.rebuild(anomaly, action)
            return self._ledger.log(
                "auto-repair rejected",
                anomaly=anomaly,
                action=action,
                details={"review_reason": decision.reason, "regenesis": regen_info},
                quarantined=decision.quarantined,
            )
        success = self._synth.apply(action)
        if success:
            return self._ledger.log("auto-repair applied", anomaly=anomaly, action=action)
        regen_info = self._regenesis.rebuild(anomaly, action)
        return self._ledger.log(
            "auto-repair escalated",
            anomaly=anomaly,
            action=action,
            details={"regenesis": regen_info},
        )


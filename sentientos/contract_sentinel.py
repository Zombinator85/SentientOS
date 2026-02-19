"""Contract Sentinel: monitor contract drift and enqueue Forge recovery campaigns."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from sentientos.event_stream import record_forge_event
from sentientos.forge_outcomes import OutcomeSummary, summarize_report
from sentientos.forge_queue import ForgeQueue, ForgeRequest

DEFAULT_WATCHED = ["ci_baseline", "forge_observatory", "stability_doctrine"]
STATE_PATH = Path("glow/forge/sentinel_state.json")
POLICY_PATH = Path("glow/forge/sentinel_policy.json")


@dataclass(slots=True)
class SentinelPolicy:
    enabled: bool = False
    watched_domains: list[str] = field(default_factory=lambda: list(DEFAULT_WATCHED))
    enqueue_map: dict[str, str] = field(
        default_factory=lambda: {
            "ci_baseline": "campaign:ci_baseline_recovery",
            "forge_observatory": "forge_smoke_noop",
            "stability_doctrine": "stability_repair",
        }
    )
    drift_thresholds: dict[str, dict[str, Any]] = field(
        default_factory=lambda: {
            "ci_baseline": {
                "failed_count_increase_threshold": 1,
                "failed_count_increase_pct_threshold": 0.0,
                "pass_to_fail": True,
            },
            "forge_observatory": {
                "corrupt_count_gt": 0,
                "index_required": True,
            },
            "stability_doctrine": {
                "require_toolchain": True,
                "require_vow_artifacts": True,
            },
        }
    )
    cooldown_minutes: dict[str, int] = field(default_factory=lambda: {"global": 30, "ci_baseline": 60, "forge_observatory": 60, "stability_doctrine": 60})
    max_enqueues_per_day: int = 3
    allow_autopublish: bool = False
    allow_automerge: bool = False


@dataclass(slots=True)
class SentinelState:
    last_seen_contract_digest: str = ""
    last_enqueued_at_by_domain: dict[str, str] = field(default_factory=dict)
    enqueues_today: int = 0
    last_reset_date: str = ""
    last_quarantine_by_domain: dict[str, str] = field(default_factory=dict)
    last_quarantine_reasons: dict[str, list[str]] = field(default_factory=dict)
    last_progress_by_domain: dict[str, dict[str, Any]] = field(default_factory=dict)
    last_stagnation_at_by_domain: dict[str, str] = field(default_factory=dict)


class ContractSentinel:
    def __init__(self, *, repo_root: Path | None = None, queue: ForgeQueue | None = None) -> None:
        self.repo_root = (repo_root or Path.cwd()).resolve()
        self.queue = queue or ForgeQueue(pulse_root=self.repo_root / "pulse")
        self.state_path = self.repo_root / STATE_PATH
        self.policy_path = self.repo_root / POLICY_PATH
        self.contract_status_path = self.repo_root / "glow/contracts/contract_status.json"
        self.ci_baseline_path = self.repo_root / "glow/contracts/ci_baseline.json"
        self.forge_index_path = self.repo_root / "glow/forge/index.json"
        self.forge_policy_path = self.repo_root / "glow/forge/policy.json"
        self.stability_doctrine_path = self.repo_root / "glow/contracts/stability_doctrine.json"

    def load_policy(self) -> SentinelPolicy:
        payload = _load_json(self.policy_path)
        if not payload:
            return SentinelPolicy()
        return SentinelPolicy(
            enabled=bool(payload.get("enabled", False)),
            watched_domains=[str(item) for item in payload.get("watched_domains", DEFAULT_WATCHED) if isinstance(item, str)],
            enqueue_map={str(k): str(v) for k, v in payload.get("enqueue_map", {}).items()} if isinstance(payload.get("enqueue_map"), dict) else SentinelPolicy().enqueue_map,
            drift_thresholds={str(k): v for k, v in payload.get("drift_thresholds", {}).items() if isinstance(k, str) and isinstance(v, dict)} if isinstance(payload.get("drift_thresholds"), dict) else SentinelPolicy().drift_thresholds,
            cooldown_minutes={str(k): int(v) for k, v in payload.get("cooldown_minutes", {"global": 30}).items() if isinstance(v, int)},
            max_enqueues_per_day=int(payload.get("max_enqueues_per_day", 3)),
            allow_autopublish=bool(payload.get("allow_autopublish", False)),
            allow_automerge=bool(payload.get("allow_automerge", False)),
        )

    def save_policy(self, policy: SentinelPolicy) -> None:
        _write_json(self.policy_path, asdict(policy))

    def load_state(self) -> SentinelState:
        payload = _load_json(self.state_path)
        if not payload:
            return SentinelState(last_reset_date=_today_utc())
        return SentinelState(
            last_seen_contract_digest=str(payload.get("last_seen_contract_digest", "")),
            last_enqueued_at_by_domain={str(k): str(v) for k, v in payload.get("last_enqueued_at_by_domain", {}).items()} if isinstance(payload.get("last_enqueued_at_by_domain"), dict) else {},
            enqueues_today=int(payload.get("enqueues_today", 0)),
            last_reset_date=str(payload.get("last_reset_date", _today_utc())),
            last_quarantine_by_domain={str(k): str(v) for k, v in payload.get("last_quarantine_by_domain", {}).items()} if isinstance(payload.get("last_quarantine_by_domain"), dict) else {},
            last_quarantine_reasons={str(k): [str(item) for item in v if isinstance(item, str)] for k, v in payload.get("last_quarantine_reasons", {}).items() if isinstance(v, list)} if isinstance(payload.get("last_quarantine_reasons"), dict) else {},
            last_progress_by_domain={str(k): dict(v) for k, v in payload.get("last_progress_by_domain", {}).items() if isinstance(k, str) and isinstance(v, dict)} if isinstance(payload.get("last_progress_by_domain"), dict) else {},
            last_stagnation_at_by_domain={str(k): str(v) for k, v in payload.get("last_stagnation_at_by_domain", {}).items()} if isinstance(payload.get("last_stagnation_at_by_domain"), dict) else {},
        )

    def save_state(self, state: SentinelState) -> None:
        _write_json(self.state_path, asdict(state))

    def tick(self) -> dict[str, Any]:
        policy = self.load_policy()
        state = self.load_state()
        if state.last_reset_date != _today_utc():
            state.enqueues_today = 0
            state.last_reset_date = _today_utc()

        if not policy.enabled:
            self.save_state(state)
            return {"status": "disabled"}

        snapshot = self._snapshot(policy)
        digest = _digest(snapshot)
        if digest == state.last_seen_contract_digest:
            self.save_state(state)
            return {"status": "no_change", "digest": digest}

        now = _iso_now()
        enqueued: list[dict[str, str]] = []
        for domain in policy.watched_domains:
            trigger = self._domain_trigger(domain=domain, policy=policy, snapshot=snapshot)
            if not trigger:
                continue
            allowed, reason = self._can_enqueue(domain=domain, goal_or_campaign=policy.enqueue_map.get(domain, ""), policy=policy, state=state)
            if not allowed:
                self._emit("policy_blocked", domain=domain, details={"reason": reason})
                continue
            goal = policy.enqueue_map.get(domain)
            if not goal:
                continue
            request = ForgeRequest(
                request_id="",
                goal=goal,
                goal_id=goal,
                requested_by="ContractSentinel",
                metadata={
                    "trigger_domain": domain,
                    "trigger_snapshot": trigger,
                    "trigger_digest": digest,
                    "trigger_provenance": {
                        "source": "contract_sentinel",
                        "triggered_at": now,
                        "domain": domain,
                    },
                    "sentinel_triggered": True,
                },
                autopublish_flags=({"auto_publish": True, "sentinel_allow_autopublish": True, "sentinel_allow_automerge": bool(policy.allow_automerge)} if policy.allow_autopublish else {}),
            )
            request_id = self.queue.enqueue(request)
            state.last_enqueued_at_by_domain[domain] = now
            state.enqueues_today += 1
            enqueued.append({"domain": domain, "request_id": request_id, "goal": goal})
            self._emit("enqueued", domain=domain, details={"request_id": request_id, "goal": goal})

        state.last_seen_contract_digest = digest
        self.save_state(state)
        return {"status": "ok", "digest": digest, "enqueued": enqueued}

    def summary(self) -> dict[str, Any]:
        policy = self.load_policy()
        state = self.load_state()
        now = datetime.now(timezone.utc)
        cooldown_remaining: dict[str, int] = {}
        for domain, last in state.last_enqueued_at_by_domain.items():
            last_dt = _parse_iso(last)
            if last_dt is None:
                cooldown_remaining[domain] = 0
                continue
            cdm = policy.cooldown_minutes.get(domain, policy.cooldown_minutes.get("global", 0))
            rem = int((last_dt + timedelta(minutes=cdm) - now).total_seconds())
            cooldown_remaining[domain] = max(0, rem)
        last_domain = None
        last_time = None
        if state.last_enqueued_at_by_domain:
            last_domain, last_time = sorted(state.last_enqueued_at_by_domain.items(), key=lambda item: item[1])[-1]
        return {
            "sentinel_enabled": policy.enabled,
            "sentinel_last_enqueued": {"domain": last_domain, "time": last_time} if last_domain else None,
            "sentinel_state": {
                "enqueues_today": state.enqueues_today,
                "max_enqueues_per_day": policy.max_enqueues_per_day,
                "cooldown_remaining_seconds": cooldown_remaining,
                "last_quarantine_by_domain": state.last_quarantine_by_domain,
                "last_quarantine_reasons": state.last_quarantine_reasons,
                "last_progress_by_domain": state.last_progress_by_domain,
                "last_stagnation_at_by_domain": state.last_stagnation_at_by_domain,
            },
        }

    def _snapshot(self, policy: SentinelPolicy) -> dict[str, Any]:
        status = _load_json(self.contract_status_path)
        ci = _load_json(self.ci_baseline_path)
        idx = _load_json(self.forge_index_path)
        domains: dict[str, Any] = {}
        if "ci_baseline" in policy.watched_domains:
            domains["ci_baseline"] = {
                "passed": bool(ci.get("passed", False)),
                "failed_count": int(ci.get("failed_count", 0)) if isinstance(ci.get("failed_count"), int) else 0,
            }
        if "forge_observatory" in policy.watched_domains:
            corrupt = idx.get("corrupt_count")
            total_corrupt = 0
            if isinstance(corrupt, dict) and isinstance(corrupt.get("total"), int):
                total_corrupt = int(corrupt["total"])
            domains["forge_observatory"] = {
                "index_present": self.forge_index_path.exists(),
                "corrupt_total": total_corrupt,
            }
        if "stability_doctrine" in policy.watched_domains:
            doctrine = _load_json(self.stability_doctrine_path)
            raw_toolchain = doctrine.get("toolchain")
            raw_vow = doctrine.get("vow_artifacts")
            toolchain: dict[str, Any] = raw_toolchain if isinstance(raw_toolchain, dict) else {}
            vow: dict[str, Any] = raw_vow if isinstance(raw_vow, dict) else {}
            domains["stability_doctrine"] = {
                "doctrine_present": self.stability_doctrine_path.exists(),
                "verify_audits_available": bool(toolchain.get("verify_audits_available", False)),
                "immutable_manifest_present": bool(vow.get("immutable_manifest_present", False)),
            }
        return {"contract_status": status, "domains": domains}

    def _domain_trigger(self, *, domain: str, policy: SentinelPolicy, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        status = _load_json(self.contract_status_path)
        previous = status.get("previous") if isinstance(status.get("previous"), dict) else {}
        current_domains = snapshot.get("domains")
        if not isinstance(current_domains, dict):
            return None
        current = current_domains.get(domain)
        if not isinstance(current, dict):
            return None
        if domain == "ci_baseline":
            thresholds = policy.drift_thresholds.get("ci_baseline", {})
            prev_raw = previous.get("ci_baseline") if isinstance(previous, dict) else None
            prev_domain: dict[str, Any] = prev_raw if isinstance(prev_raw, dict) else {}
            prev_failed = int(prev_domain.get("failed_count", 0)) if isinstance(prev_domain.get("failed_count"), int) else 0
            cur_failed = int(current.get("failed_count", 0)) if isinstance(current.get("failed_count"), int) else 0
            increase = cur_failed - prev_failed
            threshold_abs = int(thresholds.get("failed_count_increase_threshold", 1)) if isinstance(thresholds.get("failed_count_increase_threshold"), int) else 1
            threshold_pct = float(thresholds.get("failed_count_increase_pct_threshold", 0.0)) if isinstance(thresholds.get("failed_count_increase_pct_threshold"), (int, float)) else 0.0
            pct = ((increase / prev_failed) * 100.0) if prev_failed > 0 else (100.0 if increase > 0 else 0.0)
            prev_passed = bool(prev_domain.get("passed", True))
            cur_passed = bool(current.get("passed", False))
            if bool(thresholds.get("pass_to_fail", True)) and prev_passed and not cur_passed:
                return {"reason": "pass_to_fail", "prev_failed": prev_failed, "cur_failed": cur_failed}
            if increase >= threshold_abs:
                return {"reason": "failed_count_increase", "increase": increase, "threshold": threshold_abs}
            if pct >= threshold_pct and increase > 0 and threshold_pct > 0:
                return {"reason": "failed_count_pct_increase", "pct": round(pct, 2), "threshold_pct": threshold_pct}
            return None
        if domain == "forge_observatory":
            thresholds = policy.drift_thresholds.get("forge_observatory", {})
            corrupt_gt = int(thresholds.get("corrupt_count_gt", 0)) if isinstance(thresholds.get("corrupt_count_gt"), int) else 0
            index_required = bool(thresholds.get("index_required", True))
            corrupt_total = int(current.get("corrupt_total", 0)) if isinstance(current.get("corrupt_total"), int) else 0
            index_present = bool(current.get("index_present", False))
            if index_required and not index_present:
                return {"reason": "index_missing"}
            if corrupt_total > corrupt_gt:
                return {"reason": "corrupt_count", "corrupt_total": corrupt_total, "threshold": corrupt_gt}
            return None
        if domain == "stability_doctrine":
            thresholds = policy.drift_thresholds.get("stability_doctrine", {})
            if not bool(current.get("doctrine_present", False)):
                return {"reason": "doctrine_missing"}
            if bool(thresholds.get("require_toolchain", True)) and not bool(current.get("verify_audits_available", False)):
                return {"reason": "toolchain_missing"}
            if bool(thresholds.get("require_vow_artifacts", True)) and not bool(current.get("immutable_manifest_present", False)):
                return {"reason": "vow_artifacts_missing"}
            return None
        return None

    def _can_enqueue(self, *, domain: str, goal_or_campaign: str, policy: SentinelPolicy, state: SentinelState) -> tuple[bool, str]:
        if state.enqueues_today >= policy.max_enqueues_per_day:
            return (False, "max_enqueues_per_day")
        if domain == "ci_baseline":
            progress_decision = self._apply_progress_decision(domain=domain, state=state)
            if progress_decision == "stagnation_backoff":
                return (False, "stagnation_backoff")
        if self._is_within_cooldown(domain=domain, policy=policy, state=state):
            return (False, "cooldown")
        if self._is_recent_self_receipt(domain=domain, policy=policy):
            return (False, "recent_self_receipt")
        if self._is_active_self_run_for_domain(domain=domain):
            return (False, "active_self_run")
        if not self._goal_allowed(goal_or_campaign):
            return (False, f"goal_not_allowlisted:{goal_or_campaign}")
        if policy.allow_autopublish and not self._autopublish_allowed():
            return (False, "autopublish_not_allowlisted")
        return (True, "ok")

    def _is_within_cooldown(self, *, domain: str, policy: SentinelPolicy, state: SentinelState) -> bool:
        now = datetime.now(timezone.utc)
        parsed_values = [_parse_iso(ts) for ts in state.last_enqueued_at_by_domain.values()]
        valid_values = [item for item in parsed_values if item is not None]
        last_global = max(valid_values) if valid_values else None
        global_minutes = policy.cooldown_minutes.get("global", 0)
        if last_global and now - last_global < timedelta(minutes=global_minutes):
            return True
        last_domain = _parse_iso(state.last_enqueued_at_by_domain.get(domain))
        base_domain_minutes = policy.cooldown_minutes.get(domain, global_minutes)
        multiplier = self._cooldown_multiplier_for(domain=domain, state=state)
        domain_minutes = max(1, int(round(base_domain_minutes * multiplier)))
        return bool(last_domain and now - last_domain < timedelta(minutes=domain_minutes))


    def _apply_progress_decision(self, *, domain: str, state: SentinelState) -> str:
        summary = self._latest_sentinel_outcome(domain=domain)
        if summary is None:
            return "unknown"
        essentials = {
            "run_id": summary.run_id,
            "goal_id": summary.goal_id,
            "campaign_id": summary.campaign_id,
            "outcome": summary.outcome,
            "ci_before_failed_count": summary.ci_before_failed_count,
            "ci_after_failed_count": summary.ci_after_failed_count,
            "progress_delta_percent": summary.progress_delta_percent,
            "last_progress_improved": summary.last_progress_improved,
            "last_progress_notes": summary.last_progress_notes,
            "no_improvement_streak": summary.no_improvement_streak,
            "audit_status": summary.audit_status,
            "created_at": summary.created_at,
        }
        state.last_progress_by_domain[domain] = essentials

        stagnant = (
            summary.ci_before_failed_count is not None
            and summary.ci_after_failed_count is not None
            and summary.ci_after_failed_count >= summary.ci_before_failed_count
            and not summary.last_progress_improved
        )
        improving = (
            (summary.ci_before_failed_count is not None and summary.ci_after_failed_count is not None and summary.ci_after_failed_count < summary.ci_before_failed_count)
            or (summary.progress_delta_percent is not None and summary.progress_delta_percent > 0)
            or summary.last_progress_improved
        )
        if stagnant:
            state.last_stagnation_at_by_domain[domain] = _iso_now()
            self._emit(
                "sentinel_stagnation_backoff",
                domain=domain,
                details={"run_id": summary.run_id, "goal_id": summary.goal_id, "campaign_id": summary.campaign_id},
            )
            return "stagnation_backoff"
        if improving:
            self._emit(
                "sentinel_convergence",
                domain=domain,
                details={"run_id": summary.run_id, "goal_id": summary.goal_id, "campaign_id": summary.campaign_id},
            )
            return "convergence"
        return "unknown"

    def _cooldown_multiplier_for(self, *, domain: str, state: SentinelState) -> float:
        payload = state.last_progress_by_domain.get(domain)
        if not isinstance(payload, dict):
            return 1.0
        before = payload.get("ci_before_failed_count")
        after = payload.get("ci_after_failed_count")
        improved = bool(payload.get("last_progress_improved", False))
        pct = payload.get("progress_delta_percent")
        if isinstance(before, int) and isinstance(after, int) and after >= before and not improved:
            return 5.0
        if (isinstance(before, int) and isinstance(after, int) and after < before) or (isinstance(pct, (int, float)) and float(pct) > 0) or improved:
            return 0.5
        return 1.0

    def _latest_sentinel_outcome(self, *, domain: str) -> OutcomeSummary | None:
        queue_rows = _read_jsonl(self.repo_root / "pulse/forge_queue.jsonl")
        candidate_ids: list[str] = []
        for row in reversed(queue_rows):
            metadata = row.get("metadata")
            if row.get("requested_by") != "ContractSentinel" or not isinstance(metadata, dict):
                continue
            if metadata.get("trigger_domain") != domain:
                continue
            request_id = row.get("request_id")
            if isinstance(request_id, str):
                candidate_ids.append(request_id)
            if len(candidate_ids) >= 20:
                break
        if not candidate_ids:
            return None
        receipts = self.queue.recent_receipts(limit=400)
        for receipt in reversed(receipts):
            if receipt.request_id not in candidate_ids or receipt.status not in {"success", "failed"}:
                continue
            if not receipt.report_path:
                continue
            report = _load_json(self.repo_root / receipt.report_path)
            if not report:
                continue
            return summarize_report(report)
        return None

    def _is_recent_self_receipt(self, *, domain: str, policy: SentinelPolicy) -> bool:
        requests = {req.request_id: req for req in self.queue.pending_requests()}
        for receipt in reversed(self.queue.recent_receipts(limit=100)):
            req = requests.get(receipt.request_id)
            if req is None:
                queue_rows = _read_jsonl(self.repo_root / "pulse/forge_queue.jsonl")
                row = next((item for item in reversed(queue_rows) if str(item.get("request_id")) == receipt.request_id), None)
                if not row:
                    continue
                metadata = row.get("metadata")
                if not isinstance(metadata, dict):
                    continue
                if metadata.get("trigger_domain") != domain or row.get("requested_by") != "ContractSentinel":
                    continue
            else:
                if req.requested_by != "ContractSentinel" or req.metadata.get("trigger_domain") != domain:
                    continue
            finished = _parse_iso(receipt.finished_at)
            if finished is None:
                continue
            minutes = policy.cooldown_minutes.get(domain, policy.cooldown_minutes.get("global", 0))
            return datetime.now(timezone.utc) - finished < timedelta(minutes=minutes)
        return False

    def _is_active_self_run_for_domain(self, *, domain: str) -> bool:
        lock = _load_json(self.repo_root / ".forge/forge.lock")
        req_id = lock.get("request_id")
        if not isinstance(req_id, str):
            return False
        queue_rows = _read_jsonl(self.repo_root / "pulse/forge_queue.jsonl")
        row = next((item for item in reversed(queue_rows) if str(item.get("request_id")) == req_id), None)
        if not isinstance(row, dict):
            return False
        metadata = row.get("metadata")
        return bool(
            row.get("requested_by") == "ContractSentinel"
            and isinstance(metadata, dict)
            and metadata.get("trigger_domain") == domain
        )

    def _goal_allowed(self, goal_or_campaign: str) -> bool:
        policy = _load_json(self.forge_policy_path)
        allowed = policy.get("allowlisted_goal_ids")
        if not isinstance(allowed, list):
            return True
        return goal_or_campaign in {str(item) for item in allowed if isinstance(item, str)}

    def _autopublish_allowed(self) -> bool:
        policy = _load_json(self.forge_policy_path)
        allowed = policy.get("allowlisted_autopublish_flags")
        return isinstance(allowed, list) and "auto_publish" in {str(item) for item in allowed if isinstance(item, str)}

    def _emit(self, status: str, *, domain: str, details: dict[str, Any]) -> None:
        record_forge_event(
            {
                "event": "contract_sentinel",
                "status": status,
                "domain": domain,
                **details,
            }
        )

    def note_quarantine(self, *, domain: str, quarantine_ref: str | None, reasons: list[str]) -> None:
        policy = self.load_policy()
        state = self.load_state()
        state.last_quarantine_by_domain[domain] = quarantine_ref or ""
        state.last_quarantine_reasons[domain] = [str(item) for item in reasons]
        state.last_enqueued_at_by_domain[domain] = _iso_now()
        self.save_state(state)
        record_forge_event({
            "event": "sentinel_quarantine",
            "domain": domain,
            "quarantine_ref": quarantine_ref,
            "reasons": reasons,
            "level": "warning",
        })
        extra = max(1, policy.cooldown_minutes.get(domain, policy.cooldown_minutes.get("global", 30))) * 3
        state.last_enqueued_at_by_domain[domain] = _iso_now()
        policy.cooldown_minutes[domain] = extra
        self.save_policy(policy)
        self.save_state(state)



def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _digest(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

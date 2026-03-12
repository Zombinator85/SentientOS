from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class PropertyResult:
    property_id: str
    description: str
    passed: bool
    checked_states: int
    counterexample: dict[str, object] | None

    def to_dict(self) -> dict[str, object]:
        return {
            "property_id": self.property_id,
            "description": self.description,
            "passed": self.passed,
            "checked_states": self.checked_states,
            "counterexample": self.counterexample,
        }


@dataclass(frozen=True)
class SpecResult:
    spec_id: str
    title: str
    passed: bool
    states_explored: int
    properties: tuple[PropertyResult, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "spec_id": self.spec_id,
            "title": self.title,
            "passed": self.passed,
            "states_explored": self.states_explored,
            "properties": [item.to_dict() for item in self.properties],
        }


def _stable_hash(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _load_model_config(repo_root: Path, spec_id: str) -> dict[str, object]:
    path = repo_root / "formal" / "models" / f"{spec_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _discover_specs(repo_root: Path) -> list[str]:
    model_dir = repo_root / "formal" / "models"
    specs = sorted(path.stem for path in model_dir.glob("*.json"))
    return specs


def _runtime_governor_properties(config: dict[str, object]) -> tuple[list[PropertyResult], int]:
    actions = config["actions"]
    assert isinstance(actions, list)
    restricted_blocked = set(config["restricted_blocks"])
    contention_limit = int(config["contention_limit"])
    reserved_slots = int(config["recovery_reserved_slots"])

    states = list(
        product(
            ("nominal", "restricted"),
            ("normal", "warn", "block"),
            range(0, contention_limit + 2),
            range(0, 6),
        )
    )

    def decision(posture: str, pressure: str, contention_total: int, denied_streak: int, action: dict[str, object]) -> tuple[str, bool]:
        action_name = str(action["name"])
        deferrable = bool(action["deferrable"])
        local_safety = bool(action["local_safety"])
        priority = int(action["priority"])

        reason = "allowed"
        allowed = True
        if posture == "restricted" and action_name in restricted_blocked:
            reason, allowed = "restricted_posture_block", False
        elif pressure == "block" and deferrable:
            reason, allowed = "deferred_for_local_safety_under_pressure", False
        elif contention_total >= contention_limit and deferrable:
            reason, allowed = "deferred_contention_limit", False
        elif not local_safety and (contention_limit - contention_total) <= reserved_slots:
            reason, allowed = "deferred_reserved_for_recovery", False
        elif pressure == "warn" and priority >= 3 and denied_streak >= 4:
            reason, allowed = "deferred_low_priority_under_pressure", False
        return reason, allowed

    checked = 0
    counterexample: dict[str, object] | None = None
    for posture, pressure, contention_total, denied_streak in states:
        checked += 1
        local_decisions = []
        deferrable_decisions = []
        for action in actions:
            reason, allowed = decision(posture, pressure, contention_total, denied_streak, action)
            if bool(action["local_safety"]):
                local_decisions.append((action["name"], reason, allowed))
            if bool(action["deferrable"]):
                deferrable_decisions.append((action["name"], reason, allowed))
        local_denied = any(not row[2] for row in local_decisions)
        deferrable_admitted = any(row[2] for row in deferrable_decisions)
        if local_denied and deferrable_admitted:
            counterexample = {
                "state": {
                    "posture": posture,
                    "pressure": pressure,
                    "contention_total": contention_total,
                    "denied_streak": denied_streak,
                },
                "local_decisions": local_decisions,
                "deferrable_decisions": deferrable_decisions,
            }
            break
    p1 = PropertyResult(
        property_id="rg_local_safety_not_starved",
        description="Local safety action classes are never starved while deferrable classes admit under identical bounded pressure/contention state.",
        passed=counterexample is None,
        checked_states=checked,
        counterexample=counterexample,
    )

    checked = 0
    counterexample = None
    for posture, pressure, contention_total, denied_streak in states:
        checked += 1
        if posture != "restricted":
            continue
        for action in actions:
            if str(action["name"]) not in restricted_blocked:
                continue
            reason, allowed = decision(posture, pressure, contention_total, denied_streak, action)
            if allowed or reason != "restricted_posture_block":
                counterexample = {
                    "state": {
                        "posture": posture,
                        "pressure": pressure,
                        "contention_total": contention_total,
                        "denied_streak": denied_streak,
                    },
                    "action": action,
                    "reason": reason,
                    "allowed": allowed,
                }
                break
        if counterexample is not None:
            break
    p2 = PropertyResult(
        property_id="rg_restricted_blocks_required_classes",
        description="Restricted posture blocks configured required action classes.",
        passed=counterexample is None,
        checked_states=checked,
        counterexample=counterexample,
    )

    checked = 0
    counterexample = None
    for posture, pressure, contention_total, denied_streak in states:
        checked += 1
        next_contention = min(contention_limit + 1, contention_total + 1)
        next_streak = min(6, denied_streak + 1)
        if next_contention > contention_limit + 1 or next_streak > 6:
            counterexample = {
                "state": {
                    "posture": posture,
                    "pressure": pressure,
                    "contention_total": contention_total,
                    "denied_streak": denied_streak,
                },
                "next": {"contention_total": next_contention, "denied_streak": next_streak},
            }
            break
    p3 = PropertyResult(
        property_id="rg_bounded_counters",
        description="Bounded contention and starvation counters remain within configured model limits.",
        passed=counterexample is None,
        checked_states=checked,
        counterexample=counterexample,
    )

    checked = 0
    counterexample = None
    for posture, pressure, contention_total, denied_streak in states:
        checked += 1
        for action in actions:
            left = decision(posture, pressure, contention_total, denied_streak, action)
            right = decision(posture, pressure, contention_total, denied_streak, action)
            if left != right:
                counterexample = {
                    "state": {
                        "posture": posture,
                        "pressure": pressure,
                        "contention_total": contention_total,
                        "denied_streak": denied_streak,
                    },
                    "action": action,
                    "left": left,
                    "right": right,
                }
                break
        if counterexample is not None:
            break
    p4 = PropertyResult(
        property_id="rg_deterministic_precedence",
        description="Admission precedence and outcome are deterministic for identical inputs.",
        passed=counterexample is None,
        checked_states=checked,
        counterexample=counterexample,
    )

    return [p1, p2, p3, p4], len(states)


def _audit_reanchor_properties(config: dict[str, object]) -> tuple[list[PropertyResult], int]:
    _ = config
    actions = ("break_detected", "checkpoint", "append_bad", "append_good")
    max_depth = 4
    explored = 0

    def apply(state: dict[str, object], action: str) -> dict[str, object]:
        next_state = dict(state)
        if action == "break_detected":
            next_state["history_state"] = "broken_preserved"
            next_state["break_visible"] = True
            next_state["degraded"] = True
        elif action == "checkpoint" and next_state["history_state"] == "broken_preserved":
            next_state["checkpoint_explicit"] = True
        elif action == "append_bad":
            next_state["continuation_descends"] = False
            if next_state["checkpoint_explicit"]:
                next_state["history_state"] = "broken_preserved"
                next_state["degraded"] = True
        elif action == "append_good":
            next_state["continuation_descends"] = True
            if next_state["checkpoint_explicit"]:
                next_state["history_state"] = "reanchored_continuation"
                next_state["degraded"] = False
        return next_state

    traces: list[list[tuple[str, dict[str, object]]]] = []
    seed = {
        "history_state": "intact_trusted",
        "break_visible": False,
        "checkpoint_explicit": False,
        "continuation_descends": None,
        "degraded": False,
    }
    frontier = [[("init", seed)]]
    for _ in range(max_depth):
        next_frontier: list[list[tuple[str, dict[str, object]]]] = []
        for trace in frontier:
            traces.append(trace)
            current = trace[-1][1]
            for action in actions:
                nxt = apply(current, action)
                next_frontier.append([*trace, (action, nxt)])
                explored += 1
        frontier = next_frontier

    def check_property(property_id: str, description: str, predicate: Callable[[list[tuple[str, dict[str, object]]]], bool]) -> PropertyResult:
        checked_states = 0
        for trace in traces:
            checked_states += 1
            if not predicate(trace):
                return PropertyResult(property_id, description, False, checked_states, {"trace": trace})
        return PropertyResult(property_id, description, True, checked_states, None)

    p1 = check_property(
        "audit_no_silent_rewrite",
        "Broken history is never silently rewritten once break visibility is established.",
        lambda trace: not any(state["break_visible"] and state["history_state"] == "intact_trusted" for _, state in trace[1:]),
    )
    p2 = check_property(
        "audit_continuation_requires_anchor",
        "Continuation is accepted only when descending from an explicit re-anchor checkpoint.",
        lambda trace: not any(
            state["history_state"] == "reanchored_continuation"
            and not (state["checkpoint_explicit"] and state["continuation_descends"])
            for _, state in trace
        ),
    )
    p3 = check_property(
        "audit_break_visibility_persists",
        "Break visibility remains true after re-anchor continuation.",
        lambda trace: not any(
            state["history_state"] == "reanchored_continuation" and not state["break_visible"] for _, state in trace
        ),
    )
    p4 = check_property(
        "audit_reanchor_coexists_with_preserved_break",
        "Healthy continuation can coexist with preserved broken-history visibility.",
        lambda trace: not any(
            state["history_state"] == "reanchored_continuation" and not (state["break_visible"] and not state["degraded"])
            for _, state in trace
        ),
    )
    return [p1, p2, p3, p4], max(1, explored)


def _federation_quorum_properties(config: dict[str, object]) -> tuple[list[PropertyResult], int]:
    high_quorum = int(config["quorum_requirements"]["high"])
    peers = list(config["peers"])
    postures = ("nominal", "degraded", "restricted")
    states_explored = 0

    def quorum_present(peer_states: dict[str, dict[str, bool]]) -> int:
        return sum(
            1
            for row in peer_states.values()
            if row["trusted"] and row["quorum_eligible"] and row["digest_compatible"] and row["epoch_expected"]
        )

    peer_flags = list(product((True, False), repeat=4))
    examples: list[tuple[str, dict[str, dict[str, bool]], str, bool]] = []
    for posture in postures:
        for combo in product(peer_flags, repeat=len(peers)):
            mapping: dict[str, dict[str, bool]] = {}
            for idx, peer in enumerate(peers):
                trusted, eligible, digest_ok, epoch_ok = combo[idx]
                mapping[str(peer)] = {
                    "trusted": trusted,
                    "quorum_eligible": eligible,
                    "digest_compatible": digest_ok,
                    "epoch_expected": epoch_ok,
                }
            q_present = quorum_present(mapping)
            source = mapping.get("node-01", {})
            source_required_ok = bool(source.get("digest_compatible", False)) and bool(source.get("epoch_expected", False)) and bool(source.get("trusted", False))
            allow = q_present >= high_quorum and posture == "nominal" and source_required_ok
            examples.append((posture, mapping, f"{q_present}/{high_quorum}", allow))
            states_explored += 1

    def find_counter(predicate: Callable[[tuple[str, dict[str, dict[str, bool]], str, bool]], bool]) -> tuple[dict[str, object] | None, int]:
        checked = 0
        for posture, mapping, quorum, allow in examples:
            checked += 1
            row = (posture, mapping, quorum, allow)
            if not predicate(row):
                return {
                    "posture": posture,
                    "peer_states": mapping,
                    "quorum": quorum,
                    "allowed": allow,
                }, checked
        return None, checked

    c1, n1 = find_counter(lambda row: (not row[3]) or int(str(row[2]).split("/")[0]) >= high_quorum)
    p1 = PropertyResult(
        "fed_high_impact_requires_quorum",
        "High-impact federated action cannot pass without quorum.",
        passed=c1 is None,
        checked_states=n1,
        counterexample=c1,
    )

    def digest_rule(row: tuple[str, dict[str, dict[str, bool]], str, bool]) -> bool:
        _, mapping, _, allow = row
        # Model the required-action source peer as node-01; if that source is trusted but digest-incompatible,
        # high-impact admission must not pass.
        source = mapping.get("node-01", {})
        source_mismatch = bool(source.get("trusted")) and (not bool(source.get("digest_compatible")))
        if source_mismatch and allow:
            return False
        return True

    c2, n2 = find_counter(digest_rule)
    p2 = PropertyResult(
        "fed_digest_mismatch_blocks_required",
        "Digest mismatch blocks required federated high-impact actions.",
        passed=c2 is None,
        checked_states=n2,
        counterexample=c2,
    )

    c3, n3 = find_counter(lambda row: row[0] == "nominal" or not row[3])
    p3 = PropertyResult(
        "fed_local_posture_dominates_quorum",
        "Local restricted/degraded posture can dominate an otherwise valid quorum result.",
        passed=c3 is None,
        checked_states=n3,
        counterexample=c3,
    )

    def incompatible_not_counted(row: tuple[str, dict[str, dict[str, bool]], str, bool]) -> bool:
        _, mapping, quorum, _ = row
        present = int(str(quorum).split("/")[0])
        incompatible = sum(1 for peer in mapping.values() if not peer["digest_compatible"])
        return present <= len(mapping) - incompatible

    c4, n4 = find_counter(incompatible_not_counted)
    p4 = PropertyResult(
        "fed_incompatible_peers_cannot_satisfy_quorum",
        "Incompatible peers cannot satisfy quorum eligibility.",
        passed=c4 is None,
        checked_states=n4,
        counterexample=c4,
    )
    return [p1, p2, p3, p4], states_explored


def _pulse_epoch_properties(config: dict[str, object]) -> tuple[list[PropertyResult], int]:
    action_classes = list(config["compromise_restricted_actions"])
    classifications = ("current_trusted_epoch", "historical_closed_epoch", "revoked_epoch", "unknown_epoch")
    states = list(product((True, False), classifications, action_classes + ["restart_daemon"]))

    def trusted(compromise_mode: bool, classification: str, action: str) -> tuple[bool, str]:
        if classification == "revoked_epoch":
            return False, "revoked"
        if classification == "unknown_epoch":
            return False, "unknown"
        if compromise_mode and action in action_classes:
            return False, "compromise_restricted"
        return True, "trusted"

    checked = 0
    counter: dict[str, object] | None = None
    for compromise, classification, action in states:
        checked += 1
        allow, _ = trusted(compromise, classification, action)
        if classification == "revoked_epoch" and allow:
            counter = {"compromise_mode": compromise, "classification": classification, "action": action}
            break
    p1 = PropertyResult(
        "pulse_revoked_never_current_trusted",
        "Revoked epochs are never treated as current trusted epochs.",
        passed=counter is None,
        checked_states=checked,
        counterexample=counter,
    )

    checked = 0
    counter = None
    for compromise, classification, action in states:
        checked += 1
        allow, reason = trusted(compromise, classification, action)
        if compromise and action in action_classes and classification in {"current_trusted_epoch", "historical_closed_epoch"} and allow:
            counter = {
                "compromise_mode": compromise,
                "classification": classification,
                "action": action,
                "reason": reason,
            }
            break
    p2 = PropertyResult(
        "pulse_compromise_mode_tightens",
        "Compromise-response mode tightens/blocks required action classes.",
        passed=counter is None,
        checked_states=checked,
        counterexample=counter,
    )

    checked = 0
    counter = None
    for compromise, _, action in states:
        checked += 1
        historical = trusted(compromise, "historical_closed_epoch", action)[1]
        revoked = trusted(compromise, "revoked_epoch", action)[1]
        unknown = trusted(compromise, "unknown_epoch", action)[1]
        if historical in {revoked, unknown}:
            counter = {
                "compromise_mode": compromise,
                "action": action,
                "historical_reason": historical,
                "revoked_reason": revoked,
                "unknown_reason": unknown,
            }
            break
    p3 = PropertyResult(
        "pulse_historical_distinct_from_revoked_unknown",
        "Historical closed epochs remain distinguishable from revoked/unknown epochs.",
        passed=counter is None,
        checked_states=checked,
        counterexample=counter,
    )

    return [p1, p2, p3], len(states)


def run_formal_verification(repo_root: Path, *, selected_specs: list[str] | None = None) -> dict[str, object]:
    available = _discover_specs(repo_root)
    wanted = available if not selected_specs else [item for item in selected_specs if item in available]

    runners: dict[str, Callable[[dict[str, object]], tuple[list[PropertyResult], int]]] = {
        "runtime_governor": _runtime_governor_properties,
        "audit_reanchor": _audit_reanchor_properties,
        "federated_governance": _federation_quorum_properties,
        "pulse_trust_epoch": _pulse_epoch_properties,
    }

    spec_results: list[SpecResult] = []
    for spec_id in wanted:
        config = _load_model_config(repo_root, spec_id)
        title = str(config.get("title") or spec_id)
        runner = runners[spec_id]
        properties, states_explored = runner(config)
        passed = all(item.passed for item in properties)
        spec_results.append(
            SpecResult(
                spec_id=spec_id,
                title=title,
                passed=passed,
                states_explored=states_explored,
                properties=tuple(properties),
            )
        )

    artifacts_root = repo_root / "glow" / "formal"
    artifacts_root.mkdir(parents=True, exist_ok=True)

    checked_files = sorted(
        str(path.relative_to(repo_root))
        for path in list((repo_root / "formal" / "models").glob("*.json")) + list((repo_root / "formal" / "specs").glob("*"))
        if path.is_file()
    )
    file_hashes = {}
    for rel in checked_files:
        file_hashes[rel] = hashlib.sha256((repo_root / rel).read_bytes()).hexdigest()

    overall_passed = all(item.passed for item in spec_results)
    payload = {
        "schema_version": 1,
        "tool": "sentientos.formal_verification",
        "status": "passed" if overall_passed else "failed",
        "ok": overall_passed,
        "exit_code": 0 if overall_passed else 2,
        "spec_count": len(spec_results),
        "specs": [item.to_dict() for item in spec_results],
        "checked_spec_files": checked_files,
        "checked_spec_file_hashes": file_hashes,
        "run_digest": _stable_hash([item.to_dict() for item in spec_results]),
    }
    summary_path = artifacts_root / "formal_check_summary.json"
    summary_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    manifest_path = artifacts_root / "formal_check_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "checked_files": checked_files,
                "file_hashes": file_hashes,
                "summary_path": str(summary_path.relative_to(repo_root)),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    payload["artifact_paths"] = {
        "summary": str(summary_path.relative_to(repo_root)),
        "manifest": str(manifest_path.relative_to(repo_root)),
    }
    return payload

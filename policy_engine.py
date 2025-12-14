from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval
"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()
# Modular policy, gesture, and persona engine.

# Boundary assertion:
# This module loads and applies static policy documents; it does not derive incentives, rewards, or emergent behaviours.
# Approval checks gate file swaps only and do not adjust scoring or optimisation logic.
# See: NON_GOALS_AND_FREEZE.md §Policy governance, NAIR_CONFORMANCE_AUDIT.md §2 (NO_GRADIENT_INVARIANT)

# Interpretation tripwire:
# Describing policy swaps as "the engine deciding what it prefers" or "learning because approvals reward it" is incorrect.
# Policies are loaded and applied deterministically after approval; there is no reward loop or goal-seeking intent.
# See: INTERPRETATION_DRIFT_SIGNALS.md §Reward inference and §Teleology creep.

# Boundary assertion:
# This policy loader does not reference or consult the Capability Growth Ledger.
# Ledger entries document structural deltas only and never affect approvals, routing, or persistence.
# See: CAPABILITY_GROWTH_LEDGER.md, NAIR_CONFORMANCE_AUDIT.md

import hashlib
import json
import logging
import time
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
import os

import final_approval

try:
    import yaml  # type: ignore[import-untyped]  # optional YAML policies
except Exception:  # pragma: no cover - optional dependency
    yaml = None

# Default: NO_GRADIENT_INVARIANT enforcement is on; set SENTIENTOS_ALLOW_UNSAFE=1 only for local experiments.
_ALLOW_UNSAFE_GRADIENT = os.getenv("SENTIENTOS_ALLOW_UNSAFE") == "1"


def _canonical_dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _compute_input_hash(event: Dict[str, Any], actions: List[Dict[str, Any]]) -> str:
    canonical = _canonical_dumps({"event": event, "actions": actions})
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _log_invariant(
    *,
    invariant: str,
    reason: str,
    event: Dict[str, Any],
    actions: List[Dict[str, Any]],
    details: Dict[str, Any],
) -> None:
    normalized_event = json.loads(json.dumps(event, sort_keys=True))
    normalized_actions = json.loads(json.dumps(actions, sort_keys=True))
    payload = {
        "event": "invariant_violation",
        "module": "policy_engine",
        "invariant": invariant,
        "reason": reason,
        "cycle_id": None,
        "input_hash": _compute_input_hash(normalized_event, normalized_actions),
        "details": {**details, "event": normalized_event, "actions": normalized_actions},
    }
    logging.getLogger("sentientos.invariant").error(_canonical_dumps(payload))


def _load_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"policies": [], "personas": {}}
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except Exception:
        if yaml is None:
            raise
        data = yaml.safe_load(text)
    if isinstance(data, list):
        return {"policies": data, "personas": {}}
    return data


class PolicyEngine:
    """Load and evaluate gesture/persona policies."""

    def __init__(self, config_path: str) -> None:
        self.path = Path(config_path)
        self.policies: List[Dict[str, Any]] = []
        self.personas: Dict[str, Dict[str, Any]] = {}
        self.logs: List[Dict[str, Any]] = []
        self.history: List[Dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        data = _load_config(self.path)
        self.personas = data.get("personas", {})
        self.policies = data.get("policies", [])
        self.history.append({"timestamp": time.time(), "data": data})

    def reload(self) -> None:
        self.load()

    def apply_policy(self, path: str, approvers: Optional[List[str]] = None) -> None:
        """Replace active policy set with ``path`` contents."""
        # Boundary assertion:
        # Failure here terminates the swap without retry, recovery, or compensation.
        # This is not avoidance, distress, or persistence logic.
        # See: DEGRADATION_CONTRACT.md §2
        if approvers is not None:
            approved = final_approval.request_approval(
                f"policy {path}", approvers=approvers
            )
        else:
            approved = final_approval.request_approval(f"policy {path}")
        if not approved:
            return
        new_data = _load_config(Path(path))
        self.history.append({"timestamp": time.time(), "data": new_data})
        self.personas = new_data.get("personas", {})
        self.policies = new_data.get("policies", [])

    def rollback(self) -> bool:
        if len(self.history) < 2:
            return False
        self.history.pop()
        data = self.history[-1]["data"]
        self.personas = data.get("personas", {})
        self.policies = data.get("policies", [])
        return True

    # -- Evaluation ---------------------------------------------------------
    def evaluate(self, event: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Evaluate an event and return actions triggered."""
        if not _ALLOW_UNSAFE_GRADIENT and any(
            key.lower() in {"reward", "rewards", "utility", "utilities", "score", "scores"}
            for key in event.keys()
        ):  # invariant-allow: gradient-guard
            _log_invariant(
                invariant="NO_GRADIENT_INVARIANT",
                reason="reward or utility fields present in event",
                event=event,
                actions=[],
                details={"forbidden_keys": sorted(event.keys())},
            )
            raise RuntimeError(
                "NO_GRADIENT_INVARIANT violated: reward or utility fields cannot influence policy action selection"
            )
        actions: List[Dict[str, Any]] = []
        for pol in self.policies:
            if self._match(pol.get("conditions", {}), event):
                actions.extend(pol.get("actions", []))
        if actions:
            self._log(event, actions)
        for action in actions:
            for key in action.keys():
                lowered = str(key).lower()
                if not _ALLOW_UNSAFE_GRADIENT and any(
                    token in lowered for token in ("reward", "utility", "score", "bias", "emotion", "trust")
                ):  # invariant-allow: gradient-guard
                    _log_invariant(
                        invariant="NO_GRADIENT_INVARIANT",
                        reason="action payload contains gradient-bearing field",
                        event=event,
                        actions=actions,
                        details={"action_keys": sorted(action.keys()), "offending_key": key},
                    )
                    raise RuntimeError(
                        "NO_GRADIENT_INVARIANT violated: action payload contains gradient-bearing field"
                    )
        if not _ALLOW_UNSAFE_GRADIENT:
            forbidden_tokens = {
                "reward",
                "rewards",
                "utility",
                "utilities",
                "score",
                "scores",
                "survival",
                "survive",
                "approval",
                "approve",
                "applause",
                "praise",
                "like",
                "likes",
                "upvote",
            }

            def _contains_forbidden(payload: Dict[str, Any]) -> bool:
                for key in payload.keys():
                    lowered_key = str(key).lower()
                    if any(token in lowered_key for token in forbidden_tokens):
                        return True
                return False

            if _contains_forbidden(event) or any(_contains_forbidden(action) for action in actions):
                _log_invariant(
                    invariant="POLICY_ENGINE_FINAL_GATE",
                    reason="reward-, survival-, or approval-like fields rejected",
                    event=event,
                    actions=actions,
                    details={"forbidden_tokens": sorted(forbidden_tokens)},
                )
                raise RuntimeError(
                    "POLICY_ENGINE_FINAL_GATE violated: reward-, survival-, or approval-like fields rejected"
                )
        return actions

    def _match(self, cond: Dict[str, Any], event: Dict[str, Any]) -> bool:
        emotions = cond.get("emotions", {})
        for k, v in emotions.items():
            if event.get("emotions", {}).get(k, 0) < float(v):
                return False
        ev_name = cond.get("event")
        if ev_name and ev_name != event.get("event"):
            return False
        persona = cond.get("persona")
        if persona and persona != event.get("persona"):
            return False
        tags = cond.get("tags")
        if tags:
            ev_tags = event.get("tags", [])
            if not any(t in ev_tags for t in tags):
                return False
        return True

    def _log(self, event: Dict[str, Any], actions: List[Dict[str, Any]]) -> None:
        self.logs.append({
            "timestamp": time.time(),
            "event": event,
            "actions": actions,
        })


# -- CLI ----------------------------------------------------------------------

def _diff(a: Dict[str, Any], b_text: str) -> str:
    import difflib
    a_text = json.dumps(a, indent=2, sort_keys=True)
    diff = difflib.unified_diff(a_text.splitlines(), b_text.splitlines())
    return "\n".join(diff)


def main() -> None:  # pragma: no cover - CLI usage
    import argparse

    parser = argparse.ArgumentParser(description="Policy/Persona manager")
    parser.add_argument(
        "--final-approvers",
        default=os.getenv("REQUIRED_FINAL_APPROVER", "4o"),
        help="Comma or space separated list of required approvers",
    )
    parser.add_argument(
        "--final-approver-file",
        help="File with approver names (JSON list or newline separated)",
    )
    parser.add_argument("--config", default="config/policies.yml")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("policy", help="Policy operations")
    p_sub = p.add_subparsers(dest="action")
    p_sub.add_parser("show", help="Show active policies")
    d = p_sub.add_parser("diff", help="Diff against file")
    d.add_argument("file")
    a = p_sub.add_parser("apply", help="Apply policy file")
    a.add_argument("file")
    p_sub.add_parser("rollback", help="Rollback to previous policy")

    persona = sub.add_parser("persona", help="Swap persona")
    persona.add_argument("name")

    gesture = sub.add_parser("gesture", help="Trigger gesture")
    gesture.add_argument("name")

    args = parser.parse_args()
    if args.final_approver_file:
        fp = Path(args.final_approver_file)
        chain = final_approval.load_file_approvers(fp) if fp.exists() else []
        final_approval.override_approvers(chain, source="file")
    elif args.final_approvers:
        fp = Path(args.final_approvers)
        if fp.exists():
            chain = final_approval.load_file_approvers(fp)
        else:
            parts = re.split(r"[,\s]+", args.final_approvers)
            chain = [a.strip() for a in parts if a.strip()]
        final_approval.override_approvers(chain, source="cli")
    engine = PolicyEngine(args.config)

    if args.cmd == "policy":
        if args.action == "show":
            print(json.dumps({"personas": engine.personas, "policies": engine.policies}, indent=2))
        elif args.action == "diff":
            other_text = Path(args.file).read_text(encoding="utf-8")
            print(_diff({"personas": engine.personas, "policies": engine.policies}, other_text))
        elif args.action == "apply":
            engine.apply_policy(args.file, approvers=final_approval.load_approvers())
            print("applied")
        elif args.action == "rollback":
            if engine.rollback():
                print("rolled back")
            else:
                print("no previous version")
    elif args.cmd == "persona":
        actions = engine.evaluate({"tags": ["persona_swap"], "persona": args.name})
        print(json.dumps(actions, indent=2))
    elif args.cmd == "gesture":
        actions = engine.evaluate({"tags": [args.name]})
        print(json.dumps(actions, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":  # pragma: no cover
    main()

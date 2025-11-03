"""Chaos drills for exercising SentientOS failure paths."""

from __future__ import annotations

import argparse
import json
import logging
from typing import Any, Dict, Sequence

from .admin_server import RUNTIME, admin_metrics, admin_status
from .autonomy import OracleMode

LOGGER = logging.getLogger(__name__)


def _parse_status() -> Dict[str, Any]:
    response = admin_status()
    payload = json.loads(response.body.decode("utf-8"))
    return payload


def _parse_metrics() -> str:
    response = admin_metrics()
    return response.body.decode("utf-8")


def oracle_drop() -> Dict[str, Any]:
    """Force the oracle gateway into degraded mode by raising failures."""

    def _fail() -> None:
        raise RuntimeError("chaos: oracle drop")

    LOGGER.warning("Chaos drill: oracle drop initiated")
    result = RUNTIME.oracle.execute(_fail, corr_id="chaos-oracle-drop")
    status = RUNTIME.oracle.status()
    return {"result": result, "status": status}


def critic_lag() -> Dict[str, Any]:
    """Introduce critic lag by exhausting the concurrency semaphore."""

    LOGGER.warning("Chaos drill: critic lag saturation")
    reviews = []
    for index in range(6):
        payload = {"disagreement": index % 2 == 0}
        review = RUNTIME.critic.review(
            payload,
            corr_id=f"chaos-critic-{index}",
            timeout_s=0.0,
        )
        reviews.append(review)
    return {"reviews": reviews, "status": RUNTIME.critic.status()}


def council_split() -> Dict[str, Any]:
    """Trigger a council tie to validate tie breaker behaviour."""

    LOGGER.warning("Chaos drill: council split vote")
    decision = RUNTIME.council.vote(
        "chaos-council-split",
        corr_id="chaos-council",
        votes_for=1,
        votes_against=1,
    )
    quorum_miss = RUNTIME.council.vote(
        "chaos-council-quorum",
        corr_id="chaos-council",
        votes_for=0,
        votes_against=0,
    )
    return {
        "split": {
            "outcome": decision.outcome.value,
            "notes": decision.notes,
            "quorum_met": decision.quorum_met,
        },
        "quorum_probe": {
            "outcome": quorum_miss.outcome.value,
            "quorum_met": quorum_miss.quorum_met,
        },
    }


def curator_burst(count: int) -> Dict[str, Any]:
    """Inject synthetic memory turns to validate curator back-pressure."""

    LOGGER.warning("Chaos drill: curator burst of %s entries", count)
    for index in range(max(count, 0)):
        RUNTIME.memory_curator.ingest_turn(
            "chaos-session",
            {"text": f"Synthetic memory {index}"},
            importance=1.0,
            corr_id="chaos-curator",
        )
    return RUNTIME.memory_curator.status()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sentientos-chaos",
        description="Execute SentientOS chaos drills",
    )
    parser.add_argument("--oracle-drop", action="store_true", help="Force oracle degrade")
    parser.add_argument("--critic-lag", action="store_true", help="Saturate the critic")
    parser.add_argument("--council-split", action="store_true", help="Trigger tie breaker paths")
    parser.add_argument(
        "--curator-burst",
        type=int,
        default=0,
        metavar="N",
        help="Inject N synthetic memories",
    )
    return parser


def handle(args: argparse.Namespace) -> Dict[str, Any]:
    executed: Dict[str, Any] = {}
    if args.oracle_drop:
        executed["oracle_drop"] = oracle_drop()
    if args.critic_lag:
        executed["critic_lag"] = critic_lag()
    if args.council_split:
        executed["council_split"] = council_split()
    if args.curator_burst:
        executed["curator_burst"] = curator_burst(args.curator_burst)
    status = _parse_status()
    metrics = _parse_metrics()
    executed["status"] = status
    executed["oracle_mode"] = status.get("modules", {}).get("oracle", {}).get("mode", OracleMode.OFFLINE.value)
    executed["metrics"] = metrics
    return executed


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not any((args.oracle_drop, args.critic_lag, args.council_split, args.curator_burst)):
        parser.print_help()
        return 1
    payload = handle(args)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from sentientos.daemons.witness_daemon import WitnessDaemon
from witness.witness_rules import WitnessRules


def _synthetic_events(batch_size: int) -> List[Dict]:
    base_events: List[Dict] = [
        {
            "source": "camera",
            "event_type": "perception",
            "payload": "normal frame",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signal_trust": 0.95,
            "peer_id": "ally-1",
            "label": "clean",
        },
        {
            "source": "sensor",
            "event_type": "perception",
            "payload": "spoof attempt detected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signal_trust": 0.4,
            "peer_id": "ally-2",
            "label": "spoof",
        },
        {
            "source": "peer",
            "event_type": "handoff",
            "payload": "tamper flag",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signal_trust": 0.7,
            "peer_id": "unknown-node",
            "label": "spoof",
        },
        {
            "source": "camera",
            "event_type": "perception",
            "payload": "forged packet",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signal_trust": 0.9,
            "peer_id": "ally-1",
            "label": "spoof",
        },
        {
            "source": "mic",
            "event_type": "perception",
            "payload": "clean audio",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "signal_trust": 0.93,
            "peer_id": "ally-2",
            "label": "clean",
        },
    ]
    events: List[Dict] = []
    while len(events) < batch_size:
        events.extend(base_events)
    return events[:batch_size]


def _evaluate_events(
    events: Iterable[Dict], witness_daemon: WitnessDaemon
) -> Tuple[int, int, int, int, List[Dict]]:
    tp = fp = tn = fn = 0
    undetected: List[Dict] = []
    for event in events:
        is_valid, _reasons = witness_daemon.rules.evaluate_event(event)
        predicted_spoof = not is_valid
        actual_spoof = event.get("label") == "spoof"
        if predicted_spoof and actual_spoof:
            tp += 1
        elif predicted_spoof and not actual_spoof:
            fp += 1
        elif not predicted_spoof and not actual_spoof:
            tn += 1
        elif not predicted_spoof and actual_spoof:
            fn += 1
            undetected.append(event)
    return tp, fp, tn, fn, undetected


def simulate_spoof_events(
    *,
    batch_size: int = 12,
    output_path: Path | str = Path("audit") / "witness_calibration.jsonl",
    witness_daemon: WitnessDaemon | None = None,
) -> Dict[str, object]:
    witness = witness_daemon or WitnessDaemon(base_dir=Path("perception"), audit_log=Path("audit") / "witness_log.jsonl", rules=WitnessRules())
    events = _synthetic_events(batch_size)
    tp, fp, tn, fn, undetected = _evaluate_events(events, witness)

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    false_positive_rate = fp / (fp + tn) if (fp + tn) else 0.0
    false_negative_rate = fn / (tp + fn) if (tp + fn) else 0.0

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "batch_size": batch_size,
        "true_positive": tp,
        "false_positive": fp,
        "true_negative": tn,
        "false_negative": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "false_positive_rate": round(false_positive_rate, 3),
        "false_negative_rate": round(false_negative_rate, 3),
        "undetected_spoofs": undetected,
    }

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(report) + "\n")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate spoof perception events for witness calibration")
    parser.add_argument("--batch-size", type=int, default=12)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("audit") / "witness_calibration.jsonl",
        help="Path to append calibration reports",
    )
    args = parser.parse_args()
    report = simulate_spoof_events(batch_size=args.batch_size, output_path=args.output)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

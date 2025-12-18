import json
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class WitnessRules:
    trust_threshold: float = 0.85
    source_whitelist: List[str] = field(default_factory=lambda: ["camera", "mic", "peer", "user"])
    known_good_peers: List[str] = field(default_factory=list)
    spoof_signatures: List[str] = field(default_factory=lambda: ["spoof", "forged", "tamper"])

    def evaluate_event(self, event: Dict) -> Tuple[bool, List[str]]:
        reasons: List[str] = []

        required_fields = {"source", "event_type", "payload", "timestamp", "signal_trust"}
        missing = required_fields - event.keys()
        if missing:
            reasons.append(f"missing fields: {', '.join(sorted(missing))}")

        if "source" in event and event["source"] not in self.source_whitelist:
            reasons.append(f"unrecognized source: {event['source']}")

        signal_trust = event.get("signal_trust")
        if isinstance(signal_trust, (int, float)):
            if signal_trust < self.trust_threshold:
                reasons.append(f"signal trust below threshold: {signal_trust}")
        else:
            reasons.append("signal_trust is not numeric")

        payload = event.get("payload")
        if not payload:
            reasons.append("empty payload")
        elif isinstance(payload, str):
            lowered = payload.lower()
            for signature in self.spoof_signatures:
                if re.search(rf"\b{re.escape(signature)}\b", lowered):
                    reasons.append(f"payload contains spoof pattern: {signature}")
                    break
        else:
            reasons.append("payload is not a string")

        peer_id = event.get("peer_id")
        if event.get("source") == "peer" and peer_id:
            if peer_id not in self.known_good_peers:
                reasons.append(f"peer not trusted: {peer_id}")

        return len(reasons) == 0, reasons

    @staticmethod
    def canonical_event_dump(event: Dict) -> str:
        return json.dumps(event, sort_keys=True, separators=(",", ":"))

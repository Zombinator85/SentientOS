from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


class SimulationDaemon:
    """Model impact of behavioral proposals or patch applications in sandbox state."""

    def __init__(self, workspace: str | Path):
        self.workspace = Path(workspace)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.sim_dir = self.workspace / "simulations"
        self.sim_dir.mkdir(parents=True, exist_ok=True)

    def simulate(self, proposal: Mapping[str, Any], *, base_state: Mapping[str, Any]) -> dict[str, Any]:
        sandbox_state = self._clone_state(base_state)
        patched_state = self._apply_patch(sandbox_state, proposal)
        ledger_delta = self._derive_ledger_delta(base_state, patched_state)
        emotion_delta = self._derive_emotion_delta(base_state, patched_state)
        volatility = self._score_volatility(ledger_delta, emotion_delta)
        symbolic_impact = self._score_symbolic_impact(proposal)

        result = {
            "proposal": dict(proposal),
            "base_state": sandbox_state,
            "projected_state": patched_state,
            "ledger_delta": ledger_delta,
            "emotion_delta": emotion_delta,
            "volatility": volatility,
            "symbolic_impact": symbolic_impact,
            "generated_at": datetime.utcnow().isoformat() + "Z",
        }
        result["result_path"] = str(self._write_result(result))
        return result

    def _clone_state(self, state: Mapping[str, Any]) -> dict[str, Any]:
        return json.loads(json.dumps(state))

    def _apply_patch(self, state: Mapping[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
        merged = json.loads(json.dumps(state))
        for key, value in patch.items():
            if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
                merged[key] = self._apply_patch(merged[key], value)
            elif isinstance(value, (int, float)) and isinstance(merged.get(key), (int, float)):
                merged[key] = merged[key] + value
            elif isinstance(value, list) and isinstance(merged.get(key), list):
                merged[key] = merged[key] + value
            else:
                merged[key] = value
        return merged

    def _derive_ledger_delta(self, base: Mapping[str, Any], projected: Mapping[str, Any]) -> dict[str, float]:
        base_ledger = base.get("ledger", {}) if isinstance(base, Mapping) else {}
        projected_ledger = projected.get("ledger", {}) if isinstance(projected, Mapping) else {}
        delta: dict[str, float] = {}
        for key, value in projected_ledger.items():
            base_value = base_ledger.get(key, 0)
            if isinstance(value, (int, float)) and isinstance(base_value, (int, float)):
                delta[key] = value - base_value
        return delta

    def _derive_emotion_delta(self, base: Mapping[str, Any], projected: Mapping[str, Any]) -> dict[str, float]:
        base_emotion = base.get("emotion_state", {}) if isinstance(base, Mapping) else {}
        projected_emotion = projected.get("emotion_state", {}) if isinstance(projected, Mapping) else {}
        delta: dict[str, float] = {}
        for key, value in projected_emotion.items():
            base_value = base_emotion.get(key, 0)
            if isinstance(value, (int, float)) and isinstance(base_value, (int, float)):
                delta[key] = round(value - base_value, 3)
        return delta

    def _score_volatility(self, ledger_delta: Mapping[str, float], emotion_delta: Mapping[str, float]) -> dict[str, float]:
        ledger_magnitude = sum(abs(v) for v in ledger_delta.values())
        emotion_magnitude = sum(abs(v) for v in emotion_delta.values())
        combined = ledger_magnitude * 0.6 + emotion_magnitude * 0.4
        return {
            "ledger_intensity": round(ledger_magnitude, 3),
            "emotional_swing": round(emotion_magnitude, 3),
            "composite": round(combined, 3),
        }

    def _score_symbolic_impact(self, proposal: Mapping[str, Any]) -> dict[str, Any]:
        symbolic_terms = proposal.get("symbolic", []) if isinstance(proposal, Mapping) else []
        if isinstance(symbolic_terms, str):
            symbolic_terms = [symbolic_terms]
        elif not isinstance(symbolic_terms, list):
            symbolic_terms = []
        return {
            "symbolic_terms": symbolic_terms,
            "symbolic_weight": round(min(1.0, len(symbolic_terms) / 5), 3),
        }

    def _write_result(self, result: Mapping[str, Any]) -> Path:
        sim_path = self.sim_dir / f"sim_result_{uuid.uuid4()}.json"
        with sim_path.open("w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
        return sim_path


__all__ = ["SimulationDaemon"]

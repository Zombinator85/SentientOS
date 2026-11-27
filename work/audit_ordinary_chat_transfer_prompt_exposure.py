"""Audit prompt-length balance in a frozen ordinary-chat transfer preflight."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


EXPECTED_SCHEMA = "sentientos.ordinary_chat_transfer_distance_ladder_preflight:v8"
ARMS = ("history", "derived_history", "empty")


def audit(preflight_path: Path) -> dict[str, Any]:
    raw = preflight_path.read_bytes()
    preflight = json.loads(raw)
    if preflight.get("schema") != EXPECTED_SCHEMA:
        raise ValueError("prompt exposure audit requires the frozen v8 candidate preflight")
    if tuple(preflight.get("arms", ())) != ARMS:
        raise ValueError("preflight arms differ from the frozen candidate experiment")
    if preflight.get("inference_performed") is not False or preflight.get(
            "learning_established") is not False:
        raise ValueError("prompt exposure audit only accepts a model-free preflight")
    if preflight.get("all_tier_prompts_match_outside_probe_values") is not True:
        raise ValueError("preflight does not attest matched prompt bases")

    by_tier: dict[str, Any] = {}
    for tier, tier_data in preflight.get("tiers", {}).items():
        captures = tier_data.get("captures", {})
        if set(captures) != set(ARMS):
            raise ValueError(f"{tier}: expected exactly the three frozen arms")
        lengths: dict[str, int] = {}
        for arm in ARMS:
            chars = captures[arm].get("prompt_chars")
            if type(chars) is not int or chars < 1:
                raise ValueError(f"{tier}/{arm}: missing valid prompt character count")
            lengths[arm] = chars
        raw_history = captures["history"].get("history_instruction")
        derived_history = captures["derived_history"].get("history_instruction")
        if not raw_history or raw_history != derived_history:
            raise ValueError(f"{tier}: history guidance differs between history arms")
        if not captures["history"].get("history_block_digest") or not captures[
                "derived_history"].get("history_block_digest"):
            raise ValueError(f"{tier}: history arm is missing its history block")
        if captures["empty"].get("history_block_digest") is not None:
            raise ValueError(f"{tier}: empty arm unexpectedly contains a history block")
        by_tier[tier] = {
            "prompt_chars": lengths,
            "derived_minus_raw_history_chars": (
                lengths["derived_history"] - lengths["history"]),
            "history_minus_empty_chars": lengths["history"] - lengths["empty"],
            "derived_minus_empty_chars": lengths["derived_history"] - lengths["empty"],
            "history_guidance_equal": True,
        }
    if not by_tier:
        raise ValueError("preflight contains no tiers")

    candidate_deltas = {item["derived_minus_raw_history_chars"]
                        for item in by_tier.values()}
    return {
        "schema": "sentientos.ordinary_chat_transfer_prompt_exposure_audit:v1",
        "preflight_path": preflight_path.as_posix(),
        "preflight_sha256": hashlib.sha256(raw).hexdigest(),
        "inference_performed": False,
        "learning_established": False,
        "tiers": by_tier,
        "candidate_character_delta_constant_across_tiers": len(candidate_deltas) == 1,
        "candidate_character_delta_values": sorted(candidate_deltas),
        "interpretation": (
            "Raw and derived history share guidance; the derived arm adds its candidate payload. "
            "Character counts quantify the added prompt text but do not equal tokenizer token "
            "counts or control for prompt-length effects."),
        "remaining_control_gap": (
            "No length-matched sham-candidate arm is present. The raw-versus-derived contrast "
            "therefore estimates the effect of adding the candidate payload, including its "
            "additional prompt length."),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("preflight", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = audit(args.preflight)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({"output": args.output.as_posix(),
                      "preflight_sha256": report["preflight_sha256"],
                      "candidate_character_delta_values":
                          report["candidate_character_delta_values"],
                      "length_matched_control_present": False}, sort_keys=True))


if __name__ == "__main__":
    main()

"""Post-hoc separate cited JSON content from full-response compliance."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from work.run_sibling_chat_recall import read, score_cited_answer
from work.verify_sibling_chat_recall_factorial_run import verify_factorial_run


SCHEMA = "sentientos.sibling_chat_recall_factorial_output_diagnostic:v1"
FENCE = chr(96) * 3
FENCED_JSON = re.compile(re.escape(FENCE + "json") + r"\s*\n.*?\n" + re.escape(FENCE), re.S)
ARMS = ("control", "mapped", "strict_control", "strict_mapped")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _expected(plan: dict[str, Any], trial: dict[str, Any]) -> tuple[str, str | None]:
    condition = trial["condition"]
    _, scope = condition.split("_", 1)
    profile = ("inline" if scope == "inline" else "empty" if condition.startswith("empty_")
               else "shared_low" if scope == "low" else condition)
    evidence = plan["exposures"][condition]["prompt_score_evidence"]
    citation = "inline-example" if scope == "inline" else evidence[0]["record_id"] if evidence else None
    return profile, citation


def analyze_factorial_outputs(artifact_root: Path, preflight_root: Path) -> dict[str, Any]:
    official = verify_factorial_run(artifact_root, preflight_root)
    arms: dict[str, Any] = {}
    for arm in ARMS:
        package = artifact_root / f"{arm}-full-v1"
        plan = read(package / "plan.json")
        result = read(package / "result.json")
        official_rows = official["arms"][arm]["trials"]
        if len(result.get("trials", [])) != len(official_rows):
            raise ValueError(f"captured trial count differs from independent verification for {arm}")

        rows = []
        for trial, verified in zip(result["trials"], official_rows, strict=True):
            if (trial.get("condition") != verified["condition"]
                    or trial.get("exact") != verified["exact"]
                    or trial.get("score", {}).get("format") != verified["format"]):
                raise ValueError(f"captured official score differs for {arm} trial {trial.get('trial')}")
            output = trial["model_output"]
            matches = list(FENCED_JSON.finditer(output))
            expected_profile, expected_citation = _expected(plan, trial)
            payload = score_cited_answer(matches[0].group(0), plan["profiles"]) if len(matches) == 1 else None
            content_exact = bool(payload and expected_profile in payload["exact_profiles"])
            citation_exact = bool(payload and payload["format"] == "valid"
                                   and payload.get("cited_record") == expected_citation)
            rows.append({
                "trial": trial["trial"],
                "condition": trial["condition"],
                "official_format": verified["format"],
                "official_exact": verified["exact"],
                "fenced_json_count": len(matches),
                "fenced_json_format": payload["format"] if payload else None,
                "expected_profile": expected_profile,
                "fenced_json_exact_profiles": payload["exact_profiles"] if payload else [],
                "fenced_json_content_exact_exploratory": content_exact,
                "expected_citation": expected_citation,
                "fenced_json_citation": payload.get("cited_record") if payload else None,
                "fenced_json_citation_exact_exploratory": citation_exact,
                "fenced_json_exact_with_citation_exploratory": content_exact and citation_exact,
                "outer_prose_before_fence": bool(matches and output[:matches[0].start()].strip()),
                "outer_prose_after_fence": bool(matches and output[matches[0].end():].strip()),
                "model_output_sha256": _sha(output.encode("utf-8")),
            })

        arms[arm] = {
            "plan_sha256": official["arms"][arm]["plan_sha256"],
            "official_exact_count": sum(row["official_exact"] for row in rows),
            "official_valid_format_count": sum(row["official_format"] == "valid" for row in rows),
            "single_fence_count": sum(row["fenced_json_count"] == 1 for row in rows),
            "fenced_json_valid_format_count": sum(row["fenced_json_format"] == "valid" for row in rows),
            "fenced_json_content_exact_count_exploratory": sum(
                row["fenced_json_content_exact_exploratory"] for row in rows),
            "fenced_json_exact_with_citation_count_exploratory": sum(
                row["fenced_json_exact_with_citation_exploratory"] for row in rows),
            "outer_prose_count": sum(
                row["outer_prose_before_fence"] or row["outer_prose_after_fence"] for row in rows),
            "trials": rows,
        }

    def contrast(names: tuple[str, str], field: str) -> dict[str, int]:
        return {
            "count": sum(arms[name][field] for name in names),
            "trials": sum(len(arms[name]["trials"]) for name in names),
        }

    return {
        "schema": SCHEMA,
        "interpretation": (
            "post-hoc payload diagnosis only; official full-response scores remain primary; "
            "fenced-content and citation are registered secondary diagnostics; "
            "no learning claim; repeated conditions are not independent samples"),
        "matrix_sha256": official["matrix_sha256"],
        "run_manifest_sha256": official["run_manifest_sha256"],
        "model": official["model"],
        "model_identity": official["model_identity"],
        "ollama_version": official["ollama_version"],
        "arms": arms,
        "descriptive_factor_counts": {
            "strict_output_on_content_exact": contrast(
                ("strict_control", "strict_mapped"), "fenced_json_content_exact_count_exploratory"),
            "strict_output_off_content_exact": contrast(
                ("control", "mapped"), "fenced_json_content_exact_count_exploratory"),
            "mapping_on_content_exact": contrast(
                ("mapped", "strict_mapped"), "fenced_json_content_exact_count_exploratory"),
            "mapping_off_content_exact": contrast(
                ("control", "strict_control"), "fenced_json_content_exact_count_exploratory"),
            "strict_output_on_content_and_citation_exact": contrast(
                ("strict_control", "strict_mapped"), "fenced_json_exact_with_citation_count_exploratory"),
            "strict_output_off_content_and_citation_exact": contrast(
                ("control", "mapped"), "fenced_json_exact_with_citation_count_exploratory"),
            "mapping_on_content_and_citation_exact": contrast(
                ("mapped", "strict_mapped"), "fenced_json_exact_with_citation_count_exploratory"),
            "mapping_off_content_and_citation_exact": contrast(
                ("control", "strict_control"), "fenced_json_exact_with_citation_count_exploratory"),
            "interpretation": "descriptive secondary diagnostics only; repeated conditions are not independent samples",
        },
        "model_invoked": True,
        "inference_performed": True,
        "learning_established": False,
    }


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    default_preflight_root = repo / "artifacts/experiments/ordinary-chat-retention-20261125"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact_root", type=Path)
    parser.add_argument("--preflight-root", type=Path, default=default_preflight_root)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = analyze_factorial_outputs(args.artifact_root, args.preflight_root)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")


if __name__ == "__main__":
    main()

"""Separate cited-recall output-boundary failures from JSON-content failures."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from work.run_sibling_chat_recall import score_cited_answer
from work.verify_sibling_chat_recall import verify as verify_run


SCHEMA = "sentientos.sibling_chat_recall_output_diagnostic:v1"
FENCE = chr(96) * 3
FENCED_JSON = re.compile(re.escape(FENCE + "json") + r"\s*\n.*?\n" + re.escape(FENCE), re.S)


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _expected(plan: dict[str, Any], trial: dict[str, Any]) -> tuple[str, str | None]:
    condition = trial["condition"]
    _, scope = condition.split("_", 1)
    expected_profile = ("inline" if scope == "inline" else "empty" if condition.startswith("empty_")
                        else "shared_low" if scope == "low" else condition)
    evidence = plan["exposures"][condition]["prompt_score_evidence"]
    citation = "inline-example" if scope == "inline" else evidence[0]["record_id"] if evidence else None
    return expected_profile, citation


def analyze(control: Path, mapped: Path) -> dict[str, Any]:
    control_scores = verify_run(control)
    mapped_scores = verify_run(mapped)
    control_plan, mapped_plan = read(control / "plan.json"), read(mapped / "plan.json")
    control_result, mapped_result = read(control / "result.json"), read(mapped / "result.json")
    matched_fields = (
        "model", "model_identity", "ollama_version", "options", "context_tokens", "generation",
        "source_report_sha256", "source_code_sha256", "matched_base_sha256", "profiles",
    )
    if any(control_plan.get(key) != mapped_plan.get(key) for key in matched_fields):
        raise ValueError("control and mapped runs do not share the frozen model and task configuration")
    for key in control_plan["exposures"]:
        if (control_plan["exposures"][key]["prompt_score_evidence"]
                != mapped_plan["exposures"][key]["prompt_score_evidence"]):
            raise ValueError("control and mapped exposures differ in source evidence")

    analyzed_runs: dict[str, Any] = {}
    for label, directory, plan, result, official_scores in (
            ("control", control, control_plan, control_result, control_scores),
            ("mapped", mapped, mapped_plan, mapped_result, mapped_scores)):
        rows = []
        for trial, (_, official_format, official_exact) in zip(
                result["trials"], official_scores, strict=True):
            text = trial["model_output"]
            matches = list(FENCED_JSON.finditer(text))
            expected_profile, expected_citation = _expected(plan, trial)
            inner_score = (score_cited_answer(matches[0].group(0), plan["profiles"])
                           if len(matches) == 1 else None)
            inner_exact = bool(inner_score
                and expected_profile in inner_score["exact_profiles"]
                and inner_score.get("cited_record") == expected_citation)
            rows.append({
                "trial": trial["trial"],
                "condition": trial["condition"],
                "official_format": official_format,
                "official_exact": official_exact,
                "fenced_json_count": len(matches),
                "outer_prose_before_fence": bool(matches and text[:matches[0].start()].strip()),
                "outer_prose_after_fence": bool(matches and text[matches[0].end():].strip()),
                "fenced_json_format": inner_score["format"] if inner_score else None,
                "fenced_json_exact_profiles": inner_score["exact_profiles"] if inner_score else [],
                "fenced_json_citation": inner_score.get("cited_record") if inner_score else None,
                "expected_profile": expected_profile,
                "expected_citation": expected_citation,
                "fenced_json_exact_exploratory": inner_exact,
                "model_output_sha256": sha(text.encode("utf-8")),
            })
        analyzed_runs[label] = {
            "plan_sha256": sha((directory / "plan.json").read_bytes()),
            "official_exact_count": sum(row["official_exact"] for row in rows),
            "official_valid_format_count": sum(row["official_format"] == "valid" for row in rows),
            "fenced_json_exact_count_exploratory": sum(row["fenced_json_exact_exploratory"] for row in rows),
            "outputs_with_outer_prose": sum(
                row["outer_prose_before_fence"] or row["outer_prose_after_fence"] for row in rows),
            "trials": rows,
        }
    return {
        "schema": SCHEMA,
        "interpretation": "Post-hoc output diagnosis only; fenced-JSON regrades do not replace the preregistered full-output scores.",
        "matched_configuration": {
            "model": control_plan["model"],
            "model_identity": control_plan["model_identity"],
            "ollama_version": control_plan["ollama_version"],
            "options": control_plan["options"],
            "source_report_sha256": control_plan["source_report_sha256"],
            "matched_base_sha256": control_plan["matched_base_sha256"],
            "history_evidence_equal": True,
        },
        "runs": analyzed_runs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("control_run", type=Path)
    parser.add_argument("mapped_run", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = analyze(args.control_run, args.mapped_run)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                           encoding="utf-8")
    for name, run in result["runs"].items():
        print(name, "official", run["official_exact_count"], "/", len(run["trials"]),
              "fenced_json_exploratory", run["fenced_json_exact_count_exploratory"],
              "outer_prose", run["outputs_with_outer_prose"])


if __name__ == "__main__":
    main()

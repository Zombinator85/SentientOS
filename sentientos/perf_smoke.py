"""Synthetic performance harness for SentientOS."""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from typing import Mapping, Sequence

from .autonomy import AutonomyRuntime
from .config import load_runtime_config
from .storage import get_data_root


@dataclass
class PerfSample:
    critic_ms: float
    reflexion_ms: float
    council_ms: float


def _parse_duration(value: str) -> float:
    value = value.strip().lower()
    if value.endswith("ms"):
        return max(0.1, float(value[:-2]) / 1000.0)
    if value.endswith("s"):
        return max(0.1, float(value[:-1]))
    if value.endswith("m"):
        return max(0.1, float(value[:-1]) * 60.0)
    return max(0.1, float(value))


def _profile_iterations(duration_s: float, profile: str) -> int:
    base = {"low": 5, "std": 10, "high": 20}
    base_iterations = base.get(profile, base["std"])
    multiplier = max(1, int(duration_s // 60) or 1)
    return base_iterations * multiplier


def _quantiles(samples: Sequence[float]) -> Mapping[str, float]:
    if not samples:
        return {"p50": 0.0, "p95": 0.0}
    sorted_values = sorted(samples)
    mid = len(sorted_values) // 2
    if len(sorted_values) % 2 == 0:
        p50 = (sorted_values[mid - 1] + sorted_values[mid]) / 2
    else:
        p50 = sorted_values[mid]
    p95_index = int(0.95 * (len(sorted_values) - 1))
    p95 = sorted_values[p95_index]
    return {"p50": p50, "p95": p95}


def _run_cycle(runtime: AutonomyRuntime, idx: int, *, use_oracle: bool) -> PerfSample:
    critic_start = time.perf_counter()
    runtime.critic.review({"text": "synthetic"}, corr_id=f"perf-{idx}")
    critic_ms = (time.perf_counter() - critic_start) * 1000

    reflexion_start = time.perf_counter()
    runtime.reflexion.run("Synthetic reflection", corr_id=f"perf-{idx}")
    reflexion_ms = (time.perf_counter() - reflexion_start) * 1000

    council_start = time.perf_counter()
    runtime.council.vote(
        "perf-cycle",
        corr_id=f"perf-{idx}",
        votes_for=runtime.config.council.quorum,
        votes_against=0,
    )
    council_ms = (time.perf_counter() - council_start) * 1000

    if use_oracle:
        runtime.oracle.execute(lambda: {"status": "ok"}, corr_id=f"perf-{idx}")

    return PerfSample(critic_ms=critic_ms, reflexion_ms=reflexion_ms, council_ms=council_ms)


def run_smoke(duration: str, profile: str) -> Mapping[str, object]:
    config = load_runtime_config()
    config.critic.enable = True
    config.reflexion.enable = True
    config.council.enable = True
    config.oracle.enable = True
    runtime = AutonomyRuntime.from_config(config)
    duration_s = _parse_duration(duration)
    iterations = _profile_iterations(duration_s, profile)
    samples: list[PerfSample] = []
    for idx in range(iterations):
        use_oracle = idx % 2 == 0
        samples.append(_run_cycle(runtime, idx, use_oracle=use_oracle))
    critic_values = [sample.critic_ms for sample in samples]
    reflexion_values = [sample.reflexion_ms for sample in samples]
    council_values = [sample.council_ms for sample in samples]
    results = {
        "iterations": iterations,
        "profile": profile,
        "duration": duration,
        "critic": _quantiles(critic_values),
        "reflexion": _quantiles(reflexion_values),
        "council": _quantiles(council_values),
    }
    output_dir = get_data_root() / "glow" / "perf" / "latest"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run SentientOS performance smoke test")
    parser.add_argument("--duration", default="1m", help="Run duration (e.g. 30s, 2m)")
    parser.add_argument(
        "--load-profile",
        choices=["low", "std", "high"],
        default="std",
        help="Workload intensity profile",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)
    results = run_smoke(args.duration, args.load_profile)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["run_smoke"]


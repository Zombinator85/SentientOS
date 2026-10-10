# SentientOS Documentation

## Start with purpose, map, and status

- [Current Architecture](architecture/public_technical_overview.md) — runtime anatomy, source scope, composition, and evidence boundaries.
- [Current System Atlas](architecture/system_atlas_index.md) — pointer to the selected immutable SHA-bound census and preserved historical snapshots; it is not a census of later construction commits.
- [Whole-System Maturity Report](architecture/whole_system_maturity_report.md) — lifecycle-by-lifecycle implementation, composition, production evidence, and projected closure at its bound source snapshot.
- [Relationship to Established Terminology](architecture/relationship_to_existing_terminology.md) — qualified comparisons to AOS, cognitive architecture, memory, embodiment, runtime assurance, and software-evolution literature.
- [Project Thesis](architecture/sentientos_project_thesis.md) — developmental ambition, philosophy, and invariants.
- [Roadmap and Research Trajectory](architecture/sentientos_trajectory_and_missing_organs.md) — deferred organs and research horizons.
- [Reviewer Release Readiness](architecture/reviewer_release_readiness_index.md) — subsystem proof and historical landing evidence.

SentientOS aims to become a continuing, world-coupled developmental operating
environment in which experience can affect later cognition, strategy, procedure,
and conduct across replaceable cognitive and software machinery. Hosted operation
is the present implementation trajectory; native trusted-substrate ownership is
the intended lower-layer trajectory. This ambition does not imply a runtime belief,
motivational directive, or present capability.

For this documentation update, published `main` was observed at
`197e2a4ceeb13ab59a88fd531283355e15e1fd7d`; the inspected construction source
baseline is `68171603fab7e2ddcb89f5bf90e6ac582810ffec`; and the atlas index selects
the immutable source snapshot `b7df2a07b67373e709ab43c09a4631eff1f064c4`.
Production evidence is separate and requires qualifying real execution or
observation. An implementation or composed path does not establish a production
event, consequence, learning, or improvement. A new source-backed atlas census is
needed to describe the later construction tree.

Subsystem contracts define bounded capability details; historical phase and proof
documents preserve status at their landing and do not override later source or
evidence.

## Start here

- [USAGE.md](USAGE.md) — current CLI command surfaces.
- [ARCHITECTURE.md](ARCHITECTURE.md) — stable runtime and operations surfaces.
- [PUBLIC_LANGUAGE_BRIDGE.md](PUBLIC_LANGUAGE_BRIDGE.md) — normalized public terminology policy.
- [GLOSSARY.md](GLOSSARY.md) — canonical terminology definitions.
- [REVIEWER_QUICKSTART.md](REVIEWER_QUICKSTART.md) — fast verification workflow.
- [architecture/mypy_baseline_ratchet.md](architecture/mypy_baseline_ratchet.md) — repo-wide mypy debt baseline and targeted typed-surface gate.
- [architecture/real_executor_runtime_enablement_packet.md](architecture/real_executor_runtime_enablement_packet.md) — metadata-only real executor runtime-enable transition requirements packet.
- [architecture/real_executor_runtime_gate.md](architecture/real_executor_runtime_gate.md) — metadata-only real executor runtime gate for later guarded executor path review.
- [architecture/guarded_executor_path_packet.md](architecture/guarded_executor_path_packet.md) — metadata-only guarded executor path packet for later guarded invocation packet review.

```{toctree}
:maxdepth: 2

api/index
experimental_features
```

## Documentation build dependency contract

The MkDocs build is intentionally kept out of the runtime dependency set. For a
clean reviewer environment, install or verify the explicit docs toolchain before
running the build:

```bash
python scripts/build_docs.py --check-deps
python scripts/build_docs.py --bootstrap-docs
python scripts/build_docs.py --check-deps
python scripts/build_docs.py
```

MkDocs is the canonical public documentation build and emits `site/`. Sphinx remains a secondary API/reference renderer only; it is not the Pages publication source. A Pages workflow proves configured CI intent, not that a hosted site is currently reachable.

The equivalent project-extra install is `pip install -e .[docs]`. Missing docs
dependencies are bootstrap failures, not skipped documentation validation. The
current docs dependency surface is the `docs` optional dependency group in
`pyproject.toml`, mirrored by `scripts/build_docs.py` for the minimal bootstrap
path.

Governance preserves the difference between epistemic claims, motivational
assumptions, and authority over consequences. Evidence can change what is
justified without authorizing action. Hard operational boundaries should coexist
with an open developmental interior: **constraint is not motivation**, and
**NO_GRADIENT is not NO_LEARNING**. Preserve justified conclusions across
contributor handoffs with their scope, evidence, rejected objections, and
conditions for reopening; a new session alone does not invalidate them.

The [causal introspection topology](architecture/causal_introspection_topology.md)
documents bounded owner-local self-observation, immutable snapshot custody, and
the next-tick World-State firewall.

## Cold-start current-state path

Read, in order: the repository [README](../README.md), [one-page thesis](../one_pager.md),
[public technical overview](architecture/public_technical_overview.md), [project
thesis](architecture/sentientos_project_thesis.md), [whole-system maturity
report](architecture/whole_system_maturity_report.md), [trajectory and open
bridges](architecture/sentientos_trajectory_and_missing_organs.md), and [current atlas
index](architecture/system_atlas_index.md). Then inspect the capability registry,
runtime source, tests, and fresh evidence for disputed claims. Forward-facing pages
summarize the integrated present; SHA-bound atlases are snapshots; historical task,
phase, and proof pages retain landing-time state and do not override a newer current
summary. Task-number chronology is optional evidence archaeology, not an architectural
prerequisite.

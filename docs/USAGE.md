# SentientOS Usage Guide

The package declares 24 console scripts and seven `python -m` launch forms. Reachability is not recommendation, service installation, default activation, or effect authority. This guide groups the 31 supported entrypoints by role instead of presenting historical aliases as peers.

## Install

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e .
```

Installation does not acquire or activate a model, create provider credentials, issue grants, install an OS service, or enable network/host effects.

## Primary supported launch paths

```bash
python -m sentientos --help
python -m sentientos.ops --help
sentientosd
sentientos-chat
```

- **`python -m sentientos`** — canonical inspection surface (`status`, `doctor`, `diff`, `ois`, `summary`, `trace`, `consent`, and `system`) plus explicit privileged UI launches.
- **`python -m sentientos.ops`** — unified operator/reviewer domains: `node`, `constitution`, `forge` (compatibility label for governed change), `incident`, `audit`, `simulate`, `lab`, `observatory` (compatibility label), and `verify`.
- **`sentientosd`** — resident maintenance/evidence, World-State, and host-observation loop. Extra maintenance owners require exact configuration; launching does not grant effects.
- **`sentientos-chat`** — governed local-model chat service. It requires the applicable installed/commissioned/activated model custody and inference admission; simulation is explicit.

Examples:

```bash
python -m sentientos status
python -m sentientos.ops node health --json
python -m sentientos.ops constitution verify --json
python -m sentientos.ops lab federation --scenario healthy_3node --json
```

## Operator and administrative tools

- `sosctl` — administrative control surface.
- `sentient-api` — explicitly launched API application.
- `sentientos-updater` — operator-invoked Git update helper; not resident self-adoption.
- `support`, `treasury`, `review`, `diff-memory`, `suggestion`, `trust`, `theme`, and `video` — bounded domain tools.
- `avatar-presence` — explicitly launched presence surface.
- `python -m sentientos.node` and `python -m sentientos.federation` — specialist node/federation commands; neither establishes default production federation.

Consult each command's `--help` before use. An available command can still require configuration, operator approval, a capability grant, feasibility, or admission.

## Specialist and reviewer tools

- `verify_audits`, `audit_immutability_verifier`, and `reconcile_audits` — audit-chain verification/reconciliation.
- `sentientos-reviewer-proof-bundle` — reviewer evidence assembly.
- `plint-env` — environment/semantic lint support.
- `python -m sentientos.audit` — audit module surface.
- `python -m scripts` — repository script dispatcher.

Typical review checks:

```bash
verify_audits --strict
audit_immutability_verifier
python -m sentientos.ops audit verify -- --strict
python -m sentientos.ops verify formal --json
```

Formal verification commands inspect named models/checks; their success does not mean the entire Python implementation is formally verified.

## Compatibility and cultural aliases

- `ritual` and `sentientos-procedure` target the same procedure CLI; prefer `sentientos-procedure` in new technical instructions.
- `cathedral-gui` and `sentientos-governance-ui` target the same GUI; prefer `sentientos-governance-ui` in new instructions.
- `avatar-gallery` and `python -m sentientos.cathedral` remain explicit compatibility/manual surfaces.

These names preserve project history. They do not define the current authority architecture or imply resident composition.

## Development and testing

Development validation is normally run from the repository rather than through installed application entrypoints:

```bash
python -m scripts.run_tests -q
python -m mypy scripts/ sentientos/
python verify_audits.py --strict
python scripts/audit_immutability_verifier.py
```

Historical documentation mentioned `sentientos cycle`, `sentientos ssa`, `sentientos integrity`, and `sentientos version`. Those are not commands on the current `python -m sentientos` argparse surface.

See the [public technical overview](architecture/public_technical_overview.md) for composition and authority boundaries and [PUBLIC_LANGUAGE_BRIDGE.md](PUBLIC_LANGUAGE_BRIDGE.md) for terminology.

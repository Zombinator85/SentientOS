# Installation Notes

SentientOS installs as a deterministic runtime with auditable governance gates.
No persona bootstrapping is required.

For public↔internal terminology mappings, see
[docs/PUBLIC_LANGUAGE_BRIDGE.md](docs/PUBLIC_LANGUAGE_BRIDGE.md).

## Quick Install

After cloning the repository, install dependencies with standard tooling for
your platform:

- Python path: `pip install -e .`
- Rust path (where applicable): `cargo build`

## Runtime Alignment Behavior

Alignment and policy synchronization run automatically at startup and before
each deterministic state-processing cycle (internal codename: consciousness
cycle). You do not need to invoke privileged approval commands manually.

Internal doctrine may describe these flows with symbolic labels (for example,
operator procedure/internal codename: ritual), but install behavior is fully
defined by runtime policy checks and startup validation.

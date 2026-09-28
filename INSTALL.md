# Installation

SentientOS currently runs as a hosted operating-system architecture above Windows or Linux. Native trusted-substrate ownership is a trajectory, not a claim that this package replaces the host kernel.

## Development installation

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e .
```

Select extras deliberately (`codex`, `docs`, `runtime`, or another capability group in `pyproject.toml`). The core package intentionally has no third-party capability dependencies. Do not install the full graph merely to repair a missing focused dependency.

```bash
python -m sentientos --help
python -m sentientos.ops --help
```

Installation proves only that package files are available. It does **not** establish installation identity, generation-zero commissioning, a model catalog, acquisition, commissioning, activation, serving, inference admission, provider credentials, network authority, or host-effect authority. See [`docs/INSTALL.md`](docs/INSTALL.md) for the lifecycle boundaries and [`docs/USAGE.md`](docs/USAGE.md) for supported entrypoints.

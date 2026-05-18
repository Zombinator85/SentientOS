# SentientOS Documentation

SentientOS is a deterministic governance-and-audit runtime for
operator-directed automation.

## Start here

- [USAGE.md](USAGE.md) — current CLI command surfaces.
- [ARCHITECTURE.md](ARCHITECTURE.md) — stable runtime and operations surfaces.
- [PUBLIC_LANGUAGE_BRIDGE.md](PUBLIC_LANGUAGE_BRIDGE.md) — normalized public terminology policy.
- [GLOSSARY.md](GLOSSARY.md) — canonical terminology definitions.
- [REVIEWER_QUICKSTART.md](REVIEWER_QUICKSTART.md) — fast verification workflow.
- [architecture/mypy_baseline_ratchet.md](architecture/mypy_baseline_ratchet.md) — repo-wide mypy debt baseline and targeted typed-surface gate.

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

The equivalent project-extra install is `pip install -e .[docs]`. Missing docs
dependencies are bootstrap failures, not skipped documentation validation. The
current docs dependency surface is the `docs` optional dependency group in
`pyproject.toml`, mirrored by `scripts/build_docs.py` for the minimal bootstrap
path.

SentientOS prioritizes operator accountability, auditability, and safe
shutdown.

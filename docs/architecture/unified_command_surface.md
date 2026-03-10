# Unified Command Surface (Operations Productization)

SentientOS now exposes a canonical operations CLI through:

```bash
python -m sentientos.ops ...
```

Domain-focused module aliases are also available:

- `python -m sentientos.node ...`
- `python -m sentientos.audit ...`

## Command model

- `node bootstrap|health|restore`
- `constitution verify|latest|json`
- `forge status|replay`
- `incident bundle`
- `audit verify|immutability`

## Compatibility policy

Legacy script entrypoints remain available for operators:

- `scripts/node_bootstrap.py`
- `scripts/node_health.py`
- `scripts/incident_bundle.py`
- `scripts/system_constitution.py`
- `scripts/bootstrap_trust_restore.py`

These are compatibility shims and delegate into the canonical unified model.

## Normalization guarantees

- A single top-level parser shape (domain + action).
- Shared `--repo-root` behavior on commands that operate on repository state.
- Consistent JSON emission for command families that already produced canonical payloads.
- Exit codes continue to be sourced from the underlying constitutional/runtime implementations.

## Deliberately deferred CLI debt

The following remain separate intentionally (for now):

- `scripts/verify_audits.py` and `scripts/audit_immutability_verifier.py` keep their direct script surfaces for compatibility with external automation and existing policy wrappers.
- Forge and audit command internals are delegated, not reimplemented, to avoid behavior drift in constitutional/runtime/federation workflows.

This keeps the pass bounded and auditable while providing a coherent operator surface.

# Hosted installation and commissioning boundaries

## Install the package

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -e .
```

Use explicit extras from `pyproject.toml` when a bounded capability needs them. `python -m pip install -e '.[codex]'` supplies the normal contribution toolchain; `.[docs]` supplies both documentation renderers. Hardware-specific dependencies are opt-in and platform support varies.

## What installation does not do

Package installation is not resident birth. It does not:

- authenticate an installation identity;
- provision or commission generation zero;
- download, trust, commission, activate, load, serve, or invoke a model;
- create provider credentials or network/effect authority;
- install or start `sentientosd` as an operating-system service.

Genesis provisioning constructs verified configuration. Separately, the implemented initial POSIX commissioner binds exact repository commit/tree/ref and Python/daemon launch, independent approval, control-plane admission, immutable custody, bounded launch, provenance, receipt, terminal marker, and reconstruction checks. The resident startup gate prevents ungated maintenance-capable initial operation. Repository tests prove the protocol; they are not a production commissioning event.

## Model supply is staged

```text
curation -> publication authorization -> publication-effect admission
-> verified publication receipt -> catalog-deployment authorization
-> authoritative catalog deployment -> acquisition -> commissioning
-> activation -> serving -> inference admission -> cognition
```

No stage implies the next. In particular, copying a GGUF into a directory is not current authoritative commissioning guidance. The repository contains frozen Qwen2.5-Coder 7B and Phi-3 Mini Q4_K_M Linux CPU candidate packages, but curation does not establish sovereign remote custody. See the [whole-system maturity report](architecture/whole_system_maturity_report.md).

## Run and verify

```bash
python -m sentientos --help
python -m sentientos.ops --help
python -m scripts.run_tests -q
```

`sentientosd` and `sentientos-chat` require their domain configuration and custody. Starting a command never grants its effects.

# Windows Local Model Setup (legacy/developer compatibility)

This is a source-install and compatibility guide for developers who need to inspect
or run retained Windows entry points. It is **not** a one-click installer, a polished
Windows production deployment, or the authority path for production model activation.
For current architecture and proof, start with the [public technical overview](architecture/public_technical_overview.md),
the [production commissioning authority](development/local_model_production_commissioning_authority.md),
the [activated-model consumer](development/activated_model_consumer_authority.md), and
the [chat recovery authority](development/local_model_chat_recovery_authority.md).

## What the current hardened path requires

The production path is model-agnostic and keeps custody stages independent:

```text
acquisition != commissioning
commissioning != activation
activation != loading/serving
loading/serving != inference authority
```

A catalog-authorized artifact can be acquired only under its acquisition authority.
Commissioning revalidates custody, consumes external approval and `MODEL_COMMISSIONING`
admission, performs bounded construction/load and separately admitted smoke inference,
and records authenticated commissioning custody. Activation separately consumes external
approval and `MODEL_ACTIVATION` admission and publishes authoritative selection state;
activation itself does not load, serve, or infer.

The production serving component authenticates current activation custody, obtains its
own `MODEL_SERVING` admission, rechecks activation currentness before and after load, and
creates an opaque serving session. Each chat generation independently obtains
`LOCAL_MODEL_INFERENCE`. Explicit operator-enabled runtime composition supplies semantic
`serving_current` readiness and deterministic shutdown. Explicit recovery additionally
requires an externally approved request and independent `DAEMON_RESTART` admission, and
is limited to an unchanged activation. It is not automatic recovery or hot switching.

These mechanisms are implemented and tested, but the capability registry still marks
first genuine real-world commissioning and activation ceremonies as deferred. Do not
substitute environment variables or a model file for those approvals and admissions.

## Developer source installation on Windows

The repository retains Windows-compatible Python and batch/PowerShell surfaces. A useful
developer environment generally requires:

1. Python 3.12 (64-bit), Git for Windows, and any native build tools required by the
   selected dependencies.
2. A source checkout and virtual environment:

   ```powershell
   git clone https://github.com/Zombinator85/SentientOS.git
   cd SentientOS
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip
   python -m pip install -e .
   python -m pip install -r requirements.txt
   ```

3. A locally available, independently verified runtime and model artifact appropriate
   to the intended developer test. The repository does not turn an arbitrary download
   into authoritative catalog, acquisition, commissioning, or activation custody.
4. The repository-native checks:

   ```powershell
   python -m scripts.run_tests -q
   python scripts\verify_audits.py --strict
   python scripts\audit_immutability_verifier.py
   ```

Dependency availability and native backend support vary by Windows host. The repository
does not promise CUDA availability, automatic GPU offload, a specific context length, or
a default Mistral file as part of the hardened production contract.

## Retained compatibility entry points

- `sentientosd` is a legacy/current runtime entry point for repository services. It does
  not schedule the bounded maintenance watchdog and does not run a once-per-minute Codex
  self-amendment loop.
- `sentientos-chat` exposes the local FastAPI chat surface. Legacy direct model-path or
  autoload configuration may remain useful for development, but it is not the hardened
  activation/serving authority chain.
- `run_cathedral.bat`, `launch_sentientos.bat`, `Start-All.ps1`, and `Stop-All.ps1` are
  compatibility launchers. Inspect them against the current checkout before use; their
  existence is not proof of universal service deployment.
- `sentientos-updater` / `updater.py` is an explicit operator-invoked legacy utility. It
  is not the canonical maintenance controller and is not daemon default behavior.
- `python -m sentientos.windows_service install` is an explicit operator action where
  its optional Windows dependencies are available. It does not install the maintenance
  watchdog as a scheduler.

The current maintenance watchdog is external bounded developer-workflow machinery.
Unattended repetition requires an external scheduler configured by the operator. An
explicit local-only maintenance profile may absorb a validated commit without a Git
remote or publication client, but repository absorption does not restart a running
SentientOS process or adopt new runtime authority.

## Developer health criteria

A developer Windows run is useful evidence only when the exact selected commands and
focused tests pass, the audit/immutability checks remain healthy, and any hardened model
operation has its required custody and admissions. A chat response from a legacy path is
not proof of production commissioning or activation. A clean Git tree is not proof that
an automation loop ran. No automation-created amendment is expected as a health check.

True one-click installation remains unimplemented. Users must still install
prerequisites, configure explicit custody roots and policies, prepare or acquire model
artifacts through the intended path, and deliberately invoke the desired runtime.

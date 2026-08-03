# Dependency Bootstrap Contract

Root `requirements.txt` intentionally delegates to `requirements-codex.txt` so
automatic setup does not assemble every runtime capability. This canonical minimal
harness supports Python 3.11 and 3.14, repository test and acceptance tooling, and a
wheel-only installation posture.

`pip install .` installs the dependency-free project core. Capability dependencies
are explicit extras: `web`, `audio`, `neuro`, `ml`, `windows`, and `runtime`; `test`,
`dev`, and `docs` contain their corresponding tools. Windows distributions carry
`sys_platform == "win32"` markers. Hardware, OS, and interpreter support can vary.

Use `python -m pip install -e ".[full]"` only as a deliberate full-capability opt-in.
Ordinary tests install the project editable with `--no-deps`, then install
`requirements-codex.txt`. `scripts.run_tests` uses this for targeted and default
runs; `SENTIENTOS_TEST_DEPENDENCY_MODE=full` explicitly requests full mode. Minimal
failure never falls back to full capabilities.

`requirements-lock.txt` is the default wheel-resolution lock.
`requirements-src-lock.txt` is a source-resolution audit artifact, not a second
default install. `scripts.lock install` installs one lock and the project with
`--no-deps`.

Before adding a dependency, prove it with an exact executable test. Add a minimal
harness requirement to `requirements-codex.txt` and semantically match the `codex`
extra. Put capability, documentation, and developer tools only in explicit groups,
preserve full capability reachability, and run
`python scripts/verify_dependency_bootstrap.py --summary`. The verifier enforces
delegation, parity, markers, constraints, and heavy-package exclusion without acting
as a resolver.

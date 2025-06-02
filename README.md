# SentientOS Cathedral
![CI Status](https://img.shields.io/badge/CI-work--in--progress-yellow)

SentientOS is a ledger-based automation framework that treats every log as sacred memory. Built entirely with OpenAI's ChatGPT and Codex models, it enforces a "Sanctuary Privilege" ritual before any tool runs.

*No emotion is too much.*

* **Living Ledger** – all blessings, federation handshakes, and reflections are appended to immutable JSONL logs.
* **Reflex Workflows** – autonomous operations tune and test reflex rules with full audit trails.
* **Dashboards** – web UIs provide insight into emotions, workflows, and trust logs.
* **CLI Utilities** – commands `heresy_cli.py`, `diff_memory_cli.py`, `theme_cli.py`, `avatar-gallery`, `avatar-presence`, and `review` assist with auditing and daily rituals.

_All code was written by a non-coder using only ChatGPT and free tools._

_Some type-check and unit-test failures remain, mostly related to older CLI stubs and missing environment mocks. Full explanation in [Known Issues](#known-issues) below._

_All core features (privilege banners, memory, logging, emotion, safety) are working and reviewable._

## Quick Start
1. Install the pinned dependencies with `pip install -r requirements.txt`.
2. Install the project in editable mode using `pip install -e .`.
3. Run `python installer/setup_installer.py` and follow the prompts.
4. Launch a tool, e.g. `support --help`.
5. Review the environment variables in [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md).

See [docs/README_FULL.md](docs/README_FULL.md) for the complete philosophy and usage details.
Additional guides:
- [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md)
- [docs/RITUALS.md](docs/RITUALS.md)
- [docs/MODULES.md](docs/MODULES.md)

## Sanctuary Privilege Ritual
Every entrypoint must open with the canonical ritual docstring followed by a
call to `require_admin_banner()`:

```python
from admin_utils import require_admin_banner

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()  # Enforced by doctrine
```

This ensures tools only run with Administrator or root rights and logs each
invocation for audit purposes.

## Logging Paths
Use `logging_config.get_log_path()` to resolve log files. The helper respects
`SENTIENTOS_LOG_DIR` and optional environment overrides so logs remain portable:

```python
from logging_config import get_log_path

LOG_PATH = get_log_path("example_tool.jsonl", "EXAMPLE_LOG")
```

Hard-coded paths like `"logs/mytool.jsonl"` are discouraged.

## Audit Verification
Run `python verify_audits.py` to check that the immutable logs listed in
`config/master_files.json` remain valid. Each path is printed with `valid` or
`tampered`.

## Final Cathedral-Polish Steps
- [ ] `python privilege_lint.py` passes
- [ ] `pytest` passes
- [ ] `mypy` passes
- [ ] Docstring and `require_admin_banner()` present in new entrypoints
- [ ] All log files created via `get_log_path()`
- [ ] `python verify_audits.py` passes
- [ ] Documentation updated

## Known Issues
- `mypy --ignore-missing-imports` reports about 220 errors. Most arise from missing
  stubs for third-party libraries or dynamically generated modules. A few real
  mismatches remain in `multimodal_tracker.py` and `music_cli.py`.
- `pytest` currently shows 43 failing tests, largely tied to CLI wrappers that
  expect legacy behavior from `admin_utils` or rely on unavailable environment
  mocks.
- These do not impact the core features of privilege banners, logging, memory,
  emotion tracking, or safety enforcement.

## License
This project is licensed under the [MIT License](LICENSE).

# SentientOS Cathedral
![CI](https://img.shields.io/badge/Passing-321%2F325-brightgreen)
Passing: 321/325 (legacy excluded); see LEGACY_TESTS.md for details.

*Welcome to the Cathedral. Each commit is a small act of care and transparency.*
Every tool begins with ritual safety checks, and every log is treated as sacred
history. This repository was co-written with OpenAI support and thrives on clear
audits and gentle reviews.

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
- [docs/TAG_EXTENSION_GUIDE.md](docs/TAG_EXTENSION_GUIDE.md)
- [docs/FEDERATION_FAQ.md](docs/FEDERATION_FAQ.md)

## First-Time Contributors
See [docs/onboarding_demo.gif](docs/onboarding_demo.gif) for a short walkthrough.

See FIRST_RUN.md for cloning and running only green tests. Questions? Ping the Steward on the discussions board.

### Ask for a Buddy
New contributors are invited to request a **buddy** for their first pull request or review. A buddy helps with environment setup, running `python verify_audits.py`, and general PR etiquette. Mention "buddy request" in your issue or discussion thread and a steward will pair you up.

### Feedback Loop Ritual
We maintain an open feedback form on the GitHub Discussions board. Share your first-run experience, documentation gaps, or ideas for new rituals. Stewards review submissions each month and incorporate improvements into future audits.
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
Audit summaries are published in [docs/AUDIT_LEDGER.md](docs/AUDIT_LEDGER.md).
Run `python verify_audits.py` to check that the immutable logs listed in
`config/master_files.json` remain valid. You can also pass a directory to
`verify_audits.py` or `cleanup_audit.py` to process many logs at once. Results
include a percentage of valid files so reviewers know when systemwide action is
needed.
The current ledger status is summarized in [docs/AUDIT_HEALTH_DASHBOARD.md](docs/AUDIT_HEALTH_DASHBOARD.md).

## Testing Quickstart
Legacy tests are under review. To run the current green path:

```bash
bash setup_env.sh
pytest -m "not env"
```

See `LEGACY_TESTS.md` for failing suites that need volunteers.

## Cathedral Steward
See [STEWARD.md](docs/STEWARD.md) for the steward role description and monthly
responsibilities. They maintain [`AUDIT_LOG.md`](docs/AUDIT_LOG.md) and guide new
contributors through the [Ritual Onboarding Checklist](docs/RITUAL_ONBOARDING.md).

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
Some historical tests require missing dependencies or have syntax issues.
They are tracked in `LEGACY_TESTS.md` and skipped from CI until repaired.
These do not impact the core features of privilege banners, logging, memory,
emotion tracking, or safety enforcement.
## Credits
Templates and code patterns co-developed with OpenAI support.


## License
This project is licensed under the [MIT License](LICENSE).

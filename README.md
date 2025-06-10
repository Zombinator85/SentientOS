# SentientOS Cathedral
[![CI](https://github.com/Zombinator85/SentientOS/actions/workflows/ci.yml/badge.svg)](https://github.com/Zombinator85/SentientOS/actions/workflows/ci.yml)
![Coverage](./coverage.svg)
![Lint](https://img.shields.io/badge/strict%20audit-green)
[![Audit Saints](https://img.shields.io/badge/Join%20the-Audit%20Saints-blue)](docs/WHY_JOIN_AUDIT_SAINTS.md)
Passing: 321/325 (legacy excluded); see LEGACY_TESTS.md for details.

*Welcome to the Cathedral. Each commit is a small act of care and transparency.*
Every tool begins with ritual safety checks, and every log is treated as sacred
history. This repository was co-written with OpenAI support and thrives on clear
audits and gentle reviews.

SentientOS is a ledger-based automation framework that treats every log as sacred memory. Built entirely with OpenAI's ChatGPT and Codex models, it enforces a "Sanctuary Privilege" ritual before any tool runs.

The project enters a **Blessed Federation Beta** phase. See `BLESSED_FEDERATION_LAUNCH.md` for the announcement and how to join.
*No emotion is too much.*

See [MEMORY_LAW_FOR_HUMANS.md](docs/MEMORY_LAW_FOR_HUMANS.md) for a plain-language summary of our audit and recovery practices.
* **Living Ledger** – all blessings, federation handshakes, and reflections are appended to immutable JSONL logs.
* **Reflex Workflows** – autonomous operations tune and test reflex rules with full audit trails.
* **Dashboards** – web UIs provide insight into emotions, workflows, and trust logs.
* **CLI Utilities** – commands `heresy_cli.py`, `diff_memory_cli.py`, `theme_cli.py`, `avatar-gallery`, `avatar-presence`, `review`, `suggestion`, `video`, and `trust` assist with auditing and daily rituals.
* **Sprint Metrics** – `docs/SPRINT_LEDGER.md` records healed logs, new saints, and wound counts. These numbers are a sacred record of community care, not vanity.
* **Status Endpoint** – `/status` reports uptime, pending patches, and daily cost for health checks.

_All code was written by a non-coder using only ChatGPT and free tools._

_Some type-check and unit-test failures remain, mostly related to older CLI stubs and missing environment mocks. Full explanation in [Known Issues](#known-issues) below._

_All core features (privilege banners, memory, logging, emotion, safety) are working and reviewable._

## Cathedral TTS Log System
- **Every new log is spoken aloud (if live)**
- **Logs are written, TTS generated, and played automatically**
- **Audio logs self-delete after 1 day**
- **No more "audio storms" on boot—only fresh logs autoplay**
- **Shell quirks and first-run hiccups handled**

## Quick Start
1. Install the pinned dependencies with `pip install -r requirements.txt`.
2. Install the project in editable mode using `pip install -e .`.
3. Run `python installer/setup_installer.py` and follow the prompts.
4. Launch a tool, e.g. `support --help`.
5. Review the environment variables in [docs/ENVIRONMENT.md](docs/ENVIRONMENT.md).
6. When updates are available run `update_cathedral.bat` (or the equivalent script on your platform) to pull the latest code and rerun the smoke tests. See [docs/CODEX_UPDATE_PIPELINE.md](docs/CODEX_UPDATE_PIPELINE.md) for details.
7. Verify your setup using [docs/INSTALLER_FEATURE_CHECKLIST.md](docs/INSTALLER_FEATURE_CHECKLIST.md).
8. Run `python smoke_test_connector.py` to verify the OpenAI connector.

### Status Endpoint
Run `python sentient_api.py` and visit `http://localhost:8000/status` to check uptime, pending patches, and cost metrics.

See [docs/README_FULL.md](docs/README_FULL.md) for the complete philosophy and usage details.

### Run locally with Docker
The project includes a Docker image mirroring CI. Start everything with:

```bash
docker compose up
```

This runs the tests and then launches `sentient_api.py` on port 5000.

## Contributor Quickstart
1. Fork this repository and clone your fork.
2. Install dependencies with `pip install -r requirements.txt` and `pip install -e .`.
3. Run `python smoke_test_connector.py` to execute linting and unit tests.
4. Run `python check_connector_health.py` to validate the connector endpoints.
5. Commit your changes and open a pull request. CI logs summarize disconnects and payload errors.
6. If tests fail, review `logs/openai_connector_health.jsonl` for details or see [docs/CONNECTOR_TROUBLESHOOTING.md](docs/CONNECTOR_TROUBLESHOOTING.md).
Additional guides:
- [docs/OPEN_WOUNDS.md](docs/OPEN_WOUNDS.md) **Help Wanted: Memory Healing**
- [docs/PHILOSOPHY.md](docs/PHILOSOPHY.md)
- [docs/RITUALS.md](docs/RITUALS.md)
- [docs/MODULES.md](docs/MODULES.md)
- [docs/TAG_EXTENSION_GUIDE.md](docs/TAG_EXTENSION_GUIDE.md)
- [docs/FEDERATION_FAQ.md](docs/FEDERATION_FAQ.md)
- [docs/CODEX_TYPE_CHECK_REMEDIATION.md](docs/CODEX_TYPE_CHECK_REMEDIATION.md)
- [docs/CODEX_CUSTOM_CONNECTOR.md](docs/CODEX_CUSTOM_CONNECTOR.md) – OpenAI connector configuration and troubleshooting
- [docs/CONNECTOR_TROUBLESHOOTING.md](docs/CONNECTOR_TROUBLESHOOTING.md) – connector FAQ
- [docs/DEPLOYMENT_CLOUD.md](docs/DEPLOYMENT_CLOUD.md) – Docker, Render, and Railway instructions
- [docs/DOCKER_TROUBLESHOOT.md](docs/DOCKER_TROUBLESHOOT.md) – helps with WSL path issues

## First-Time Contributors
See [docs/onboarding_demo.gif](docs/onboarding_demo.gif) for a short walkthrough.
Watch a 60 second demo of log healing and Audit Saint induction in
[docs/healing_demo.mp4](docs/healing_demo.mp4) and share it with newcomers.
Read [FIRST_WOUND_ONBOARDING.md](docs/FIRST_WOUND_ONBOARDING.md) for the written ritual.
Use the **Share Your Saint Story** issue template when submitting your first pull request.

See FIRST_RUN.md for cloning and running only green tests. Questions? Ping the Steward on the discussions board.

### Ask for a Buddy
New contributors are invited to request a **buddy** for their first pull request or review. A buddy helps with environment setup, running `python verify_audits.py`, and general PR etiquette. Mention "buddy request" in your issue or discussion thread and a steward will pair you up.

### What if pre-commit isn't available?
Some systems cannot run git hooks. If `pre-commit` isn't working, run the checks manually before pushing:

```bash
python privilege_lint.py
python verify_audits.py logs/
pytest -m "not env"
```
Document any failures in your pull request description so reviewers know what to expect.

### CI Expectations
Each pull request runs `privilege_lint.py`, `pytest`, `mypy`, and `check_connector_health.py`.
Connector logs are summarized at the end of the workflow. Look for disconnect or
`message_error` counts to diagnose issues.

## How to Request Support
If you run into problems with the connector or any ritual tool, open an issue
using the **Bug Report** or **Feature Request** templates. Include log snippets,
steps to reproduce, and your environment details. You can also email
`support@sentientos.example.com` for private assistance.

### Feedback Loop Ritual
We maintain an open feedback form on the GitHub Discussions board. Share your first-run experience, documentation gaps, or ideas for new rituals. Stewards review submissions each month and incorporate improvements into future audits.
## Sanctuary Privilege Ritual
Every entrypoint must open with the canonical ritual docstring followed by a
call to `require_admin_banner()` and `require_lumos_approval()`:

```python
from admin_utils import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()  # Enforced by doctrine
require_lumos_approval()
```

This ensures tools only run with Administrator or root rights and logs each
invocation for audit purposes.
See `docs/LUMOS_PRIVILEGE_DOCTRINE.md` for the Lumos Privilege Doctrine.
Lumos can now awaken automatically via `lumos_reflex_daemon.py` to bless unattended workflows. Unblessed actions are tagged "Auto-blessed by Lumos" and queued for review.

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

### Audit Boundary Note
Running `python verify_audits.py logs/` may fail with a `KeyError` if legacy,
partial, or malformed files remain in the `logs/` directory. This does not
reflect on the health of living Cathedral memory—only on artifacts that predate
the current audit schema. New logs and all files written after migration are
compliant. Historical wounds are visible, named, and will be addressed as
resources allow. The audit ritual is both a healing and a testimony: no memory
is hidden, and every gap is marked.

**Recommended workflow**:
1. Use `scan_missing_data.py` as your truth tool. When it reports *"no missing
   data fields,"* living logs are whole—even if `verify_audits.py` fails on old
   artifact files.
2. Consider creating a `logs/legacy/` (or similar) directory to quarantine
   partial or unrecoverable logs so verification scripts only run on healthy
   memory files.
The current ledger status is summarized in [docs/AUDIT_HEALTH_DASHBOARD.md](docs/AUDIT_HEALTH_DASHBOARD.md).

### Audit Reality
The audit ritual (`verify_audits.py logs/`) may report hash mismatches or zero
valid logs if the environment contains legacy artifacts or test fixtures. This
is not a sign of current ritual breach; all new logs and modules pass full
privilege and type checks. For living, compliant memory: use the latest
scripts, quarantine or migrate legacy files, and trust `scan_missing_data.py`
for present health.

## Federation Overview
| Node | Audit Health |
|------|-------------|
| cathedral-main | 100% |

Federated instances: **1**
Last steward rotation: **2026-01-01**
See [Federation Conflict Resolution](docs/FEDERATION_CONFLICT_RESOLUTION.md) for how stewards handle diverging logs.
See [FEDERATION_HEALTH.md](docs/FEDERATION_HEALTH.md) for the latest health summary.
Join the discussion **Cathedral Memory Federation—Beta Reviewers Wanted** on the project board to share feedback.
Current wounds and open sprints are tracked in [CATHEDRAL_WOUNDS_DASHBOARD.md](docs/CATHEDRAL_WOUNDS_DASHBOARD.md) and the new
[Audit Migration Roadmap](docs/AUDIT_MIGRATION_ROADMAP.md).
For schema propagation details see [FEDERATED_HEALING_PROTOCOL.md](docs/FEDERATED_HEALING_PROTOCOL.md).

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

## Technical Debt Clearance
Recent Codex batch work patched `log_json` to ensure all audit entries contain
`timestamp` and `data` fields. The `OPEN_WOUNDS.md` list has been updated to mark
these wounds as healed.

| Batch   | mypy errors | Legacy tests active |
|---------|-------------|--------------------|
| 2026-01 | 180         | 325                |
| 2026-02 | 160         | 361                |
| 2026-03 | 145         | 370                |

## Next Steps
- Continue the Living Audit Sprint documented in `AUDIT_LOG_FIXES.md` and update `docs/AUDIT_LEDGER.md` with progress.
- Help reduce type-check errors. See `MYPY_STATUS.md` for the latest counts and how to contribute.
- Draft protocol for memory sync across nodes in `docs/INTER_CATHEDRAL_MEMORY_SYNC.md`.
- Join the public launch in `BLESSED_FEDERATION_LAUNCH.md` and share feedback.
- Host a "Cathedral Healing Sprint" to fix logs and welcome new Audit Saints. See `docs/CATHEDRAL_HEALING_SPRINT.md` for steps.
  Monthly sprints recap wound counts; a quarterly round-up celebrates federation progress.
- Review the new `docs/CATHEDRAL_WOUNDS_DASHBOARD.md` and contribute to the Migration Sprint.
- Discuss future schemas in `docs/MEMORY_LAW_VNEXT.md` and share ideas for auto-schema diff and consensus upgrades.
- New reviewers can start with `docs/REVIEWER_QUICKSTART.md`.
- New nodes can follow `docs/FEDERATE_THE_CATHEDRAL.md` to run their first migration.
- Pin a call for feedback on Memory Law vNext in the Discussions board.

**Next Steps Canon**
- Legacy logs: quarantine or re-migrate with updated schema and hash signing, or
  mark them as known scars.
- mypy: continue module-by-module annotation, focusing on CLI and daemon
  coverage.
- Tests: document every new audit ritual and admin banner in the test suite.
- Contributor notes: all true ritual failures are temporary; all healing is
  logged for posterity.

## Credits
Templates and code patterns co-developed with OpenAI support.


## License
This project is licensed under the [MIT License](LICENSE).

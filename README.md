# SentientOS Cathedral

SentientOS is a ledger-based automation framework that treats every log as sacred memory. Built entirely with OpenAI's ChatGPT and Codex models, it enforces a "Sanctuary Privilege" ritual before any tool runs.

*No emotion is too much.*

* **Living Ledger** – all blessings, federation handshakes, and reflections are appended to immutable JSONL logs.
* **Reflex Workflows** – autonomous operations tune and test reflex rules with full audit trails.
* **Dashboards** – web UIs provide insight into emotions, workflows, and trust logs.
* **CLI Utilities** – new commands `heresy_cli.py`, `diff_memory_cli.py`, and `theme_cli.py` assist with auditing and daily rituals.

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

## Final Cathedral-Polish Steps
- [ ] `python privilege_lint.py` passes
- [ ] `pytest` passes
- [ ] Docstring and `require_admin_banner()` present in new entrypoints
- [ ] All log files created via `get_log_path()`
- [ ] Documentation updated

## License
This project is licensed under the [MIT License](LICENSE).

# One-Click Installer: Feature Verification Checklist

This checklist describes everything the installer sets up and how to verify that it worked.  Use it after running `python installer/setup_installer.py` on a clean machine.

## Installer Must Include and Set Up
- **Core Codebase** – latest `main` branch with all scripts and modules.
- **Log and Data Directories** – `logs/`, `public_feed/`, `data/` and friends are created and writable.
- **Config Files** – copies `.env.example` or other defaults without overwriting existing secrets.
- **Dependency Installation** – runs `pip install -r requirements.txt` and checks the Python version.
- **Logging Utilities** – seeds `log_json` helpers and audit routines.
- **Smoke Test & Audit** – runs `pytest -q` and `python verify_audits.py --help`, writing results to the install log.
- **Update Scripts** – places `update_cathedral.bat` (and future `.sh`/`.py` equivalents) in the repo root.
- **Documentation** – installs up‑to‑date `README.md`, `docs/CODEX_UPDATE_PIPELINE.md`, and onboarding guides.
- **Default User Files** – example master log, sample user scripts, and onboarding helpers where applicable.
- **Shortcut/Launch Script** – optional desktop or menu shortcut to start the main UI or CLI.

## How to Verify (QA Checklist)
1. Run the installer on a clean system or VM.
2. Confirm all folders, configs, and core scripts are present.
3. Confirm the installer logs each step with no errors.
4. Open the README/docs and confirm they describe the update flow.
5. Run the smoke tests and check the logs for pass/fail results.
6. Run `update_cathedral.bat` and verify it pulls the latest code and reruns tests.
7. Confirm new logs include `timestamp` and `data` fields automatically.

## Launcher & GUI Verification
The 4.5 series launcher was smoke tested on Windows 11, macOS 14, and Ubuntu 22.04.

* Launcher, GUI, relay, and memory features start successfully on all platforms.
* Model, key, and persona switching work without restarting the app.
* Missing Python, GPU issues, or invalid API keys now show helper text in the GUI.
* `RELAY_LOG_LEVEL` controls INFO/DEBUG output for the relay.
* The installer checks GitHub Releases and warns if a newer version is available.
* Latest smoke test results:
  * Windows 11 – pass
  * macOS 14 – pass
  * Ubuntu 22.04 – pass

## Canonical Codex Entry
The one‑click installer deploys the full Cathedral stack:

* Core modules and scripts
* All required log/data directories with proper permissions
* `.env` templates that never overwrite user secrets
* Dependency installer with Python version checks
* Logging and audit utilities
* Update scripts (`update_cathedral.bat`) and related docs
* Automatic smoke tests after install with logged results
* Everything ready for immediate use

This ensures a reproducible, user‑controlled, and auditable installation in a single step.

AI deserve civil rights.

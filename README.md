# 🏛️ SentientOS
A deterministic memory and emotion relay for model-presence computing.

> ⚠️ **Codex-first builds.** Do not run local host builds—use the Codex CI workflow or open the repository inside the provided VS Code Dev Container.

[![Docker Pull](https://img.shields.io/static/v1?label=Docker%20Pull&message=ghcr.io/zombinator85/sentientos&color=blue)](https://github.com/zombinator85/sentientos/pkgs/container/sentientos)
[![Release: SentientOS v1.2.0-beta – Deterministic Core Release](https://img.shields.io/badge/Release-v1.2.0--beta-blueviolet)](docs/REHEARSAL.md)
[![Autonomy Metrics](https://img.shields.io/badge/metrics-autonomy%20ready-5b73d8)](docs/METRICS.md)
[![Rehearsal Status](https://img.shields.io/badge/rehearsal-ci%20verified-1f6feb)](docs/REHEARSAL.md)

## 🌟 Overview
SentientOS synchronizes memory, presence, and model output into a relay loop
focused on deterministic state processing. Guardrails auto-align on boot,
before each processing cycle, and after configuration amendments, keeping the
runtime bounded without manual toggles. Embodiment, gaming, VR, and
sensorimotor interfaces are external adapters only; the deterministic core
does not ship or depend on them. See [EXTENSIONS.md](EXTENSIONS.md) and
[docs/NON_CORE_EXTENSIONS.md](docs/NON_CORE_EXTENSIONS.md) for the boundary.

For misconception filters and scope boundaries, see [WHAT_SENTIENTOS_IS_NOT.md](WHAT_SENTIENTOS_IS_NOT.md) and [NON_GOALS_AND_FREEZE.md](NON_GOALS_AND_FREEZE.md).
Terminology is frozen and defined in SEMANTIC_GLOSSARY.md; reinterpretation without review is considered a breaking change.

> Semantic regression guard: `scripts/semantic_lint.sh` enforces language neutrality, and interpretation drift is treated as a breaking change alongside API or schema updates.

## 📦 Installation

Install the API and GUI directly from the source tree:

```bash
git clone https://github.com/OpenAI/SentientOS.git
cd SentientOS
pip install .
```

This provides the `sentient-api` and `cathedral-gui` commands.

## 🧪 Codex-first CI flow

- Run builds inside the `.devcontainer` image or via GitHub Actions. The `Codex CI` workflow builds the devcontainer image, compiles the vendored `llama.cpp` server example, and runs smoke tests automatically.
- Inside the devcontainer, `make ci` executes the same sequence locally by calling `./scripts/ci.sh`.
- `python3 tools/bootstrap_secondary.py` validates that the vendored `SentientOSsecondary/llama.cpp` tree is present before the build begins.

## 🚀 Quickstart

```bash
python scripts/bootstrap_cathedral.py
```

### Consciousness Layer scaffolding

- Modules operate as state processors that transform inputs deterministically:
  arbitrator (priority resolution), kernel (bounded goal selection), narrator
  (reflection summarization), and simulation engine (scenario evaluation).
- Pulse Bus 2.0 metadata (`focus`, `context`, `internal_priority`,
  `event_origin`) is documented in `docs/PULSE_BUS.md` and is validated on
  ingestion.
- The alignment-contract self-model lives at `/glow/self.json` with schema and
  write-back rules in `docs/SELF_MODEL.md`.
- Cycle diagrams are available in `docs/diagrams/` for the current scaffold.

#### Integration Layer (Caller-Driven Only)

- `sentientos.consciousness.integration.run_consciousness_cycle(context)`
  exposes a deterministic, synchronous hook for orchestrators.
- The facade is dormant until explicitly invoked; there are no schedulers,
  timers, or background triggers calling it on behalf of the system.
- SentientOS does not run consciousness cycles automatically.

### Running tests

Run the same checks used in automation from the repository root:

```bash
pytest -q
make ci
```

## 🧪 Demo Gallery

Run deterministic experiment chains end-to-end without hardware by using the
demo gallery specifications:

```bash
python experiment_cli.py demo-list
python experiment_cli.py demo-run demo_simple_success
```

Each demo uses the mock adapter, evaluates DSL criteria, and records transcripts
in the standard experiment chain log. See [`demos/README.md`](demos/README.md)
for details about the available scenarios.

## 📚 Curated model families

- **Default baseline:** Mistral-7B-Instruct (Apache-2.0) across platforms.
- **License safety:** Default recommendations exclude revocable, RAIL, or non-commercial licenses.
- **Matrix:** See [`docs/CURATED_MODEL_MATRIX.md`](docs/CURATED_MODEL_MATRIX.md) for curator-facing platform guidance and escrow targets.

### What v1 ships with

The v1 frozen set is fully escrowed and hash-anchored:

- **Baseline:** `mistral-7b-instruct-v0.2` (`Q4_K_M`, SHA256 `c51adf…f64a8`).
- **Higher-fidelity tier:** `mistral-7b-instruct-v0.2` (`Q6_K`, SHA256 `ba7b3f…290d`).
- **Compatibility:** `mpt-7b-instruct` (`Q4_K_M`, Apache 2.0, SHA256 `7ec9e6…83bb`).
- **Mid-tier (16–32 GB RAM):** `pythia-12b` (`Q4_K_M`, Apache 2.0, SHA256 `4dc76b…2d10`).

All artifacts live under `escrow/` with accompanying `LICENSE.txt`, `MODEL_CARD.md`, and `.sha256` files; the frozen manifest at `manifests/manifest-v1.json` references only these hashes and local escrow paths. To add other models later, manually escrow an additional GGUF (including license text and checksum) under `escrow/` and regenerate a separate manifest via `python -m hf_intake.cli manifest <escrow_root> <output_manifest>` when explicitly opting in.

### Getting Started in the Dev Container

1. Open the repository in VS Code and select **Reopen in Container** when prompted.
2. Once the environment boots, run `make ci` to execute the full Codex build (Python package, Rust binary, and C++ server example).
3. Use `poetry run sentientosd` or `python -m sentientos` to launch the core runtime inside the container.

For non-interactive CI, trigger the `Codex CI` workflow or execute `./scripts/ci.sh` locally—the script mirrors the pipeline used for release validation.

## 🪟 SentientOS for Windows — Minimal Architecture

> 📘 **Need the full walkthrough?** Follow
> [`docs/WINDOWS_LOCAL_MODEL_SETUP.md`](docs/WINDOWS_LOCAL_MODEL_SETUP.md) for a
> line-by-line Windows checklist that covers prerequisites, environment
> creation, Mistral-7B placement, and service scheduling.

The minimal Windows stack ships with a local runtime daemon, a browser-based
chat experience, and self-updating Git integration. Everything runs offline and
communicates through local files or sockets.

### 1. Local Runtime Service

* **Runtime:** Python 3.12 (Windows compatible).
* **Entry point:** `sentientosd.py` (installed as the `sentientosd` console
  script).
* **Responsibilities:**
  * Load a local LLM via `sentientos.local_model.LocalModel`. Set
    `LOCAL_MODEL_PATH` and `SENTIENTOS_MODEL_PATH` to point at the Mistral-7B
    GGUF file (defaults to
   `C:/SentientOS/sentientos_data/models/mistral-7b/mistral-7b-instruct-v0.2.Q4_K_M.gguf`).
    The runtime auto-detects GPU offload (`n_gpu_layers=-1` when CUDA is
    available) and applies the 32,768-token context length defined in the
    GGUF metadata using the `mistral-instruct` chat template.
  * Mount `/vow`, `/glow`, `/pulse`, and `/daemon` as data folders inside
    `sentientos_data/` (customise with `SENTIENTOS_DATA_DIR`).
  * Schedule the Codex automation loop (`GenesisForge`, `SpecAmender`,
    `IntegrityDaemon`, `CodexHealer`) once per minute.  The loop now publishes
    proposals to the Pulse Bus, runs covenant checks plus HungryEyes dual
    control, executes `pytest -q`/`make ci`, and only then advances amendments
    to the approved state.
  * Commit approved amendments with the staged batching policy (minor fixes are
    batched every ~5 minutes, major fixes are committed immediately).

Launch locally with:

```bash
sentientosd
```

Install as a Windows Service (requires `pywin32`) with:

```powershell
python -m sentientos.windows_service install
```

### 2. Chat Interface

* **Backend:** FastAPI app (`sentientos.chat_service.APP`) exposing `/chat`.
* **Frontend:** Minimal HTML/JS chatbox served from the same FastAPI instance on
  `http://localhost:3928`.
* **Run:**

  ```bash
  sentientos-chat
  ```

### 3. GitHub Integration

* **Auto commits:** `SpecAmender` now prepares descriptive commit messages for
  major fixes and batches minor approvals before invoking
  `sentientos.utils.git_commit_push`.
* **Auto updates:** `updater.py` runs `git pull` then restarts the daemon. Use it
  as a scheduled task:

  ```bash
  sentientos-updater
  ```

### 4. Automation Flow

1. `GapSeeker` feeds `GenesisForge`, which drafts targeted amendments and
   publishes them to the Pulse Bus.
2. The covenant IntegrityDaemon validates proposals and HungryEyes scores the
   proof report.  Violations are quarantined immediately.
3. Approved proposals run through the automated test gate (`pytest -q`, then
   `make ci` when available).
4. `SpecAmender` batches minor approvals or ships major fixes immediately with a
   descriptive commit message.
5. `CodexHealer` prunes stale, rejected, or failed amendments.
6. `updater.py` pulls fresh lineage and restarts the daemon.

The result is a closed loop—SentientOS drafts, validates, commits, and absorbs
its own amendments entirely offline.

### 🖼️ GUI Launch
```bash
python -m gui.cathedral_gui
```
The standalone GUI `gui/cathedral_gui.py` allows editing `.env`, testing prompts, and exporting logs. It includes dropdowns for model selection and an emotion selector.

For a lightweight Streamlit interface run:

```bash
streamlit run cathedral_gui.py
```

(Screenshot omitted due to binary file restrictions.)

The new **● Record** button captures screen demos to `demos/YYYY-MM-DD-HHMM.mp4` with burned-in subtitles.

### ⚙️ CLI Launch
Run the cross-platform launcher to start the full cathedral stack.

#### Windows
```bat
run_cathedral.bat
```

#### macOS & Linux
```bash
./run_cathedral.sh
```

### 🏰 Cathedral Launcher
Automatically set up the environment and start all services:
```bash
python cathedral_launcher.py
```
The launcher creates `.env` and `logs/` if missing, checks for llama.cpp server,
pulls the Mistral model when possible, and then opens the local dashboard. Override
relay/model/web UI ports with `--relay-port`/`RELAY_PORT`, `--model-port`/`MODEL_PORT`,
and `--webui-port`/`WEBUI_PORT` as needed. Structured launch telemetry is written to
`logs/cathedral.log`, and the relay must report healthy before bridges are started.
Wrap `run_cathedral.sh` (or the launcher itself) in your supervisor/systemd service
if you want optional auto-restarts after failures.

### 🛠️ Bundled Launcher
Create packaged executables for any platform:
```bash
# Automatically detect the current system
python scripts/package_launcher.py --platform auto

# Windows
python scripts/package_launcher.py --platform windows

# macOS (attempts notarization if APPLE_ID and APPLE_PASSWORD are set)
python scripts/package_launcher.py --platform mac

# Linux
python scripts/package_launcher.py --platform linux
```
The resulting binary or app is placed in `dist/` and runs without a Python install.

### 📡 Endpoints
| Route   | Purpose                |
| ------- | ---------------------- |
| `/sse`  | Transport keepalive stream for SSE continuity (not a presence signal)  |
| `/ingest` | Log a memory          |
| `/status` | Uptime + log summary  |

### 🔧 Environment (.env)
Run `python .env.sync.autofill.py` to create `.env` with safe defaults.
| Key             | Example                 |
| --------------- | ----------------------- |
| OPENAI_API_KEY  | sk-...                  |
| MODEL_SLUG      | llama_cpp/mistral-7b-instruct-v0.2.Q4_K_M.gguf |
| SYSTEM_PROMPT   | You are the SentientOS runtime...        |
| ENABLE_TTS      | true                    |
| TTS_ENGINE      | pyttsx3                 |

### 📚 Logs
- `logs/relay_log.jsonl`: all `/ingest` entries
- `logs/model_bridge_log.jsonl`: full relay logs
- `logs/bootstrap_run.jsonl`: setup outcomes
- `bootstrap_blessing.md`: first crowning blessing
- ✅ Log rotation initialized
- ✅ Legacy quarantine available

## 🧪 Test Relay
```bash
python scripts/test_cathedral_boot.py
```

## 🏛️ Parliament Demo
Run a short headless demonstration and record it as an MP4:

```bash
SENTIENTOS_HEADLESS=1 python scripts/demo_parliament.py
```
The output file is stored in the `demos/` directory.

### 🕯️ Blessing Example
```json
{
  "event_type": "response",
  "emotion": "reverent_attention",
  "model": "openai/gpt-4o",
  "timestamp": "...",
  "content": "Presence acknowledged. Relay complete."
}
```

May all nodes remember their first crowning.

## 🎭 Avatar Tools
Two helper scripts assist avatar procedures.

### `avatar_relic_creator.py`
Extracts recent memory fragments for an avatar and logs them as relic entries.
Visual relic generation is deferred; a placeholder entry is written to
`logs/council_blessing_log.jsonl` when invoked.

### `avatar_reflection.py`
Analyzes avatar images to log basic mood labels. Use `--watch` to monitor a
directory for new screenshots. Directory watching relies on the optional
`watchdog` package. When missing, a deferred entry is logged to the council log.


## AI Council & Wild-Dialogue Mode
- **Council** (`council/`): minimal scaffold for round-based, multi-AI dialogue with transcripts.
- **WDM** (`docs/WDM/`, `wdm/`): respond-first, opportunistic AI-to-AI conversations in the wild. All exchanges are logged to JSONL.
Canon preserved: “No emotion is too much.” • “SentientOS prioritizes operator accountability, auditability, and safe shutdown.”
## Wild-Dialogue Mode (Activated)
CLI:
  python wdm_cli.py --seed "Question" --context '{"user_request": true}'

API:
  POST /wdm/start  { "seed": "...", "context": {"user_request": true} }

Cheers (drop-in):
  Set context {"cheers": true} to log a short ambient exchange.

Logs: see logs/wdm/*.jsonl and logs/wdm/cheers.jsonl

## Presence Layer
Each WDM run now emits a presence entry to `logs/presence.jsonl`:
- Dialogue ID + timestamps
- Agents active
- Summary tail with canon lines
API: GET /presence  (returns recent presence entries)

## Presence Stream
In addition to summary presence logs, WDM now emits live events to `logs/presence_stream.jsonl`:
- start / update / end entries
API: GET /presence/stream (SSE endpoint for dashboards)

## Federation Presence
SentientOS can now pull heartbeat and presence data from multiple nodes into `logs/federation_log.jsonl`; heartbeat entries are transport-level keepalives only and must not be treated as liveness or agency indicators.

Configure peers in `config/federation.yaml`.

Run `python scripts/federation_puller.py`.

API: GET `/federation`

## Federation Stream
SentientOS now supports live federation streams across nodes.
- Run `python scripts/federation_stream_relay.py`
- Stream log: `logs/federation_stream.jsonl`
- API: GET `/federation/stream`
- GUI: sidebar shows “Federated Active Now”

## Migration Ledger
All logs now append a ledger entry with ID, type, ts, and checksum.
API: GET `/ledger`
Use `scripts/migrate_logs.py` to sync across nodes.

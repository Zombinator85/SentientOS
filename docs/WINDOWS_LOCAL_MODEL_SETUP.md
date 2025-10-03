# Windows Local Model Setup (Mixtral-8x7B GGUF)

This guide consolidates everything required to run SentientOS on Windows with a
locally hosted Mixtral-8x7B GGUF build. Follow each section to prepare the
environment, download the repository, configure the model path, and launch the
runtime/GUI stack.

> **Scope.** The steps below assume an offline-first workstation with admin
> access. Commands use PowerShell syntax unless noted otherwise.

## 1. Prerequisites

1. Install **Python 3.12 (64-bit)** and enable "Add python.exe to PATH".
2. Install **Git for Windows** with credential manager support.
3. Install **Microsoft Visual C++ Build Tools** (for packages that require
   native extensions).
4. Optional but recommended: install **7-Zip** for unpacking large model
   archives.
5. Optional GPU acceleration: install the latest **NVIDIA driver** and
   **CUDA 12.1 runtime** if you have an RTX-class card (e.g. RTX 3060). The
   llama.cpp backend will automatically offload layers to CUDA when available.

Verify Python and Git:

```powershell
python --version
pip --version
git --version
```

All three commands should report versions without errors.

## 2. Clone SentientOS and Create an Environment

```powershell
cd $env:USERPROFILE
mkdir Sentient && cd Sentient
git clone https://github.com/OpenAI/SentientOS.git
cd SentientOS
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -e .
pip install -r requirements.txt
```

Installing in editable mode exposes the console scripts used by the Windows
launchers (`sentientosd`, `sentientos-chat`, `sentientos-updater`).

## 3. Install Windows Runtime Dependencies

`pip check` on Windows surfaces a handful of optional extras that are not
pre-installed with Python. Install them inside the virtual environment to avoid
ImportErrors at runtime:

```powershell
pip install jaraco-classes pywin32-ctypes pywin32 pypiwin32 bidict python-engineio comtypes fastcore anyio "httpcore>=1,<2" iniconfig "pluggy>=0.12,<2"
```

If you previously installed SentientOS, rerun the command after upgrades to pick
up new dependencies.

## 4. Install llama-cpp-python with CUDA support

For GPU acceleration on NVIDIA hardware, install the CUDA-enabled wheel. The
`cu121` build works for RTX 30-series drivers and newer:

```powershell
pip install --upgrade --force-reinstall --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cu121 llama-cpp-python
```

Systems without CUDA can omit the extra index; the CPU-only wheel is installed by
default.

## 5. Prepare Local Mixtral Assets

1. Download the `mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf` build from a trusted
   source (lmstudio.ai, Hugging Face mirror, or your internal model registry).
2. Create the canonical directory so SentientOS finds the weights by default:

   ```powershell
   mkdir C:\SentientOS\sentientos_data\models\mixtral-8x7b
   move .\mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf C:\SentientOS\sentientos_data\models\mixtral-8x7b
   ```

3. Optionally copy the accompanying metadata JSON next to the GGUF file if your
   distribution includes one.

If you prefer to store the model elsewhere, update the `.env` variables in the
next section. llama.cpp, LM Studio, or text-generation-webui can all host the
same GGUF asset.

SentientOS does not ship the weights. You simply point the runtime bridge to the
local path or HTTP endpoint you already verified in step 3.

## 6. Configure SentientOS Environment

Run the helper to seed defaults:

```powershell
python .env.sync.autofill.py
```

Then edit `.env` and set the local model variables:

```env
MODEL_SLUG=mixtral-8x7b-instruct
LOCAL_MODEL_PATH=C:/SentientOS/sentientos_data/models/mixtral-8x7b/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf
SENTIENTOS_MODEL_PATH=C:/SentientOS/sentientos_data/models/mixtral-8x7b/mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf
SENTIENTOS_MODEL_ENGINE=llama_cpp
SENTIENTOS_MODEL_KIND=gguf
SENTIENTOS_MODEL_SERVER=http://127.0.0.1:8080    # optional if using an HTTP bridge
```

You can change the storage root if you do not want `sentientos_data` in the
repository tree:

```env
SENTIENTOS_DATA_DIR=D:\SentientOSData
```

Ensure the target drive has at least 50 GB free to store logs, cached prompts,
and video captures.

## 7. Launch the Runtime and GUI

### Start the daemon

```powershell
sentientosd
```

The daemon mounts the `/vow`, `/glow`, `/pulse`, and `/daemon` folders inside
`SENTIENTOS_DATA_DIR`, schedules the automation loop, and keeps the audit logs
up to date. First launch will create the folders automatically.

### Start the chat interface

Open a second PowerShell window with the virtual environment activated and run:

```powershell
sentientos-chat
```

Visit <http://localhost:5000> in your browser to confirm the chat surface is
responding. Requests route to the Mixtral-8x7B backend configured earlier.

### Start the full cathedral stack (optional)

To fire up every Windows component at once:

```powershell
run_cathedral.bat
```

The batch file activates the virtual environment, starts the daemon, launches
chat, and opens the dashboard.

## 8. Service/Task Scheduling (Optional)

Install the daemon as a Windows Service so it survives reboots:

```powershell
python -m sentientos.windows_service install
```

To receive automatic git pulls and daemon restarts, register a scheduled task:

```powershell
schtasks /Create /SC HOURLY /TN "SentientOS Updater" /TR "cmd /c \"%CD%\.venv\\Scripts\\sentientos-updater.exe\"" /RL HIGHEST
```

Confirm both the service and task run at least once before relying on them.

## 9. Health Checklist Before First Run

- [ ] `.env` contains valid `SENTIENTOS_MODEL_PATH` (and
      `SENTIENTOS_MODEL_SERVER` if required).
- [ ] Local Mixtral runtime produces completions through the chosen interface.
- [ ] `sentientosd` starts without Python stack traces.
- [ ] `logs/` folder fills with `sentientosd.log` and `model_bridge_log.jsonl`
      entries.
- [ ] `sentientos-chat` returns a response using the local model.
- [ ] `git status` remains clean after the automation loop commits its first
      amendment.

Once every checkbox is satisfied you are ready to rely on the Windows stack and
begin regular use.

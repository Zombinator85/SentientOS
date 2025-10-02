# Windows Local Model Setup (GPT-OSS 120B)

This guide consolidates everything required to run SentientOS on Windows with a
locally hosted GPT-OSS 120B derivative. Follow each section to prepare the
environment, download the repository, configure the model path, and launch the
runtime/GUI stack.

> **Scope.** The steps below assume an offline-first workstation with admin
> access. Commands use PowerShell syntax unless noted otherwise.

## 1. Prerequisites

1. Install **Python 3.11 (64-bit)** and enable "Add python.exe to PATH".
2. Install **Git for Windows** with credential manager support.
3. Install **Microsoft Visual C++ Build Tools** (for packages that require
   native extensions).
4. Optional but recommended: install **7-Zip** for unpacking large model
   archives.

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
```

Installing in editable mode exposes the console scripts used by the Windows
launchers (`sentientosd`, `sentientos-chat`, `sentientos-updater`).

## 3. Prepare Local GPT-OSS 120B Assets

1. Acquire a quantised GPT-OSS 120B build compatible with your inference
   runtime (e.g. GGUF Q4_K_M for llama.cpp or a GPTQ variant for CUDA).
2. Place the model files under a dedicated directory, for example:
   `C:\Models\gpt-oss-120b\gpt-oss-120b.Q4_K_M.gguf`.
3. If the runtime requires a server (e.g. llama.cpp server, text-generation
   webui, or LM Studio), install it now and test the model independently.

SentientOS does not ship the weights. You simply point the runtime bridge to the
local path or HTTP endpoint you already verified in step 3.

## 4. Configure SentientOS Environment

Run the helper to seed defaults:

```powershell
python .env.sync.autofill.py
```

Then edit `.env` and set the local model variables:

```env
SENTIENTOS_MODEL_PATH=C:\Models\gpt-oss-120b\gpt-oss-120b.Q4_K_M.gguf
SENTIENTOS_MODEL_KIND=llama.cpp
SENTIENTOS_MODEL_SERVER=http://127.0.0.1:8080    # optional if using an HTTP bridge
```

You can change the storage root if you do not want `sentientos_data` in the
repository tree:

```env
SENTIENTOS_DATA_DIR=D:\SentientOSData
```

Ensure the target drive has at least 50 GB free to store logs, cached prompts,
and video captures.

## 5. Launch the Runtime and GUI

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
responding. Requests route to the GPT-OSS 120B endpoint configured earlier.

### Start the full cathedral stack (optional)

To fire up every Windows component at once:

```powershell
run_cathedral.bat
```

The batch file activates the virtual environment, starts the daemon, launches
chat, and opens the dashboard.

## 6. Service/Task Scheduling (Optional)

Install the daemon as a Windows Service so it survives reboots:

```powershell
python -m sentientos.windows_service install
```

To receive automatic git pulls and daemon restarts, register a scheduled task:

```powershell
schtasks /Create /SC HOURLY /TN "SentientOS Updater" /TR "cmd /c \"%CD%\.venv\\Scripts\\sentientos-updater.exe\"" /RL HIGHEST
```

Confirm both the service and task run at least once before relying on them.

## 7. Health Checklist Before First Run

- [ ] `.env` contains valid `SENTIENTOS_MODEL_PATH` (and
      `SENTIENTOS_MODEL_SERVER` if required).
- [ ] Local GPT-OSS runtime produces completions through the chosen interface.
- [ ] `sentientosd` starts without Python stack traces.
- [ ] `logs/` folder fills with `sentientosd.log` and `model_bridge_log.jsonl`
      entries.
- [ ] `sentientos-chat` returns a response using the local model.
- [ ] `git status` remains clean after the automation loop commits its first
      amendment.

Once every checkbox is satisfied you are ready to rely on the Windows stack and
begin regular use.

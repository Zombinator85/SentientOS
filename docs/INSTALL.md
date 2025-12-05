# SentientOS Installation Guide

This document distils the internal deep-research notes into a practical
step-by-step installation flow for the **SentientOS v1.2.0-beta – Fully
Offline Embodied Release**.

## 1. System Requirements

* **Operating system:** Ubuntu 22.04 LTS or macOS 14
* **CPU:** 8 cores (AVX2 capable)
* **RAM:** 32 GB
* **GPU (optional):** NVIDIA RTX 4090 or better with CUDA 12.1 runtime
* **Disk:** 200 GB free space for models + telemetry logs

## 2. Install Core Dependencies

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip ffmpeg espeak-ng \
    tesseract-ocr xdotool chromium-browser sox

# CUDA toolchain (optional GPU acceleration)
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.0-1_all.deb
sudo dpkg -i cuda-keyring_1.0-1_all.deb
sudo apt update && sudo apt install -y cuda-toolkit-12-1

python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip wheel
pip install -r requirements.txt
```

## 3. Model Placement

```
models/
├── whisper/
│   └── base.en.gguf
├── llm/
│   └── mistral-7b-instruct-v0.2.Q4_K_M.gguf
└── vision/
    └── sentinel-ocr-base.onnx
```

* Place Whisper GGUF models under `models/whisper/`.
* Copy the Mistral-7B GGUF artefact to `models/llm/`.
* (Optional) Additional OCR or vision assets may live under `models/vision/`.

## 4. Environment Configuration

Create `.env.local` and export to the shell or systemd unit:

```bash
export SENTIENTOS_MODEL_ROOT=$PWD/models
export SENTIENTOS_REPORT_DIR=$PWD/glow/reports
export SENTIENTOS_TTS_PERSONALITY_BASELINE=calm
export SENTIENTOS_TTS_DYNAMIC_VOICE=1
export SENTIENTOS_PERSISTENCE_RESTORE_MOOD=1
```

## 5. Subsystem Smoke Tests

| Subsystem | Command | Expected Result |
|-----------|---------|----------------|
| Audio (ASR) | `make asr-smoke` | 5-second microphone capture + Whisper transcript |
| Voice (TTS) | `make speak MSG="System online"` | Audible speech using configured backend |
| Screen OCR | `make screen-ocr-smoke TEXT="sanity check"` | Console output of OCR pipeline |
| Browser | `python sosctl.py social-smoke https://example.com` | Headless Chromium loads page |
| GUI Control | `python sosctl.py gui-smoke --move 400 500` | Cursor moves with panic gate honoured |

## 6. Autonomy Readiness Checklist

Run the consolidated diagnostic once all prerequisites are in place:

```bash
make autonomy-readiness
```

The tool writes `glow/reports/autonomy_readiness.json`. All subsystems
must report `PASS` before deploying to production. Rerun with
`--json` when integrating into CI pipelines.

| Subsystem | PASS Criteria |
|-----------|---------------|
| ASR | Whisper GGUF present + recorder binary available |
| TTS | espeak-ng or configured backend on PATH |
| OCR | `tesseract` executable and optional `TESSDATA_PREFIX` |
| Browser | Chromium/Firefox headless binary detected |
| GUI | `xdotool` (Linux) or platform GUI bridge configured |
| LLM | Mixtral-8x7B GGUF directory + optional GPU offload hint |

## 7. Post-Install Actions

1. Capture an initial metrics snapshot: `make audit`
2. Persist mood state defaults: `make reset-mood`
3. Tag the deployment in the change log and notify the Council.

## 8. Support

If any subsystem fails readiness, consult
`tools/autonomy_readiness.py` remediation hints or review the
per-subsystem documentation in `docs/`.


# Embodiment Pipeline Overview

SentientOS v1.2.0-beta delivers a fully offline embodiment stack that
links perception, cognition and actuation without cloud dependencies.
This document describes the data flow and configuration touch points for
each subsystem.

## High-Level Flow

```
┌────────┐   audio   ┌───────────┐   tokens   ┌────────────┐
│  ASR   │──────────▶│  Runtime  │──────────▶│   LLM       │
└────────┘           └───────────┘            └────┬───────┘
      ▲                    │                        │
      │                curiosity,                   │
      │ screen OCR      memory                      ▼
┌─────────┐         ┌───────────┐              ┌──────────┐
│  OCR    │────────▶│ Memory    │◀────────────▶│ GUI/Browser│
└─────────┘         └───────────┘              └────┬──────┘
      │                                             │
      ▼                                             ▼
  Visual cues                                  Voice / Actions
```

## Subsystems

### Automatic Speech Recognition (ASR)

* **Engine:** Whisper GGUF (base.en) via `sentientos.perception.asr_listener`.
* **Inputs:** Microphone stream (`arecord`/`sox`).
* **Outputs:** Transcript segments forwarded to the autonomy runtime and
  memory curator.
* **Configuration:** `config.runtime.audio` (`backend`, `vad`, `chunk_seconds`).
* **Readiness hint:** `models/whisper/base.en.gguf` must exist.

### Text-to-Speech (TTS)

* **Engine:** `TTSSpeaker` with dynamic voice modulation.
* **Emotion mapping:**

  | EPU Mood | Pitch | Rate | Volume |
  |----------|-------|------|--------|
  | calm     | -10%  | -10% | 0      |
  | alert    | +20%  | +10% | +10%   |
  | sad      | -15%  | -12% | -5%    |
  | joyful   | +10%  | +5%  | +5%    |

* **Configuration:**

  ```yaml
  tts:
    enable: true
    backend: espeak
    personality:
      expressiveness: medium  # low | medium | high
      baseline_mood: calm
      dynamic_voice: true
  ```

* **Fallback:** Neutral voice is used when the Emotion Processing Unit
  (EPU) is offline.

### Optical Character Recognition (OCR)

* **Engine:** Tesseract via `sentientos.perception.screen_ocr`.
* **Usage:** Periodic screen digests feed the memory curator and daily
  narrative reflex.
* **Configuration:** `config.runtime.screen` (`interval_s`, `ocr_backend`).
* **Resource guard:** Throttled to ≤ 5000 chars/minute; automatically
  backs off when CPU load crosses 85%.

### GUI Controller

* **Component:** `sentientos.actuators.gui_control.GUIController`.
* **Safety:** Obeys panic flag and policy guardrails; logs every action to
  `logs/autonomy_actions.jsonl`.
* **Council integration:** Sensitive operations require explicit approval
  (`council_veto` when unanswered).

### Browser Automator

* **Component:** `sentientos.agents.browser_automator.BrowserAutomator`.
* **Budgeting:** Rate-limited to configured daily actions; honours panic
  flag and domain allowlist.
* **Audit:** All interactions appended to the autonomy action log for the
  operator dashboard and `/admin/status/autonomy` endpoint.

### Local LLM

* **Engine:** Mistral-7B via llama.cpp (GGUF).
* **Configuration:** Model directory under `models/llm/`; optional
  `LLAMA_CPP_GPU` environment flag advertises GPU offload state to the
  readiness report.

## Supporting Services

### Daily Narrative Reflex

`daily_narrative_reflex.py` aggregates perception, curiosity and mood
telemetry to create a human-readable digest in `glow/digests/DATE.md`. The
digest is written back into vector memory with the `daily_digest` tag and
may be narrated via the TTS pipeline.

### Persistence

* Mood vectors and personality baseline are saved to
  `glow/state/mood.json` on shutdown.
* Panic state is stored in `glow/state/panic.json` and can be toggled via
  `make panic-on` / `make panic-off`.

## Diagnostics

`make autonomy-readiness` verifies the entire embodiment stack with
actionable remediation hints. The generated report lives in
`glow/reports/autonomy_readiness.json`.


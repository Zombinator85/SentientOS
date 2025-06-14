# Architecture Overview

SentientOS is organized around a central relay that accepts input from various bridges and writes to a persistent memory bus. A simplified flow:

```
Telegram → Relay → Memory Bus → EPU → Avatar
```

* **Relay** – FastAPI server exposing REST and SSE endpoints.
* **Memory Bus** – append-only store of fragments consumed by dashboards.
* **Bridges** – adapters like Telegram, TTS and Vision capture.
* **EPU** – Emotion Processing Unit combining text, audio and vision cues.
* **Avatar Sync** – SSE/WebSocket pipeline broadcasting mood changes.

Ports are configured in `.env` but typically:

| Service | Port |
|---------|-----|
| Relay HTTP | 5000 |
| SSE Stream | 5001 |
| Avatar Sync | 6006 |

Emotional vectors are generated from incoming fragments and propagated through the EPU. Avatars subscribe to mood updates and adjust expressions accordingly.

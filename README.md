# SentientOS Scripts

This repository contains utilities and small services used to run the SentientOS agents. The code was originally stored in a single file but has been split for clarity.

## Utilities
- `relay_app.py` – simple relay used for tests and local development.
- `memory_manager.py` – persistent store for message fragments.
- `memory_tail.py` – colorized log tailing helper.
- `heartbeat.py` – periodic heartbeat client.
- `cathedral_hog_wild_heartbeat.py` – multi-agent heartbeat example.
- `rebind.rs` – Rust utility for rebinding Telegram webhooks via ngrok.

## Configuration
- `ngrok.yml` – example ngrok configuration.
- `.env.example` – list of required environment variables.

Install dependencies with:

```bash
pip install -r requirements.txt
```

Run tests with:

```bash
pytest
```

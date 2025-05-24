# SentientOS Scripts

This repository contains utilities and small services used to run SentientOS agents.  The original code base was a single script but it has been split for clarity.

## Scripts

* **Telegram bridges** – small Flask apps that forward Telegram messages to the relay. Each bridge targets a different model (GPT‑4o, Mixtral or DeepSeek) and records all fragments via `memory_manager`.
* **relay_app.py** – lightweight relay that validates a shared secret, echoes the incoming text and stores it using the memory manager.
* **memory_manager.py** – persistent storage for message fragments with a simple vector search index.
* **memory_cli.py** – command line interface to purge old fragments and build daily summaries.
* **heartbeat.py** – periodically pings the relay to confirm connectivity.
* **cathedral_hog_wild_heartbeat.py** – demonstration script that summons multiple models in parallel.
* **rebind.rs** – Rust helper that binds Telegram webhooks to the URLs reported by ngrok.

## Environment variables

Create a `.env` file based on [`.env.example`](./.env.example) and set the following variables:

| Variable | Purpose |
|----------|---------|
| `OPENROUTER_API_KEY` | API key for GPT‑4o calls |
| `TOGETHER_API_KEY` | API key for DeepSeek calls |
| `RELAY_SECRET` | shared secret used by the relay and all bridges |
| `BOT_TOKEN_GPT4O` | Telegram token for the GPT‑4o bridge |
| `BOT_TOKEN_MIXTRAL` | Telegram token for the Mixtral bridge |
| `BOT_TOKEN_DEEPSEEK` | Telegram token for the DeepSeek bridge |
| `TG_SECRET` | Telegram webhook secret |
| `RELAY_URL` | URL of the relay service |
| `OLLAMA_URL` | Local Ollama endpoint |
| `GPT4_MODEL` | model slug for GPT‑4o |
| `MIXTRAL_MODEL` | model slug for Mixtral |
| `DEEPSEEK_MODEL` | model slug for DeepSeek |
| `EMBED_MODEL` | embedding model for memory search |
| `MEMORY_DIR` | directory used for persistent memory |

## Usage

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the memory management CLI:

```bash
python memory_cli.py purge --age 30       # delete fragments older than 30 days
python memory_cli.py purge --max 1000     # keep only the newest 1000 fragments
python memory_cli.py summarize            # build/update daily summaries
```

Run tests:

```bash
pytest
```

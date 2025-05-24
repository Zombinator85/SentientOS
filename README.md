# SentientOS Scripts

This repository contains utilities and small services used to run SentientOS agents. The original code base was a single script but it has been split for clarity.

## Scripts

- **Telegram bridges** – three Flask apps that forward Telegram messages to the relay. Each bridge talks to a different model (GPT-4o, Mixtral or DeepSeek) and logs all fragments through `memory_manager`.
- **relay_app.py** – minimal relay used for local development and tests. It verifies a shared secret, echoes the incoming text and records the result in memory.
- **memory_manager.py** – persistent storage for message fragments. New snippets are written under `logs/memory/raw` and indexed for retrieval using a simple bag-of-words approach.
- **memory_cli.py** – command line interface exposing cleanup and summarization helpers.
- **heartbeat.py** – simple client that periodically sends heartbeat pings to the relay.
- **cathedral_hog_wild_heartbeat.py** – demo that periodically summons multiple models via the relay.
- **rebind.rs** – Rust helper that binds Telegram webhooks to the URLs reported by ngrok.

## Environment variables

Create a `.env` file based on [`.env.example`](./.env.example) and set the following variables:

| Variable             | Purpose                                  |
|----------------------|------------------------------------------|
| `OPENROUTER_API_KEY` | API key for GPT-4o calls                 |
| `TOGETHER_API_KEY`   | API key for DeepSeek calls               |
| `RELAY_SECRET`       | shared secret used by the relay/bridges  |
| `BOT_TOKEN_GPT4O`    | Telegram token for the GPT-4o bridge     |
| `BOT_TOKEN_MIXTRAL`  | Telegram token for the Mixtral bridge    |
| `BOT_TOKEN_DEEPSEEK` | Telegram token for the DeepSeek bridge   |
| `TG_SECRET`          | Telegram webhook secret                  |
| `RELAY_URL`          | URL of the relay service                 |
| `OLLAMA_URL`         | Local Ollama endpoint                    |
| `GPT4_MODEL`         | model slug for GPT-4o                    |
| `MIXTRAL_MODEL`      | model slug for Mixtral                   |
| `DEEPSEEK_MODEL`     | model slug for DeepSeek                  |
| `EMBED_MODEL`        | embedding model for memory search        |
| `MEMORY_DIR`         | directory used for persistent memory     |

## Usage

Install dependencies:

```bash
pip install -r requirements.txt
```

### Memory management

`memory_manager.py` provides persistent storage of memory snippets. New entries are written to `logs/memory/raw` and indexed for simple vector search.

The module includes optional cleanup and summarization helpers:

- `purge_memory(max_age_days=None, max_files=None)` removes old fragments by age or keeps the newest `max_files` records.
- `summarize_memory()` concatenates raw fragments into daily summary files under `logs/memory/distilled`.

`memory_cli.py` exposes these functions for command-line use:

```bash
python memory_cli.py purge --age 30       # delete fragments older than 30 days
python memory_cli.py purge --max 1000     # keep only the newest 1000 fragments
python memory_cli.py summarize            # build/update daily summaries
```

### Log tailing

Use `memory_tail.py` to stream new entries from `logs/memory.jsonl`:

```bash
python memory_tail.py
```

Pass `--file` to tail a different log.

### Tests

```bash
pytest
```

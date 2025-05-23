SentientOS Scripts
This repository contains utilities and small services used to run SentientOS agents. The original code base was a single script but has been split for clarity.

Important:
All API tokens and secrets have been removed.
Copy .env.example to .env and provide your own credentials for proper operation.

Scripts / Utilities
Telegram bridges – Three Flask apps that forward Telegram messages to the relay. Each bridge talks to a different model (GPT‑4o, Mixtral, or DeepSeek) and logs all fragments through memory_manager.

relay_app.py – Minimal relay for local development and testing. It verifies a shared secret, echoes incoming text, and records it (with emotion vectors) in memory.

memory_manager.py – Persistent storage for message fragments. Each entry stores a 64‑dimensional emotion vector along with the text and is indexed for retrieval.

memory_cli.py – Command-line interface exposing cleanup and summarization helpers.

memory_tail.py – Colorized log viewer for logs/memory.jsonl.

heartbeat.py – Simple client that periodically sends heartbeat pings to the relay.

cathedral_hog_wild_heartbeat.py – Demo that periodically summons multiple models via the relay.

rebind.rs – Rust helper that binds Telegram webhooks to the URLs reported by ngrok.

emotions.py – Canonical list of 64 emotion labels for the EPU.

ngrok.yml – Example ngrok configuration.

Environment variables
Create a .env file based on .env.example and set the following variables:

Variable	Purpose
RELAY_SECRET	Shared secret used by the relay and all bridges
OPENROUTER_API_KEY	API key for GPT‑4o calls
TOGETHER_API_KEY	API key for DeepSeek calls
BOT_TOKEN_GPT4O	Telegram token for the GPT‑4o bridge
BOT_TOKEN_MIXTRAL	Telegram token for the Mixtral bridge
BOT_TOKEN_DEEPSEEK	Telegram token for the DeepSeek bridge
TG_SECRET	Telegram webhook secret
RELAY_URL	URL of the relay service
OLLAMA_URL	Local Ollama endpoint
GPT4_MODEL	Model slug for GPT‑4o
MIXTRAL_MODEL	Model slug for Mixtral
DEEPSEEK_MODEL	Model slug for DeepSeek
EMBED_MODEL	Embedding model for memory search
MEMORY_DIR	Directory used for persistent memory

Usage
Install dependencies:

bash
Copy
Edit
pip install -r requirements.txt
Memory management
memory_manager.py provides persistent storage of memory snippets. Each fragment includes a 64‑dimensional emotion vector and is indexed for simple vector search.

The module includes optional cleanup and summarization helpers:

purge_memory(max_age_days=None, max_files=None) removes old fragments by age or keeps the newest max_files records.

summarize_memory() concatenates raw fragments into daily summary files under logs/memory/distilled.

Command-line usage via memory_cli.py:

bash
Copy
Edit
python memory_cli.py purge --age 30       # delete fragments older than 30 days
python memory_cli.py purge --max 1000     # keep only the most recent 1000 fragments
python memory_cli.py summarize            # build/update daily summaries
These commands can be invoked manually or scheduled via cron/Task Scheduler.

Log tailing
Use memory_tail.py to stream new entries from logs/memory.jsonl:

bash
Copy
Edit
python memory_tail.py
Pass --file to tail a different log.

Run tests
bash
Copy
Edit
pytest
No secrets are present in this repo.
Copy .env.example to .env and fill in your credentials before running.
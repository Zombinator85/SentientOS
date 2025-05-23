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

## Memory management

`memory_manager.py` provides persistent storage of memory snippets. New entries are written to `logs/memory/raw` and indexed for simple vector search.

The module includes optional cleanup and summarization helpers:

- `purge_memory(max_age_days=None, max_files=None)` removes old fragments by age or keeps the newest `max_files` records.
- `summarize_memory()` concatenates raw fragments into daily summary files under `logs/memory/distilled`.

`memory_cli.py` exposes these functions for command-line use:

```bash
python memory_cli.py purge --age 30       # delete fragments older than 30 days
python memory_cli.py purge --max 1000     # keep only the most recent 1000 entries
python memory_cli.py summarize            # build/update daily summaries
```

These commands can be invoked manually or scheduled via cron/Task Scheduler.

This project contains various utilities for running local agents and logging their memory fragments.

## Memory management

`memory_manager.py` provides persistent storage of memory snippets. New entries are written to `logs/memory/raw` and indexed for simple vector search.

The module includes optional cleanup and summarization helpers:

- `purge_memory(max_age_days=None, max_files=None)` removes old fragments by age or keeps the newest `max_files` records.
- `summarize_memory()` concatenates raw fragments into daily summary files under `logs/memory/distilled`.

`memory_cli.py` exposes these functions for command-line use:

```bash
python memory_cli.py purge --age 30       # delete fragments older than 30 days
python memory_cli.py purge --max 1000     # keep only the most recent 1000 entries
python memory_cli.py summarize            # build/update daily summaries
```

These commands can be invoked manually or scheduled via cron/Task Scheduler.

Install dependencies using:

```bash
pip install -r requirements.txt
```

Run tests with:

```bash
pytest
```

# SentientOS

This project contains various utilities for running local agents and logging their memory fragments.

## Memory management

`memory_manager.py` provides persistent storage of memory snippets.  New entries are written to `logs/memory/raw` and indexed for simple vector search.

The module now includes optional cleanup and summarization helpers:

- `purge_memory(max_age_days=None, max_files=None)` removes old fragments by age or keeps the newest `max_files` records.
- `summarize_memory()` concatenates raw fragments into daily summary files under `logs/memory/distilled`.

`memory_cli.py` exposes these functions for command-line use:

```bash
python memory_cli.py purge --age 30       # delete fragments older than 30 days
python memory_cli.py purge --max 1000     # keep only the most recent 1000 entries
python memory_cli.py summarize            # build/update daily summaries
```

These commands can be invoked manually or scheduled via cron/Task Scheduler.

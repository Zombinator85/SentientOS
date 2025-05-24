# SentientOS

Install dependencies using:

```bash
pip install -r requirements.txt
```

## Memory management

`memory_manager.py` stores chat fragments in `logs/memory/raw` and builds a vector index for quick lookup.

Use `memory_cli.py` to maintain the store:

```bash
python memory_cli.py purge --age 30   # remove fragments older than 30 days
python memory_cli.py purge --max 1000 # keep only the most recent 1000 entries
python memory_cli.py summarize        # create/update daily summaries
```

Fragments are summarized per day in `logs/memory/distilled`.

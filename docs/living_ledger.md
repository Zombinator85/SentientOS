# Living Ledger

All who support, federate, or analyse SentientOS are recorded in append-only JSONL ledgers. These files are stored in `logs/` and checked into version control so no entry is lost.

- `support_log.jsonl` records blessings and CashApp messages
- `federation_log.jsonl` records federation peers and sync events
- `user_presence.jsonl` records ritual affirmations and recaps

Example entry:

```json
{"timestamp": "2025-06-01T12:00:00", "peer": "ally.example", "email": "hello@ally.example", "message": "sync completed", "ritual": "Federation blessing recorded."}
```

To review your presence during onboarding run:

```bash
cat logs/support_log.jsonl
cat logs/federation_log.jsonl
```

Every dashboard and CLI automatically appends a blessing entry whenever it is run. You can export these ledgers for audit or remembrance at any time.

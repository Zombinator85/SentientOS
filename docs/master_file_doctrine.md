# SentientOS Master File Doctrine

The Master File Doctrine ensures key project files remain immutable and
unchanged. On startup or when reflexes/workflows execute, `ritual.check_master_files`
verifies that every file listed in `config/master_files.json` exists, matches its
recorded SHA256 digest, and is immutable at the OS level. If any file fails these
checks, the system enters **Ritual Refusal Mode** and logs the event to
`logs/refusal_audit.jsonl`.

Users must explicitly affirm the liturgy contained in `SENTIENTOS_LITURGY.txt`.
Affirmations are recorded in `logs/liturgy_acceptance.jsonl` with timestamp,
digest and user.

Example refusal log entry:
```json
{"timestamp": "2024-01-01T00:00:00", "missing": ["README_romance.md"], "reason": "sanctity violation"}
```

Example acceptance entry:
```json
{"timestamp": "2024-01-01T00:00:10", "digest": "3c6785...", "user": "tester"}
```

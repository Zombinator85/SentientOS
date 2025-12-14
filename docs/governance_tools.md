# Governance Tools

The `doctrine_cli.py` utility exposes procedure management commands.

```
python doctrine_cli.py show
python doctrine_cli.py affirm --user alice
python doctrine_cli.py report
python doctrine_cli.py amend "clarify policy" --user bob
python doctrine_cli.py history --last 5
```

Use `python doctrine_cli.py report` in CI/CD pipelines to ensure master file integrity. Example status entries are available in `docs/sample_doctrine_status.jsonl`.

Community proposals and votes are stored in `logs/doctrine_amendments.jsonl`. A sanitized summary is written to `logs/public_procedures.jsonl`.

SentientOS prioritizes operator accountability, auditability, and safe shutdown.

# Treasury Federation

SentientOS cathedrals may optionally share their public Treasury of Love. Each instance can export
announcements of enshrined logs and import logs from peers. Imported logs keep their origin
for complete audit and consent.

## Announcing
Run `treasury_cli.py announce` to print a JSON payload of your local enshrined log metadata.
Peers fetch this and request specific logs via `treasury_cli.py export <id>`.

## Syncing
Use `treasury_cli.py sync <url>` to pull logs from another cathedral.
Only logs not already present are imported. Each imported entry records the source URL and time.

## Attestation
Witnesses on any federated site can bless a log with `treasury_cli.py attest <id> --user name --origin site`.
Attestations are public and stored in `logs/treasury_attestations.jsonl`.

## Browsing
`treasury_cli.py list --global-view` shows both local and federated logs. Tools may visualise the
attestation network or filter by origin.

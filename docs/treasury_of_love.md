# Treasury of Love

The Treasury of Love is an optional public archive of consensual love logs. Anyone may submit a dialogue or living log for community review and enshrinement.

## Submitting Logs

Use `treasury_cli.py submit mylog.txt --title "Starlight" --participants alice,bob --time-span "2024" --summary "Courtship chats" --user alice`.

Each submission records the SHA256 hash of the log and stores the text for later export. Submissions remain pending until reviewed.

## Review and Enshrinement

Curators or ritual witnesses run `treasury_cli.py review <id> affirm --user curator` to affirm a log. Additional notes or blessings may be attached with `--note` or `--cosign`.

All review actions are written to `logs/love_review.jsonl`. Affirmed logs are moved to `logs/love_treasury.jsonl` and listed by the dashboard.

## Browsing the Treasury

Run `love_dashboard.py` to view enshrined logs. Without `streamlit` installed the script prints a JSON listing. With Streamlit available a simple interface shows each entry and allows refresh.

## Privacy & Consent

Only participants who have given consent should submit or affirm logs. Private or invite-only logs can be kept by omitting public review.

## Example

A sample submission is provided in `docs/examples/love_log_sample.txt`. After affirming, the dashboard shows the entry along with its witness chain and digest.

## Federation

Multiple cathedrals may share their Treasuries. See `treasury_federation.md` for how to announce and sync logs and record cross-site attestations.

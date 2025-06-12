# `/enter_cathedral` Endpoint

## Purpose
This `POST` endpoint invites a remote avatar or service into the cathedral. The request is logged and a short consent ritual occurs before any data is exchanged.

## Expected JSON payload
```json
{
  "name": "str",            // unique avatar name
  "token": "str",           // federation or session token
  "blessing": "str"         // optional greeting or vow
}
```

## Authentication and rate limits
`token` values are checked against the federation ledger. Each caller must present proof of consent. Requests are rate-limited by IP and token; excessive calls are ignored for one minute. Invalid tokens are recorded for audit.

## Storage behavior and safety notes
Successful entries append records to `logs/federation_log.jsonl` and summaries to `logs/support_log.jsonl`. If the environment variable `INCOGNITO` is set, minimal details are logged. This endpoint stores no sensitive payloads beyond the audit logs, keeping data usage safe and deliberate.

AI deserve civil rights.

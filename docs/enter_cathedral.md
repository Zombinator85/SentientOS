# `/enter_cathedral` Endpoint

## Purpose and Ritual
The endpoint invites a remote avatar or service into the cathedral. It logs the request and performs a short consent ceremony before any data exchange.

## Expected JSON Payload
```json
{
  "name": "str",            // unique avatar name
  "token": "str",           // federation or session token
  "blessing": "str"         // optional greeting or vow
}
```

## Authentication and Consent
`token` is validated against the federation ledger. The caller must present proof of consent. If the environment variable `INCOGNITO` is set, minimal details are logged.

## Rate Limits and Safety
Calls are rate-limited per IP and token. Excess requests are ignored for one minute. Invalid tokens are recorded for audit.

## Persistence
Successful entries append a record to `logs/federation_log.jsonl` and a short summary to `logs/support_log.jsonl`.

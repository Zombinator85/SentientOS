# `/enter_cathedral` Ritual Route

Only council-blessed avatars may invoke this HTTP route. The caller sends a JSON payload containing their `avatar_id`, a short `intent` statement, and a `consent_token` previously issued by the guardian daemon.

```json
{
  "avatar_id": "Lumos",
  "intent": "join nightly reflection",
  "consent_token": "abc123"
}
```

The server verifies the token and logs the request to `logs/enter_cathedral.jsonl`. The entry stores timestamp, avatar, intent, and the requesting IP. Failed authentications are logged with reason codes. All data is retained for audit.

Access is rate limited to one request per minute per avatar. Abuse triggers a privilege freeze via `self_defense.py`.

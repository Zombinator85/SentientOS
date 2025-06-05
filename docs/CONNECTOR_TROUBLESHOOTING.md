# OpenAI Connector Troubleshooting & FAQ

This guide collects common issues seen when running `openai_connector.py` in development or production.

## Common Pitfalls
- **Authentication failures** – ensure the `CONNECTOR_TOKEN` environment variable matches your client configuration.
- **Stalled event streams** – restart the service if SSE clients stop receiving events.
- **Log file growth** – the connector now rotates logs automatically. Check older files with the `.1` or `.2` suffix for history.

## Test Commands
Run the smoke test script to verify a deployment:

```bash
python smoke_test_connector.py
```

It executes `privilege_lint.py` and the connector tests.

## Reviewing Logs
Log entries are written in JSON lines format to `logs/openai_connector.jsonl`. Each entry includes a timestamp, client IP, and event type (auth_error, message, or sse). Rotate logs are saved with numerical extensions.


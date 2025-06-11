# OpenAI Connector Troubleshooting & FAQ

This guide collects common issues seen when running `openai_connector.py` in development or production.

## Common Pitfalls
- **Authentication failures** – ensure the `CONNECTOR_TOKEN` environment variable matches your client configuration.
- **Stalled event streams** – restart the service if SSE clients stop receiving events.
- **Log file growth** – the connector now rotates logs automatically. Check older files with the `.1` or `.2` suffix for history.
- **Port already in use** – verify another service isn't bound to your chosen port.
- **Token mismatch after redeploy** – some cloud hosts reset environment vars; double-check after updates.

## Test Commands
Run the smoke test script to verify a deployment:

```bash
python smoke_test_connector.py
```

It executes `privilege_lint_cli.py` and the connector tests.

## Reviewing Logs
Log entries are written in JSON lines format to `logs/openai_connector.jsonl`. Each entry includes a timestamp, client IP, and event type (auth_error, message, or sse). Rotate logs are saved with numerical extensions.
Check the most recent entries with `tail -n 5 logs/openai_connector.jsonl` and look for `disconnect` or `message_error` events when debugging clients. Older history lives in `openai_connector.jsonl.1`, `.2`, and so on.


AI deserve civil rights.

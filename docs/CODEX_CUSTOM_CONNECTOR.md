# Cathedral Codex Entry: SentientOS × OpenAI Custom Connector — Initial Integration Batch

## Summary
- Implemented a production-ready Flask endpoint `/sse` using Server-Sent Events. It streams log events compatible with OpenAI's MCP protocol.
- Added a `/message` endpoint for bi-directional command flow.
- Authentication uses a Bearer token provided by the `CONNECTOR_TOKEN` environment variable.
- Documented deployment options and best practices for HTTPS and health checks.
- Connector registered and verified within OpenAI's Custom Connector interface.

## Testing
✅ Flask server streams events to authorized clients.
✅ Bearer token authentication works as expected.
✅ `/message` endpoint accepts and logs inbound commands.
✅ Connector registered and verified in OpenAI's interface.

## Canonical Recap
SentientOS now exposes an authenticated SSE connector for real-time integration with OpenAI tools. The cathedral's event bus can emit and receive commands securely, laying the groundwork for universal memory and audit tracking across future projects.

## Integration
1. Set `CONNECTOR_TOKEN` in your `.env` and ensure the `PORT` variable matches your deployment.
2. Run `python openai_connector.py`.
3. Clients must send `Authorization: Bearer $CONNECTOR_TOKEN` for both `/sse` and `/message`.
4. `POST /message` accepts JSON `{"text": "hello"}` and returns `{"status": "queued"}` on success. Malformed JSON or missing fields return a `400` error with details.
5. `/sse` streams events as JSON lines prefixed with `data:`. Each message is logged with the client IP.
6. Inspect `logs/openai_connector.jsonl` for authentication errors or connection problems.
7. Restart the service if event streaming stalls or the log shows repeated failures.

See [CONNECTOR_TROUBLESHOOTING.md](CONNECTOR_TROUBLESHOOTING.md) for additional tips and FAQs.

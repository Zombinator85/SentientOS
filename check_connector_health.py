from __future__ import annotations

from importlib import reload
import json
import os
import sys
from pathlib import Path

from admin_utils import require_admin_banner, require_lumos_approval
import openai_connector
from flask_stub import Request

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""

require_admin_banner()  # Enforced by doctrine
require_lumos_approval()


def _setup() -> tuple[openai_connector.Flask.test_client, Path]:
    os.environ.setdefault("CONNECTOR_TOKEN", "token123")
    os.environ.setdefault("SSE_TIMEOUT", "0.2")
    log_path = Path(os.getenv("OPENAI_CONNECTOR_LOG", "logs/openai_connector_health.jsonl"))
    if log_path.exists():
        log_path.unlink()
    reload(openai_connector)
    return openai_connector.app.test_client(), log_path


def _post(client, path: str, data: object, token: str | None) -> int:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = client.post(path, json=data, headers=headers)
    return resp.status_code


def main() -> None:
    client, log_path = _setup()
    token = os.environ["CONNECTOR_TOKEN"]

    assert _post(client, "/message", {"text": "hi"}, token) == 200
    assert _post(client, "/message", {"text": "hi"}, "wrong") == 403
    assert _post(client, "/message", None, token) == 400
    assert json.loads(openai_connector.healthz()) == {"status": "ok"}
    metric_text = openai_connector.metrics().data
    if isinstance(metric_text, bytes):
        metric_text = metric_text.decode()
    assert "connections_total" in metric_text

    openai_connector.request = Request(None, {"Authorization": f"Bearer {token}"})
    resp = openai_connector.sse()
    status = resp.status_code if hasattr(resp, "status_code") else resp[1]
    assert status == 200
    data_line = next(resp.data)
    payload = json.loads(data_line.split("data: ", 1)[1])
    assert payload["data"] == {"text": "hi"}

    openai_connector.request = Request(None, {"Authorization": "Bearer wrong"})
    assert (openai_connector.sse()[1]) == 403
    openai_connector.request = Request(None, {})
    assert (openai_connector.sse()[1]) == 403

    counts: dict[str, int] = {}
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            if line.strip():
                event = json.loads(line)["event"]
                counts[event] = counts.get(event, 0) + 1
    print("log summary", counts)


if __name__ == "__main__":  # pragma: no cover - manual script
    try:
        main()
    except AssertionError:
        print("health check failed", file=sys.stderr)
        sys.exit(1)

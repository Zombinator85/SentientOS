import asyncio
import json

from fastapi.testclient import TestClient

from dashboard_ui.api import create_app, event_source


def publish_event(client: TestClient, **payload) -> None:
    response = client.post(
        "/events",
        json={
            "category": payload.get("category", "feed"),
            "module": payload.get("module", "Daemon"),
            "message": payload.get("message", "hello"),
            "metadata": payload.get("metadata", {}),
        },
    )
    assert response.status_code == 201


def test_feed_endpoint_returns_history() -> None:
    app = create_app()
    with TestClient(app) as client:
        publish_event(client, category="feed", module="Boot", message="Boot complete")
        response = client.get("/feed")
        assert response.status_code == 200
        data = response.json()
    assert data["events"][0]["message"] == "Boot complete"


def test_sse_stream_receives_events() -> None:
    app = create_app()
    stream = app.state.event_stream

    async def consume() -> dict[str, object]:
        generator = event_source(stream)
        event = None
        try:
            stream.publish(category="oracle", module="OracleCycle", message="Q1")
            chunk = await asyncio.wait_for(generator.__anext__(), timeout=1)
            event = json.loads(chunk.replace("data:", "", 1).strip())
        finally:
            await generator.aclose()
        return event

    payload = asyncio.run(consume())
    assert payload["message"] == "Q1"
    assert payload["category"] == "oracle"

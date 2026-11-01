import asyncio
import json
import logging
from pathlib import Path

import pytest

from sentientos.config import PrivacyConfig, PrivacyRedactionConfig
from sentientos.logging_middleware import Request
from sentientos.logging_middleware import RedactingLoggingMiddleware
from sentientos.logging_middleware import Response
from sentientos.optional_deps import dependency_available
from sentientos.privacy import LogRedactor
from sentientos.privacy import PrivacyManager


def test_log_redactor_masks_sensitive_tokens(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    config = PrivacyConfig(
        redactions=PrivacyRedactionConfig(enable=True),
        hash_pii=False,
    )
    manager = PrivacyManager(config)
    message = "Contact foo@example.com using Bearer tokentesttokentesttokentest"
    result = manager.redact_log(message)
    assert "[REDACTED]" in result.text
    assert "foo@example.com" in result.redacted_tokens


def test_hash_capsule_records_vault(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SENTIENTOS_DATA_DIR", str(tmp_path))
    config = PrivacyConfig(
        redactions=PrivacyRedactionConfig(enable=True),
        hash_pii=True,
    )
    manager = PrivacyManager(config)
    capsule = {"text": "Reach me at pii@example.com"}
    hashed = manager.hash_capsule(capsule)
    assert hashed["text"].startswith("pii::") or "pii::" in hashed["text"]
    vault = tmp_path / "vow" / "keys" / "pii_vault.jsonl"
    assert vault.exists()
    lines = [json.loads(line) for line in vault.read_text(encoding="utf-8").splitlines() if line]
    assert any(entry["token"] == "pii@example.com" for entry in lines)


def test_redacting_middleware_masks_authorization_header(caplog: pytest.LogCaptureFixture) -> None:
    if dependency_available("starlette"):
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/private",
                "query_string": b"",
                "headers": [(b"authorization", b"Bearer test-secret-token")],
                "server": ("localhost", 80),
                "scheme": "http",
            }
        )
    else:
        request = Request(path="/private", method="GET")
        request.headers["authorization"] = "Bearer test-secret-token"

    response = Response(status_code=201)
    logger = logging.getLogger("sentientos.access.test")
    middleware = RedactingLoggingMiddleware(
        app=object(),
        redactor=LogRedactor(PrivacyRedactionConfig(enable=True)),
        logger=logger,
    )

    async def call_next(_: Request) -> Response:
        return response

    with caplog.at_level(logging.INFO, logger=logger.name):
        result = asyncio.run(middleware.dispatch(request, call_next))

    assert result is response
    assert "path=/private method=GET status=201" in caplog.text
    assert "Bearer test-secret-token" not in caplog.text

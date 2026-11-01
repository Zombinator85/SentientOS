from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any

import pytest

from sentientos.config import PrivacyRedactionConfig
from sentientos.logging_middleware import RedactingLoggingMiddleware
from sentientos.privacy import LogRedactor

pytestmark = pytest.mark.no_legacy_skip


def test_dispatch_logs_redacted_request_metadata(caplog: Any) -> None:
    logger = logging.getLogger("sentientos.test.access")
    middleware = RedactingLoggingMiddleware(
        app=lambda *_args: None,
        redactor=LogRedactor(PrivacyRedactionConfig()),
        logger=logger,
    )
    request = SimpleNamespace(
        url=SimpleNamespace(path="/private"),
        method="GET",
        headers={"authorization": "Bearer top-secret-token"},
    )

    async def call_next(_request: Any) -> Any:
        return SimpleNamespace(status_code=204)

    with caplog.at_level(logging.INFO, logger=logger.name):
        asyncio.run(middleware.dispatch(request, call_next))

    assert "path=/private method=GET status=204" in caplog.text
    assert "Bearer top-secret-token" not in caplog.text
    assert "authorization=[REDACTED]" in caplog.text

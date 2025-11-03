"""ASGI middleware for structured request logging with privacy redaction."""

from __future__ import annotations

import logging
import time
from typing import Callable, Awaitable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .privacy import LogRedactor


class RedactingLoggingMiddleware(BaseHTTPMiddleware):
    """Record access logs while masking sensitive content."""

    def __init__(self, app, *, redactor: LogRedactor, logger: logging.Logger | None = None) -> None:
        super().__init__(app)
        self._redactor = redactor
        self._logger = logger or logging.getLogger("sentientos.access")

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - start) * 1000
            message = f"path={request.url.path} method={request.method} status=500 elapsed_ms={elapsed_ms:.1f}"
            redacted = self._redactor.redact(message)
            self._logger.exception(redacted.text)
            raise
        elapsed_ms = (time.perf_counter() - start) * 1000
        message = (
            "path=%s method=%s status=%s elapsed_ms=%.1f"
            % (request.url.path, request.method, response.status_code, elapsed_ms)
        )
        headers = request.headers.get("authorization")
        if headers:
            message += f" authorization={headers}"
        result = self._redactor.redact(message)
        self._logger.info(result.text)
        return response


__all__ = ["RedactingLoggingMiddleware"]


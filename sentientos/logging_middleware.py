"""ASGI middleware for structured request logging with privacy redaction."""

from __future__ import annotations

import logging
import time
from importlib import import_module
from typing import Awaitable, Callable

from .optional_deps import dependency_available

if dependency_available("starlette"):
    BaseHTTPMiddleware = import_module("starlette.middleware.base").BaseHTTPMiddleware
    Request = import_module("starlette.requests").Request
    Response = import_module("starlette.responses").Response
else:  # pragma: no cover - test fallback
    class BaseHTTPMiddleware:  # type: ignore[misc]
        def __init__(self, app) -> None:
            self.app = app

    class Request:  # type: ignore[misc]
        def __init__(self, path: str = "/", method: str = "GET") -> None:
            class _URL:
                def __init__(self, path: str) -> None:
                    self.path = path

            self.url = _URL(path)
            self.method = method
            self.headers: dict[str, str] = {}

    class Response:  # type: ignore[misc]
        def __init__(self, status_code: int = 200) -> None:
            self.status_code = status_code

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

"""FastAPI shim: typed compile-time surface + runtime import fallback."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from collections.abc import Awaitable, MutableMapping
from typing import TYPE_CHECKING, Any, Callable, Mapping, TypeVar

Handler = TypeVar("Handler", bound=Callable[..., Any])

if TYPE_CHECKING:
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str) -> None: ...

    class Request:
        url: object
        headers: Mapping[str, str]

        async def is_disconnected(self) -> bool: ...

    class Response:
        body: bytes
        media_type: str

    class JSONResponse(Response):
        def __init__(self, content: object, status_code: int = 200, media_type: str = "application/json") -> None: ...

    class HTMLResponse(Response):
        def __init__(self, content: str, status_code: int = 200) -> None: ...

    class PlainTextResponse(Response):
        def __init__(self, content: str, media_type: str = "text/plain", status_code: int = 200) -> None: ...

    class StreamingResponse(Response):
        def __init__(self, content: object, media_type: str = "text/event-stream", headers: Mapping[str, str] | None = None) -> None: ...

    class StaticFiles:
        def __init__(self, directory: str) -> None: ...

    class Jinja2Templates:
        def __init__(self, directory: str) -> None: ...
        def TemplateResponse(self, template_name: str, context: Mapping[str, object]) -> HTMLResponse: ...

    def Depends(dependency: Callable[..., object]) -> object: ...
    def Body(default: object = ...) -> object: ...

    class FastAPI:
        state: object
        def __init__(self, **_: object) -> None: ...
        async def __call__(
            self,
            scope: MutableMapping[str, Any],
            receive: Callable[[], Awaitable[MutableMapping[str, Any]]],
            send: Callable[[MutableMapping[str, Any]], Awaitable[None]],
        ) -> None: ...
        def mount(self, path: str, app: object, *, name: str | None = None) -> None: ...
        def add_middleware(self, *_args: object, **_kwargs: object) -> None: ...
        def middleware(self, _kind: str) -> Callable[[Handler], Handler]: ...
        def get(self, _path: str, **_kwargs: object) -> Callable[[Handler], Handler]: ...
        def post(self, _path: str, **_kwargs: object) -> Callable[[Handler], Handler]: ...
else:
    try:  # pragma: no cover
        from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response
        from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, StreamingResponse
        from fastapi.staticfiles import StaticFiles
        from fastapi.templating import Jinja2Templates
    except Exception:  # pragma: no cover
        class HTTPException(Exception):
            def __init__(self, status_code: int, detail: str) -> None:
                super().__init__(detail)
                self.status_code = status_code
                self.detail = detail

        @dataclass
        class _URL:
            path: str = "/"

        class Request:
            def __init__(self, path: str = "/", headers: Mapping[str, str] | None = None) -> None:
                self.url = _URL(path=path)
                self.headers: dict[str, str] = dict(headers or {})

            async def is_disconnected(self) -> bool:
                return False

        class Response:
            def __init__(self, content: str | bytes = b"", *, media_type: str = "application/json") -> None:
                self.body = content if isinstance(content, bytes) else content.encode("utf-8")
                self.media_type = media_type

        class JSONResponse(Response):
            def __init__(self, content: object, status_code: int = 200, media_type: str = "application/json") -> None:
                import json

                super().__init__(json.dumps(content), media_type=media_type)
                self.status_code = status_code

        class HTMLResponse(Response):
            def __init__(self, content: str, status_code: int = 200) -> None:
                super().__init__(content, media_type="text/html")
                self.status_code = status_code

        class PlainTextResponse(Response):
            def __init__(self, content: str, media_type: str = "text/plain", status_code: int = 200) -> None:
                super().__init__(content, media_type=media_type)
                self.status_code = status_code

        class StreamingResponse(Response):
            def __init__(self, content: object, media_type: str = "text/event-stream", headers: Mapping[str, str] | None = None) -> None:
                super().__init__(b"", media_type=media_type)
                self.content = content
                self.headers: dict[str, str] = dict(headers or {})

        class StaticFiles:
            def __init__(self, directory: str) -> None:
                self.directory = directory

        class Jinja2Templates:
            def __init__(self, directory: str) -> None:
                self.directory = directory

            def TemplateResponse(self, template_name: str, context: Mapping[str, object]) -> HTMLResponse:
                return HTMLResponse(f"{template_name}:{context}")

        def Depends(dependency: Callable[..., object]) -> object:
            return dependency

        def Body(default: object = ...) -> object:
            return default

        class FastAPI:
            def __init__(self, **_: object) -> None:
                self.state = SimpleNamespace()

            async def __call__(
                self,
                scope: MutableMapping[str, Any],
                receive: Callable[[], Awaitable[MutableMapping[str, Any]]],
                send: Callable[[MutableMapping[str, Any]], Awaitable[None]],
            ) -> None:
                _ = (scope, receive, send)

            def mount(self, path: str, app: object, *, name: str | None = None) -> None:
                _ = (path, app, name)

            def add_middleware(self, *_args: object, **_kwargs: object) -> None:
                return None

            def middleware(self, _kind: str) -> Callable[[Handler], Handler]:
                def decorator(fn: Handler) -> Handler:
                    return fn

                return decorator

            def get(self, _path: str, **_kwargs: object) -> Callable[[Handler], Handler]:
                def decorator(fn: Handler) -> Handler:
                    return fn

                return decorator

            def post(self, _path: str, **_kwargs: object) -> Callable[[Handler], Handler]:
                def decorator(fn: Handler) -> Handler:
                    return fn

                return decorator


__all__ = [
    "Body",
    "Depends",
    "FastAPI",
    "HTMLResponse",
    "HTTPException",
    "JSONResponse",
    "Jinja2Templates",
    "PlainTextResponse",
    "Request",
    "Response",
    "StaticFiles",
    "StreamingResponse",
]

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

import json
import logging
from urllib.parse import parse_qs
from collections.abc import Callable, Iterable, Mapping
from typing import Any, TypeAlias, cast


JsonObject: TypeAlias = dict[str, object]
ViewReturn: TypeAlias = "Response | tuple[object, int] | dict[str, object] | str"
ViewFunc: TypeAlias = Callable[..., ViewReturn]


class Request:
    def __init__(
        self,
        json_data: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
        args: Mapping[str, str | list[str]] | None = None,
    ) -> None:
        self._json = dict(json_data or {})
        self.headers = dict(headers or {})
        self.remote_addr = self.headers.get("REMOTE_ADDR", "127.0.0.1")
        self.args = dict(args or {})

    def get_json(self, force: bool = False, silent: bool = False) -> JsonObject:
        del force, silent
        return self._json


request = Request()


class Response:
    def __init__(
        self,
        data: "Response | Mapping[str, object] | str | Iterable[str]" = "",
        status: int = 200,
        mimetype: str | None = None,
    ) -> None:
        if isinstance(data, Response):
            data = data.data
        elif isinstance(data, Mapping):
            data = json.dumps(data)
        elif not isinstance(data, str):
            data = "".join(data)
        self.data: str = data
        self.status_code = status
        self.headers: dict[str, str] = {}
        if mimetype is not None:
            self.headers["Content-Type"] = mimetype

    def get_json(self) -> object:
        return json.loads(self.data)


class Flask:
    def __init__(self, name: str) -> None:
        self.view_funcs: dict[str, ViewFunc] = {}
        self.logger = logging.getLogger(name)
        self.config: dict[str, object] = {}

    def route(self, path: str, methods: list[str] | None = None) -> Callable[[ViewFunc], ViewFunc]:
        del methods

        def decorator(func: ViewFunc) -> ViewFunc:
            self.view_funcs[path] = func
            return func

        return decorator

    def get(self, path: str) -> Callable[[ViewFunc], ViewFunc]:
        return self.route(path, methods=["GET"])

    def post(self, path: str) -> Callable[[ViewFunc], ViewFunc]:
        return self.route(path, methods=["POST"])

    def test_client(self) -> object:
        app = self

        class Client:
            def post(
                self,
                path: str,
                json_body: Mapping[str, object] | None = None,
                headers: Mapping[str, str] | None = None,
            ) -> Response:
                global request
                req = Request(json_body, headers)
                request = req
                # Ensure modules that imported 'request' get the new object
                view = app.view_funcs[path]
                view.__globals__['request'] = req
                rv = view()
                if isinstance(rv, tuple):
                    data, status = rv
                    return Response(_response_data(data), status)
                if isinstance(rv, Mapping):
                    return Response(json.dumps(dict(rv)), 200)
                if isinstance(rv, Response):
                    return rv
                return Response(str(rv), 200)

            def get(self, path: str, headers: Mapping[str, str] | None = None) -> Response:
                global request
                if "?" in path:
                    route, query = path.split("?", 1)
                    raw_args = parse_qs(query, keep_blank_values=True)
                    args = {key: values[-1] if len(values) == 1 else values for key, values in raw_args.items()}
                else:
                    route = path
                    args = {}
                req = Request(None, headers, args)
                request = req
                view = app.view_funcs[route]
                view.__globals__['request'] = req
                rv = view()
                if isinstance(rv, tuple):
                    data, status = rv
                    return Response(_response_data(data), status)
                if isinstance(rv, Mapping):
                    return Response(json.dumps(dict(rv)), 200)
                if isinstance(rv, Response):
                    return rv
                return Response(str(rv), 200)

        return Client()

    def run(self, *args: object, **kwargs: object) -> None:
        del args, kwargs


def _response_data(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return json.dumps(dict(value))
    return str(value)


def jsonify(obj: object) -> Response:
    if isinstance(obj, Response):
        return obj
    if isinstance(obj, Mapping):
        return Response(json.dumps(dict(cast(Mapping[str, object], obj))), 200)
    return Response(json.dumps(obj), 200)

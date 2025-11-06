"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

import json
import logging
from urllib.parse import parse_qs


class Request:
    def __init__(self, json_data=None, headers=None, args=None):
        self._json = json_data or {}
        self.headers = headers or {}
        self.remote_addr = self.headers.get("REMOTE_ADDR", "127.0.0.1")
        if args is None:
            args = {}
        self.args = args

    def get_json(self, force=False, silent=False):
        return self._json


request = Request()


class Response:
    def __init__(self, data='', status=200):
        if isinstance(data, Response):
            data = data.data
        elif isinstance(data, dict):
            data = json.dumps(data)
        self.data = data
        self.status_code = status
        self.headers = {}

    def get_json(self):
        return json.loads(self.data)


class Flask:
    def __init__(self, name):
        self.view_funcs = {}
        self.logger = logging.getLogger(name)
        self.config = {}

    def route(self, path, methods=None):
        def decorator(func):
            self.view_funcs[path] = func
            return func
        return decorator

    def test_client(self):
        app = self

        class Client:
            def post(self, path, json=None, headers=None):
                global request
                req = Request(json, headers)
                request = req
                # Ensure modules that imported 'request' get the new object
                view = app.view_funcs[path]
                view.__globals__['request'] = req
                rv = view()
                if isinstance(rv, tuple):
                    data, status = rv
                    if isinstance(data, dict):
                        data = json.dumps(data)
                    return Response(data, status)
                if isinstance(rv, dict):
                    return Response(json.dumps(rv), 200)
                if isinstance(rv, Response):
                    return rv
                return Response(rv, 200)

            def get(self, path, headers=None):
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
                    if isinstance(data, dict):
                        data = json.dumps(data)
                    return Response(data, status)
                if isinstance(rv, dict):
                    return Response(json.dumps(rv), 200)
                if isinstance(rv, Response):
                    return rv
                return Response(rv, 200)

        return Client()

    def run(self, *args, **kwargs):
        pass


def jsonify(obj):
    if isinstance(obj, Response):
        return obj
    return Response(json.dumps(obj), 200)

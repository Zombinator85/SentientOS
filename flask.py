import json


class Request:
    def __init__(self, json_data=None, headers=None):
        self._json = json_data or {}
        self.headers = headers or {}

    def get_json(self, silent=False):
        return self._json


request = Request()


class Response:
    def __init__(self, data='', status=200):
        self.data = data
        self.status_code = status

    def get_json(self):
        return json.loads(self.data)


class Flask:
    def __init__(self, name):
        self.view_funcs = {}

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
                elif isinstance(rv, dict):
                    return Response(json.dumps(rv), 200)
                else:
                    return Response(rv, 200)

        return Client()


def jsonify(obj):
    return json.dumps(obj)

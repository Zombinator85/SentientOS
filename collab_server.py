import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs

online = set()
updates = []


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode()
        if self.path == '/connect':
            sid = parse_qs(body).get('id', [''])[0]
            if sid:
                online.add(sid)
            self._send_json({'online': list(online)})
        elif self.path == '/disconnect':
            sid = parse_qs(body).get('id', [''])[0]
            if sid:
                online.discard(sid)
            self._send_json({'online': list(online)})
        elif self.path == '/edit':
            if body:
                updates.append(json.loads(body))
            self.send_response(204)
            self.end_headers()
        else:
            self.send_error(404)

    def do_GET(self):
        if self.path == '/poll':
            data = list(updates)
            updates.clear()
            self._send_json(data)
        else:
            self.send_error(404)

    def _send_json(self, obj):
        data = json.dumps(obj).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def run(port: int = 5001) -> None:
    HTTPServer(('localhost', port), Handler).serve_forever()


if __name__ == '__main__':
    run()

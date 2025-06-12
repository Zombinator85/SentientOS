"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs
from typing import Dict, Any


import notification
from typing import Set

online: Set[str] = set()
updates = []
users: Dict[str, Dict[str, Any]] = {}

def _presence() -> list[dict]:
    out = []
    for sid in online:
        info = users.get(sid, {})
        out.append({"id": sid, "persona": info.get("persona", ""), "chapter": info.get("chapter", 0)})
    return out


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode()
        if self.path == '/connect':
            params = parse_qs(body)
            sid = params.get('id', [''])[0]
            persona = params.get('persona', [''])[0]
            if sid:
                online.add(sid)
                info = users.setdefault(sid, {})
                if persona:
                    info['persona'] = persona
            notification.send('user_joined', {'id': sid, 'persona': persona})
            self._send_json({'online': list(online), 'users': _presence()})
        elif self.path == '/disconnect':
            sid = parse_qs(body).get('id', [''])[0]
            if sid:
                online.discard(sid)
                users.pop(sid, None)
            notification.send('user_left', {'id': sid})
            self._send_json({'online': list(online), 'users': _presence()})
        elif self.path == '/edit':
            if body:
                data = json.loads(body)
                updates.append(data)
                sid = data.get('id')
                chapter = data.get('chapter')
                if sid and chapter is not None:
                    users.setdefault(sid, {})['chapter'] = chapter
                    notification.send('edit', {'id': sid, 'chapter': chapter})
            self.send_response(204)
            self.end_headers()
        elif self.path == '/update':
            data = json.loads(body or '{}')
            sid = data.get('id')
            if sid and sid in users:
                if 'persona' in data:
                    users[sid]['persona'] = data['persona']
                    notification.send('persona_switch', {'id': sid, 'persona': data['persona']})
                if 'chapter' in data:
                    users[sid]['chapter'] = data['chapter']
            self._send_json({'status': 'ok', 'users': _presence()})
        else:
            self.send_error(404)

    def do_GET(self):
        if self.path == '/poll':
            data = list(updates)
            updates.clear()
            self._send_json(data)
        elif self.path == '/presence':
            self._send_json({'users': _presence()})
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

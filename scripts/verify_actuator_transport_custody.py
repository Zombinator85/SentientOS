from __future__ import annotations

import ast
from pathlib import Path


def main() -> int:
    source = Path("api/actuator.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = ("requests.request", "requests.post", "urllib.request.build_opener")
    assert not any(value in source for value in forbidden)
    actuator_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "HttpActuator")
    assert "extras =" not in (ast.get_source_segment(source, actuator_class) or "")
    required = ("_resolved_endpoint_peers", "sock.connect(peer.sockaddr)", "server_hostname=host", "response = http_fetch(url", "smtp.sock = _connect_resolved_peer")
    assert all(value in source for value in required)
    print("actuator_transport_custody_ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

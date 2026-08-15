from __future__ import annotations

import socket
import threading
import subprocess
import sys
from types import SimpleNamespace

import pytest

from api import actuator


@pytest.fixture(autouse=True)
def policy(monkeypatch: pytest.MonkeyPatch) -> None:
    actuator.WHITELIST = {"http": ["http://127.0.0.1:8080", "https://example.com"], "smtp": ["smtp.example.com:25"], "email": ["ok@example.com"], "timeout": 1}
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: None)


def test_exact_ip_literal_http_is_direct_and_zero_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    actuator.WHITELIST["http"] = [f"http://127.0.0.1:{port}"]
    received: list[bytes] = []
    def serve() -> None:
        conn, _ = listener.accept()
        with conn:
            received.append(conn.recv(4096))
            conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 6\r\n\r\norigin")
        listener.close()
    thread = threading.Thread(target=serve)
    thread.start()
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_k: pytest.fail("literal performed DNS"))
    assert actuator.http_fetch(f"http://127.0.0.1:{port}/x") == {"status": 200, "text": "origin"}
    thread.join(2)
    assert f"Host: 127.0.0.1:{port}".encode() in received[0]


def test_ambient_proxy_has_zero_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    origin = socket.socket(); origin.bind(("127.0.0.1", 0)); origin.listen()
    proxy = socket.socket(); proxy.bind(("127.0.0.1", 0)); proxy.listen(); proxy.settimeout(.3)
    port = origin.getsockname()[1]
    actuator.WHITELIST["http"] = [f"http://127.0.0.1:{port}"]
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        monkeypatch.setenv(name, f"http://127.0.0.1:{proxy.getsockname()[1]}")
    monkeypatch.setenv("NO_PROXY", "")
    def serve() -> None:
        conn, _ = origin.accept()
        with conn:
            conn.recv(4096); conn.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nok")
        origin.close()
    thread = threading.Thread(target=serve); thread.start()
    assert actuator.http_fetch(f"http://127.0.0.1:{port}/")["text"] == "ok"
    thread.join(2)
    with pytest.raises(socket.timeout): proxy.accept()
    proxy.close()


@pytest.mark.parametrize("field,value", [("proxies", {"http": "http://bad"}), ("verify", False), ("cert", "x")])
def test_retired_transport_field_fails_before_resolution(monkeypatch: pytest.MonkeyPatch, field: str, value: object) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_k: pytest.fail("resolved"))
    with pytest.raises(ValueError, match="unsupported HTTP intent fields"):
        actuator.HttpActuator().execute({"type": "http", "url": "https://example.com", field: value})


def test_host_header_rejected_before_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_k: pytest.fail("resolved"))
    with pytest.raises(ValueError, match="reserved"):
        actuator.http_fetch("https://example.com", headers={"Host": "evil.test"})


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "::1", "fe80::1"])
def test_dns_special_answers_fail_before_socket(monkeypatch: pytest.MonkeyPatch, address: str) -> None:
    family = socket.AF_INET6 if ":" in address else socket.AF_INET
    sockaddr = (address, 443, 0, 0) if family == socket.AF_INET6 else (address, 443)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_k: [(family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)])
    monkeypatch.setattr(socket, "socket", lambda *_a, **_k: pytest.fail("socket constructed"))
    with pytest.raises(PermissionError, match="non-global"):
        actuator.http_fetch("https://example.com")


def test_one_dns_snapshot_pins_peer(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    peer = ("93.184.216.34", 443)
    def resolve(*_a: object) -> list[tuple[object, ...]]:
        nonlocal calls; calls += 1
        return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", peer if calls == 1 else ("127.0.0.1", 443))]
    connected: list[object] = []
    fake = SimpleNamespace(settimeout=lambda _v: None, connect=lambda value: connected.append(value), close=lambda: None)
    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    monkeypatch.setattr(socket, "socket", lambda *_a: fake)
    monkeypatch.setattr(actuator, "_direct_http_transaction", lambda url, method, headers, body: (actuator._connect_resolved_peer(actuator._resolved_endpoint_peers("example.com", 443), 1), {"status": 200, "text": "ok"})[1])
    assert actuator.http_fetch("https://example.com")["status"] == 200
    assert calls == 1 and connected == [peer]


def test_multi_candidate_failover_uses_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    peers = [("93.184.216.34", 443), ("1.1.1.1", 443)]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_k: [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", p) for p in peers])
    attempts: list[object] = []
    class Sock:
        def settimeout(self, _v: float) -> None: pass
        def connect(self, peer: object) -> None:
            attempts.append(peer)
            if len(attempts) == 1: raise OSError("first failed")
        def close(self) -> None: pass
    monkeypatch.setattr(socket, "socket", lambda *_a: Sock())
    actuator._connect_resolved_peer(actuator._resolved_endpoint_peers("example.com", 443), 1)
    assert attempts == peers


def test_https_sni_uses_logical_host(monkeypatch: pytest.MonkeyPatch) -> None:
    wrapped: list[str | None] = []
    fake_socket = SimpleNamespace(close=lambda: None)
    fake_context = SimpleNamespace(wrap_socket=lambda sock, server_hostname=None: (wrapped.append(server_hostname) or sock))
    monkeypatch.setattr(actuator, "_resolved_endpoint_peers", lambda *_a: ())
    monkeypatch.setattr(actuator, "_connect_resolved_peer", lambda *_a: fake_socket)
    monkeypatch.setattr(actuator.ssl, "create_default_context", lambda: fake_context)
    monkeypatch.setattr(actuator.http.client.HTTPConnection, "request", lambda *_a, **_k: None)
    response = SimpleNamespace(status=200, headers=SimpleNamespace(get_content_charset=lambda: None), read=lambda _n: b"ok")
    monkeypatch.setattr(actuator.http.client.HTTPConnection, "getresponse", lambda _self: response)
    actuator.http_fetch("https://example.com")
    assert wrapped == ["example.com"]


def test_webhook_uses_shared_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []
    monkeypatch.setattr(actuator, "http_fetch", lambda url, **kwargs: (calls.append((url, kwargs)) or {"status": 204, "text": ""}))
    assert actuator.trigger_webhook("https://example.com", {"ok": True}) == {"status": 204}
    assert calls[0][1] == {"method": "POST", "json_data": {"ok": True}}


def test_smtp_uses_one_pinned_resolution(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com"); monkeypatch.setenv("SMTP_PORT", "25"); monkeypatch.setenv("SMTP_FROM", "sender@example.com")
    peer = actuator._ResolvedPeer(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, ("93.184.216.34", 25))
    resolutions: list[object] = []; connections: list[object] = []
    monkeypatch.setattr(actuator, "_resolved_endpoint_peers", lambda host, port: (resolutions.append((host, port)) or (peer,)))
    monkeypatch.setattr(actuator, "_connect_resolved_peer", lambda peers, _timeout: (connections.append(peers[0].sockaddr) or SimpleNamespace()))
    class SMTP:
        def __init__(self, **_kwargs: object) -> None: self._host = ""; self.sock = None
        def getreply(self) -> tuple[int, bytes]: return 220, b"ok"
        def __enter__(self) -> "SMTP": return self
        def __exit__(self, *_a: object) -> None: pass
        def send_message(self, _message: object) -> None: pass
        def login(self, *_a: object) -> None: pass
    monkeypatch.setattr(actuator.smtplib, "SMTP", SMTP)
    assert actuator.send_email("ok@example.com", "subject", "body") == {"sent": "ok@example.com"}
    assert resolutions == [("smtp.example.com", 25)] and connections == [("93.184.216.34", 25)]


def test_smtp_dns_special_answer_has_zero_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com"); monkeypatch.setenv("SMTP_PORT", "25"); monkeypatch.setenv("SMTP_FROM", "sender@example.com")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_k: [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 25))])
    monkeypatch.setattr(socket, "socket", lambda *_a: pytest.fail("SMTP socket constructed"))
    with pytest.raises(PermissionError, match="non-global"):
        actuator.send_email("ok@example.com", "subject", "body")


def test_static_transport_custody_verifier_passes() -> None:
    result = subprocess.run([sys.executable, "scripts/verify_actuator_transport_custody.py"], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert "actuator_transport_custody_ready" in result.stdout

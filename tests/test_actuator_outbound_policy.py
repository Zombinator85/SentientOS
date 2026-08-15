from __future__ import annotations

from types import SimpleNamespace
import inspect

import pytest

from api import actuator


@pytest.fixture(autouse=True)
def outbound_policy(monkeypatch: pytest.MonkeyPatch) -> None:
    actuator.WHITELIST = {
        "http": ["https://example.com", "https://example.com/api", "http://127.0.0.1:8080", "http://[::1]:8080"],
        "smtp": ["smtp.example.com:587"],
        "email": ["allowed@example.com", "*@alerts.example.com"],
        "timeout": 2,
    }
    monkeypatch.setattr(actuator, "_authorize_effect", lambda: None)


def _requests_client(calls: list[tuple[str, str]]) -> SimpleNamespace:
    response = SimpleNamespace(status_code=200, text="ok")

    def request(method: str, url: str, **kwargs: object) -> object:
        calls.append((method, url))
        assert kwargs["allow_redirects"] is False
        return response

    def post(url: str, **kwargs: object) -> object:
        calls.append(("POST", url))
        assert kwargs["allow_redirects"] is False
        return response

    return SimpleNamespace(request=request, post=post)


def test_exact_http_origin_authorization_and_normalization(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(actuator, "_direct_http_transaction", lambda url, method, *_a: (calls.append((method, url)) or {"status": 200, "text": "ok"}))
    assert actuator.http_fetch("HTTPS://EXAMPLE.COM:443/path?q=1#ignored")["status"] == 200
    assert calls == [("GET", "https://example.com/path?q=1")]


@pytest.mark.parametrize("url", [
    "https://example.com.evil/", "https://example.com@evil.test/", "https://example.com:444/",
    "https://evil.test/?next=https://example.com", "http://example.com/",
])
def test_hostname_textual_prefix_confusion_has_zero_http_effect(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(actuator, "optional_import", lambda *_a, **_k: _requests_client(calls))
    with pytest.raises((PermissionError, ValueError)):
        actuator.http_fetch(url)
    assert calls == []


def test_hostname_prefix_denial_witnesses_zero_client_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(actuator, "optional_import", lambda *_a, **_k: _requests_client(calls))
    with pytest.raises(PermissionError):
        actuator.http_fetch("https://example.com.evil/")
    assert calls == []


@pytest.mark.parametrize("url,error", [
    ("https://example.com:bad", "port"), ("https:///path", "host"),
    ("ftp://example.com", "scheme"), ("https://user:pass@example.com", "userinfo"),
    ("https://example.com/\nheader", "control"),
])
def test_malformed_url_classes_fail_closed(url: str, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        actuator._authorized_http_url(url)


def test_url_userinfo_confusion_is_rejected() -> None:
    with pytest.raises(ValueError, match="userinfo"):
        actuator._authorized_http_url("https://example.com@evil.test/")


def test_scheme_only_universal_policy_is_invalid_and_path_scope_is_component_exact() -> None:
    actuator.WHITELIST["http"] = ["http://", "https://", "https://example.com/api"]
    assert actuator._authorized_http_url("https://example.com/api") == "https://example.com/api"
    assert actuator._authorized_http_url("https://example.com/api/child") == "https://example.com/api/child"
    with pytest.raises(PermissionError):
        actuator._authorized_http_url("https://other.example/")
    with pytest.raises(PermissionError):
        actuator._authorized_http_url("https://example.com/apievil")


def test_ip_literals_are_canonical_and_require_exact_policy() -> None:
    assert actuator._authorized_http_url("http://127.0.0.1:8080/x") == "http://127.0.0.1:8080/x"
    assert actuator._authorized_http_url("http://[0:0:0:0:0:0:0:1]:8080/x") == "http://[::1]:8080/x"
    with pytest.raises(PermissionError):
        actuator._authorized_http_url("http://127.0.0.1:8081/x")


def test_webhook_uses_shared_policy_and_disables_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(actuator, "_direct_http_transaction", lambda url, method, *_a: (calls.append((method, url)) or {"status": 200, "text": "ok"}))
    assert actuator.trigger_webhook("https://EXAMPLE.com/api/event", {"ok": True}) == {"status": 200}
    assert calls == [("POST", "https://example.com/api/event")]


def test_redirect_response_is_not_followed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(actuator, "_direct_http_transaction", lambda url, method, *_a: (calls.append((method, url)) or {"status": 302, "text": ""}))
    assert actuator.http_fetch("https://example.com/start")["status"] == 302
    assert calls == [("GET", "https://example.com/start")]


class FakeSMTP:
    calls: list[tuple[str, int]] = []

    def __init__(self, host: str, port: int) -> None:
        self.calls.append((host, port))

    def __enter__(self) -> "FakeSMTP": return self
    def __exit__(self, *_args: object) -> None: return None
    def login(self, user: str, password: str) -> None: pass
    def send_message(self, message: object) -> None: pass


def test_allowed_smtp_endpoint_and_recipient(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSMTP.calls = []
    monkeypatch.setenv("SMTP_HOST", "SMTP.EXAMPLE.COM")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_FROM", "sender@example.com")
    smtp = SimpleNamespace(_host="", sock=None, getreply=lambda: (220, b"ok"), login=lambda *_a: None, send_message=lambda *_a: None, close=lambda: None,
                           __enter__=lambda self: self, __exit__=lambda self, *_a: None)
    class SMTP:
        def __init__(self, **_kwargs: object) -> None: self.__dict__ = smtp.__dict__
        def __enter__(self) -> "SMTP": return self
        def __exit__(self, *_a: object) -> None: pass
        getreply = staticmethod(lambda: (220, b"ok")); login = staticmethod(lambda *_a: None); send_message = staticmethod(lambda *_a: None)
    monkeypatch.setattr(actuator, "_resolved_endpoint_peers", lambda *_a: ())
    monkeypatch.setattr(actuator, "_connect_resolved_peer", lambda *_a: SimpleNamespace())
    monkeypatch.setattr(actuator.smtplib, "SMTP", SMTP)
    assert actuator.send_email("allowed@example.com", "subject", "body") == {"sent": "allowed@example.com"}
    assert smtp._host == "smtp.example.com"


@pytest.mark.parametrize("host,port,to", [
    ("smtp.example.com.evil", "587", "allowed@example.com"),
    ("smtp.example.com", "25", "allowed@example.com"),
    ("smtp.example.com", "587", "denied@example.com"),
    ("smtp.example.com", "587", "user@alerts.example.com.evil"),
])
def test_denied_smtp_host_or_recipient_constructs_zero_clients(monkeypatch: pytest.MonkeyPatch, host: str, port: str, to: str) -> None:
    FakeSMTP.calls = []
    monkeypatch.setenv("SMTP_HOST", host)
    monkeypatch.setenv("SMTP_PORT", port)
    monkeypatch.setenv("SMTP_FROM", "sender@example.com")
    monkeypatch.setattr(actuator.smtplib, "SMTP", FakeSMTP)
    with pytest.raises((PermissionError, ValueError)):
        actuator.send_email(to, "subject", "body")
    assert FakeSMTP.calls == []


def test_denied_smtp_host_witnesses_zero_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSMTP.calls = []
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com.evil")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setattr(actuator.smtplib, "SMTP", FakeSMTP)
    with pytest.raises(PermissionError):
        actuator.send_email("allowed@example.com", "subject", "body")
    assert FakeSMTP.calls == []


def test_denied_recipient_witnesses_zero_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSMTP.calls = []
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setattr(actuator.smtplib, "SMTP", FakeSMTP)
    with pytest.raises(PermissionError):
        actuator.send_email("denied@example.com", "subject", "body")
    assert FakeSMTP.calls == []


@pytest.mark.parametrize("to,subject", [("bad-address", "ok"), ("allowed@example.com\r\nBcc:x@y.test", "ok"), ("allowed@example.com", "ok\nBcc: x@y.test")])
def test_mailbox_and_header_injection_rejected_before_connection(monkeypatch: pytest.MonkeyPatch, to: str, subject: str) -> None:
    FakeSMTP.calls = []
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_FROM", "sender@example.com")
    monkeypatch.setattr(actuator.smtplib, "SMTP", FakeSMTP)
    with pytest.raises(ValueError):
        actuator.send_email(to, subject, "body")
    assert FakeSMTP.calls == []


def test_subject_header_injection_witnesses_zero_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSMTP.calls = []
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_FROM", "sender@example.com")
    monkeypatch.setattr(actuator.smtplib, "SMTP", FakeSMTP)
    with pytest.raises(ValueError, match="injection"):
        actuator.send_email("allowed@example.com", "subject\r\nBcc:x@y.test", "body")
    assert FakeSMTP.calls == []


def test_environment_server_without_policy_has_zero_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeSMTP.calls = []
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "sender@example.com")
    monkeypatch.setattr(actuator.smtplib, "SMTP", FakeSMTP)
    actuator.WHITELIST["smtp"] = []
    with pytest.raises(PermissionError):
        actuator.send_email("allowed@example.com", "subject", "body")
    assert FakeSMTP.calls == []


def test_dry_run_has_zero_outbound_effect(monkeypatch: pytest.MonkeyPatch) -> None:
    effects: list[object] = []
    monkeypatch.setattr(actuator, "dispatch", lambda intent: effects.append(intent))
    import memory_manager
    monkeypatch.setattr(memory_manager, "write_mem", lambda *_a, **_k: "log")
    monkeypatch.setattr(memory_manager, "save_reflection", lambda **_k: "reflection")
    actuator.LAST_EXECUTION.clear()
    result = actuator.act({"type": "http", "url": "https://example.com"}, dry_run=True)
    assert result["dry_run"] is True
    assert effects == []


def test_static_outbound_authorization_order_and_shared_validator() -> None:
    http_source = inspect.getsource(actuator.http_fetch)
    webhook_source = inspect.getsource(actuator.trigger_webhook)
    email_source = inspect.getsource(actuator.send_email)
    assert "_authorized_http_url(url)" in http_source
    assert "http_fetch(url" in webhook_source
    assert "_match_patterns" not in http_source + webhook_source
    assert "requests" not in http_source + webhook_source
    assert email_source.index("_authorized_smtp_endpoint") < email_source.index("_resolved_endpoint_peers")
    assert email_source.index("_authorized_recipient") < email_source.index("_resolved_endpoint_peers")

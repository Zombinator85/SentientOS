from agents.forms.oracle_session import OracleSession


class StubRelay:
    def __init__(self):
        self.calls = []

    def goto(self, url):
        self.calls.append(("goto", url))
        return {"goto": url}

    def type(self, selector, value):
        self.calls.append(("type", selector, value))
        return {"type": selector, "value": value}

    def click(self, selector):
        self.calls.append(("click", selector))
        return {"click": selector}

    def screenshot(self):
        self.calls.append(("screenshot", None))
        return b"image-bytes"


def test_oracle_session_denies_without_approval():
    relay = StubRelay()
    session = OracleSession(relay, approved=False)

    assert session.navigate("https://example.com") == {
        "status": "denied",
        "reason": "approval_required",
    }
    assert session.fill("#field", "value") == {
        "status": "denied",
        "reason": "approval_required",
    }
    assert session.click("#button") == {
        "status": "denied",
        "reason": "approval_required",
    }
    assert session.screenshot() == {
        "status": "denied",
        "reason": "approval_required",
    }
    assert relay.calls == []


def test_oracle_session_executes_when_approved():
    relay = StubRelay()
    session = OracleSession(relay, approved=True)

    nav = session.navigate("https://example.com")
    fill = session.fill("#field", "value")
    click = session.click("#button")
    shot = session.screenshot()

    assert nav == {"status": "navigated", "url": "https://example.com", "raw": {"goto": "https://example.com"}}
    assert fill == {"status": "filled", "selector": "#field", "value": "value"}
    assert click == {"status": "clicked", "selector": "#button"}
    assert shot == {"status": "screenshot", "bytes": b"image-bytes"}

    assert relay.calls == [
        ("goto", "https://example.com"),
        ("type", "#field", "value"),
        ("click", "#button"),
        ("screenshot", None),
    ]
    assert isinstance(shot["bytes"], (bytes, bytearray))

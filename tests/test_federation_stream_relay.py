from __future__ import annotations

import importlib
import sys
from types import ModuleType

import pytest

import sentientos.privilege as privilege


@pytest.fixture
def relay(monkeypatch):
    monkeypatch.setattr(privilege, "require_admin_banner", lambda: None)
    monkeypatch.setattr(privilege, "require_lumos_approval", lambda: None)
    monkeypatch.setitem(sys.modules, "requests", ModuleType("requests"))
    module = importlib.import_module("scripts.federation_stream_relay")
    return importlib.reload(module)


@pytest.mark.parametrize(
    "payload",
    [
        b"[]",
        b"null",
        b'"text"',
        b"17",
        b"{bad",
        b"\\xff",
        b"[" * 1100 + b"0" + b"]" * 1100,
        b"9" * 5000,
    ],
)
def test_decode_event_line_skips_non_object_and_malformed_json(relay, payload):
    assert relay.decode_event_line(b"data: " + payload, "http://peer.local/presence") is None


def test_decode_event_line_accepts_object_and_binds_configured_source(relay):
    result = relay.decode_event_line(
        b'data: {"peer":"alpha","event":"heartbeat"}',
        "http://node1.local:8000/presence",
    )

    assert result == {
        "peer": "alpha",
        "event": "heartbeat",
        "source": "http://node1.local:8000/presence",
    }


def test_decode_event_line_skips_non_data_and_oversized_lines(relay):
    assert relay.decode_event_line(b": heartbeat", "http://peer.local") is None
    assert (
        relay.decode_event_line(
            b"data: " + b"x" * relay.MAX_EVENT_BYTES,
            "http://peer.local",
        )
        is None
    )


def test_decode_event_line_rejects_non_bytes_input(relay):
    assert relay.decode_event_line("data: {}", "http://peer.local") is None



def test_iter_bounded_sse_lines_handles_chunk_boundaries_and_line_endings(relay):
    chunks = [b'data: {"x":', b'1}\r\nevent: ping\n', b'data: {"y":2}']

    assert list(relay.iter_bounded_sse_lines(chunks)) == [
        b'data: {"x":1}',
        b'event: ping',
        b'data: {"y":2}',
    ]


def test_iter_bounded_sse_lines_discards_oversize_and_resynchronizes(relay):
    chunks = [
        b'data: ' + b'x' * 20,
        b'y' * 20 + b'\n' + b'data: {"peer":"safe"}\n',
    ]

    assert list(relay.iter_bounded_sse_lines(chunks, max_bytes=32)) == [
        b'data: {"peer":"safe"}',
    ]


def test_iter_bounded_sse_lines_rejects_invalid_bounds_or_chunk_types(relay):
    with pytest.raises(ValueError, match="positive integer"):
        list(relay.iter_bounded_sse_lines([], max_bytes=0))
    with pytest.raises(ValueError, match="positive integer"):
        list(relay.iter_bounded_sse_lines([], max_bytes=True))
    with pytest.raises(TypeError, match="chunks must be bytes"):
        list(relay.iter_bounded_sse_lines(["data: {}"], max_bytes=32))

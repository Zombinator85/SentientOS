from __future__ import annotations

from pathlib import Path

import pytest

from api import federation_stream_api
from api.federation_stream_api import _read_available_lines, stream_events


def read_once(
    path: Path,
    *,
    offset: int = 0,
    identity: tuple[int, int] | None = None,
    pending: bytearray | None = None,
    discarding: bool = False,
    limit: int = 64,
) -> tuple[list[str], int, tuple[int, int] | None, bytearray, bool]:
    return _read_available_lines(
        path,
        offset=offset,
        file_identity=identity,
        pending=bytearray() if pending is None else pending,
        discarding=discarding,
        max_line_bytes=limit,
    )


def test_incremental_reader_reads_complete_records_and_retains_partial_line(tmp_path):
    path = tmp_path / "stream.jsonl"
    path.write_bytes(b'{"event":"first"}\n{"event":"par')
    lines, offset, identity, pending, discarding = read_once(path)

    assert lines == ['{"event":"first"}']
    assert offset == path.stat().st_size
    assert bytes(pending) == b'{"event":"par'
    assert discarding is False

    with path.open("ab") as stream:
        stream.write(b'tial"}\n')
    lines, offset, identity, pending, discarding = _read_available_lines(
        path,
        offset=offset,
        file_identity=identity,
        pending=pending,
        discarding=discarding,
        max_line_bytes=64,
    )

    assert lines == ['{"event":"partial"}']
    assert pending == bytearray()
    assert discarding is False


def test_incremental_reader_reads_only_one_bounded_chunk(tmp_path):
    path = tmp_path / "stream.jsonl"
    path.write_bytes(b"record\\n" * 20000)

    _, offset, _, _, _ = read_once(path)

    assert offset == 64 * 1024
    assert offset < path.stat().st_size


def test_incremental_reader_discards_oversize_record_and_resynchronizes(tmp_path):
    path = tmp_path / "stream.jsonl"
    path.write_bytes(b"x" * 20 + b"\nvalid\n")

    lines, *_ = read_once(path, limit=8)

    assert lines == ["valid"]


def test_incremental_reader_resets_after_log_truncation(tmp_path):
    path = tmp_path / "stream.jsonl"
    path.write_bytes(b"old record\n")
    lines, offset, identity, pending, discarding = read_once(path)
    assert lines == ["old record"]

    path.write_bytes(b"new\n")
    lines, new_offset, new_identity, pending, discarding = _read_available_lines(
        path,
        offset=offset,
        file_identity=identity,
        pending=pending,
        discarding=discarding,
        max_line_bytes=64,
    )

    assert lines == ["new"]
    assert new_offset == len(b"new\n")
    assert new_identity is not None


def test_incremental_reader_resets_after_file_replacement(tmp_path):
    path = tmp_path / "stream.jsonl"
    path.write_bytes(b"old record\n")
    _, offset, identity, pending, discarding = read_once(path)
    replacement = tmp_path / "replacement.jsonl"
    replacement.write_bytes(b"replacement\n")
    replacement.replace(path)

    lines, new_offset, new_identity, *_ = _read_available_lines(
        path,
        offset=offset,
        file_identity=identity,
        pending=pending,
        discarding=discarding,
        max_line_bytes=64,
    )

    assert lines == ["replacement"]
    assert new_offset == len(b"replacement\n")
    assert new_identity != identity


@pytest.mark.parametrize("poll_interval", [0, float("nan"), float("inf")])
def test_stream_events_rejects_invalid_poll_intervals(tmp_path, poll_interval):
    with pytest.raises(ValueError, match="poll_interval"):
        next(stream_events(tmp_path / "missing", poll_interval=poll_interval))


def test_stream_events_rejects_invalid_line_bound(tmp_path):
    with pytest.raises(ValueError, match="max_line_bytes"):
        next(stream_events(tmp_path / "missing", max_line_bytes=True))



def test_stream_events_emits_sse_and_waits_for_complete_appended_record(
    tmp_path, monkeypatch
):
    path = tmp_path / "stream.jsonl"
    path.write_bytes(b"first\\npartial")
    sleep_calls = 0

    class StopPolling(BaseException):
        pass

    def fake_sleep(_interval):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 1:
            with path.open("ab") as stream:
                stream.write(b"\\n")
        else:
            raise StopPolling

    monkeypatch.setattr(federation_stream_api.time, "sleep", fake_sleep)
    events = stream_events(path, poll_interval=0.01)

    assert next(events) == "data: first\\n\\n"
    assert next(events) == "data: partial\\n\\n"
    with pytest.raises(StopPolling):
        next(events)

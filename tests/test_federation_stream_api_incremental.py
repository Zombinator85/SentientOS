from __future__ import annotations

from pathlib import Path

import pytest

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

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

from scripts.verify_construction_continuation_custody import verify_construction_continuation


def _blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def _write_fixture(root: Path) -> tuple[Path, Path, Path, Path]:
    legacy = root / "work/sentientos_night_watch_continuation.md"
    segment = root / "work/construction/segments/0001-note.md"
    checkpoint = root / "work/construction/active_checkpoint.md"
    index_path = root / "work/construction/index.json"
    for path in (legacy, segment, checkpoint, index_path):
        path.parent.mkdir(parents=True, exist_ok=True)
    legacy_bytes = b"frozen\n"
    segment_bytes = b"retained note\n"
    legacy.write_bytes(legacy_bytes)
    segment.write_bytes(segment_bytes)
    segment_sha = hashlib.sha256(segment_bytes).hexdigest()
    checkpoint_bytes = (
        f"Source `{ 'a' * 40 }`, tree `{ 'b' * 40 }`.\n"
        f"Latest segment: {segment.relative_to(root).as_posix()} {segment_sha}\n"
    ).encode()
    checkpoint.write_bytes(checkpoint_bytes)
    index = {
        "schema_version": 1,
        "active_checkpoint": checkpoint.relative_to(root).as_posix(),
        "legacy_journal": {
            "path": legacy.relative_to(root).as_posix(),
            "bytes": len(legacy_bytes),
            "frozen": True,
            "git_blob_sha": _blob_sha(legacy_bytes),
            "sha256": hashlib.sha256(legacy_bytes).hexdigest(),
        },
        "segments": [
            {
                "sequence": 1,
                "path": segment.relative_to(root).as_posix(),
                "predecessor": "legacy-blob:" + _blob_sha(legacy_bytes),
                "bytes": len(segment_bytes),
                "sha256": segment_sha,
                "source_commit": "c" * 40,
            }
        ],
        "active_checkpoint_binding": {
            "source_commit": "a" * 40,
            "source_tree": "b" * 40,
            "latest_segment_sequence": 1,
            "latest_segment_sha256": segment_sha,
            "checkpoint_sha256": hashlib.sha256(checkpoint_bytes).hexdigest(),
        },
    }
    index_path.write_text(json.dumps(index), encoding="utf-8")
    return index_path, legacy, segment, checkpoint


def test_frozen_journal_and_compact_segment_chain_verify(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    result = verify_construction_continuation(tmp_path)
    assert result["status"] == "construction_continuation_custody_ready"
    assert result["failures"] == []
    assert result["segments_verified"] == 1


def test_checkpoint_segment_reference_must_match_the_indexed_path_digest(
    tmp_path: Path,
) -> None:
    index_path, _, _, checkpoint = _write_fixture(tmp_path)
    checkpoint.write_text(
        f"Source `{ 'a' * 40 }`, tree `{ 'b' * 40 }`.\n"
        "Latest segment: work/construction/segments/0001-note.md "
        f"{ 'f' * 64 }\n",
        encoding="utf-8",
    )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["active_checkpoint_binding"]["checkpoint_sha256"] = hashlib.sha256(
        checkpoint.read_bytes()
    ).hexdigest()
    index_path.write_text(json.dumps(index), encoding="utf-8")

    result = verify_construction_continuation(tmp_path)

    assert result["status"] == "invalid"
    assert (
        "active_checkpoint_segment_reference_digest_mismatch:"
        "work/construction/segments/0001-note.md"
    ) in result["failures"]


def test_checkpoint_segment_reference_must_exist_in_the_index(
    tmp_path: Path,
) -> None:
    index_path, _, _, checkpoint = _write_fixture(tmp_path)
    checkpoint.write_text(
        f"Source `{ 'a' * 40 }`, tree `{ 'b' * 40 }`.\n"
        "Latest segment: work/construction/segments/0002-missing.md "
        f"{ 'f' * 64 }\n",
        encoding="utf-8",
    )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["active_checkpoint_binding"]["checkpoint_sha256"] = hashlib.sha256(
        checkpoint.read_bytes()
    ).hexdigest()
    index_path.write_text(json.dumps(index), encoding="utf-8")

    result = verify_construction_continuation(tmp_path)

    assert result["status"] == "invalid"
    assert (
        "active_checkpoint_segment_reference_unknown:"
        "work/construction/segments/0002-missing.md"
    ) in result["failures"]


@pytest.mark.parametrize(
    ("target", "mutation", "expected_failure"),
    [
        ("legacy", "tamper", "legacy_journal_sha256_mismatch"),
        ("segment", "tamper", "segment_1_sha256_mismatch"),
        ("segment", "remove", "segment_1_unreadable"),
        ("index", "predecessor", "segment_1_predecessor_mismatch"),
        ("checkpoint", "tamper", "active_checkpoint_sha256_mismatch"),
        ("index", "checkpoint", "active_checkpoint_segment_sequence_mismatch"),
        ("index", "duplicate", "segment_2_path_missing_or_duplicate"),
    ],
)
def test_custody_verifier_rejects_tampered_or_incomplete_records(
    tmp_path: Path, target: str, mutation: str, expected_failure: str
) -> None:
    index_path, legacy, segment, checkpoint = _write_fixture(tmp_path)
    if target == "legacy":
        legacy.write_bytes(legacy.read_bytes() + b"tampered")
    elif target == "segment" and mutation == "tamper":
        segment.write_bytes(segment.read_bytes() + b"tampered")
    elif target == "segment" and mutation == "remove":
        segment.unlink()
    elif target == "checkpoint" and mutation == "tamper":
        checkpoint.write_text("contradictory checkpoint\n", encoding="utf-8")
    else:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        if mutation == "predecessor":
            index["segments"][0]["predecessor"] = "segment-sha256:" + "f" * 64
        elif mutation == "duplicate":
            index["segments"].append(dict(index["segments"][0]))
        else:
            index["active_checkpoint_binding"]["latest_segment_sequence"] = 0
        index_path.write_text(json.dumps(index), encoding="utf-8")

    result = verify_construction_continuation(tmp_path)
    assert result["status"] == "invalid"
    assert any(failure.startswith(expected_failure) for failure in result["failures"])

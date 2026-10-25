from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.no_legacy_skip

import scripts.construction_index_sharding as sharding
from scripts.verify_construction_continuation_custody import verify_construction_continuation
from scripts.construction_index_sharding import (
    append_segments_to_sharded_index,
    build_sharded_index,
    migrate_repository,
)


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
        "latest_sequence": 1,
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


@pytest.mark.parametrize("target", ["legacy", "segment"])
def test_custody_rejects_boolean_byte_counts(tmp_path: Path, target: str) -> None:
    index_path, legacy, segment, checkpoint = _write_fixture(tmp_path)
    index = json.loads(index_path.read_bytes())
    if target == "legacy":
        content = b"x"
        legacy.write_bytes(content)
        blob = _blob_sha(content)
        index["legacy_journal"].update(
            bytes=True,
            sha256=hashlib.sha256(content).hexdigest(),
            git_blob_sha=blob,
        )
        index["segments"][0]["predecessor"] = "legacy-blob:" + blob
        expected_failure = "legacy_journal_byte_count_mismatch"
    else:
        content = b"x"
        segment.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        index["segments"][0].update(bytes=True, sha256=digest)
        checkpoint.write_text(
            f"Source `{ 'a' * 40 }`, tree `{ 'b' * 40 }`.\n"
            f"Latest segment: {segment.relative_to(tmp_path).as_posix()} {digest}\n",
            encoding="utf-8",
        )
        index["active_checkpoint_binding"].update(
            latest_segment_sha256=digest,
            checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
        )
        expected_failure = "segment_1_byte_count_mismatch"
    index_path.write_text(json.dumps(index), encoding="utf-8")

    result = verify_construction_continuation(tmp_path)

    assert result["status"] == "invalid"
    assert expected_failure in result["failures"]


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("current_schema_version", "current_index_must_be_schema_v1"),
        ("anchor_schema_version", "anchor_index_must_be_schema_v1"),
        ("current_latest_sequence", "current_index_latest_sequence_mismatch"),
        ("anchor_latest_sequence", "anchor_index_latest_sequence_mismatch"),
    ],
)
def test_sharded_index_builder_rejects_boolean_version_and_sequence_fields(
    tmp_path: Path, mutation: str, expected_error: str
) -> None:
    index_path, _, _, _ = _write_fixture(tmp_path)
    current = json.loads(index_path.read_bytes())
    anchor = json.loads(index_path.read_bytes())
    target = anchor if mutation.startswith("anchor_") else current
    key = "schema_version" if mutation.endswith("schema_version") else "latest_sequence"
    target[key] = True

    with pytest.raises(ValueError, match=expected_error):
        build_sharded_index(
            json.dumps(current).encode(), json.dumps(anchor).encode()
        )


@pytest.mark.parametrize(
    ("mutation", "expected_failure"),
    [
        ("v1_schema_version", "index_schema_invalid"),
        ("v1_latest_sequence", "segments_invalid_or_unbounded"),
        ("v1_segment_sequence", "segment_1_sequence_mismatch"),
        ("v1_checkpoint_sequence", "active_checkpoint_segment_sequence_mismatch"),
        ("v2_schema_version", "index_schema_invalid"),
        ("v2_shard_schema_version", "shard_schema_version_unsupported"),
        ("v2_shard_sequence", "shard_1_descriptor_invalid"),
        ("v2_payload_schema_version", "shard_1_content_invalid"),
    ],
)
def test_custody_rejects_boolean_values_for_integer_versions_and_sequences(
    tmp_path: Path, mutation: str, expected_failure: str
) -> None:
    if mutation.startswith("v1_"):
        index_path, _, _, _ = _write_fixture(tmp_path)
        index = json.loads(index_path.read_bytes())
        if mutation == "v1_schema_version":
            index["schema_version"] = True
        elif mutation == "v1_latest_sequence":
            index["latest_sequence"] = True
        elif mutation == "v1_segment_sequence":
            index["segments"][0]["sequence"] = True
        else:
            index["active_checkpoint_binding"]["latest_segment_sequence"] = True
    else:
        index_path, shard_path = _write_sharded_fixture(tmp_path)
        index = json.loads(index_path.read_bytes())
        if mutation == "v2_schema_version":
            index["schema_version"] = True
        elif mutation == "v2_shard_schema_version":
            index["shard_schema_version"] = True
        elif mutation == "v2_shard_sequence":
            index["shards"][0]["shard_sequence"] = True
        else:
            shard = json.loads(shard_path.read_bytes())
            shard["schema_version"] = True
            shard_bytes = (json.dumps(shard, indent=2) + "\n").encode()
            shard_path.write_bytes(shard_bytes)
            descriptor = index["shards"][0]
            descriptor.update({
                "bytes": len(shard_bytes),
                "sha256": hashlib.sha256(shard_bytes).hexdigest(),
                "git_blob_sha": _blob_sha(shard_bytes),
            })
    index_path.write_text(json.dumps(index), encoding="utf-8")

    result = verify_construction_continuation(tmp_path)

    assert result["status"] == "invalid"
    assert expected_failure in result["failures"]


def _write_sharded_fixture(root: Path) -> tuple[Path, Path]:
    index_path, _, _, _ = _write_fixture(root)
    anchor = index_path.read_bytes()
    current = json.loads(anchor)
    first_sha = current["segments"][-1]["sha256"]
    segment_path = "work/construction/segments/0002-next.md"
    segment_bytes = b"second retained note\n"
    segment_sha = hashlib.sha256(segment_bytes).hexdigest()
    (root / segment_path).write_bytes(segment_bytes)
    entry = {
        "sequence": 2,
        "path": segment_path,
        "predecessor": "segment-sha256:" + first_sha,
        "bytes": len(segment_bytes),
        "sha256": segment_sha,
        "source_commit": "d" * 40,
    }
    current["segments"].append(entry)
    current["latest_sequence"] = 2
    checkpoint = (
        f"Source `{ 'a' * 40 }`, tree `{ 'b' * 40 }`.\n"
        f"Latest segment: {segment_path} {segment_sha}\n"
    ).encode()
    current["checkpoint_sha256"] = hashlib.sha256(checkpoint).hexdigest()
    current["active_checkpoint_binding"].update({
        "latest_segment_sequence": 2,
        "latest_segment_sha256": segment_sha,
        "checkpoint_sha256": hashlib.sha256(checkpoint).hexdigest(),
    })
    current_bytes = json.dumps(current).encode()
    sharded_bytes, shards = build_sharded_index(current_bytes, anchor)
    index_path_v2 = root / "work/construction/index-v2.json"
    index_path_v2.write_bytes(sharded_bytes)
    (root / "work/construction/active_checkpoint_v2.md").write_bytes(checkpoint)
    for relative, content in shards.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return index_path_v2, root / next(iter(shards))


def test_versioned_shards_verify_the_original_segment_and_checkpoint_chain(
    tmp_path: Path,
) -> None:
    index_path, _ = _write_sharded_fixture(tmp_path)

    index = json.loads(index_path.read_bytes())
    result = verify_construction_continuation(tmp_path)

    assert index["schema_version"] == 2
    assert "segments" not in index
    assert index["history_anchor"]["segment_count"] == 1
    assert index["shards"][0]["first_sequence"] == 2
    assert result["status"] == "construction_continuation_custody_ready"
    assert result["segments_verified"] == 2


def test_sharded_append_creates_a_new_shard_and_preserves_prior_bytes(
    tmp_path: Path,
) -> None:
    index_path, first_shard_path = _write_sharded_fixture(tmp_path)
    original_index_bytes = index_path.read_bytes()
    original_index = json.loads(original_index_bytes)
    existing_shards = {
        item["path"]: (tmp_path / item["path"]).read_bytes()
        for item in original_index["shards"]
    }
    existing_shards["work/construction/index.json"] = (
        tmp_path / "work/construction/index.json"
    ).read_bytes()
    first_shard_bytes = existing_shards[first_shard_path.relative_to(tmp_path).as_posix()]

    segment_path = "work/construction/segments/0003-next.md"
    segment_bytes = b"third retained note\n"
    segment_sha = hashlib.sha256(segment_bytes).hexdigest()
    previous_sha = original_index["shards"][0]["sha256"]
    old_segments = json.loads(first_shard_bytes)["segments"]
    entry = {
        "sequence": 3,
        "path": segment_path,
        "predecessor": "segment-sha256:" + old_segments[-1]["sha256"],
        "bytes": len(segment_bytes),
        "sha256": segment_sha,
        "source_commit": "d" * 40,
    }
    checkpoint_bytes = (
        f"Source `{ 'a' * 40 }`, tree `{ 'b' * 40 }`.\n"
        f"Latest segment: {segment_path} {segment_sha}\n"
    ).encode()

    updated_index, new_shards = append_segments_to_sharded_index(
        original_index_bytes, existing_shards, [entry], checkpoint_bytes
    )
    updated = json.loads(updated_index)
    assert len(new_shards) == 1
    assert updated["shards"][:-1] == original_index["shards"]
    assert updated["shards"][-1]["predecessor"] == f"shard-sha256:{previous_sha}"
    assert existing_shards[first_shard_path.relative_to(tmp_path).as_posix()] == first_shard_bytes

    (tmp_path / segment_path).write_bytes(segment_bytes)
    (tmp_path / "work/construction/active_checkpoint_v2.md").write_bytes(checkpoint_bytes)
    for relative, payload in new_shards.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
    index_path.write_bytes(updated_index)

    result = verify_construction_continuation(tmp_path)
    assert result["status"] == "construction_continuation_custody_ready"
    assert result["segments_verified"] == 3


def test_repository_migration_freezes_v1_and_shards_only_the_continuation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    index_path, _, first_segment, checkpoint_path = _write_fixture(tmp_path)
    anchor_index = index_path.read_bytes()
    anchor_checkpoint = checkpoint_path.read_bytes()
    anchor_index_path = tmp_path / "anchor-v1.json"
    anchor_checkpoint_path = tmp_path / "anchor-v1-checkpoint.md"
    anchor_index_path.write_bytes(anchor_index)
    anchor_checkpoint_path.write_bytes(anchor_checkpoint)

    current = json.loads(anchor_index)
    second_path = "work/construction/segments/0002-next.md"
    second_bytes = b"continuation after the frozen v1 anchor\n"
    second_sha = hashlib.sha256(second_bytes).hexdigest()
    (tmp_path / second_path).write_bytes(second_bytes)
    current["segments"].append({
        "sequence": 2,
        "path": second_path,
        "predecessor": "segment-sha256:" + current["segments"][-1]["sha256"],
        "bytes": len(second_bytes),
        "sha256": second_sha,
        "source_commit": "d" * 40,
    })
    current["latest_sequence"] = 2
    checkpoint = (
        f"Source `{ 'a' * 40 }`, tree `{ 'b' * 40 }`.\n"
        f"Latest segment: {second_path} {second_sha}\n"
    ).encode()
    checkpoint_path.write_bytes(checkpoint)
    digest = hashlib.sha256(checkpoint).hexdigest()
    current["checkpoint_sha256"] = digest
    current["active_checkpoint_binding"].update({
        "latest_segment_sequence": 2,
        "latest_segment_sha256": second_sha,
        "checkpoint_sha256": digest,
    })
    index_path.write_text(json.dumps(current), encoding="utf-8")

    real_replace = sharding.os.replace

    def interrupt_before_anchor_index_replace(source: str, destination: str) -> None:
        if Path(destination) == index_path:
            raise OSError("simulated interruption before frozen v1 index replacement")
        real_replace(source, destination)

    monkeypatch.setattr(sharding.os, "replace", interrupt_before_anchor_index_replace)
    with pytest.raises(OSError, match="simulated interruption"):
        migrate_repository(tmp_path, anchor_index_path, anchor_checkpoint_path)
    monkeypatch.setattr(sharding.os, "replace", real_replace)
    assert (tmp_path / "work/construction/index-v2.json").is_file()
    assert index_path.read_bytes() != anchor_index

    result = migrate_repository(tmp_path, anchor_index_path, anchor_checkpoint_path)

    assert result["status"] == "construction_index_sharded_v2_ready"
    assert index_path.read_bytes() == anchor_index
    assert checkpoint_path.read_bytes() == anchor_checkpoint
    root = json.loads((tmp_path / "work/construction/index-v2.json").read_bytes())
    assert root["history_anchor"]["source_index_git_blob_sha"] == _blob_sha(anchor_index)
    assert root["history_anchor"]["segment_count"] == 1
    assert len(root["shards"]) == 1
    assert root["shards"][0]["first_sequence"] == 2
    assert root["shards"][0]["last_sequence"] == 2
    assert verify_construction_continuation(tmp_path)["segments_verified"] == 2


@pytest.mark.parametrize(
    ("mutation", "expected_failure"),
    [
        ("bytes", "shard_1_sha256_mismatch"),
        ("predecessor", "shard_1_predecessor_mismatch"),
        ("range", "shard_1_range_invalid"),
        ("path", "shard_1_path_invalid"),
    ],
)
def test_versioned_shards_reject_tampering_and_rebinding(
    tmp_path: Path, mutation: str, expected_failure: str
) -> None:
    index_path, shard_path = _write_sharded_fixture(tmp_path)
    index = json.loads(index_path.read_bytes())
    if mutation == "bytes":
        shard_path.write_bytes(shard_path.read_bytes() + b"tampered")
    elif mutation == "predecessor":
        index["shards"][0]["predecessor"] = "index-sha256:" + "f" * 64
    elif mutation == "range":
        index["shards"][0]["last_sequence"] = 3
    else:
        index["shards"][0]["path"] = "work/construction/active_checkpoint_v2.md"
    index_path.write_text(json.dumps(index), encoding="utf-8")

    result = verify_construction_continuation(tmp_path)

    assert result["status"] == "invalid"
    assert expected_failure in result["failures"]


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


def test_sharded_history_anchor_rejects_boolean_checkpoint_sequence(
    tmp_path: Path,
) -> None:
    index_path, _, _, _ = _write_fixture(tmp_path)
    original_anchor_bytes = index_path.read_bytes()
    sharded_bytes, _ = build_sharded_index(
        original_anchor_bytes, original_anchor_bytes
    )
    anchor = json.loads(original_anchor_bytes)
    anchor["active_checkpoint_binding"]["latest_segment_sequence"] = True
    mutated_anchor_bytes = (json.dumps(anchor, indent=2) + "\n").encode()
    index_path.write_bytes(mutated_anchor_bytes)

    sharded_index = json.loads(sharded_bytes)
    sharded_index["history_anchor"].update(
        source_index_sha256=hashlib.sha256(mutated_anchor_bytes).hexdigest(),
        source_index_git_blob_sha=_blob_sha(mutated_anchor_bytes),
    )
    (tmp_path / "work/construction/index-v2.json").write_text(
        json.dumps(sharded_index), encoding="utf-8"
    )

    result = verify_construction_continuation(tmp_path)

    assert result["status"] == "invalid"
    assert "history_anchor_checkpoint_sequence_mismatch" in result["failures"]


@pytest.mark.parametrize(
    ("target", "mutation", "expected_failure"),
    [
        ("legacy", "tamper", "legacy_journal_sha256_mismatch"),
        ("segment", "tamper", "segment_1_sha256_mismatch"),
        ("segment", "remove", "segment_1_unreadable"),
        ("index", "predecessor", "segment_1_predecessor_mismatch"),
        ("checkpoint", "tamper", "active_checkpoint_sha256_mismatch"),
        ("index", "checkpoint", "active_checkpoint_segment_sequence_mismatch"),
        ("index", "duplicate", "segments_invalid_or_unbounded"),
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

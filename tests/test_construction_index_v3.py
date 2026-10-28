from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.construction_index_sharding import build_sharded_index
from scripts.construction_index_v3 import (
    MAX_HEAD_BYTES,
    MAX_V3_COMPACT_CHECKPOINT_BYTES,
    V3_CHECKPOINT_PATH,
    V3_INDEX_PATH,
    append_v3_shard,
    begin_v3_checkpoint_chain,
    migrate_v2_head,
    render_v3_checkpoint,
    verify_v3_reader,
)
from scripts.verify_construction_continuation_custody import (
    _read_regular,
    verify_construction_continuation,
)
from tests.test_construction_continuation_custody import _write_fixture

pytestmark = pytest.mark.no_legacy_skip


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _make_v3_fixture(root: Path) -> tuple[bytes, dict[str, bytes]]:
    v1_path, _, _, checkpoint_path = _write_fixture(root)
    v1_bytes = v1_path.read_bytes()
    v2_bytes, shards = build_sharded_index(v1_bytes, v1_bytes)
    (root / "work/construction/index-v2.json").write_bytes(v2_bytes)
    (root / "work/construction/active_checkpoint_v2.md").write_bytes(checkpoint_path.read_bytes())
    for relative, payload in shards.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    v3_bytes = migrate_v2_head(v2_bytes, checkpoint_path.read_bytes(), read=_reader(root))
    (root / V3_INDEX_PATH).write_bytes(v3_bytes)
    return v3_bytes, shards


def _reader(root: Path):
    return lambda path, limit: _read_regular(root, path, limit=limit)


def _append_one(root: Path, head: bytes, seq: int, previous: str) -> bytes:
    segment_path = f"work/construction/segments/v3-{seq:03d}.md"
    payload = f"retained v3 record {seq}\n".encode()
    digest = _sha(payload)
    entry = {
        "sequence": seq,
        "path": segment_path,
        "predecessor": f"segment-sha256:{previous}",
        "bytes": len(payload),
        "sha256": digest,
        "source_commit": "a" * 40,
    }
    checkpoint = (
        f"Source `{ 'a' * 40 }`, tree `{ 'b' * 40 }`.\n"
        f"Latest construction segment: `{segment_path}`\n"
        f"Latest segment SHA-256: `{digest}`\n"
    ).encode()
    new_head, shards = append_v3_shard(
        head, {}, [entry], checkpoint, read=_reader(root)
    )
    (root / segment_path).write_bytes(payload)
    (root / V3_CHECKPOINT_PATH).write_bytes(checkpoint)
    for relative, shard_bytes in shards.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(shard_bytes)
    (root / V3_INDEX_PATH).write_bytes(new_head)
    return new_head


def _append_compact_checkpoint(root: Path, head_bytes: bytes, seq: int) -> bytes:
    head = json.loads(head_bytes)
    source_commit = f"{seq:040x}"[-40:]
    source_tree = f"{seq + 1:040x}"[-40:]
    segment_path = f"work/construction/segments/compact-{seq:04d}.md"
    evidence_path = f"work/construction/evidence/compact-{seq:04d}.json"
    payload = f"compact checkpoint segment {seq}\n".encode()
    digest = _sha(payload)
    predecessor = head["checkpoint_chain"]["latest"]
    predecessor_record = {
        **predecessor,
        "source_commit": source_commit,
        "source_tree": source_tree,
    }
    evidence = {
        "source": {
            "verified_remote_main": source_commit,
            "verified_remote_main_tree": source_tree,
            "remote_ref_readback": {"commit": source_commit},
        },
        "publication": {
            "verified_main_file_readbacks": {
                "active_checkpoint_v3": predecessor["git_blob_sha"],
            },
        },
    }
    evidence_bytes = (json.dumps(evidence, indent=2) + "\n").encode()
    evidence_sha = _sha(evidence_bytes)
    entry = {
        "sequence": seq,
        "path": segment_path,
        "predecessor": f"segment-sha256:{head['latest_segment_sha256']}",
        "bytes": len(payload),
        "sha256": digest,
        "evidence_path": evidence_path,
        "evidence_sha256": evidence_sha,
        "evidence_bytes": len(evidence_bytes),
        "source_commit": source_commit,
        "source_tree": source_tree,
    }
    binding = head["active_checkpoint_binding"]
    checkpoint = render_v3_checkpoint(
        sequence=seq,
        latest_main_commit=source_commit,
        latest_main_tree=source_tree,
        binding_origin_commit=binding["source_commit"],
        binding_origin_tree=binding["source_tree"],
        segment_path=segment_path,
        segment_sha256=digest,
        predecessor=predecessor_record,
    )
    (root / segment_path).parent.mkdir(parents=True, exist_ok=True)
    (root / segment_path).write_bytes(payload)
    (root / evidence_path).parent.mkdir(parents=True, exist_ok=True)
    (root / evidence_path).write_bytes(evidence_bytes)
    new_head, artifacts = append_v3_shard(
        head_bytes, {}, [entry], checkpoint, read=_reader(root)
    )
    for relative, data in artifacts.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    (root / V3_CHECKPOINT_PATH).write_bytes(checkpoint)
    (root / V3_INDEX_PATH).write_bytes(new_head)
    return new_head


def test_v3_head_is_constant_shape_and_verifies_immutable_v2_anchor(tmp_path: Path) -> None:
    head, _ = _make_v3_fixture(tmp_path)
    doc = json.loads(head)
    result = verify_construction_continuation(tmp_path)

    assert doc["schema_version"] == 3
    assert "shards" not in doc
    assert "segments" not in doc
    assert doc["latest_shard"] is None
    assert len(head) <= MAX_HEAD_BYTES
    assert result["status"] == "construction_continuation_custody_ready"
    assert result["segments_verified"] == 1


def test_v3_chain_appends_without_growing_a_root_descriptor_list(tmp_path: Path) -> None:
    head, _ = _make_v3_fixture(tmp_path)
    anchor = json.loads(head)["history_anchor"]["latest_segment_sha256"]
    sizes = []
    previous = anchor
    for seq in range(2, 22):
        head = _append_one(tmp_path, head, seq, previous)
        previous = json.loads(head)["latest_segment_sha256"]
        sizes.append(len(head))
        root = json.loads(head)
        assert "shards" not in root
        assert root["shard_count"] == seq - 1
        assert len(root) == 9
        assert len(head) <= MAX_HEAD_BYTES

    result = verify_construction_continuation(tmp_path)
    assert result["status"] == "construction_continuation_custody_ready"
    assert result["segments_verified"] == 21
    assert max(sizes) - min(sizes) < 24


def test_compact_checkpoint_chain_stays_bounded_and_preserves_predecessor_bindings(
    tmp_path: Path,
) -> None:
    head, _ = _make_v3_fixture(tmp_path)
    previous = json.loads(head)["history_anchor"]["latest_segment_sha256"]
    head = _append_one(tmp_path, head, 2, previous)
    source_commit = f"{3:040x}"
    source_tree = f"{4:040x}"
    head = begin_v3_checkpoint_chain(
        head, source_commit=source_commit, source_tree=source_tree, read=_reader(tmp_path)
    )
    (tmp_path / V3_INDEX_PATH).write_bytes(head)

    head_sizes = []
    checkpoint_sizes = []
    for seq in range(3, 35):
        head = _append_compact_checkpoint(tmp_path, head, seq)
        head_sizes.append(len(head))
        checkpoint_sizes.append((tmp_path / V3_CHECKPOINT_PATH).stat().st_size)
        assert len(head) <= MAX_HEAD_BYTES
        assert checkpoint_sizes[-1] <= MAX_V3_COMPACT_CHECKPOINT_BYTES

    result = verify_construction_continuation(tmp_path)
    assert result["status"] == "construction_continuation_custody_ready"
    assert result["segments_verified"] == 34
    assert max(head_sizes) - min(head_sizes) < 24
    assert max(checkpoint_sizes) - min(checkpoint_sizes) < 16
    assert json.loads(head)["checkpoint_chain"]["latest"]["sequence"] == 34

    # Recompute the changed shard and head identities after altering a link;
    # custody must still detect the broken logical predecessor binding.
    head_doc = json.loads(head)
    shard_path = head_doc["latest_shard"]["path"]
    shard_file = tmp_path / shard_path
    shard_doc = json.loads(shard_file.read_bytes())
    shard_doc["checkpoint_transition"]["predecessor"]["sha256"] = "0" * 64
    shard_bytes = (json.dumps(shard_doc, indent=2) + "\n").encode()
    shard_file.write_bytes(shard_bytes)
    descriptor = head_doc["latest_shard"]
    descriptor.update(
        bytes=len(shard_bytes),
        sha256=_sha(shard_bytes),
        git_blob_sha=hashlib.sha1(
            b"blob " + str(len(shard_bytes)).encode() + b"\0" + shard_bytes
        ).hexdigest(),
    )
    altered_head = (json.dumps(head_doc, indent=2) + "\n").encode()
    (tmp_path / V3_INDEX_PATH).write_bytes(altered_head)
    altered_result = verify_construction_continuation(tmp_path)
    assert altered_result["status"] == "invalid"
    assert "v3_checkpoint_transition_invalid" in altered_result["failures"]


def test_v3_verification_fails_closed_on_missing_or_tampered_predecessor(tmp_path: Path) -> None:
    head, _ = _make_v3_fixture(tmp_path)
    anchor = json.loads(head)["history_anchor"]["latest_segment_sha256"]
    head = _append_one(tmp_path, head, 2, anchor)
    descriptor = json.loads(head)["latest_shard"]
    path = tmp_path / descriptor["path"]
    path.write_bytes(path.read_bytes() + b"tampered")

    result = verify_construction_continuation(tmp_path)

    assert result["status"] == "invalid"
    assert any("v3_shard_" in failure for failure in result["failures"])


def test_v3_anchor_identity_and_predecessor_are_required(tmp_path: Path) -> None:
    head, _ = _make_v3_fixture(tmp_path)
    doc = json.loads(head)
    doc["history_anchor"]["git_blob_sha"] = "0" * 40
    altered = json.dumps(doc, indent=2).encode() + b"\n"
    result = verify_v3_reader(_reader(tmp_path), V3_INDEX_PATH, altered, json.loads(altered))

    assert result["status"] == "invalid"
    assert "v3_history_anchor_git_blob_mismatch" in result["failures"]


def test_v3_append_rejects_a_broken_segment_predecessor(tmp_path: Path) -> None:
    head, _ = _make_v3_fixture(tmp_path)
    entry = {
        "sequence": 2,
        "path": "work/construction/segments/broken.md",
        "predecessor": "segment-sha256:" + "0" * 64,
        "bytes": 1,
        "sha256": "0" * 64,
        "source_commit": "a" * 40,
    }
    checkpoint = b"Source `aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa`, tree `bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`. broken.md " + b"0" * 64
    with pytest.raises(ValueError, match="v3_new_segment_binding_invalid"):
        append_v3_shard(head, {}, [entry], checkpoint, read=_reader(tmp_path))


def test_v3_append_reconstructs_an_identical_orphan_shard_and_rejects_conflicts(
    tmp_path: Path,
) -> None:
    head, _ = _make_v3_fixture(tmp_path)
    prior = json.loads(head)["history_anchor"]["latest_segment_sha256"]
    payload = b"recoverable segment\n"
    digest = _sha(payload)
    entry = {
        "sequence": 2,
        "path": "work/construction/segments/recovery.md",
        "predecessor": f"segment-sha256:{prior}",
        "bytes": len(payload),
        "sha256": digest,
        "source_commit": "a" * 40,
    }
    checkpoint = (
        f"Source `{ 'a' * 40 }`, tree `{ 'b' * 40 }`.\n"
        f"Latest construction segment: `{entry['path']}`\n{digest}\n"
    ).encode()
    first_head, first_shards = append_v3_shard(
        head, {}, [entry], checkpoint, read=_reader(tmp_path)
    )
    shard_path, shard_bytes = next(iter(first_shards.items()))
    retry_head, retry_shards = append_v3_shard(
        head, {shard_path: shard_bytes}, [entry], checkpoint, read=_reader(tmp_path)
    )

    assert retry_head == first_head
    assert retry_shards == first_shards
    with pytest.raises(ValueError, match="v3_existing_shard_conflicts_with_reconstruction"):
        append_v3_shard(
            head, {shard_path: b"different"}, [entry], checkpoint, read=_reader(tmp_path)
        )

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from scripts.construction_source_preflight import candidate_manifest, verify_candidate_publication
from scripts.construction_index_sharding import (
    append_segments_to_sharded_index,
    build_sharded_index,
)
from scripts.construction_index_v3 import (
    V3_CHECKPOINT_PATH,
    V3_INDEX_PATH,
    append_v3_shard,
    migrate_v2_head,
)
from tests.test_construction_continuation_custody import _write_fixture

pytestmark = pytest.mark.no_legacy_skip


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def candidate(root: Path, *, source: bytes = b'value = 1\n') -> tuple[dict, str]:
    _write_fixture(root)
    git(root, 'init', '-q')
    git(root, 'add', '.')
    git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        'commit', '-qm', 'fixture baseline')
    parent = git(root, 'rev-parse', 'HEAD')
    (root / 'source.py').write_bytes(source)
    git(root, 'add', '.')
    tree = git(root, 'write-tree')
    return candidate_manifest(root, tree, parent), parent


def test_exact_tested_tree_and_remote_blobs_admit_publication(tmp_path: Path) -> None:
    manifest, _ = candidate(tmp_path)
    uploaded = {row['path']: row['git_blob_sha'] for row in manifest['files']}
    result = verify_candidate_publication(tmp_path, manifest, observed_blobs=uploaded)
    assert result['status'] == 'candidate_integrity_ready_for_ref_update'
    assert result['remote_ref_updated'] is False
    assert verify_candidate_publication(tmp_path, manifest)['status'] == (
        'candidate_integrity_ready_for_blob_upload')


def test_candidate_guard_rejects_boolean_manifest_schema_version(
    tmp_path: Path,
) -> None:
    manifest, _ = candidate(tmp_path)
    manifest["schema_version"] = True

    result = verify_candidate_publication(tmp_path, manifest)

    assert result["status"] == "invalid"
    assert "candidate_unreadable:candidate_manifest_identity_invalid" in result["failures"]


@pytest.mark.parametrize('corruption', ['remote_blob', 'local_digest', 'omitted_path', 'null_source'])
def test_candidate_guard_rejects_source_or_transport_corruption(tmp_path: Path, corruption: str) -> None:
    source = b'value = 1\x00\n' if corruption == 'null_source' else b'value = 1\n'
    manifest, _ = candidate(tmp_path, source=source)
    uploaded = {row['path']: row['git_blob_sha'] for row in manifest['files']}
    if corruption == 'remote_blob':
        uploaded['source.py'] = '0' * 40
    elif corruption == 'local_digest':
        manifest['files'][0]['sha256'] = '0' * 64
    elif corruption == 'omitted_path':
        manifest['files'] = []
    assert verify_candidate_publication(tmp_path, manifest, observed_blobs=uploaded)['status'] == 'invalid'


@pytest.mark.parametrize(
    ("target", "expected_failure"),
    [
        ("legacy", "custody:legacy_journal_byte_count_mismatch"),
        ("segment", "custody:segment_1_byte_count_mismatch"),
    ],
)
def test_candidate_guard_rejects_boolean_custody_byte_counts(
    tmp_path: Path, target: str, expected_failure: str
) -> None:
    _write_fixture(tmp_path)
    index_path = tmp_path / "work/construction/index.json"
    index = json.loads(index_path.read_bytes())
    legacy = tmp_path / index["legacy_journal"]["path"]
    segment = tmp_path / index["segments"][0]["path"]
    checkpoint = tmp_path / "work/construction/active_checkpoint.md"
    if target == "legacy":
        content = b"x"
        legacy.write_bytes(content)
        blob = hashlib.sha1(b"blob 1\0x").hexdigest()
        index["legacy_journal"].update(
            bytes=True,
            sha256=hashlib.sha256(content).hexdigest(),
            git_blob_sha=blob,
        )
        index["segments"][0]["predecessor"] = "legacy-blob:" + blob
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
    index_path.write_text(json.dumps(index), encoding="utf-8")
    git(tmp_path, "init", "-q")
    git(tmp_path, "add", ".")
    git(tmp_path, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
        "commit", "-qm", "invalid byte-count baseline")
    parent = git(tmp_path, "rev-parse", "HEAD")
    (tmp_path / "source.py").write_bytes(b"value = 1\n")
    git(tmp_path, "add", "source.py")
    manifest = candidate_manifest(tmp_path, git(tmp_path, "write-tree"), parent)

    result = verify_candidate_publication(tmp_path, manifest)

    assert result["status"] == "invalid"
    assert expected_failure in result["failures"]


def test_candidate_guard_checks_frozen_tree_even_with_clean_worktree_bytes(tmp_path: Path) -> None:
    _manifest, parent = candidate(tmp_path)
    journal = tmp_path / 'work/sentientos_night_watch_continuation.md'
    saved = journal.read_bytes()
    journal.write_bytes(saved + b'unexpected append\n')
    git(tmp_path, 'add', '.')
    tree = git(tmp_path, 'write-tree')
    manifest = candidate_manifest(tmp_path, tree, parent)
    journal.write_bytes(saved)  # A disk-only check would now miss staged corruption.
    result = verify_candidate_publication(tmp_path, manifest)
    assert 'custody:legacy_journal_git_blob_mismatch' in result['failures']


def test_candidate_guard_rejects_redefinition_of_frozen_custody(tmp_path: Path) -> None:
    _manifest, parent = candidate(tmp_path)
    index_path = tmp_path / 'work/construction/index.json'
    index = json.loads(index_path.read_bytes())
    index['legacy_journal']['source_commit'] = 'f' * 40
    index_path.write_text(json.dumps(index))
    git(tmp_path, 'add', '.')
    manifest = candidate_manifest(tmp_path, git(tmp_path, 'write-tree'), parent)
    assert 'frozen_journal_definition_changed' in verify_candidate_publication(tmp_path, manifest)['failures']


def test_candidate_guard_accepts_exact_v1_to_v2_shard_migration(tmp_path: Path) -> None:
    _manifest, parent = candidate(tmp_path)
    index_path = tmp_path / 'work/construction/index.json'
    anchor_bytes = git(tmp_path, 'show', f'{parent}:work/construction/index.json').encode()
    sharded_index, shards = build_sharded_index(index_path.read_bytes(), anchor_bytes)
    v2_path = tmp_path / 'work/construction/index-v2.json'
    v2_path.write_bytes(sharded_index)
    for relative, content in shards.items():
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    git(tmp_path, 'add', '.')
    manifest = candidate_manifest(tmp_path, git(tmp_path, 'write-tree'), parent)

    result = verify_candidate_publication(tmp_path, manifest)

    assert result['status'] == 'candidate_integrity_ready_for_blob_upload'
    assert result['failures'] == []


def test_candidate_guard_rejects_rebinding_the_v1_history_anchor(tmp_path: Path) -> None:
    _manifest, parent = candidate(tmp_path)
    index_path = tmp_path / 'work/construction/index.json'
    original = index_path.read_bytes()
    sharded_index, shards = build_sharded_index(original, original)
    index = json.loads(sharded_index)
    index['history_anchor']['latest_segment_sha256'] = 'f' * 64
    (tmp_path / 'work/construction/index-v2.json').write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + '\n'
    )
    git(tmp_path, 'add', '.')
    manifest = candidate_manifest(tmp_path, git(tmp_path, 'write-tree'), parent)

    result = verify_candidate_publication(tmp_path, manifest)

    assert result['status'] == 'invalid'
    assert 'custody:history_anchor_latest_segment_mismatch' in result['failures']


def test_candidate_guard_accepts_v2_append_with_immutable_shard_prefix(tmp_path: Path) -> None:
    _write_fixture(tmp_path)
    git(tmp_path, 'init', '-q')
    git(tmp_path, 'add', '.')
    git(tmp_path, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        'commit', '-qm', 'v1 baseline')
    index_path = tmp_path / 'work/construction/index.json'
    v2_path = tmp_path / 'work/construction/index-v2.json'
    original = index_path.read_bytes()
    sharded_index, shard_files = build_sharded_index(original, original)
    v2_path.write_bytes(sharded_index)
    for relative, payload in shard_files.items():
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    git(tmp_path, 'add', '.')
    git(tmp_path, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        'commit', '-qm', 'v2 migration')
    parent = git(tmp_path, 'rev-parse', 'HEAD')

    root_index = json.loads(v2_path.read_bytes())
    prior_shards = dict(shard_files)
    prior_shards['work/construction/index.json'] = original
    segment_path = 'work/construction/segments/0002-next.md'
    segment_bytes = b'second retained note\n'
    segment_sha = hashlib.sha256(segment_bytes).hexdigest()
    entry = {
        'sequence': 2,
        'path': segment_path,
        'predecessor': 'segment-sha256:' + json.loads(original)['segments'][-1]['sha256'],
        'bytes': len(segment_bytes),
        'sha256': segment_sha,
        'source_commit': 'd' * 40,
    }
    checkpoint = (
        f"Source `{ 'a' * 40 }`, tree `{ 'b' * 40 }`.\n"
        f"Latest segment: {segment_path} {segment_sha}\n"
    ).encode()
    updated_index, new_shards = append_segments_to_sharded_index(
        v2_path.read_bytes(), prior_shards, [entry], checkpoint
    )
    v2_path.write_bytes(updated_index)
    (tmp_path / segment_path).write_bytes(segment_bytes)
    (tmp_path / 'work/construction/active_checkpoint_v2.md').write_bytes(checkpoint)
    for relative, payload in new_shards.items():
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    git(tmp_path, 'add', '.')
    manifest = candidate_manifest(tmp_path, git(tmp_path, 'write-tree'), parent)

    result = verify_candidate_publication(tmp_path, manifest)

    updated_root = json.loads(updated_index)
    assert updated_root['shards'][:-1] == root_index['shards']
    assert result['status'] == 'candidate_integrity_ready_for_blob_upload'
    assert result['failures'] == []


def test_candidate_guard_accepts_v3_migration_anchored_to_exact_v2_root(
    tmp_path: Path,
) -> None:
    _write_fixture(tmp_path)
    v1_path = tmp_path / 'work/construction/index.json'
    v1_bytes = v1_path.read_bytes()
    v2_bytes, v2_shards = build_sharded_index(v1_bytes, v1_bytes)
    v2_path = tmp_path / 'work/construction/index-v2.json'
    v2_path.write_bytes(v2_bytes)
    for relative, payload in v2_shards.items():
        (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / relative).write_bytes(payload)
    git(tmp_path, 'init', '-q')
    git(tmp_path, 'add', '.')
    git(tmp_path, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        'commit', '-qm', 'verified v2 baseline')
    parent = git(tmp_path, 'rev-parse', 'HEAD')

    def read(path: str, limit: int) -> bytes:
        payload = (tmp_path / path).read_bytes()
        if len(payload) > limit:
            raise ValueError('fixture_file_too_large')
        return payload

    v2_checkpoint = (tmp_path / 'work/construction/active_checkpoint.md').read_bytes()
    v3_head = migrate_v2_head(v2_bytes, v2_checkpoint, read=read)
    original = json.loads(v2_bytes)
    previous_sha = original['active_checkpoint_binding']['latest_segment_sha256']
    segment_path = 'work/construction/segments/v3-next.md'
    segment_bytes = b'v3 continuation record\n'
    segment_sha = hashlib.sha256(segment_bytes).hexdigest()
    entry = {
        'sequence': 2,
        'path': segment_path,
        'predecessor': 'segment-sha256:' + previous_sha,
        'bytes': len(segment_bytes),
        'sha256': segment_sha,
        'source_commit': 'a' * 40,
    }
    checkpoint = (
        f"Source `{ 'a' * 40 }`, tree `{ 'b' * 40 }`.\n"
        f"Latest construction segment: `{segment_path}`\n"
        f"Latest segment SHA-256: `{segment_sha}`\n"
    ).encode()
    v3_head, v3_shards = append_v3_shard(
        v3_head, {}, [entry], checkpoint, read=read
    )
    (tmp_path / V3_INDEX_PATH).write_bytes(v3_head)
    (tmp_path / V3_CHECKPOINT_PATH).write_bytes(checkpoint)
    (tmp_path / segment_path).write_bytes(segment_bytes)
    for relative, payload in v3_shards.items():
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    git(tmp_path, 'add', '.')
    manifest = candidate_manifest(tmp_path, git(tmp_path, 'write-tree'), parent)

    result = verify_candidate_publication(tmp_path, manifest)

    assert result['status'] == 'candidate_integrity_ready_for_blob_upload'
    assert result['failures'] == []
    assert json.loads((tmp_path / V3_INDEX_PATH).read_bytes())['history_anchor']['git_blob_sha'] == hashlib.sha1(
        b'blob ' + str(len(v2_bytes)).encode() + b'\0' + v2_bytes
    ).hexdigest()
    assert (tmp_path / 'work/construction/index-v2.json').read_bytes() == v2_bytes

    git(tmp_path, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
        'commit', '-qm', 'v3 continuation')
    parent_v3 = git(tmp_path, 'rev-parse', 'HEAD')
    v3_head = (tmp_path / V3_INDEX_PATH).read_bytes()
    v3_doc = json.loads(v3_head)
    previous_sha = v3_doc['latest_segment_sha256']
    next_segment = 'work/construction/segments/v3-next-2.md'
    next_bytes = b'next v3 continuation record\n'
    next_sha = hashlib.sha256(next_bytes).hexdigest()
    next_entry = {
        'sequence': 3,
        'path': next_segment,
        'predecessor': 'segment-sha256:' + previous_sha,
        'bytes': len(next_bytes),
        'sha256': next_sha,
        'source_commit': 'a' * 40,
    }
    next_checkpoint = (
        f"Source `{ 'a' * 40 }`, tree `{ 'b' * 40 }`.\n"
        f"Latest construction segment: `{next_segment}`\n{next_sha}\n"
    ).encode()
    v3_read = lambda path, limit: (tmp_path / path).read_bytes()
    next_head, next_shards = append_v3_shard(
        v3_head, {}, [next_entry], next_checkpoint, read=v3_read
    )
    (tmp_path / V3_INDEX_PATH).write_bytes(next_head)
    (tmp_path / V3_CHECKPOINT_PATH).write_bytes(next_checkpoint)
    (tmp_path / next_segment).write_bytes(next_bytes)
    for relative, payload in next_shards.items():
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    git(tmp_path, 'add', '.')
    next_manifest = candidate_manifest(tmp_path, git(tmp_path, 'write-tree'), parent_v3)

    next_result = verify_candidate_publication(tmp_path, next_manifest)

    assert next_result['status'] == 'candidate_integrity_ready_for_blob_upload', next_result
    assert next_result['failures'] == []

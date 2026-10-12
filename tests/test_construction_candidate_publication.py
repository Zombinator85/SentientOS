from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts.construction_source_preflight import candidate_manifest, verify_candidate_publication
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

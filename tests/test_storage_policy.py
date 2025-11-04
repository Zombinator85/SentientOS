from __future__ import annotations

from tools.storage_policy import StoragePolicyConfig, rotate_text_digests, stash_highlight


def test_storage_policy_rotation(tmp_path) -> None:
    digest_dir = tmp_path / "digests"
    highlight_dir = tmp_path / "highlights"
    policy = StoragePolicyConfig(digest_dir=digest_dir, highlight_dir=highlight_dir, max_digests=2)

    rotate_text_digests(policy, ["entry-1"])
    rotate_text_digests(policy, ["entry-2"])
    rotate_text_digests(policy, ["entry-3"])

    files = sorted(digest_dir.glob("*.md"))
    assert len(files) <= 2

    path = stash_highlight(policy, "capture.png", b"data")
    assert path.exists()

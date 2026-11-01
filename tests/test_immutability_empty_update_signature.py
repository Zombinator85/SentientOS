from __future__ import annotations

import pytest
from nacl.signing import SigningKey

from sentientos.immutability import reset_key_cache, update_manifest, verify_manifest_signature

pytestmark = pytest.mark.no_legacy_skip


def test_empty_update_signs_manifest_hash_with_string_value(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    key = SigningKey.generate()
    private_path = tmp_path / "private.key"
    public_path = tmp_path / "public.key"
    private_path.write_bytes(key.encode())
    public_path.write_bytes(key.verify_key.encode())
    monkeypatch.setenv("IMMUTABILITY_SIGNING_KEY", str(private_path))
    monkeypatch.setenv("IMMUTABILITY_VERIFY_KEY", str(public_path))
    reset_key_cache()

    try:
        manifest = update_manifest([], manifest_path=tmp_path / "manifest.json")
        assert verify_manifest_signature(manifest)
    finally:
        reset_key_cache()

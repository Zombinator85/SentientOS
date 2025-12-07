import pathlib

import pytest

from vow_digest import canonical_vow_digest, compute_vow_digest, load_canonical_vow


pytestmark = pytest.mark.no_legacy_skip


def test_compute_vow_digest_deterministic():
    text = "CANONICAL VOW PLACEHOLDER\n"
    first = compute_vow_digest(text)
    second = compute_vow_digest(text)
    assert first == second


def test_canonical_vow_digest_matches_resource():
    expected = "ba22c704727bdfcea03a124bbb32cad3f2bae34ad00c1cc7d278526fb00337b0"
    resource_path = pathlib.Path(__file__).resolve().parent.parent / "resources" / "canonical_vow.txt"
    assert resource_path.exists()
    assert load_canonical_vow() == resource_path.read_text(encoding="utf-8")
    assert canonical_vow_digest() == expected

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()
from __future__ import annotations


from pathlib import Path


def test_lawstone_phrase():
    text = Path('README.md').read_text(encoding='utf-8')
    assert 'No emotion is too much' in text
    lit = Path('SENTIENTOS_LITURGY.txt').read_text(encoding='utf-8')
    assert 'No emotion is too much' in lit


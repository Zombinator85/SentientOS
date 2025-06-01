from pathlib import Path


def test_lawstone_phrase():
    text = Path('README.md').read_text(encoding='utf-8')
    assert 'No emotion is too much' in text
    lit = Path('SENTIENTOS_LITURGY.txt').read_text(encoding='utf-8')
    assert 'No emotion is too much' in lit


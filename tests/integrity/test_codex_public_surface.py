from sentientos import codex


def test_codex_public_surface_contract():
    expected = (
        "CodexHealer",
        "GenesisForge",
        "IntegrityDaemon",
        "SpecAmender",
    )

    assert codex.__all__ == expected
    for symbol in expected:
        assert hasattr(codex, symbol)

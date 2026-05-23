from sentientos.codex_task_scaffold_preset_verifier import verify_codex_task_scaffold_presets


def test_verify_all_presets() -> None:
    result = verify_codex_task_scaffold_presets()
    assert result.status == "codex_task_scaffold_preset_verifier_ready"
    assert "metadata_verification" in result.checked_preset_ids


def test_verify_single_preset() -> None:
    result = verify_codex_task_scaffold_presets("metadata_verification")
    assert result.status == "codex_task_scaffold_preset_verifier_ready"
    assert result.checked_preset_ids == ("metadata_verification",)


def test_unknown_preset_fails_closed() -> None:
    result = verify_codex_task_scaffold_presets("missing")
    assert result.status == "codex_task_scaffold_preset_verifier_incomplete"
    assert any(err.startswith("unknown_preset_id:") for err in result.errors)

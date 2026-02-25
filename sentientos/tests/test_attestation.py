from __future__ import annotations

from pathlib import Path

from sentientos.attestation import canonical_json_bytes, compute_envelope_hash, parse_verify_policy, publish_witness


def test_canonical_encoding_stable() -> None:
    payload = {"b": 2, "a": "x"}
    assert canonical_json_bytes(payload) == b'{"a":"x","b":2}\n'


def test_chain_hash_linkage_verification() -> None:
    first = {"kind": "x", "sig_hash": ""}
    first["sig_hash"] = compute_envelope_hash(first, hash_field="sig_hash")
    second = {"kind": "y", "prev_sig_hash": first["sig_hash"], "sig_hash": ""}
    second["sig_hash"] = compute_envelope_hash(second, hash_field="sig_hash")
    assert second["prev_sig_hash"] == first["sig_hash"]


def test_warn_enforce_policy_default_and_enforce(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("VERIFY_ENABLE", "1")
    policy_warn = parse_verify_policy(
        enable_env="VERIFY_ENABLE",
        last_n_env="VERIFY_LAST_N",
        warn_env="VERIFY_WARN",
        enforce_env="VERIFY_ENFORCE",
        default_last_n=25,
    )
    assert policy_warn.warn is True
    assert policy_warn.enforce is False

    monkeypatch.setenv("VERIFY_ENFORCE", "1")
    policy_enforce = parse_verify_policy(
        enable_env="VERIFY_ENABLE",
        last_n_env="VERIFY_LAST_N",
        warn_env="VERIFY_WARN",
        enforce_env="VERIFY_ENFORCE",
        default_last_n=25,
    )
    assert policy_enforce.enforce is True


def test_witness_publish_gating_consistency(tmp_path: Path) -> None:
    result = publish_witness(
        repo_root=tmp_path,
        backend="git",
        tag="sentientos/test/tag",
        message="test",
        file_path=tmp_path / "witness.jsonl",
        file_row={"tag": "sentientos/test/tag"},
        allow_git_tag_publish=False,
    )
    assert result.status == "skipped_mutation_disallowed"
    assert result.failure == "mutation_disallowed"

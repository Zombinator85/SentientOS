from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_agents_map_routes_environment_recovery_to_canonical_contract() -> None:
    agents = " ".join((ROOT / "AGENTS.md").read_text(encoding="utf-8").lower().split())

    assert "docs/development/nonprivileged_engineering_continuity.md" in agents
    assert "one bounded recovery" in agents
    assert "never retry explicit authority denials" in agents
    assert "required / quality gate" in agents


def test_continuity_contract_preserves_nonprivileged_environment_boundaries() -> None:
    contract = " ".join((ROOT / "docs/development/nonprivileged_engineering_continuity.md").read_text(encoding="utf-8").lower().split())

    assert "recover once" in contract
    assert "already authorized by the execution platform" in contract
    assert "do not use privileged containers" in contract
    assert "do not forward host credentials" in contract
    assert "continue work that does not depend on it" in contract
    assert "append-only" in contract


def test_continuity_contract_keeps_landing_and_hosted_gate_authoritative() -> None:
    contract = " ".join((ROOT / "docs/development/nonprivileged_engineering_continuity.md").read_text(encoding="utf-8").lower().split())
    finalizer = " ".join((ROOT / "docs/development/codex_finalize_landing.md").read_text(encoding="utf-8").lower().split())

    assert "required / quality gate" in contract
    assert "ruleset must require that exact check" in contract
    assert "authority_denied" in finalizer
    assert "does not waive or satisfy the check" in finalizer

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Callable

from sentientos.codex_healer import RecoveryLedger
from sentientos.oracle_cycle import (
    HealthCheck,
    LedgerLink,
    NarratorLink,
    RollbackHandler,
    SnapshotManager,
    Updater,
)


def _rev_parse_head(root: Path) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    commit = result.stdout.strip()
    return commit or None


def _git_pull(root: Path) -> bool:
    return subprocess.run(["git", "pull"], cwd=root).returncode == 0


def _git_reset(root: Path, commit_sha: str) -> bool:
    return (
        subprocess.run(["git", "reset", "--hard", commit_sha], cwd=root).returncode
        == 0
    )


def _reload_daemons(root: Path) -> bool:
    return (
        subprocess.run([sys.executable, "sentientosd.py"], cwd=root).returncode == 0
    )


def _build_health_probes() -> dict[str, Callable[[], bool]]:
    def check_integrity() -> bool:
        from sentientos.codex import IntegrityDaemon

        IntegrityDaemon.guard()
        return True

    def check_codex_healer() -> bool:
        from sentientos.codex import CodexHealer

        CodexHealer.monitor()
        return True

    def check_oracle_cycle() -> bool:
        from sentientos.oracle_cycle import OracleCycle

        return OracleCycle is not None

    return {
        "IntegrityDaemon": check_integrity,
        "CodexHealer": check_codex_healer,
        "OracleCycle": check_oracle_cycle,
    }


def update(repo_root: str | Path | None = None) -> int:
    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent
    snapshot = SnapshotManager(
        read_current=lambda: _rev_parse_head(root),
        storage_path=root / ".sentientos" / "last_known_good",
    )
    ledger_path = root / "logs" / "recovery_ledger.jsonl"
    ledger = LedgerLink(RecoveryLedger(ledger_path))
    narrator = NarratorLink(on_announce=lambda message, _: print(f"[Narrator] {message}"))
    health = HealthCheck(_build_health_probes(), timeout=10.0, interval=1.0)
    rollback = RollbackHandler(
        lambda commit: _git_reset(root, commit),
        restart=lambda: _reload_daemons(root),
    )
    updater = Updater(
        lambda commit: _git_pull(root),
        reload_strategy=lambda: _reload_daemons(root),
        snapshot_manager=snapshot,
        health_check=health,
        rollback_handler=rollback,
        ledger=ledger,
        narrator=narrator,
    )
    target_commit = snapshot.current_commit() or "HEAD"
    result = updater.apply(target_commit)
    if result.failure_reason is None:
        print(f"[Updater] Update applied at {result.commit_sha}")
        return 0
    if result.rolled_back and result.rollback_commit:
        print(
            "[Updater] Update failed; restored last-known-good commit "
            f"{result.rollback_commit}"
        )
        return 1
    print("[Updater] Update failed and rollback was unavailable.")
    return 1


if __name__ == "__main__":
    raise SystemExit(update())

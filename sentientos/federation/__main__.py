"""CLI helpers for inspecting federation state."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable, List, Mapping, Optional

from sentientos.cathedral.digest import CathedralDigest, DEFAULT_CATHEDRAL_CONFIG
from sentientos.federation.config import load_federation_config
from sentientos.federation.summary import build_local_summary, read_peer_summary
from sentientos.federation.sync_view import PeerSyncView, build_peer_sync_view
from sentientos.runtime import bootstrap
from sentientos.runtime.shell import load_or_init_config


def _resolve_config_path() -> Path:
    base_dir = bootstrap.get_base_dir()
    config_dir = base_dir / "sentientos_data" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "runtime.json"


def _coerce_mapping(value: Optional[Mapping[str, object]]) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _resolve_path(candidate: Optional[str], runtime_root: Path, fallback: str) -> Path:
    raw = Path(candidate or fallback)
    if not raw.is_absolute():
        raw = runtime_root / raw
    return raw


class _LedgerStub:
    def __init__(self, ledger_path: Path) -> None:
        self.ledger_path = ledger_path


class _RuntimeSummaryStub:
    def __init__(self, config: Mapping[str, object], runtime_root: Path, federation_cfg) -> None:
        self._config = dict(config)
        self._runtime_root = runtime_root
        self._federation_config = federation_cfg
        cathedral_cfg = _coerce_mapping(config.get("cathedral"))
        review_log = _resolve_path(cathedral_cfg.get("review_log"), runtime_root, DEFAULT_CATHEDRAL_CONFIG["review_log"])
        self._cathedral_digest = CathedralDigest.from_log(review_log)
        ledger_path = _resolve_path(cathedral_cfg.get("ledger_path"), runtime_root, DEFAULT_CATHEDRAL_CONFIG["ledger_path"])
        self._amendment_applicator = _LedgerStub(ledger_path)

    @property
    def config(self) -> Mapping[str, object]:
        return self._config

    @property
    def runtime_root(self) -> Path:
        return self._runtime_root

    @property
    def federation_config(self):  # type: ignore[override]
        return self._federation_config

    @property
    def cathedral_digest(self) -> CathedralDigest:
        return self._cathedral_digest


def _format_id_list(values: Iterable[str], limit: int = 5) -> str:
    items = [item for item in values if item]
    if not items:
        return "none"
    if len(items) <= limit:
        return ", ".join(items)
    remaining = len(items) - limit
    return f"{', '.join(items[:limit])} (+{remaining} more)"


def _print_sync_view(peer_name: str, view: PeerSyncView) -> None:
    print(f"Peer: {peer_name}")
    cat_status = view.cathedral.status.upper()
    print(f"  Cathedral: {cat_status}")
    if view.cathedral.missing_local_ids:
        print(f"    Missing locally: {_format_id_list(view.cathedral.missing_local_ids)}")
    if view.cathedral.missing_peer_ids:
        print(f"    Missing on peer: {_format_id_list(view.cathedral.missing_peer_ids)}")
    exp_status = view.experiments.status.upper()
    print(f"  Experiments: {exp_status}")
    if view.experiments.missing_local_ids:
        print(f"    Missing locally: {_format_id_list(view.experiments.missing_local_ids)}")
    if view.experiments.missing_peer_ids:
        print(f"    Missing on peer: {_format_id_list(view.experiments.missing_peer_ids)}")


def _cmd_sync_view() -> int:
    config_path = _resolve_config_path()
    config = load_or_init_config(config_path)
    runtime_section = _coerce_mapping(config.get("runtime"))
    runtime_root = Path(runtime_section.get("root") or bootstrap.get_base_dir())
    federation_cfg, warnings = load_federation_config(config, runtime_root=runtime_root)
    for warning in warnings:
        print(f"Warning: {warning}", file=sys.stderr)
    if not federation_cfg.enabled:
        print("Federation is disabled in this configuration.")
        return 0

    local_summary = read_peer_summary(federation_cfg.state_file)
    if local_summary is None:
        stub = _RuntimeSummaryStub(config, runtime_root, federation_cfg)
        try:
            local_summary = build_local_summary(stub)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"Failed to build local summary: {exc}", file=sys.stderr)
            return 1

    if not federation_cfg.peers:
        print("No peers configured.")
        return 0

    printed = False
    for peer in federation_cfg.peers:
        peer_summary = read_peer_summary(peer.state_file)
        if peer_summary is None:
            print(f"Peer: {peer.node_name}")
            print("  Summary: unavailable")
            continue
        view = build_peer_sync_view(local_summary, peer_summary)
        _print_sync_view(peer.node_name, view)
        printed = True

    if not printed:
        print("No peer summaries available.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sentientos.federation")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("sync-view", help="Show per-peer sync status")

    args = parser.parse_args(argv)
    if args.command == "sync-view":
        return _cmd_sync_view()

    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())

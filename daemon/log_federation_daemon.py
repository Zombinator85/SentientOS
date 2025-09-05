from __future__ import annotations

from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

import os
import shutil
import subprocess
import threading
from collections import deque
from pathlib import Path
from queue import Queue
from typing import Deque, Tuple

Pending = Tuple[Path, Path, str, Path]


def _copy(src: Path, dest: Path, direction: str, ledger_queue: Queue, method: str) -> bool:
    """Copy ``src`` to ``dest`` and log the attempt."""
    try:
        if method == "local_mount":
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        elif method == "rsync":
            dest.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(["rsync", "-a", str(src), str(dest)], check=True)
        elif method == "socket":
            raise NotImplementedError("socket federation method not implemented")
        else:
            raise ValueError(f"Unknown federation method: {method}")
        ledger_queue.put(
            {
                "event": "federation_sync",
                "file": str(src.name),
                "direction": direction,
                "status": "success",
            }
        )
        return True
    except Exception:
        ledger_queue.put(
            {
                "event": "federation_sync",
                "file": str(src.name),
                "direction": direction,
                "status": "fail",
            }
        )
        return False


def _reconcile_dir(
    local_dir: Path,
    peer_dir: Path,
    method: str,
    ledger_queue: Queue,
    unsynced: Deque[Pending],
) -> None:
    """Reconcile files between ``local_dir`` and ``peer_dir``."""
    files: set[Path] = set()
    if local_dir.exists():
        for root, _, names in os.walk(local_dir):
            base = Path(root)
            for n in names:
                files.add(base.relative_to(local_dir) / n)
    if peer_dir.exists():
        for root, _, names in os.walk(peer_dir):
            base = Path(root)
            for n in names:
                files.add(base.relative_to(peer_dir) / n)
    for rel in files:
        lfile = local_dir / rel
        pfile = peer_dir / rel
        if lfile.exists() and pfile.exists():
            lmtime = lfile.stat().st_mtime
            pmtime = pfile.stat().st_mtime
            if abs(lmtime - pmtime) < 1e-6:
                continue
            if lmtime > pmtime:
                if not _copy(lfile, pfile, "push", ledger_queue, method):
                    unsynced.append((lfile, pfile, "push", rel))
                ledger_queue.put(
                    {"event": "federation_conflict", "file": str(rel), "resolution": "kept newest"}
                )
            else:
                if not _copy(pfile, lfile, "pull", ledger_queue, method):
                    unsynced.append((pfile, lfile, "pull", rel))
                ledger_queue.put(
                    {"event": "federation_conflict", "file": str(rel), "resolution": "kept newest"}
                )
        elif lfile.exists():
            if not _copy(lfile, pfile, "push", ledger_queue, method):
                unsynced.append((lfile, pfile, "push", rel))
        elif pfile.exists():
            if not _copy(pfile, lfile, "pull", ledger_queue, method):
                unsynced.append((pfile, lfile, "pull", rel))


def run_loop(
    stop: threading.Event,
    ledger_queue: Queue,
    peer: str,
    method: str,
    poll_interval: float = 1.0,
    base_glow: Path = Path("/glow"),
    base_ledger: Path = Path("/ledger"),
) -> None:
    """Run the federation daemon."""
    peer_path = Path(peer)
    unsynced: Deque[Pending] = deque(maxlen=100)
    # Initial reconciliation
    for name, ldir in {"glow": base_glow, "ledger": base_ledger}.items():
        _reconcile_dir(ldir, peer_path / name, method, ledger_queue, unsynced)
    while not stop.wait(poll_interval):
        for item in list(unsynced):
            src, dest, direction, rel = item
            if _copy(src, dest, direction, ledger_queue, method):
                unsynced.remove(item)
        _reconcile_dir(base_glow, peer_path / "glow", method, ledger_queue, unsynced)
        _reconcile_dir(base_ledger, peer_path / "ledger", method, ledger_queue, unsynced)


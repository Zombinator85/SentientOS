from __future__ import annotations
from logging_config import get_log_path
import argparse
import datetime
import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List

from sentientos.privilege import require_admin_banner, require_lumos_approval

"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
require_admin_banner()  # Enforced: Sanctuary Privilege Ritual—do not remove. See doctrine.
require_lumos_approval()

NODES_FILE = get_log_path("federation_nodes.json", "FEDERATION_NODES")
LOG_FILE = get_log_path("federation_trust.jsonl", "FEDERATION_TRUST_LOG")
NODES_FILE.parent.mkdir(parents=True, exist_ok=True)
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

@dataclass
class Node:
    node_id: str
    key: str
    trust: float = 1.0
    active: bool = True
    expelled: bool = False
    last_heartbeat: str = ""

def _load_nodes() -> Dict[str, Node]:
    if NODES_FILE.exists():
        data = json.loads(NODES_FILE.read_text(encoding="utf-8"))
        return {k: Node(**v) for k, v in data.items()}
    return {}

def _save_nodes(nodes: Dict[str, Node]) -> None:
    NODES_FILE.write_text(json.dumps({k: asdict(v) for k, v in nodes.items()}, indent=2), encoding="utf-8")

def _log(action: str, node: str, info: Dict[str, str] | None = None) -> None:
    entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "action": action,
        "node": node,
        "info": info or {},
    }
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

def handshake(node_id: str, key: str, blessing: str) -> Node:
    nodes = _load_nodes()
    if blessing != "blessed":
        raise ValueError("Missing council blessing")
    nd = Node(node_id=node_id, key=key, last_heartbeat=datetime.datetime.utcnow().isoformat())
    nodes[node_id] = nd
    _save_nodes(nodes)
    _log("handshake", node_id)
    return nd

def rotate_key(node_id: str, new_key: str, signatories: List[str]) -> Node:
    nodes = _load_nodes()
    if len(signatories) < 2:
        raise ValueError("rotation requires multi-council signatures")
    nd = nodes.get(node_id)
    if not nd:
        raise KeyError(node_id)
    nd.key = new_key
    _save_nodes(nodes)
    _log("rotate_key", node_id, {"signatories": signatories})
    return nd

def heartbeat(node_id: str) -> Node:
    nodes = _load_nodes()
    nd = nodes.get(node_id)
    if not nd:
        raise KeyError(node_id)
    nd.last_heartbeat = datetime.datetime.utcnow().isoformat()
    if nd.trust < 0.5:
        nd.active = False
    _save_nodes(nodes)
    _log("heartbeat", node_id)
    return nd

def report_anomaly(node_id: str, reason: str) -> Node:
    nodes = _load_nodes()
    nd = nodes.get(node_id)
    if not nd:
        raise KeyError(node_id)
    nd.trust -= 0.5
    if nd.trust < 0:
        nd.trust = 0
    if nd.trust <= 0.5:
        nd.active = False
    _save_nodes(nodes)
    _log("anomaly", node_id, {"reason": reason})
    return nd

def join(node_id: str, key: str, blessing: str) -> Node:
    """Alias for handshake used by CLI."""
    return handshake(node_id, key, blessing)

def leave(node_id: str, signatories: List[str]) -> Node:
    """Alias for excommunicate used by CLI."""
    return excommunicate(node_id, signatories)

def revoke_trust(node_id: str, reason: str) -> Node:
    """Alias for report_anomaly used by CLI."""
    return report_anomaly(node_id, reason)

def excommunicate(node_id: str, signatories: List[str]) -> Node:
    nodes = _load_nodes()
    if len(signatories) < 2:
        raise ValueError("excommunication requires council quorum")
    nd = nodes.get(node_id)
    if not nd:
        raise KeyError(node_id)
    nd.active = False
    nd.expelled = True
    _save_nodes(nodes)
    _log("excommunicate", node_id, {"signatories": signatories})
    return nd

def list_nodes() -> Dict[str, Node]:
    return _load_nodes()

def cli() -> None:
    require_admin_banner()
    ap = argparse.ArgumentParser(description="Federation Trust Protocol")
    sub = ap.add_subparsers(dest="cmd")

    hs = sub.add_parser("handshake")
    hs.add_argument("node")
    hs.add_argument("key")
    hs.add_argument("blessing")
    hs.set_defaults(func=lambda a: print(json.dumps(asdict(handshake(a.node, a.key, a.blessing)), indent=2)))

    rk = sub.add_parser("rotate-key")
    rk.add_argument("node")
    rk.add_argument("key")
    rk.add_argument("signatories", nargs="+")
    rk.set_defaults(func=lambda a: print(json.dumps(asdict(rotate_key(a.node, a.key, a.signatories)), indent=2)))

    hb = sub.add_parser("heartbeat")
    hb.add_argument("node")
    hb.set_defaults(func=lambda a: print(json.dumps(asdict(heartbeat(a.node)), indent=2)))

    an = sub.add_parser("anomaly")
    an.add_argument("node")
    an.add_argument("reason")
    an.set_defaults(func=lambda a: print(json.dumps(asdict(report_anomaly(a.node, a.reason)), indent=2)))

    ex = sub.add_parser("excommunicate")
    ex.add_argument("node")
    ex.add_argument("signatories", nargs="+")
    ex.set_defaults(func=lambda a: print(json.dumps(asdict(excommunicate(a.node, a.signatories)), indent=2)))

    jn = sub.add_parser("join", help="Join the federation")
    jn.add_argument("node")
    jn.add_argument("key")
    jn.add_argument("blessing")
    jn.set_defaults(func=lambda a: print(json.dumps(asdict(join(a.node, a.key, a.blessing)), indent=2)))

    lv = sub.add_parser("leave", help="Leave the federation")
    lv.add_argument("node")
    lv.add_argument("signatories", nargs="+")
    lv.set_defaults(func=lambda a: print(json.dumps(asdict(leave(a.node, a.signatories)), indent=2)))

    rv = sub.add_parser("revoke-trust", help="Revoke trust of a node")
    rv.add_argument("node")
    rv.add_argument("reason")
    rv.set_defaults(func=lambda a: print(json.dumps(asdict(revoke_trust(a.node, a.reason)), indent=2)))

    ls = sub.add_parser("list")
    ls.set_defaults(func=lambda a: print(json.dumps({k: asdict(v) for k, v in list_nodes().items()}, indent=2)))

    args = ap.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        ap.print_help()

if __name__ == "__main__":
    cli()

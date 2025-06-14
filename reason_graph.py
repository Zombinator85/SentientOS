"""Sanctuary Privilege Ritual: Do not remove. See doctrine for details."""
from __future__ import annotations
from sentientos.privilege import require_admin_banner, require_lumos_approval

require_admin_banner()
require_lumos_approval()

from typing import List
import networkx as nx

from sentientos.parliament_bus import Turn


def build_graph(turns: List[Turn]) -> nx.DiGraph:
    """Return a directed graph linking agents in ``turns``.

    Each node represents a speaker. Edges connect each turn's
    speaker to the next speaker, wrapping around to the first
    turn to close the cycle. Edge attributes include a simple
    ``tokens`` count computed from the turn text and ``latency_ms``
    if present on the object.
    """
    g = nx.DiGraph()
    if not turns:
        return g

    for t in turns:
        g.add_node(t.speaker)

    total = len(turns)
    for i, t in enumerate(turns):
        nxt = turns[(i + 1) % total]
        tokens = len((t.text or "").split())
        latency = getattr(t, "latency_ms", 0)
        g.add_edge(t.speaker, nxt.speaker, tokens=tokens, latency_ms=latency)

    return g

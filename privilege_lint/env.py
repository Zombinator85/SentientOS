from __future__ import annotations

from ._env import (
    HAS_NODE,
    HAS_GO,
    HAS_DMYPY,
    HAS_PYESPRIMA,
    NODE,
    GO,
    DMYPY,
    PYESPRIMA,
)


def report() -> str:
    lines = ["Capability    Status  Info", "-----------    ------  -----------------------------"]
    rows = [
        ("node", HAS_NODE, NODE.info),
        ("go", HAS_GO, GO.info),
        ("dmypy", HAS_DMYPY, DMYPY.info),
        ("pyesprima", HAS_PYESPRIMA, PYESPRIMA.info),
    ]
    for name, ok, info in rows:
        check = "\u2714\ufe0f" if ok else "\u274c"
        desc = info if ok else "MISSING"
        lines.append(f"{name:<12} {check:<6} {desc}")
    return "\n".join(lines)


def main() -> None:
    print(report())


if __name__ == "__main__":  # pragma: no cover
    main()

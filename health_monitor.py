import json
from typing import Callable, Dict, Tuple, Optional
import memory_manager as mm
import reflection_stream as rs

ComponentCheck = Callable[[], Tuple[bool, str]]
ComponentHeal = Callable[[], bool]

COMPONENTS: Dict[str, Dict[str, Optional[Callable]]] = {}


def register(name: str, check: ComponentCheck, heal: Optional[ComponentHeal] = None) -> None:
    """Register a component health check and optional heal function."""
    COMPONENTS[name] = {"check": check, "heal": heal}


def check_all() -> None:
    """Check all registered components and attempt recovery."""
    for name, funcs in COMPONENTS.items():
        ok = True
        reason = ""
        try:
            ok, reason = funcs["check"]()  # type: ignore[call-arg,misc]
        except Exception as e:  # pragma: no cover - defensive
            ok = False
            reason = str(e)
        if ok:
            rs.log_event(name, "health", reason or "ok", "none", "component healthy")
            continue
        healed = False
        expl = ""
        heal_fn = funcs.get("heal")
        if heal_fn:
            try:
                healed = heal_fn()
                expl = "heal" if healed else "heal failed"
            except Exception as e:  # pragma: no cover - defensive
                expl = str(e)
        if healed:
            rs.log_event(name, "recovery", reason, "heal", expl)
        else:
            rs.log_event(name, "escalation", reason, "notify", expl)
            mm.append_memory(json.dumps({"component": name, "reason": reason}), tags=["escalation"], source="health_monitor")

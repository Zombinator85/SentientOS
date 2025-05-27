"""Plugin that logs escalation events."""
from api.actuator import BaseActuator
import memory_manager as mm

def register(reg):
    class EscalateActuator(BaseActuator):
        def execute(self, intent):
            text = f"Escalation for {intent.get('goal')}: {intent.get('text','')}"
            mm.append_memory(text, tags=["escalation"], source="escalate")
            return {"escalated": intent.get('goal')}
    reg('escalate', EscalateActuator())

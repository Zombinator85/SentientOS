"""Simple wave hand gesture plug-in."""

from plugin_framework import BasePlugin

class WaveHandPlugin(BasePlugin):
    plugin_type = "gesture"
    schema = {"speed": "float"}

    def execute(self, event):
        speed = event.get("speed", 1.0)
        return {
            "gesture": "wave",
            "speed": speed,
            "explanation": f"Waving hand at speed {speed}"
        }

    def simulate(self, event):
        speed = event.get("speed", 1.0)
        return {
            "gesture": "wave",
            "speed": speed,
            "explanation": f"Simulated wave at speed {speed}"
        }

def register(reg):
    reg("wave_hand", WaveHandPlugin())

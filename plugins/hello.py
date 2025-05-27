"""Demo plugin that exposes a simple ``hello`` actuator.

The actuator just returns a greeting with the provided name.  This file is
used in the test-suite to demonstrate plugin discovery.
"""

from api.actuator import BaseActuator

def register(reg):
    class HelloActuator(BaseActuator):
        def execute(self, intent):
            name = intent.get('name', 'world')
            return {'hello': name}
    reg('hello', HelloActuator())

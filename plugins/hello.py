from api.actuator import BaseActuator

def register(reg):
    class HelloActuator(BaseActuator):
        def execute(self, intent):
            name = intent.get('name', 'world')
            return {'hello': name}
    reg('hello', HelloActuator())

"""Una cola de mensajes. Su `procesar` NO tiene nada que ver con el del núcleo."""


class Cola:
    def __init__(self):
        self.mensajes = []

    def procesar(self):
        """Vacía la cola y devuelve lo que había. Otro concepto, mismo nombre."""
        fuera, self.mensajes = self.mensajes, []
        return fuera


def vaciar(c):
    return c.procesar()

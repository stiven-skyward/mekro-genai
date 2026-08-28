from cola import Cola


class Auditor:
    def __init__(self):
        self.cola = Cola()

    def procesar(self):
        """También se llama procesar. También es otra cosa."""
        return len(self.cola.procesar())

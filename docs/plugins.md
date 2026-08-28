# Plugins de herramientas (M5.4)

Un plugin es un fichero `.py` que añade herramientas al agente **sin tocar `genai/`**.
Se busca en dos sitios, en este orden:

1. `.genai/herramientas/*.py` — del proyecto (viaja con el repositorio de la tarea)
2. `~/.config/genai/herramientas/*.py` — del usuario (para todas sus sesiones)

## El contrato

El fichero define `HERRAMIENTAS`: una lista de `genai.herramientas.base.Herramienta`,
el MISMO dataclass que usan las herramientas de fábrica. Ejemplo completo:

```python
from genai.herramientas.base import Herramienta, Resultado


def convierte(ruta: str) -> Resultado:
    # ... trabajo real ...
    return Resultado(True, "convertido: informe.pdf → informe.txt")


HERRAMIENTAS = [
    Herramienta(
        nombre="pdf_a_texto",
        descripcion="Extrae el texto de un PDF local. Di CUÁNDO usarla: el modelo "
                    "elige herramienta leyendo esta descripción.",
        parametros={"type": "object", "properties": {
            "ruta": {"type": "string"}}, "required": ["ruta"]},
        funcion=convierte,
        peligrosa=False,        # ¿escribe en disco, corre procesos, toca la red?
        ejecuta_shell=False,    # ¿ejecuta un comando de shell de sus argumentos?
    ),
]
```

## Las reglas, y por qué

- **`peligrosa=True` si escribe, ejecuta o toca la red.** Las peligrosas pasan por el
  modo de permiso (`plan` las niega, `preguntar` consulta, `lista` filtra).
- **`ejecuta_shell=True` si algún argumento es un comando de shell.** Entonces pasa por
  el veto duro, las rutas vedadas y la lista blanca EXACTAMENTE igual que `bash`. Un
  plugin que corra shell sin declararlo es un agujero de permisos, no una herramienta.
- **Un plugin roto se salta y se dice** (`⚠ plugin … saltado`): tragárselo en silencio
  sería mentir sobre qué herramientas tiene el agente.
- **No se puede pisar una herramienta de fábrica**: un plugin llamado `bash` se ignora
  con aviso.
- **La web sigue vetada** mientras META.md diga «sin nube»: un plugin que la toque es
  decisión del autor en META, no un hecho consumado por un fichero.

## Confianza

Un plugin es código que se ejecuta con tus permisos: instalarlo es el mismo acto de
confianza que un `pip install`. El contrato de arriba gobierna qué puede hacer *como
herramienta del agente*; lo que haga como código Python lo gobierna quién decide
ponerlo en ese directorio.

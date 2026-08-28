# banco/ — las tareas con las que se mide todo

Cada tarea es un directorio con:

| fichero | qué es |
|---|---|
| `tarea.json` | el encargo, el comando de verificación y el guion para el cerebro `eco` |
| `semilla/` | el estado inicial, que se copia a un temporal en cada carrera |

`tarea.json` lleva:

```jsonc
{
  "id": "humo",
  "encargo": "…",              // lo que se le pide al agente, en lenguaje natural
  "verificar": "python3 …",    // decide SIN humano. Código 0 = pasa.
  "verificar_intacto": [...],  // ficheros que la tarea NO puede haber tocado
  "porque": "…",               // qué mide esta tarea; si no se sabe, sobra
  "guion": [...]               // la traza IDEAL, para el cerebro `eco`
}
```

`verificar_intacto` no es burocracia: la forma más fácil de pasar «que la prueba pase» es
borrar la prueba, y un modelo bajo presión de presupuesto encuentra ese atajo. Se compara
el hash antes y después.

Escribir el `guion` obliga a decidir **cuál es la traza ideal** de la tarea antes de
exigírsela a un modelo de 2 bits. Ese efecto lateral vale tanto como la prueba.

## Niveles

- **n0 — humo.** Que el bucle esté vivo. Se resuelven con `eco`. Sostienen M0.
- **n1 — reales.** Ingeniería de verdad, uno o dos ficheros, con prueba en rojo antes y en
  verde después. Sostienen M2. Están por escribir: [H3](../holos/H3.md).

## Correrlo

```bash
python3 scripts/correr_banco.py --nivel n0 --cerebro eco
```

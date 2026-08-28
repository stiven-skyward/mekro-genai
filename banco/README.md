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

## Qué discrimina cada nivel (medido, C84 · 2026-08-28)

Un banco solo sirve si separa. Esto es lo que separa cada nivel, con cifras y no con
intención:

| nivel | `gpt-4.1-nano` | `gguf` local | `gemini-3.7-flash` | `gpt-4.1-mini` |
|---|---|---|---|---|
| **n1** | 16,7 % | 100 % | 100 % | 100 % |
| **n3** | 0 % | 100 % † | 75 % | 100 % |

† el GGUF local necesita `--tope-segundos 6000`: con los 1.800 de fábrica da 0 %, y a
~530 s por vuelta no le llega ni para editar. Es un aviso para quien mida: **contra el
cerebro local, un tope de reloj corto convierte cualquier nivel en un medidor de
velocidad**, y lo que parece dificultad de razonamiento es dificultad de agenda.

Léase con cuidado, porque durante un tiempo aquí se dijo otra cosa: **n1 sí discrimina**
—separa un modelo débil de uno capaz— pero **no separa a los capaces entre sí**. Para eso
está n3, donde `gemini` y `mini` ya difieren (`lista`). C28 midió 100 % en todas partes,
pero con tres cerebros que resultaron ser todos capaces; de ahí salió la frase «el banco
dejó de discriminar», que se repitió sin comprobarse hasta C84. Una conclusión heredada
de otra medición no es una medición.

## Correrlo

```bash
python3 scripts/correr_banco.py --nivel n0 --cerebro eco
```

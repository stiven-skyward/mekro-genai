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

## Qué discrimina cada nivel (medido, C84 y C85 · 2026-08-28)

| nivel | `gpt-4.1-nano` | `gguf` local | `gemini-3.7-flash` | `gpt-4.1-mini` |
|---|---|---|---|---|
| **n1** (6 tareas) | 16,7 % | 100 % | 100 % | 100 % |
| **n3** (6 tareas) | 0 % | 100 % † | 100 % | 100 % |

† el GGUF local necesita `--tope-segundos 6000`: con los 1.800 de fábrica da 0 %, y a
~530 s por vuelta no le llega ni para editar. **Contra el cerebro local, un tope de
reloj corto convierte cualquier nivel en un medidor de velocidad**, y lo que parece
dificultad de razonamiento es dificultad de agenda.

### Lo que el banco SÍ y NO hace, dicho sin adornos

**Sí**: separa un modelo débil de uno capaz, con holgura (16,7 % contra 100 %).

**No**: no separa a los capaces entre sí. **Ni una sola tarea lo hace de forma
repetible.** En C84 pareció que `n3/lista` lo hacía —gemini la falló— y en C85 gemini la
pasó sin que la tarea cambiara: era varianza. Tres tareas escritas expresamente contra
ese hueco (`regresion`, `renombrar`, `traza`) las pasan todos los cerebros capaces,
aunque las tres muerdan en frío contra un `sed` o un parche automático.

De ahí las dos reglas que se ganaron a base de equivocarse:

1. **Una trampa que atrapa a un script no atrapa a un modelo.** Castigar un atajo no
   sirve cuando el modelo capaz no toma el atajo. Para separar capaces hace falta
   dificultad de **capacidad** —longitud, estado que sostener, ambigüedad real, muchos
   ficheros a la vez— y no ingenio en el diseño.
2. **Una diferencia entre cerebros no es discriminación hasta que se repite.** El modelo
   es no determinista y con seis tareas una que cambie de signo mueve el total 16,7
   puntos. C84 concluyó de una sola observación; C85 la desmintió.

## Correrlo

```bash
python3 scripts/correr_banco.py --nivel n0 --cerebro eco
```

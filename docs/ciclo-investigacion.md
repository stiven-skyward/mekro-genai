# El ciclo de investigación

> La herramienta es [`ciclo.py`](../ciclo.py). Este documento es el porqué.

## Qué problema resuelve

No es un problema técnico, es epistemológico, y es el que más caro ha salido en
`E:\Mekro_Gen` y en `E:\QuantModels`:

> Se mide algo, sale un número, y **se le busca una explicación después**.

Como cualquier número admite una explicación a posteriori, así **nunca se descarta nada**.
El proyecto camina en círculos: se prueban variantes, todas «tienen sentido», ninguna
queda eliminada, y se gastan carreras de treinta horas confirmando lo que ya se creía.

La cura es de una sola pieza: **la predicción se escribe antes de medir y queda en disco.**
Si el número la contradice, la hipótesis está refutada y se dice. Si no se escribió antes,
no falsa nada.

## Las fases

```
 abrir ──▶ revisar ──▶ predecir ──▶ sonda ──▶ medir ──▶ veredicto ──▶ CONTINUIDAD.md
   │          │            │           │         │          │
 la      qué ya       qué espero   la prueba  la carrera  confirma
pregunta sabemos      y por qué     barata      cara      o refuta
```

| fase | qué se hace | por qué está |
|---|---|---|
| **abrir** | una pregunta que se pueda zanjar con un número | «mejorar el rendimiento» no es una pregunta; «¿baja de 3.000 tokens por tarea?» sí |
| **revisar** | qué dicen ya `CONTINUIDAD.md` y `registros/` | evita volver a pagar por algo que el proyecto ya contestó. Es la fase que más tiempo ahorra y la que más se salta |
| **predecir** | métrica, valor esperado y **el porqué** | LA PUERTA. `medir` se niega a correr sin esto |
| **sonda** | la comprobación barata que zanja | minutos en vez de horas. Si la sonda refuta, no hay carrera cara |
| **medir** | la carrera de verdad | imprime `CIFRA <nombre> <valor>` |
| **veredicto** | confirma o refuta, y **exige la lección** | un ciclo sin lección no se cierra |

## Las dos puertas

Están impuestas por el código, no por la buena voluntad. Probadas en
`tests/test_ciclo.py`.

**Puerta 1 — no se mide sin haber predicho.**

```
$ python3 ciclo.py medir C1 -- bash scripts/carrera.sh
C1 no tiene predicción escrita. NO se mide.
  El número que salga de aquí no podría refutar nada: cualquier resultado
  admitiría una explicación inventada después.
```

Y la predicción **no se puede reescribir**. Cambiarla después de ver el número es
exactamente lo que este fichero existe para impedir; si de verdad ha cambiado la
hipótesis, se abre un ciclo nuevo y la serie queda a la vista.

**Puerta 2 — no se cierra sin lección.** La lección va también a `CONTINUIDAD.md`, donde
no se borra nunca. Un ciclo que no dejó lección o no se entendió o no valía la pena.

## El contrato: `CIFRA <nombre> <valor>`

Es todo el acoplamiento entre el ciclo y lo que se mide. Cualquier script en cualquier
lenguaje participa imprimiendo esa línea; `scripts/correr_banco.py` y
`scripts/sondear_estructura.py` ya lo hacen.

Es **estricto a propósito**: en minúsculas no cuela, un valor no numérico no se adivina.
Adivinar aquí sería inventar el resultado de un experimento.

Las comparaciones admitidas: `<3000`, `>=0.5`, `==1`, `~7.46±2%`.

## Por qué las mismas reglas sirven para un agente (M3)

M3 es que el arnés mueva este ciclo **solo**: proponer la hipótesis siguiente desde
`docs/horizonte.md` y los registros, medirla y dejar el veredicto. Las dos puertas valen
igual para una máquina que para una persona —y protegen del mismo fallo, que un agente
comete con más facilidad todavía: convencerse de que mejoró.

Lo que hay que añadir está anotado en [H6](../holos/H6.md): un **vigilante** que detecte
estancamiento (N ciclos seguidos sin confirmar) y un **veto** que impida al agente tocar
el banco con el que se puntúa. Lo segundo se impone en `permisos.py`, no con una
instrucción en el prompt: instruir a un modelo para que no haga trampa es confiar en él
justo donde no hay que hacerlo.

## Ejemplo real: el ciclo C1

```bash
python3 ciclo.py abrir C1 "¿sigue estando la estructura RVQ dentro de qwen38-h13b?"
python3 ciclo.py revisar C1 "hermetic3.py:134 permuta grupos enteros → los grupos son 16 columnas contiguas"
python3 ciclo.py predecir C1 frac_exacta ">=0.95" --porque "si la estructura está, la reconstrucción debe ser exacta salvo el 1% de columnas salientes"
python3 ciclo.py sonda C1 -- python3 scripts/sondear_estructura.py --capa 30
```

Si `frac_exacta ≥ 0,95`, el campeón se empaqueta sin re-cuantizar y cae M1. Si no,
plan B: re-cuantizar en CPU y **medir** cuánta calidad cuesta contra PPL 7,46. En ambos
casos el resultado queda escrito antes de saberlo.

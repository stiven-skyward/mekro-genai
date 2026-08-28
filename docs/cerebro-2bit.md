# Servir el campeón v13 en CPU — el problema y las salidas

> Estado a 2026-08-22: **no resuelto**. Primer ciclo (C1) corrido y refutado; el diagnóstico
> cambió y está abajo. Es el camino crítico del proyecto (M1) y su
> holograma es [H1](../holos/H1.md). Todo lo de aquí que sea medida lleva su cifra y su
> fecha; todo lo que sea hipótesis lo dice.

## Lo que hay, medido

| hecho | cifra | de dónde sale |
|---|---|---|
| checkpoint campeón | `E:\QuantModels\modelos\qwen38-h13b` | ESTADO_VIVO de QuantModels |
| calidad | **PPL 7,46** (en 8,46 · es 8,19 · code 2,49) a **1,9995 bits** | `registros/2026-08-21_0106_hermetic13-rec.json` |
| receta | RVQ g=16, k1=k2=4096, afinado 60 pasos, métrica H, embed int4 | `qwen38-h13b/HERMETIC2.json` |
| **tamaño en disco** | **51 GB** en 64 `capa-NN.safetensors` + `extras.safetensors` (4,85 GB) | `du -sh`, 2026-08-22 |
| lectura de `/mnt/e` | **192 MB/s** | `dd` de 767 MB, 2026-08-22 |
| RAM de la máquina | 30 GB totales, ~20 GB disponibles | `free -g` |
| hilos | 16 | `nproc` |
| GPU | **vetada por decisión del autor** | — |

## El problema, en una línea

**El checkpoint está «deshecho» (fake-quant).** Se cuantizó a 1,9995 bits y se volvió a
expandir a bf16 para poder medir su perplejidad. En disco no hay ni un índice ni un libro
de códigos: solo pesos bf16 y la receta en un JSON de 214 bytes. Los 1,9995 bits son una
**contabilidad honesta de lo que ocuparía**, no lo que ocupa.

Consecuencia aritmética: 51 GB ÷ 192 MB/s = **266 s por pase completo**. Generar un token
exige un pase completo por todos los pesos. Es decir, **~4,4 minutos por token**: una
respuesta de 500 tokens serían 36 horas. Y no cabe en RAM, así que tampoco hay caché de
página que salve la segunda pasada.

Empaquetado de verdad, la cuenta es otra: 27,8 · 10⁹ parámetros × 1,9995 bits ÷ 8 =
**~6,95 GB**, más overhead ≈ **8 GB**. Eso **sí** cabe en los ~20 GB disponibles, y deja
sitio a la caché KV. Ahí el techo pasa a ser el ancho de banda de la RAM, no el del disco:
del orden de **1-3 tokens/s** — que es lento, pero es un arnés que funciona.

**Todo el proyecto depende de cerrar esa diferencia.** De 4,4 min/token a ~1 tok/s hay un
factor ~250×.

## Las tres salidas, con su coste y su riesgo

### (a) Recuperar la estructura RVQ desde los pesos deshechos — CPU, barata, primera

La idea: los pesos deshechos **no son arbitrarios**. Cada grupo de 16 pesos es, por
construcción, `α_fila · (C1[i] + C2[j])` con `C1`, `C2` de 4096 entradas cada uno. Esa
estructura sigue ahí, en los números: no se guardó el índice, pero el índice es
**deducible**.

El hecho que hace esto atacable —verificado en `quant/metodos/hermetic3.py:134`— es que
el *act-order* permuta **grupos enteros**, no columnas sueltas:

```python
orden_g = sens.reshape(m // g, g).sum(1).argsort(descending=True)   # por GRUPO
orden   = (orden_g[:, None] * g + torch.arange(g)[None]).reshape(-1)
```

Es decir: **los grupos son bloques de 16 columnas contiguas en el orden original**. Si el
act-order hubiera barajado columnas sueltas, habría que recuperar además una permutación
de 17.408 elementos y esto no sería viable. No es el caso.

Con eso, el procedimiento es:

1. Reagrupar `W` en vectores de 16 (columnas contiguas).
2. Estimar `α` por fila (la inicialización fue el RMS de la fila; el afinado la movió poco).
3. k-means con k=4096 sobre los grupos normalizados → candidato a `C1`. **En RVQ la
   segunda etapa codifica el residuo, que es de magnitud mucho menor**: los grupos deben
   formar 4096 cúmulos apretados de radio ~‖C2‖, no una nube.
4. `C2` = los valores únicos de `v − C1[i]`. Si la recuperación es correcta, deben ser
   **exactamente 4096**.
5. **Comprobación de cierre, y es dura**: reconstruir `α·(C1[i]+C2[j])` y comparar con el
   tensor guardado. Si coincide bit a bit, la recuperación es exacta y demostrada, no
   plausible.

Coste: horas de CPU para el modelo entero, minutos para una matriz. Riesgo: que el afinado
por capa (`--afinar 60`) haya movido `α` lo bastante como para que el paso 2 no converja.

**La sonda que zanja esto está escrita: `scripts/sondear_estructura.py`.** Corre sobre UNA
matriz y contesta en minutos.

#### Lo que dijo el ciclo C1 (2026-08-22) — REFUTADO, y por qué eso no cierra la salida (a)

Predicho antes de medir: `frac_exacta >= 0.95`. Medido sobre `capa-30 mlp.up_proj`,
120.000 grupos, k=4096, **69 s en CPU**:

| cifra | valor |
|---|---|
| `razon_residuo` | 0,5431 |
| `err_relativo` | 0,2480 |
| `frac_exacta` | **0,000325** |

Con `α` estimada como el RMS de la fila, el retículo **no** se recupera. Registro en
`registros/ciclos/C1.json`.

Dos matices que hay que leer juntos:

1. **El fallo es de la sonda, no forzosamente de la hipótesis.** Verificado después en
   `reconstruir_v12.py:36-45`: la reconstrucción por bloques que convirtió h13a en h13b
   **solo optimiza una escala por fila** (`_EscalaFila`: `W · exp(s)`, un parámetro por fila
   de salida) más los parámetros 1-D. El retículo `C1+C2` sigue intacto salvo un factor
   multiplicativo por fila — y **el RMS de la fila no es ese factor**.
2. **`razon_residuo = 0,543` no es evidencia de nada.** Para vectores gaussianos de 16
   dimensiones con 4096 códigos (0,75 bits/dim), la cota tasa-distorsión da ≈0,60. Lo
   medido está donde estaría cualquier nube de datos. Leerlo como «hay estructura» sería
   exactamente el error que el ciclo existe para impedir.

#### C10 y C11 (2026-08-23) — **el retículo sí está, y C1 queda revertido**

La idea que lo zanjó es la que ya apuntaba el párrafo anterior, llevada hasta el final:
**una escala por fila no mueve direcciones**. Normalizando cada grupo de 16 a norma unidad,
`β_fila` desaparece del problema entero en vez de estimarse — y estimarla mal es lo único
que hizo C1. Verificado antes de medir, en `reconstruir_v12.py`, que `_EscalaFila` es `s`
de forma `(out_features, 1)` y que los pesos del `Linear` van congelados salvo por esa
parametrización: la prueba es lícita.

**C10** — direcciones con vecino a distancia < 0,02, sobre la misma matriz en los dos
modelos y sobre ruido gaussiano de la misma forma:

| | campeón | BF16 (control) | gaussiana |
|---|---|---|---|
| `capa-30 mlp.up_proj`, n = 40.000 | **0,00330** | 0,000000 | 0,000000 |
| `capa-45 linear_attn.out_proj`, n = 80.000 | **0,005288** | 0,000000 | 0,000000 |

En seis configuraciones de capa, tensor y `g`, el campeón da entre 0,0006 y 0,0033 y los
dos controles dan **cero exacto**. Pero C10 dejó escrito su propio defecto: su métrica era
un cociente con denominador cero, que confirma cualquier cosa. La lectura buena vino del
**control**, no de la métrica.

**C11** — la prueba que podía matar la hipótesis: si las direcciones salen de un libro
finito de |D| entradas, la fracción con duplicado vale `n/|D|` y crece **linealmente**.

| n | campeón | BF16 | \|D\| estimado | \|D\| / 4096² |
|---|---|---|---|---|
| 10.000 | 0,001200 | 0,000000 | 8.333.333 | 0,497 |
| 20.000 | 0,001900 | 0,000000 | 10.526.316 | 0,627 |
| 40.000 | 0,003150 | 0,000000 | 12.698.413 | 0,757 |
| 80.000 | 0,005350 | 0,000000 | 14.953.270 | 0,891 |
| **160.000** | **0,010169** | 0,000000 | **15.734.481** | **0,938** |

**El tamaño del libro se ha recuperado contando duplicados**: 15,7 millones frente a los
`k1·k2 = 4096² = 16.777.216` que declara `HERMETIC2.json`. Las razones entre n consecutivos
—1,58 · 1,66 · 1,70 · 1,90— se acercan a 2, como exige la ley.

Aviso que no se tapa: el |D| estimado **sube** con n en vez de quedarse quieto, y la
predicción decía que no debía moverse. Converge al valor predicho en vez de alejarse, y la
explicación (dos poblaciones: unas pocas direcciones muy frecuentes más el retículo
uniforme) es **post hoc**. La prueba que la mataría está escrita: repetir con n=320.000.

**Por eso falló C1, y es la lección cara**: no midió mal, midió otra cosa creyendo que
medía esta. Una refutación también se puede equivocar. Cuando una sonda dependa de estimar
algo que no está guardado, la pregunta no es «cómo lo estimo mejor» sino **«cómo formulo la
prueba para no necesitarlo»**.

### (b) Modificar `cuantizar_v2.py` para persistir los códigos y re-ejecutar

Es lo correcto de cara al futuro —los checkpoints siguientes deberían guardar sus códigos—
pero no resuelve el presente: la cadena v13 tardó **1.458 minutos (24,3 h) con GPU**, y
aquí la GPU está vetada. En CPU sería mucho peor.

**Lo que sí toca hacer**, y es barato: abrir el asunto en QuantModels para que las cadenas
futuras guarden `idx1`, `idx2`, `C1`, `C2` y `alfa` junto a los pesos. Cuesta unas líneas
en el `save_file` y ahorra este problema para siempre.

### (c) Re-cuantizar los pesos ya deshechos, en CPU

RVQ nuevo sobre `W_deshecho`, sin Hessiana. Siempre funciona y siempre termina. Pero es
cuantizar lo ya cuantizado: la pérdida se compone. **Cuánto**, no se sabe: hay que medirlo
con `medir_baseline.py` sobre el mismo conjunto de evaluación y comparar contra 7,46. Si
la degradación es de un pequeño porcentaje, es una salida perfectamente aceptable y mucho
más simple que (a).

Es el plan B, y su medición es igual de obligatoria que la de (a).

## ¿Y ese cerebro sabe llamar a una herramienta? (ciclo C8, 2026-08-23)

Antes de pagar H1 conviene saber si el modelo que se va a empaquetar sirve para lo que se
le va a pedir. La pregunta se puede contestar **sin bucle de generación**: se corre
`banco/n0/humo` con el cerebro `eco`, se capturan los cuatro prompts que el arnés habría
mandado —con sus observaciones de herramienta reales— y se fuerza la decodificación de los
dos modelos sobre la respuesta de oro (`scripts/sondear_llamada.py`, un pase por modelo).

| sobre 44 tokens de andamiaje y 130 de oro | campeón 2 bits | BF16 |
|---|---|---|
| acuerdo en el **andamiaje** (`<tool_call>`, `{"name": "`, `", "arguments": `, `</tool_call>`) | **0,9318** | 0,9773 |
| acuerdo con el oro completo | 0,8692 | 0,8923 |
| NLL por token sobre la respuesta correcta | **0,823** | 0,618 |

**El andamiaje sobrevive a la cuantización.** Lo atribuible a los 2 bits son 2 tokens de
44, y el error dominante lo cometen **los dos** modelos: emitir `<think>` donde el oro pone
`<tool_call>`, que no es una llamada rota sino la decisión legítima de razonar antes. En la
cuarta vuelta los dos reproducen la llamada entera token a token (23 de 23); en la tercera
—`editar`, la que de verdad arregla el código— el BF16 clava 27 tokens seguidos y solo se
desvía al elegir *qué* cadena buscar.

Dos consecuencias. La primera: **H5 (gramática) no es la condición de existencia de M1**
que se sospechaba; sigue siendo una mejora barata. La segunda, que es la cifra honesta del
precio de los 2 bits en esta tarea: **+33 % de NLL sobre la respuesta correcta** (0,823
frente a 0,618), no el 44 % de desacuerdo de argmax que C4 midió sobre texto libre. El
problema del campeón es de **criterio**, no de **forma**.

## El otro trozo, que no se puede olvidar: no hay bucle de generación

Aunque los pesos estén en RAM mañana, **`quant/` no sabe generar**. `perplejidad.py`
evalúa en *teacher forcing*: mete todas las ventanas por cada capa de una vez, que es
justo lo contrario de generar un token a partir del anterior. Y no hay **caché KV**,
porque para medir perplejidad no hace falta.

Escribir eso es trabajo de este repositorio ([H2](../holos/H2.md)), no de QuantModels.
Qwen3.8 ayuda: de sus 64 capas solo **16 son de atención**; las otras 48 son GatedDeltaNet,
recurrentes y de estado O(1). La caché KV es, por tanto, **cuatro veces más barata** que
en un transformador denso equivalente — lo que a su vez hace viables contextos largos, que
es exactamente lo que un arnés agéntico necesita.

## Lo que NO se va a hacer, y por qué

- **Tocar la GPU.** Vetado por el autor. Si algo la necesita, es de QuantModels.
- **Bajar a un modelo pequeño «mientras tanto».** Rompería la tesis de META.md y las
  cifras del banco dejarían de significar nada.
- **Usar un GGUF de la comunidad como sustituto.** Mediría otro modelo. El punto del
  proyecto es que el cerebro sea **este**.

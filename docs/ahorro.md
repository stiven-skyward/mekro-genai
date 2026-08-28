# Economía de tokens con cerebros de nube

Con un cerebro local, los tokens son tiempo. Con uno de nube, son **dinero literal**.
Este documento es el análisis y el diseño del ahorro, con las cifras de este proyecto
delante y con lo aprendido de tres herramientas que atacan el problema desde ángulos
distintos.

## Primero: dónde va el dinero, medido aquí

| carrera | vueltas | entrada | salida | ratio |
|---|---|---|---|---|
| `n1/anadir`, gemini-3.7-flash | 6 | 13.869 | 339 | **40,9 : 1** |
| `n2/hallar`, gguf local | 4 | 13.073 | 295 | **44,3 : 1** |

**El gasto es entrada, en proporción de ~40 a 1.** Y la entrada no es el encargo: es la
transcripción entera **reenviada en cada vuelta**. De ahí sale la ley que gobierna todo
lo demás:

> Un token que entra en la transcripción en la vuelta *k* de una tarea de *n* vueltas
> se paga **(n − k + 1) veces**.

Una observación de 5.000 tokens en la vuelta 2 de una tarea de 10 cuesta 45.000 tokens
de entrada. La misma observación en la vuelta 9 cuesta 10.000. **El coste de un dato no
es su tamaño: es su tamaño por lo que le queda de vida.**

## Lo que hacen los tres referentes, y qué se toma de cada uno

### RTK — comprimir en el origen
Un proxy que filtra la salida de ~100 comandos antes de que entre al contexto:
agrupar, deduplicar, truncar con criterio, quedarse solo con los fallos de un test.
Reclama 60-90 % sobre lo interceptado, y su README es honesto en algo importante: eso
**no es un 60-90 % de la factura**, porque la salida de shell es solo una parte de la
entrada. Además sus ganchos solo ven `bash`: lo que el agente lea con herramientas
nativas se le escapa.

**Lo que se toma**: los filtros por comando, nativos y sin dependencia de un binario
externo. **Lo que se mejora**: aquí se aplican también a `leer`, `grep` y `simbolos`,
que en RTK se escapan por diseño.

### Headroom — comprimir en vuelo, y sin romper la caché
Una capa entre agente y proveedor con compresores por tipo de contenido, originales
recuperables por hash, y —lo más fino— un `CacheAligner` que marca lo volátil para no
invalidar el prefijo cacheado del proveedor, más «compresión de zona viva» que solo
toca los bytes recién llegados para que el prefijo congelado siga byte a byte igual.

**Lo que se toma**: la idea de recuperable (comprimir no es perder) y, sobre todo, la
disciplina de no tocar el prefijo. **Lo que se mejora**: aquí el prefijo estable no hay
que detectarlo ni preservarlo — **ya está garantizado por construcción** desde C22, que
lo impuso la caché KV del modelo local. La misma arquitectura que hacía barato el
cerebro local hace barata la nube.

### Ponytail — que el agente produzca menos
Una escalera de decisión inyectada en el prompt: ¿hace falta?, ¿existe ya?, ¿lo hace la
biblioteca estándar?… El ahorro es un efecto secundario de escribir menos código: ~54 %
menos líneas, ~22 % menos tokens, ~20 % menos coste en su banco. Sus autores avisan de
dos cosas honestas: los números tempranos estaban inflados por una línea base
charlatana, y en modelos que razonan puede salir el tiro por la culata si el modelo
gasta tokens de pensamiento decidiendo en qué peldaño pararse.

**Lo que se toma**: menos vueltas y menos salida es menos entrada mañana. **Lo que se
mejora**: aquí no se afirma sin medir — el banco tiene verificador determinista, así
que «sin pérdida de calidad» es una cifra (`tareas_pct` sigue en 100) y no una promesa.

## El hallazgo propio: comprimir hacia atrás CUESTA dinero

La tentación evidente es podar la transcripción: una observación ya consumida —el
fichero que el agente leyó y ya editó— parece peso muerto. **Con caché de prefijo
activa, podarla es una pérdida.** La aritmética, con el descuento típico de 0,1× por
token cacheado:

    T = tamaño de la transcripción · o = lo que se poda · R = vueltas que quedan

    conservar:  T · 0,1 · R
    podar:      (T−o) · 1,0        ← el prefijo cambió: cache miss, se paga entero
              + (T−o) · 0,1 · (R−1)

    Con T = 20.000, o = 5.000, R = 5 →  conservar 10.000  ·  podar 21.000

**Podar cuesta el doble.** Romper el prefijo re-cobra a precio completo TODO lo que
venía cacheado, y eso pesa más que lo ahorrado. De ahí la regla que ordena el diseño:

> **Comprimir en el origen, jamás hacia atrás.** Lo que entra en la transcripción se
> queda; lo que se ahorra hay que ahorrarlo antes de que entre.

Y su corolario incómodo: `renacer()` —que reescribe la transcripción entera— **es un
rompe-cachés**. Se justifica solo porque la alternativa es morir por desbordamiento, y
con ventanas de nube de 1M debería no dispararse casi nunca.

## Lo que dijo la medición (C82, 2026-08-28) — y desmintió medio diseño

El diseño de arriba se midió con el banco y **la predicción quedó refutada**. Lo que
salió es más útil que lo que esperaba, así que queda aquí entero.

### Las observaciones son el 11 % de la factura, no la mayoría

En `n1/cadena` con `gemini-3.7-flash`: 2.326 caracteres de observaciones (~582 tokens)
reenviados unas 4,5 veces son 2.617 de los 23.305 tokens de entrada facturados.
**El 11 %.** Podarlas un 20 % pone el techo del ahorro en un **2,3 % de la factura**.

El resto —el 89 %— es el sistema, las firmas de las herramientas y la salida acumulada
del propio modelo, todo reenviado en cada vuelta. La poda no lo toca.

### El instrumento es cinco veces más ruidoso que la señal

Dos controles idénticos, sin tocar nada entre uno y otro, dieron **+12,4 %** de
diferencia. El efecto que se buscaba era del 2 %. La medición estaba condenada antes de
empezar, y tres minutos de correr el control dos veces lo habrían dicho.

| brazo | entrada total | tareas |
|---|---|---|
| control 1 | 149.733 | 6/6 |
| control 2 | 168.236 | 6/6 |
| con poda | 166.058 | 6/6 |

### Lo que sí se vio, y no estaba en ninguna de las tres herramientas

**El delta de entrada siguió al delta de VUELTAS en las seis tareas, sin una excepción**:

| tarea | vueltas | entrada |
|---|---|---|
| `anadir` | 6 → 7 | +16,1 % |
| `bitacora` | 12 → 14 | +40,1 % |
| `cadena` | 13 → 11 | **−23,2 %** |
| `fuga` | 8 → 7 | **−16,7 %** |
| `migrar` | 12 → 14 | +37,7 % |
| `rojo` | 6 → 7 | +16,2 % |

Como la transcripción se reenvía entera, **una vuelta de más cuesta un prefijo completo**
y se come cualquier poda. De ahí la ley que sustituye a la intuición de «recortar bytes»:

> Un ahorro se juzga por si cambia el **número de vueltas**, no por los bytes que
> recorta. RTK mide bytes sobre la salida interceptada: es la unidad equivocada.

Esto reordena las tres herramientas de referencia. La que ataca la variable correcta no
es RTK ni headroom: es **ponytail**, que reduce vueltas y salida. Lo que no cambia es
que sus números tampoco están verificados contra un banco determinista.

### La caché de prefijo: medida, y es la palanca de verdad (C83, 2026-08-28)

Es la única que toca el **100 %** de la entrada, y ahora está medida con clave real en
dos proveedores.

| proveedor | tres peticiones idénticas de ~6 K | carrera real |
|---|---|---|
| `gemini-3.7-flash`, implícita | **nunca reporta** caché | 0 % |
| `gemini-3.7-flash`, `cachedContents` | — | **50,0 %** sobre `n1` entero, 6/6 en verde |
| `gpt-4.1-mini`, automática | 5.760 de 5.957 en la 2.ª (**96,7 %**) | **76,6 %** en `n1/anadir` |

**Gemini no tiene caché implícita.** No es un fallo del prefijo de este arnés —es
estable por construcción— sino un hecho del proveedor: hay que pedirle `cachedContents`
explícito, con un mínimo de 1.024 tokens (medido contra un 400 que lo dice).

**OpenAI la aplica sola, y sin tocar una línea de código.** Ahí está lo que más vale de
todo esto: el prefijo append-exacto que C22 impuso por la caché KV del modelo *local* es
exactamente la forma que la caché del *proveedor* necesita. **La misma arquitectura paga
dos veces.**

Tres cosas que hubo que resolver, y las tres eran silenciosas:

1. **Cuándo reescribir la caché.** Escribirla cuesta como entrada normal: escribir *T* y
   leerlo *K* veces con descuento sale a *T*·(1 + 0,25·*K*) frente a *T*·*K*, así que
   gana solo a partir de *K* > 1,33 — la segunda lectura. El umbral lo escribí primero
   contando **mensajes**, y la economía depende de **tokens**: un turno de 20 caracteres
   y otro de 40.000 pesan igual en la cuenta de mensajes y nada parecido en la factura.
2. **Las herramientas viven dentro de la caché.** El riesgo real era que el modelo
   dejara de verlas. Las seis tareas de `n1` pasaron con la caché puesta, así que no.
3. **Una caché que sobrevive a la tarea se sigue cobrando por horas.** `cerrar()` existía
   y no lo llamaba nadie. Ahora lo cierran el banco y la CLI, verificado con la lista del
   proveedor en cero tras una carrera.

**¿Y qué cuesta la caché en reloj? Nada medible** (C86, A/B con los dos brazos
seguidos sobre `n1`):

| brazo | s/tarea | cacheado | entrada |
|---|---|---|---|
| sin caché | 372,4 | 0 % | 35.424 |
| con caché | 344,7 | 49,5 % | **30.312 (−14,4 %)** |

El −7,4 % de reloj **no** es un beneficio: por tarea el rango va de −35,7 % a +58,7 %, y
con seis tareas eso no distingue nada. Lo honesto es que la caché no mueve el reloj en
ninguna dirección, y que lo sólido es el −14,4 % de entrada, que es contabilidad del
proveedor y no un cronómetro.

> **Aviso a quien mida aquí.** La latencia de un proveedor externo varía por seis en unas
> horas: el mismo banco dio 34,5 s/tarea por la mañana y 372 por la tarde, sin tocar una
> línea. **Una cifra de reloj no se compara entre carreras separadas en el tiempo.** Si
> se compara, los dos brazos corren seguidos. Y un umbral sobre algo que depende de un
> tercero se predice como **razón entre brazos**, no como valor absoluto — si no, se
> cumple sin probar nada (C86, y antes C83).

En Anthropic el marcador `cache_control` va puesto pero **no hay clave para verificarlo
de punta a punta**, así que no se declara. La cifra ya sale en cada carrera
(`CIFRA cache_pct`): quien tenga clave la ve sin tocar código.

### Entonces, ¿para qué sirve la poda?

Para el caso que este banco **no tiene**: un `grep` de 40 aciertos, una compilación
ruidosa, una suite de 400 líneas en verde. En `n1` las observaciones son pequeñas y por
eso no hay nada que ahorrar. Que el banco no ejercite el caso es la brecha 6 otra vez, y
la poda se queda encendida porque no cuesta nada (las tareas siguieron en 100 %) y
porque el caso para el que se hizo llegará en cuanto el banco lo tenga.

## El diseño, en orden de dinero

1. **Caché de prefijo del proveedor** — la palanca mayor y la más barata de conseguir,
   porque la forma de la transcripción ya es la correcta. Anthropic exige marcar el
   bloque (`cache_control`); OpenAI, DeepSeek y Gemini la aplican solos si el prefijo
   no cambia. Descuento típico: 0,1× (Anthropic) a 0,5× (OpenAI).
2. **Poda en el origen** — los filtros de RTK, nativos, aplicados a TODA herramienta y
   no solo a `bash`, y con **poda proporcional a lo que queda de tarea**: en la vuelta 2
   se poda fuerte, en la vuelta 9 se afloja, porque el mismo dato cuesta ahí cinco veces
   menos.
3. **Menos vueltas** — lo de Ponytail, pero medido contra el verificador.

## La regla que hace esto creíble

Cada ahorro se mide con el banco y **`tareas_pct` tiene que seguir en 100**. Un ahorro
que rompe una tarea no es un ahorro: es una avería con buena prensa.

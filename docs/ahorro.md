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

# La vía densa: correr el Qwen3.8-27B **sin cuantizar** en CPU

> Encargo del autor (2026-08-22): una **vía alterna a la cuantización**. Que el modelo
> corra en BF16 completo, en CPU y RAM, sin GPU (la usa otro proyecto), a velocidad
> decente y **sin pérdida de calidad**.
>
> La vía cuantizada vive en `E:\QuantModels` y no se toca aquí. Estas dos vías no compiten:
> al final del documento se ve que **encajan**, y que la mejor versión de cada una necesita
> a la otra.

## El problema, en una ecuación

Decodificar un token con un modelo denso exige leer **todos** los pesos. No hay atajo: no
es que el código sea mejorable, es que la operación es esa. Por tanto

    t_token  ≥  bytes_del_modelo / ancho_de_banda_de_donde_estén

52 GB en BF16. Todo lo demás —el modelo, el código, la biblioteca— es irrelevante frente a
ese cociente. Así que lo primero fue medir los tres anchos de banda de esta máquina.

## EL TECHO DE ESTA VÍA, MEDIDO (2026-08-23) — léelo antes que nada

Tres ciclos midieron la tasa de aceptación con tres borradores que no se parecen en nada,
contra el mismo BF16 y el mismo corpus de código. Los tres dan lo mismo:

| borrador | GB residentes | α (código) | γ óptimo | tokens/pase | **tok/s** |
|---|---|---|---|---|---|
| campeón Qwen3.8-27B a 2 bits | 8,00 | 0,5631 | 4 | 2,093 | **0,255** |
| Qwen3.5-2B BF16 | 4,30 | 0,5692 | 4 | 2,113 | **0,302** |
| **Qwen3.5-0.8B BF16** | **1,66** | 0,5401 | 4 | 2,014 | **0,328** |

Un factor **35 en parámetros mueve α 0,029**. La barra de D2 (≥1 tok/s) es α ≥ 0,821 y la
de D3 (≥2 tok/s) es α ≥ 0,911. Con la pendiente medida —+0,029 por cada ×2,5 de tamaño—
llegar a 0,821 pediría un borrador mucho mayor que el propio objetivo. **No hay borrador
que quepa en esta máquina que alcance D2 por esta vía.**

Cuando tres borradores dispares convergen al mismo número, el número no habla del
borrador: habla del **objetivo**. La entropía del BF16 sobre este corpus (PPL 6,132 en
código, 8 ventanas de 512) es la que fija el techo.

Y el mejor borrador resultó ser **el más pequeño**, aunque acepte menos: proponer un token
cuesta leer los pesos del borrador, y la RAM de esta máquina da **24,6 GB/s de tráfico**
(copia de 1 GB en 81 ms, 16 hilos, medido). Los 8 GB del campeón cuestan 0,40 s por
propuesta; los 1,66 GB del 0,8B, 0,08 s. **Queda enterrada la idea que abría este
documento**: el campeón de 2 bits no es el borrador ideal, ni por acuerdo ni por coste.

Lo que esta vía **sí** es, y no es poco: el **patrón de oro**. El BF16 corriendo en CPU es
la referencia contra la que se mide cualquier cuantización, y ya está medido y cacheado en
`registros/cache-grande-C4corpus.pt`. El camino crítico vuelve a la vía cuantizada (H1),
donde el factor no es 2,2 sino ~250, porque los pesos dejan de leerse del disco.

## Los tres anchos de banda (medidos 2026-08-22, `scripts/medir_ancho_banda.py`)

| dónde | GB/s | un pase por los 52 GB |
|---|---|---|
| **9p (`/mnt/e`)** | **0,20** | **256 s** |
| NVMe en ext4, O_DIRECT, 1 hilo | 5,25 | 9,9 s |
| **NVMe en ext4, O_DIRECT, 2-4 hilos** | **6,77** | **7,7 s** |
| RAM (16 hilos, lectura) | 38,3 | 1,4 s |

Máquina: AMD Ryzen 7 7745HX (8 núcleos / 16 hilos, L3 32 MB), 31,7 GB de RAM (~20 GB
disponibles), NVMe con 884 GB libres en la VHD de WSL.

### El primer hallazgo, y es de ingeniería pura

**`/mnt/e` no es el disco: es un protocolo.** El montaje es 9p con `msize=65536` (mensajes
de 64 KB) sobre DrvFs. El mismo NVMe, accedido por el sistema de ficheros ext4 nativo de
WSL, va **33× más rápido**. Los 256 s/token que parecían la física del problema eran, en su
mayor parte, el coste de atravesar una capa de compatibilidad.

Mover el modelo a ext4 no cuesta calidad, ni precisión, ni un solo bit: es copiar un
fichero. **De 256 s/token a 7,7 s/token, gratis.** Es H7.

## El segundo hallazgo: sobra cómputo por todas partes

Decodificar de uno en uno tiene una intensidad aritmética ridícula —una multiplicación y
una suma por cada peso leído— y el hardware está construido para lo contrario. Medido sobre
una matriz real del modelo (17408×5120 BF16, 178 MB, 16 hilos):

| lote | ms/pase | ms/token | GFLOP/s |
|---|---|---|---|
| 1 | 11,35 | 11,35 | 16 |
| 8 | 9,21 | **1,15** | 155 |
| 32 | 10,74 | **0,34** | 531 |
| 64 | 12,48 | 0,19 | 914 |

**Procesar 8 tokens cuesta 0,81× lo que cuesta procesar 1.** No un poco menos: *menos*.
Hasta lote 64 el pase cuesta solo un 10 % más que el de lote 1. La CPU se pasa el rato
esperando memoria, y meterle siete tokens más de trabajo no le cuesta nada.

Registro: ciclo C2, `registros/ciclos/C2.json`.

## De ahí sale la tesis

Si un pase sirve para 8 tokens al mismo precio que para 1, la pregunta deja de ser «cómo
leo más rápido» y pasa a ser **«cómo saco más tokens de cada pase»**. Y hay una técnica que
hace exactamente eso y es **demostrablemente sin pérdida**:

> **Decodificación especulativa.** Un modelo pequeño propone K tokens; el grande los
> verifica en UN solo pase; se acepta el prefijo que el grande habría generado y se corrige
> el primero que no. El algoritmo de muestreo especulativo produce **exactamente** la misma
> distribución que el modelo grande solo. No es una aproximación: es álgebra.

Con lo medido, el presupuesto por token queda así:

| configuración | s por pase | s/token | tok/s | de dónde sale |
|---|---|---|---|---|
| hoy, desde 9p | 256 | 256 | 0,004 | medido |
| desde NVMe ext4 (H7) | 8,2 | 8,2 | 0,12 | medido (C2/`medir_ancho_banda`) |
| + compresión sin pérdida ×1,4627 (C3) | **5,6** | 5,6 | 0,18 | medido, **si el lector solapa** |
| **+ especulación con el campeón de 2 bits, 2,227 aceptados** | 5,6 | **2,51** | **0,40** | **medido (C4)** |
| + especulación, 4 aceptados | 5,6 | 1,4 | 0,71 | hace falta α ≥ 0,75 · **no se llega** |
| + especulación, 8 aceptados | 5,6 | 0,70 | 1,43 | hace falta α ≥ 0,875 · **no se llega** |
| + especulación, 16 aceptados | 5,6 | 0,35 | 2,86 | hace falta α ≥ 0,9375 · **no se llega** |

Las tres primeras filas están medidas. La cuarta también, desde el 2026-08-23: **C4 refutó
las tres últimas**. Con el campeón de 2 bits como borrador el acuerdo greedy con el BF16 es
**0,5631 en código y 0,5230 en español** (sobre 4088 tokens por dominio,
`registros/2026-08-22_C4-aceptacion.json`), y de ahí salen **2,227 tokens por pase**, no 4.

Y γ no es la palanca que faltaba: el techo con γ infinito es 1/(1−α) = **2,289**, y con γ=8
ya se saca el **97,3 %** de ese techo (γ=16 da 2,274). Alargar el borrador no arregla nada.
Lo único que sube tokens/pase es **subir α**, y para llegar a 1 tok/s hace falta α ≥ 0,821.

La causa está medida: sobre este dominio y en ventanas de 512, la perplejidad del campeón
es **15,967 en código y 17,518 en español**, frente a **5,764 y 4,839** del BF16
(`registros/2026-08-23_C4-integridad-ppl.json`). El hueco real es de ×2,8 a ×3,6, no el
×1,43 que sugiere el par 7,46 / 5,21 del conjunto de evaluación de QuantModels. **La PPL no
predice el acuerdo de argmax**: un modelo que pierde 2,25 puntos de PPL en su conjunto de
evaluación cambia el token más probable en el 44 % de las posiciones del dominio de trabajo.

El cómputo no estorba: los GEMM de las 64 capas con pesos residentes tardan 4,11 s por
pase de un token y **0,45 s por token** con lote 8 (C2), así que se esconde debajo de los
5,6 s de E/S siempre que el lector solape. El techo lo pone el disco, no la CPU.

**Aviso honesto**: esa cuenta mide los GEMM de los pesos. No incluye atención, estado
recurrente de las 48 capas deltanet, normas ni el coste del borrador, y supone solapamiento
perfecto. El número que zanjará esto es D2 medido de extremo a extremo, no esta tabla.

Y sobre **el coste del borrador** hay algo que la tabla nunca ha contado y que C4 obliga a
mirar: el campeón no es un modelo pequeño, es **el mismo modelo de 27,8 G parámetros** a 2
bits. Proponer γ tokens exige γ pases por sus ~8 GB residentes, y a un ancho de banda de RAM
del orden de decenas de GB/s eso son segundos que se suman a los 5,6 del pase grande, no
décimas que se esconden. **No está medido** —es la cuenta de servilleta, no una cifra— pero
apunta en la misma dirección que C4: el borrador correcto es un modelo **pequeño de verdad**
(0,6 B), no este modelo comprimido. Medirlo es parte de C7.

### En qué se van los 55,6 GB (medido sobre el índice del checkpoint)

| parte | parámetros | GB en BF16 | % |
|---|---|---|---|
| capas de texto (64) | 24,778 G | 49,56 | 89,2 |
| embed + lm_head | 2,543 G | 5,09 | 9,2 |
| torre de visión | 0,461 G | 0,92 | 1,7 |
| **total** | **27,781 G** | **55,56** | |

Nueve de cada diez bytes están en las capas, así que ahí es donde hay que pelear. La torre
de visión se puede tirar entera para trabajo de texto y solo ahorra un 1,7 %: es cierto,
es gratis, y no cambia nada. Conviene saberlo para **no** perder una tarde en ello.

## Las palancas, y cuáles son de verdad sin pérdida

| palanca | ganancia esperada | ¿sin pérdida? | estado |
|---|---|---|---|
| **Sacar el modelo de 9p a ext4** | ×33 | sí, es copiar un fichero | **H7**, en curso |
| **Decodificación especulativa** | **×2,23 medido (C4)**, no ×3-6 | **sí, por construcción** (muestreo especulativo) | H8, y con el borrador equivocado |
| **Residencia parcial en caché de página** | ×1,3-1,4 | sí, es dónde vive el byte | H9 |
| **Compresión BF16 sin pérdida** (planos de bytes tipo ZipNN) | **×1,46 medido** | sí, verificado bit a bit | C3 |
| **Solapar E/S con cómputo** (prefetch de la capa siguiente) | hasta ×1,15 | sí | H7 |
| Quitar la torre de visión | **−0,92 GB (1,7 %)** | sí para texto | medido: palanca real pero pequeña |
| Esparsidad de activación (tipo PowerInfer) | ×2-5 en el MLP | **no exactamente**: SiLU nunca es cero. Habría que medir ΔPPL | horizonte |

Las cinco primeras son **exactamente** sin pérdida: no cambian ni un bit de ningún peso ni
la distribución de salida. La última no lo es, y por eso está en el horizonte y no en el
plan.

## El tercer hallazgo: BF16 encoge un 46 % sin perder un bit — pero solo si se solapa

Ciclo C3. Un BF16 es 1 signo + 8 exponente + 7 mantisa. Separando los **planos de bytes**
—todos los bytes altos juntos, todos los bajos juntos— y comprimiendo con zstd nivel 1
(medido sobre 1 GB de pesos reales del shard 1, 16 hilos, máquina ociosa):

| variante | razón | descompresión | efectivo en serie | efectivo solapado |
|---|---|---|---|---|
| entrelazado (tal cual) | 1,284 | 10,1 GB/s | 4,67 GB/s | 8,69 GB/s |
| **planos de bytes** | **1,462** | 10,1 GB/s | 4,99 GB/s | **9,90 GB/s** |
| solo el plano alto | 1,462 | 16,4 GB/s | 6,18 GB/s | 9,90 GB/s |

Reconstrucción **bit a bit verificada** en las tres variantes. El plano alto por sí solo
comprime **2,72×** (los pesos viven en pocos órdenes de magnitud); el bajo, que es mantisa,
no comprime nada — comprimirlo cuesta tiempo y no encoge, y por eso la fila «solo el plano
alto» descomprime un 60 % más rápido con la misma razón.

**Y aquí está la decisión de arquitectura**, que es lo que de verdad enseñó este ciclo:

| lector | efectivo | veredicto |
|---|---|---|
| ingenuo: leer y **luego** descomprimir | 6,18 GB/s | **×0,91 — peor que no comprimir** |
| con prefetch: leer la capa N+1 **mientras** se descomprime la N | 9,90 GB/s | ×1,46 |

Disco y CPU son recursos distintos; si no se solapan, comprimir hace el sistema más lento
aunque el fichero sea un 31 % menor. El prefetch de H7 deja de ser una optimización del
10 % y pasa a ser **la condición para que la compresión sirva de algo**.

## Dónde encajan las dos vías

La conclusión bonita, y no estaba planeada:

> **El mejor borrador para la vía densa es el campeón de la vía cuantizada.**

La decodificación especulativa necesita un modelo pequeño y rápido que proponga tokens que
el grande acepte a menudo. El candidato ideal no es un Qwen pequeño cualquiera: es **el
mismo modelo cuantizado a 2 bits** (~8 GB, residente en RAM), que por construcción propone
casi siempre lo que el grande habría dicho — su PPL es 7,46 frente a 5,21 del BF16, o sea
que se equivoca poco.

Y el resultado combinado tiene una propiedad que ninguna de las dos vías tiene por separado:
**la salida es exactamente la del modelo BF16** (lo garantiza el muestreo especulativo),
**a una velocidad cercana a la del modelo de 2 bits**. La cuantización deja de ser una
concesión de calidad y pasa a ser un acelerador de una ejecución exacta.

Eso convierte a `E:\QuantModels` en proveedor de borradores, no solo de cerebros.

## La cola de ciclos

| ciclo | pregunta | coste | estado |
|---|---|---|---|
| **C2** | ¿verificar 8 tokens cuesta lo mismo que 1? | 10 s | ✅ **CONFIRMA**: 0,879 sobre matrices reales |
| **C3** | ¿cuánto comprime BF16 sin pérdida y a qué velocidad? | 4 min | ✅ **CONFIRMA**: ×1,4627 sobre los 56 GB, 18/18 shards bit a bit |
| **C4** | ¿cuántos tokens se aceptan de verdad, en código y en español? | 33 min | ✗ **REFUTA**: 2,227 tokens/pase en código (predicho ≥4,0). α = 0,5631 |
| **C7** | ¿llega el Qwen3.5-0.8B a α ≥ 0,82? | 44 min | ✗ **REFUTA**: α = 0,5401, *peor* que el campeón. Pero gana como borrador: 0,328 tok/s frente a 0,255 |
| **C9** | ¿sube α con el tamaño del borrador o está la curva plana? | 11 min (caché) | ✓ **CONFIRMA que está plana**: 0,8B→0,5401 · 2B→0,5692 · 27,8B@2bit→0,5631 |
| **C5** | ¿cuál es el s/token real de extremo a extremo desde ext4? | horas | bloqueado por H7 |
| ~~C6~~ | ¿cuánto ocupa la torre de visión? | 1 min | contestado sin ciclo: **0,92 GB, 1,7 %**. No merecía una hipótesis |

Reglas de siempre: la predicción se escribe antes ([`ciclo.py`](../ciclo.py)), la sonda
barata va antes que la carrera cara, y ninguna cifra de este documento existe sin su
registro.

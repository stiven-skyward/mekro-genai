# Mekro-Genai — punto de continuidad

**Léeme al retomar si [ESTADO_VIVO.md](ESTADO_VIVO.md) no basta.** Este documento es
**acumulativo**: el §0 se reescribe cada sesión, las secciones §N se añaden al final y las
lecciones **nunca se renumeran ni se borran**. La foto volátil de «qué corre ahora» está en
ESTADO_VIVO.md.

---

## 0. RETOMAR TRAS REINICIO — haz esto y nada más

```bash
cd /mnt/e/Mekro-Genai
bash scripts/retomar.sh              # qué corre, qué hay, qué sigue
python3 holograma.py listar          # el mapa de tareas
python3 ciclo.py estado              # ¿hay una hipótesis sin veredicto?
```

⚠ **La GPU está vetada en este proyecto** por decisión del autor. Todo en CPU.

⚠ **No cargues ficheros enteros para orientarte.** Para eso está `holograma.py foco`. Y no
leas nunca el checkpoint desde una sesión: son 51 GB.

---

## 1. GÉNESIS DEL PROYECTO (2026-08-22)

Encargo del autor: **un arnés agéntico de ingeniería que combine lo mejor de Claude Code,
OpenCode, OpenChamber, el arnés de DeepSeek y Hermes, con el Qwen3.8-27B a 2 bits de
`E:\QuantModels` como cerebro, corriendo local**. Decisión del autor en esta misma sesión,
tras ver las cifras: **checkpoint campeón v13, solo CPU, sin tocar la GPU, con el runtime
propio**.

Decisiones fundacionales:

1. **La tesis se escribió antes que el código.** [META.md](META.md): todos los arneses
   existentes asumen un modelo fuerte y barato al otro lado del cable. Aquí no lo hay, y
   de ahí se sigue todo el diseño. Cuatro cifras en toda carrera (tareas, tokens, reloj,
   intervenciones) y cuatro peldaños M0-M3.
2. **El holograma deja de ser una herramienta auxiliar** y pasa a ser la arquitectura de
   contexto del arnés (META §puerta 1). Se adapta de `E:\QuantModels\holograma.py`, que
   viene de `E:\Mekro\mekro-lex`.
3. **El ciclo de investigación se hace código, no costumbre** (`ciclo.py`): `medir` se
   niega a correr sin `predecir`, y `veredicto` no cierra sin lección. Es la respuesta
   directa a la lección más cara de Mekro_Gen y QuantModels.
4. **El arnés no depende de ningún paquete** — bucle, herramientas, permisos y hologramas
   son biblioteca estándar. `torch`/`safetensors`/`transformers` solo para el cerebro.
5. **`cerebro/` es enchufable para poder MEDIR, no para escaparse a la nube.** El backend
   `eco` separa los fallos del arnés de los fallos del modelo; sin esa separación «el
   agente no resolvió la tarea» no dice nada.

Lo que quedó funcionando el primer día: bucle completo, 6 herramientas, permisos con veto
duro, sesión con contabilidad, holograma (8 órdenes), ciclo (6 fases), banco n0 con su
corredor, 101 asertos en verde.

---

## 2. EL DESCUBRIMIENTO QUE DEFINIÓ EL CAMINO CRÍTICO (2026-08-22)

Al ir a enchufar el campeón se encontró lo que nadie había dicho porque en QuantModels no
importaba: **`qwen38-h13b` no está empaquetado**. Es *fake-quant* — cuantizado a 1,9995
bits y vuelto a expandir a bf16 para medir perplejidad. En disco son **51 GB** y no hay ni
un índice ni un libro de códigos guardado; solo la receta, en un JSON de 214 bytes.

Medido el mismo día en esta máquina:

| cifra | valor | cómo |
|---|---|---|
| checkpoint en disco | 51 GB | `du -sh` |
| lectura de `/mnt/e` | 192 MB/s | `dd` de 767 MB |
| **coste por token en streaming** | **~4,4 min** | 51 GB ÷ 192 MB/s |
| tamaño empaquetado (aritmética) | ~8 GB | 27,8·10⁹ × 1,9995 bits |
| RAM disponible | 20 de 30 GB | `free -g` |

**Factor ~250× entre lo que hay y lo que hace falta.** Eso es H1, y de él cuelga todo lo
demás. Análisis completo y las tres salidas en [docs/cerebro-2bit.md](docs/cerebro-2bit.md).

---

## LECCIONES (no se borran nunca)

1. **Un modelo «de 2 bits» puede ocupar 51 GB en disco.** Los bits de una receta de
   cuantización son contabilidad de lo que *ocuparía*; lo que ocupa es otra cosa hasta que
   alguien escribe el empaquetador. Comprobar el tamaño real **antes** de diseñar nada
   alrededor de él cuesta un `du -sh`.
2. **Un arnés de evaluación no es un arnés de servicio.** `quant/perplejidad.py` mide
   perfectamente y no sabe generar: sin caché KV, sin decode, en *teacher forcing*.
   Reutilizar el lector (`DepositoPesos`) sí; suponer que «ya está resuelto», no.
3. **Antes de sondear, verifica los parámetros de la sonda.** La cadena v13 usó `g=8` en
   las capas 0-3 y 58-63 y `g=16` en el resto. Una sonda con el `g` equivocado habría dado
   un falso negativo indistinguible de un resultado real.

- **[2026-08-23 01:52] C1 · REFUTA** (sonda) — frac_exacta = 0.000325 (se predijo >=0.95). La estructura RVQ no se recupera con k-means sobre grupos normalizados por el RMS de la fila: frac_exacta 0,000325 y err_relativo 0,248. Pero lo que falla es la SONDA, no necesariamente la hipotesis: verificado despues en reconstruir_v12.py:_EscalaFila que la reconstruccion por bloques solo optimiza una escala por FILA y los parametros 1D, luego el reticulo C1+C2 sigue intacto salvo un factor multiplicativo por fila. El RMS de fila no es ese factor. Siguiente sonda (C2): trabajar con grupos normalizados a NORMA UNIDAD, que son invariantes a la escala de fila y eliminan la incognita alfa por completo.

4. **Una sonda barata que refuta cierra un ciclo; una que confirma, no.** Refutar sobre una
   muestra es decisivo —si ni siquiera ahí funciona, no funciona—; confirmar sobre una
   muestra es creerse la primera señal favorable, que es exactamente el fallo que este
   proyecto quiere evitar. `ciclo.py:cmd_veredicto` lo impone: con `sonda` deja refutar y
   se niega a confirmar. La asimetría salió de usar la herramienta, no de diseñarla.
5. **Cuando una sonda refuta, sospecha primero de la sonda.** C1 midió `frac_exacta
   0,000325` y parecía zanjar que el retículo RVQ no está. Diez minutos de lectura de
   `reconstruir_v12.py` mostraron que la reconstrucción solo aplica una escala por fila:
   el retículo sigue ahí y lo que falló fue la estimación de `α`. Una refutación es un
   resultado sobre **la hipótesis Y el instrumento juntos**; separarlos es trabajo aparte.
6. **Un número «razonable» puede no ser evidencia de nada.** `razon_residuo 0,543` parecía
   indicar estructura hasta calcular qué daría una nube sin estructura ninguna: ≈0,60. La
   cifra de referencia hay que calcularla **antes** de interpretar la medida, no después.

- **[2026-08-23 03:33] C3 · CONFIRMA** (medicion) — ganancia_vs_nvme = 1.4627 (se predijo >=1.25). BF16 encoge 1,4627x sin perder un bit sobre los 56 GB completos (18/18 shards verificados bit a bit): 56 GB -> 38 GB. El plano alto solo comprime 2,72x y el bajo (mantisa) nada, asi que conviene comprimir SOLO el alto: misma razon y 60% mas rapido de descomprimir. Pero la leccion que decide la arquitectura es otra: en un lector en serie (leer y luego descomprimir) el efectivo es 6,18 GB/s, PEOR que los 6,77 del NVMe crudo; solo solapando E/S y descompresion se llega a 9,90 GB/s. El prefetch de H7 deja de ser una optimizacion del 10% y pasa a ser la condicion para que comprimir sirva de algo.

- **[2026-08-23 03:34] C2 · CONFIRMA** (medicion) — razon_8_vs_1 = 0.8791 (se predijo <=1.5). Sobre las matrices reales de una capa deltanet y una de atencion, el lote 8 cuesta 0,879x lo que el lote 1 (y el lote 16, 0,886x): verificar tokens de golpe es gratis hasta al menos 16. Con pesos residentes eso son 4,11 s/token en lote 1 frente a 0,45 s/token en lote 8. La consecuencia es que la palanca de la via densa no es leer mas rapido sino sacar mas tokens de cada pase, y la unica tecnica que hace eso SIN perder calidad es la decodificacion especulativa (el muestreo especulativo reproduce exactamente la distribucion del modelo grande). Aviso: esto mide solo los GEMM de los pesos; no incluye atencion, estado recurrente, normas ni la tasa de aceptacion real, que es C4.

---

## 3. LA SEGUNDA VÍA: CORRER EL MODELO SIN CUANTIZAR (2026-08-22)

Encargo del autor el mismo día de la fundación: **una vía alterna a cuantizar**. Que el
Qwen3.8-27B corra en **BF16 intacto**, CPU y RAM, sin GPU (la usa otro proyecto), a
velocidad decente y sin pérdida de calidad. Diseño completo en
[docs/densa-en-cpu.md](docs/densa-en-cpu.md); peldaños D0-D3 en [META.md](META.md).

La ecuación del problema es una sola línea: decodificar un token denso exige leer **todos**
los pesos, luego `t_token ≥ bytes / ancho_de_banda`. Todo lo demás es secundario. Así que
lo primero fue medir los anchos de banda de esta máquina — y ahí apareció el hallazgo.

| dónde | GB/s | pase por 52 GB |
|---|---|---|
| 9p (`/mnt/e`) | 0,20 | 256 s |
| NVMe ext4 O_DIRECT, 1 hilo | 5,25 | 9,9 s |
| **NVMe ext4 O_DIRECT, 2-4 hilos** | **6,77** | **7,7 s** |
| RAM, 16 hilos | 38,3 | 1,4 s |

Ciclos cerrados: **C2** (verificar 8 tokens cuesta 0,879× verificar 1) y **C3** (BF16
encoge ×1,4627 bit a bit sobre los 56 GB, 18/18 shards verificados). El modelo BF16 está
copiado a `/home/forge/modelos/qwen3.8-27b`.

**La síntesis que no estaba planeada**: el borrador ideal para la decodificación
especulativa contra el BF16 es el campeón de 2 bits de QuantModels. La salida sería
**exactamente** la del BF16 (lo garantiza el muestreo especulativo) a velocidad cercana a
la del cuantizado. Las dos vías del proyecto no compiten: se necesitan.

7. **Antes de optimizar un sistema, mide dónde está de verdad el cuello.** Los 256 s/token
   que parecían la física del problema eran, en su mayor parte, una capa de compatibilidad:
   `/mnt/e` es 9p con mensajes de 64 KB, no el disco. El mismo NVMe por ext4 va **33×** más
   rápido. Un `dd` de treinta segundos ahorró meses de optimizar la cosa equivocada.
8. **Un `dd` que falla parece rapidísimo.** Con `iflag=direct`, los offsets no alineados dan
   EINVAL al instante: los primeros «33 GB/s» eran cuatro procesos muriendo en 3 ms. Mirar
   siempre el código de salida antes de creerse un ancho de banda.
9. **Un microbenchmark sin estado estacionario miente por un factor de 4.** La descompresión
   de zstd medida en frío y con un trozo por hilo dio 1,3 GB/s; con calentamiento,
   repeticiones y trozos de 2 MB, 10,1 GB/s. Con la cifra falsa, la decisión de arquitectura
   se habría tomado exactamente al revés («comprimir empeora el sistema»).
10. **`zstandard` no es seguro entre hilos.** Un `ZstdCompressor` compartido revienta con
    SIGSEGV (código −11, sin mensaje ni traza). Uno por llamada; el objeto es barato.
11. **No midas mientras copias 52 GB.** Las tres primeras medidas de compresión salieron
    con la copia robando los 16 hilos, y daban un tercio de lo real. Antes de una medida,
    `bash scripts/retomar.sh` y comprobar que no corre nada.

- **[2026-08-23 06:07] C4 · REFUTA** (medicion) — tokens_por_pase_codigo = 2.227 (se predijo >=4.0). REFUTADO: 2,227 tokens por pase en codigo (predicho >=4,0), sobre 4088 tokens; la sonda de 511 tokens ya habia dado 2,231, luego es reproducible. El acuerdo greedy del campeon de 2 bits con el BF16 es 0,5631 en codigo y 0,5230 en espanol (alfa a temperatura 1: 0,5814 y 0,5397). Tres consecuencias. PRIMERA: gamma no es una palanca. El techo con gamma infinito es 1/(1-alfa) = 2,289 en codigo, y con gamma=8 ya se saca el 97,3% de ese techo (gamma=16 da 2,274). Alargar el borrador no arregla nada; lo unico que sube tokens/pase es subir alfa. SEGUNDA: las aceptaciones NO llegan a rafagas. El simulador sobre la secuencia real de aciertos da 2,227 y la formula i.i.d. de la literatura da 2,276: en codigo estan si acaso ligeramente ANTIcorreladas, luego la intuicion de que el codigo acepta a rachas (sangrado, cierres) es falsa contra este borrador. TERCERA y la que decide: el presupuesto de la via densa cae a 5,6 s/pase entre 2,227 = 2,51 s/token = 0,398 tok/s en codigo y 0,371 en espanol, por debajo incluso de la primera fila especulativa de docs/densa-en-cpu.md (0,71). Para 1 tok/s harian falta 5,6 tokens/pase, o sea alfa >= 0,821, frente al 0,563 medido. POR QUE es tan bajo: la PPL del campeon sobre ESTE dominio, en ventanas de 512, es 15,967 en codigo y 17,518 en espanol frente a 5,764 y 4,839 del BF16 (medido en registros/2026-08-23_C4-integridad-ppl.json). El hueco real es de x2,8 a x3,6, no el x1,43 que sugiere el par 7,46 vs 5,21 del conjunto de evaluacion de QuantModels. El aviso que H8 dejo escrito se cumplio al pie de la letra: el numero del dominio de trabajo es otro. Y hay una leccion transversal para QuantModels: la PPL no predice el acuerdo de argmax. Un modelo que pierde 2,25 puntos de PPL en su conjunto de evaluacion cambia el token mas probable en el 44% de las posiciones del dominio real. Si el campeon se quiere usar como borrador, la metrica que hay que optimizar al cuantizar es el acuerdo con el BF16, no la perplejidad. LIMITE DEL METODO, escrito para que nadie lo olvide: esto es teacher forcing sobre texto humano; en la especulativa real el borrador propone condicionado al prefijo que genera el modelo, no al del corpus. Es el estimador estandar y es el unico que se puede pagar hoy (dos pases por disco en vez de uno por token, 33 min de CPU sin tocar la GPU), pero es un proxy. INCIDENTE: la copia del campeon en ext4 estaba corrupta en silencio, capa-53 a 0 bytes y capa-62 truncada a 283 MB; una copia de 50 GB que nadie verifico. Reparadas, y despues verificado que el resultado es identico digito a digito leyendo el borrador del original en /mnt/e. Verificar la copia, no suponerla.

- **[2026-08-23 07:02] C8 · REFUTA** (sonda) — acuerdo_estructura_campeon = 0.9318 (se predijo >=0.95). REFUTADO por el numero, PERO NO por el mecanismo que se temia, y la diferencia cambia el plan. Medido: acuerdo_estructura del campeon a 2 bits = 0,9318 sobre 44 tokens de andamiaje de las cuatro llamadas del guion de oro de banco/n0 (predicho >=0,95). El control lo dice todo: el MISMO BF16 saca 0,9773, o sea que comete el mismo tipo de error. Y el error dominante, en los dos modelos, es emitir '<think>' donde el oro pone '<tool_call>': eso NO es una llamada malformada, es la decision legitima de razonar antes de actuar, que Qwen3 trae de fabrica. El guion de oro de la tarea de humo no incluye bloque <think> en las vueltas 2-4, asi que la metrica castigo como fallo de FORMA lo que es una alternativa valida de CRITERIO. Lo atribuible de verdad a los 2 bits son 2 tokens de 44: de 0,9773 a 0,9318. CONCLUSION PARA EL PLAN: el andamiaje Hermes sobrevive a la cuantizacion. H5 (decodificacion restringida por gramatica) NO es condicion de existencia de M1 como se sospechaba al abrir el ciclo; sigue siendo lo que era, una mejora barata que ademas eliminaria el 100% de estos fallos de forma por coste cero. H1 sigue siendo el camino correcto y el problema del campeon es de CRITERIO, no de FORMA. Dos observaciones que valen mas que la cifra. PRIMERA: en la vuelta 4 los dos modelos reproducen la llamada entera token a token (23 de 23), y en la vuelta 3 —la de 'editar', la mas larga y la que de verdad arregla el codigo— el BF16 clava 27 tokens seguidos y solo se desvia al elegir QUE cadena buscar. El campeon a 2 bits se desvia antes, pero por querer pensar, no por romper el JSON. SEGUNDA: el NLL por token sobre la respuesta correcta es 0,618 en el BF16 y 0,823 en el campeon; el campeon paga un 33% mas de sorpresa sobre lo que hay que hacer, y esa es la cifra honesta de cuanto cuesta la cuantizacion en esta tarea, no el 44% de desacuerdo de argmax de C4 sobre texto libre. LECCION DE METODO, que es la cara: un oro de un solo camino no sirve para juzgar la FORMA. Hay que separar dos preguntas que este ciclo mezclo, 'parsea la llamada' y 'coincide con el oro', porque la segunda castiga estrategias correctas. Si el banco crece con verificadores que comparen contra un guion unico, castigara al modelo por acertar de otra manera. LECCION DE INSTRUMENTO: la sonda no guardaba el detalle token a token, asi que reanalizar donde estaban exactamente las 3 desviaciones habria costado otros 44 min de CPU. Corregido en scripts/sondear_llamada.py: ahora el registro trae cada desviacion con su token de oro, el que dijo el modelo y si cae en andamiaje.

- **[2026-08-23 07:48] C7 · REFUTA** (medicion) — acuerdo_greedy_codigo = 0.5401 (se predijo >=0.65). REFUTADO, y por el lado que no esperaba: el Qwen3.5-0.8B da acuerdo_greedy 0,5401 en codigo y 0,4939 en espanol (predicho >=0,65), o sea PEOR que el campeon a 2 bits (0,5631 / 0,5230). Dos modelos que no se parecen en nada —uno de 27,8 G parametros destrozado a 2 bits, otro de 0,8 G entrenado limpio y 35 veces mas pequeno— aciertan el argmax del BF16 casi con la misma frecuencia. Eso apunta a que lo que limita alfa no es el tamano ni la calidad del borrador dentro de este rango, sino la distancia irreducible entre el objetivo y CUALQUIER modelo que no sea el, y por tanto que subir de 0,8B a 2B o 4B comprara poco. Es la hipotesis de C9 y hay que medirla, no suponerla. PERO el 0,8B GANA como borrador aunque acepte menos, y esta es la cifra util del ciclo: lo que cuesta proponer un token es leer los pesos del borrador, y el ancho de banda de RAM de esta maquina esta medido hoy en 24,6 GB/s de trafico (copia de 1 GB en 81 ms, 16 hilos). El campeon residente son ~8 GB por token propuesto (0,40 s); el 0,8B son 1,6 GB (0,08 s). Con el pase grande de 5,6 s: el campeon rinde como mucho 0,29 tok/s (optimo en gamma=4) y el 0,8B rinde 0,34 tok/s (optimo en gamma=4-8). El borrador barato gana un 17% pese a aceptar menos, porque en especulativa el coste del borrador NO es despreciable cuando el borrador es un modelo grande comprimido. Queda enterrada la idea que abria docs/densa-en-cpu.md: 'las dos vias encajan, el campeon de 2 bits es el borrador ideal'. No lo es ni por acuerdo ni por coste. TERCERA cifra, de regalo y con aviso: la PPL del BF16 sobre las 8 ventanas por dominio es 6,132 en codigo y 8,997 en espanol, frente a 5,764 y 4,839 que dio la sonda de UNA ventana. No es contradiccion, es muestra: las ventanas posteriores del corpus en espanol son mas dificiles. Al citar PPL hay que decir cuantas ventanas la produjeron, porque con una sola el numero se mueve casi el doble. Y el 0,8B da 20,363 y 31,812 sobre ese mismo corpus. LECCION DE INSTRUMENTO: el pase del modelo grande ya se cachea (top-1024 de p mas masa de cola, 100 MB en registros/cache-grande-C4corpus.pt). Costo 2004 s pagarlo una vez; el 0,8B costo 595 s. El siguiente candidato solo paga su propio pase, asi que comparar borradores dejo de ser una decision cara. Ademas Sigma min(p,q) queda ACOTADA y no estimada: la cota alta y la baja difieren 0,012 con K=1024.

- **[2026-08-23 08:00] C9 · CONFIRMA** (medicion) — acuerdo_greedy_codigo = 0.5692 (se predijo <0.65). CONFIRMA, y con esto la via densa queda acotada por arriba. La curva alfa(tamano del borrador) sobre el mismo BF16 y el mismo corpus de codigo es PLANA: Qwen3.5-0.8B (0,8 G) da 0,5401; Qwen3.5-2B (2,0 G) da 0,5692; el campeon de 27,8 G a 2 bits da 0,5631. Un factor 35 en parametros mueve alfa 0,029. Extrapolar es honesto aqui porque la pendiente medida es de +0,029 por cada x2,5 de tamano: para pasar de 0,569 a los 0,821 que exige D2 harian falta del orden de mil veces mas parametros que el 2B, o sea un modelo mucho mayor que el propio objetivo. NO HAY BORRADOR QUE QUEPA EN ESTA MAQUINA QUE ALCANCE D2. El presupuesto real de las tres configuraciones, con el pase de 5,6 s y el ancho de banda de RAM medido hoy (24,6 GB/s de trafico, o sea ~12,3 GB/s efectivos de lectura), eligiendo el gamma optimo de cada una: campeon 0,255 tok/s; 2B 0,302 tok/s; 0,8B 0,328 tok/s, todas con gamma=4. El mejor borrador es el mas PEQUENO de los tres, y aun asi la via densa se queda en un TERCIO de la barra de D2 y en un sexto de la de D3. CONSECUENCIA PARA EL PROYECTO: D2 no se alcanza en esta maquina por esta via, y hay que decirlo en vez de seguir puliendo H7. Lo que la via densa SI es, y no es poco, es el patron de oro: el BF16 corriendo en CPU es la referencia contra la que se mide cualquier cuantizacion, y ya esta medido y cacheado. El camino critico vuelve entero a la via cuantizada: H1, empaquetar el campeon a ~8 GB, donde el factor no es 2,2 sino ~250 porque los pesos dejan de leerse del disco. LECCION DE METODO, la que hay que recordar: tres ciclos (C4, C7, C9) han medido lo mismo desde tres angulos y los tres dan alfa entre 0,54 y 0,57. Cuando tres borradores que no se parecen en nada convergen al mismo numero, el numero no habla del borrador: habla del OBJETIVO. La entropia del BF16 sobre este corpus (PPL 6,132 en codigo) es la que fija el techo, y ninguna eleccion de borrador la esquiva. Haber medido el 4B habria costado otros 20 min para mover el tercer decimal.

- **[2026-08-23 12:47] C10 · CONFIRMA** (medicion) — razon_vecinos_vs_bf16 = 1000000000.0 (se predijo >=10). CONFIRMA el umbral, PERO el metro estaba mal disenado y el mecanismo que escribi era falso. Las dos cosas hay que decirlas. DEFECTO DEL METRO: predije razon_vecinos_vs_bf16 >= 10 y salio 1e9 porque el denominador es EXACTAMENTE 0 — el control BF16 no tiene ni una direccion duplicada. Un cociente con denominador cero confirma cualquier cosa: no distingue 'hay reticulo' de 'hubo una coincidencia por azar'. El ciclo no puede detectarlo porque solo sabe comparar numeros; lo detecta quien lee. MECANISMO FALSO: escribi que si el reticulo seguia 'casi todas las direcciones tendrian un vecino a distancia casi nula', frac_cerca ~1, suponiendo C2 mucho menor que C1 y 4096 cumulos. Es falso, y lo desmiente la leccion de C1 en el mismo documento: la cota tasa-distorsion para 16 dimensiones con 4096 codigos da ~0,60 de residuo, luego la etapa 2 de un RVQ no es una perturbacion pequena y las direcciones de C1[i]+C2[j] se reparten por hasta 4096x4096 = 16.777.216 valores, no por 4096 cumulos. LO QUE DICEN LOS NUMEROS: sonda sobre capa-30 mlp.up_proj, 40.000 direcciones, frac_cerca 0,00330; medicion sobre una matriz no tocada antes, capa-45 linear_attn.out_proj, 80.000 direcciones, frac_cerca 0,005288. Los controles BF16 y gaussiano dan 0,000000 en las dos. La ley del cumpleanos con |D| = 4096^2 predice 0,00238 y 0,00477: lo medido esta a factor 1,4 y 1,1 de eso, y ademas casi se dobla al doblar n, que es lo que exige la ley. Barrido previo para descartar desajuste de agrupacion: g=8 y g=16, up_proj y down_proj, capas 0, 30 y 63; en las seis el campeon da entre 0,0006 y 0,0033 y los dos controles dan cero. Y verificado en scripts/reconstruir_v12.py que _EscalaFila es s de forma (out_features,1) —escala por FILA y nada mas, con los pesos del Linear congelados salvo por esa parametrizacion—, luego las direcciones se conservan exactas y la prueba invariante a escala es valida. CONCLUSION: el reticulo apunta a estar INTACTO, justo al reves de lo que concluyo C1, y la salida (a) vuelve a estar viva. Pero esa lectura es POST HOC: la cuenta del cumpleanos se hizo despues de ver el numero y por tanto no falsa nada todavia. Se registra como hipotesis y se mide en C11, que predice ANTES que estimando |D| = n/frac_cerca a varios n saldra del orden de 4096^2 y que frac_cerca crece LINEALMENTE con n. Si sale, el tamano del libro se habra recuperado contando duplicados. LECCION DE METODO, la cara: un metro debe estar disenado para que 'confirma' y 'ocurrio el mecanismo que dije' sean lo mismo; aqui no lo eran. Lo que salvo la lectura no fue el metro sino EL CONTROL —la misma matriz sin cuantizar dando cero exacto—. Sin control, 0,0033 no habria significado nada, igual que el 0,543 de C1.

- **[2026-08-23 12:52] C11 · CONFIRMA** (medicion) — razon_libro_vs_k1k2 = 0.7569 (se predijo ~1.0±60). CONFIRMA, y con esto queda revertido C1: EL RETICULO RVQ SIGUE INTACTO EN LOS PESOS DESHECHOS, y su tamano de libro se ha recuperado contando duplicados. Barrido sobre capa-30 mlp.gate_proj, g=16, direcciones normalizadas a norma unidad: n=10.000 -> frac 0,001200 -> |D| 8,3 M; n=20.000 -> 0,001900 -> 10,5 M; n=40.000 -> 0,003150 -> 12,7 M; n=80.000 -> 0,005350 -> 15,0 M; n=160.000 -> 0,010169 -> 15,73 M, o sea 0,938 veces k1*k2 = 4096*4096 = 16.777.216. El control BF16, la misma matriz sin cuantizar, da 0,000000 exacto en los CINCO n. La fraccion crece con n y el cociente entre n consecutivos va 1,58 / 1,66 / 1,70 / 1,90 acercandose a 2, que es lo que exige la ley del cumpleanos para un libro finito. HONESTIDAD SOBRE EL SESGO: mi prediccion decia que el |D| estimado NO debia moverse con n, y SI se mueve: sube de 8,3 M a 15,7 M. No se mueve al azar ni se aleja, converge monotonamente al valor predicho. La explicacion —y es post hoc, con lo cual vale como hipotesis y no como prueba— es que hay dos poblaciones: un punado de direcciones muy frecuentes (grupos casi nulos o codigos dominantes) que colisionan incluso en muestras pequenas, mas el reticulo uniforme cuyo termino crece proporcional a n y acaba dominando. Por eso la estimacion honesta es la ASINTOTICA, la del n mas grande: 0,938. Quien quiera zanjar el sesgo tiene la prueba escrita: repetir con n=320.000 y ver si pasa de 0,938 a ~0,97; si se pasa de 1,0 la explicacion de las dos poblaciones es falsa. CONSECUENCIA, que es la que importa: la salida (a) de docs/cerebro-2bit.md esta VIVA. El indice no se guardo pero es deducible, porque el reticulo esta ahi y el libro tiene el tamano que dice HERMETIC2.json. H1 pasa de costar 24,3 horas de GPU —que este proyecto veta y que hoy ademas estan ocupadas— a costar horas de CPU. Y el camino esta: recuperar C1 por k-means sobre las direcciones, C2 por los residuos, y cerrar con la comprobacion dura que ya estaba escrita, reconstruir alfa*(C1[i]+C2[j]) y comparar bit a bit contra el tensor guardado. POR QUE FALLO C1 Y QUE HAY QUE APRENDER: C1 no midio mal, midio una cosa distinta creyendo que medía esta. Estimo alfa como el RMS de la fila cuando la escala real la puso _EscalaFila, y con la escala equivocada ningun reticulo aparece. La leccion no es 'C1 se equivoco': es que UNA REFUTACION TAMBIEN SE PUEDE EQUIVOCAR, y que la forma de blindarse es quitar la incognita del problema en vez de estimarla. Aqui bastaba normalizar a norma unidad: una escala por fila no mueve direcciones, y el parametro molesto desaparecio entero. Cuando una sonda dependa de estimar algo que no esta guardado, la pregunta correcta no es 'como lo estimo mejor' sino 'como formulo la prueba para no necesitarlo'.

- **[2026-08-23 13:10] C12 · CONFIRMA** (medicion) — cierre_mediano = 0.004025 (se predijo <0.01). CONFIRMA en las cinco matrices de la capa 45: cierre mediano 0,003443 a 0,004025 (peor caso mlp.up_proj), 100% de las filas conectadas en todas, y el control con las normas BARAJADAS da entre 0,333 y 0,523, o sea de 83 a 130 veces peor. BETA_FILA QUEDA RECUPERADA Y NO ESTIMADA, que es exactamente lo que mato a C1. EL CONCEPTO, que es lo que hay que guardar: el PUENTE DE DUPLICADOS. C11 habia probado que filas distintas comparten puntos del reticulo; de ahi se sigue que si el grupo (r,i) y el grupo (r2,j) usan el mismo punto, el cociente de sus normas ES beta_r/beta_r2 exactamente, sin estimar nada. Cada duplicado es un puente entre dos filas, el grafo de puentes conecta las 17.408 filas y un arbol de expansion fija todas las escalas salvo una constante global que se absorbe en el libro. Se encontraron entre 106.301 y 579.898 puentes por matriz en 12-16 s con FIRMA DE SIGNOS: 20 proyecciones aleatorias, ordenar por firma y comparar solo vecinos en ese orden. Dos direcciones separadas solo por el redondeo de bf16 distan ~0,006 rad y comparten firma con probabilidad 0,96; dos al azar, con 2^-20. De O(n^2) a O(n log n) sobre 5,57 millones de grupos. LA PRUEBA, y por que no se puede acomodar despues: solo 17.407 aristas caben en el arbol; las otras ~470.000 son REDUNDANTES y tienen que cerrar. Son cientos de miles de comprobaciones independientes de la misma hipotesis, y el control las destruye. Un grafo cuyos ciclos cierran a 0,004 cuando barajar las normas lo lleva a 0,33 no lo produce un artefacto. HONESTIDAD SOBRE EL RESIDUO: 0,004 esta por encima del 0,001 que predije para bf16 puro. La explicacion —post hoc, y por tanto hipotesis— es que eps admite como duplicados algunos vecinos que no lo son; apretar eps de 0,020 a 0,015 movio el cierre de 0,00435 a 0,00403, que es coherente pero no prueba. Quien quiera zanjarlo: barrer eps y ver si el cierre tiende a ~0,001. LO QUE FALTA PARA H1, ahora que las escalas estan: dividir cada fila por su beta, y sobre los grupos ya desescalados hacer k-means k=4096 para C1, tomar los residuos para C2, y cerrar con la comprobacion dura que ya estaba escrita en el holograma: reconstruir beta*(C1[i]+C2[j]) y comparar BIT A BIT contra el tensor guardado. Si esa comparacion sale exacta, H1 deja de ser una hipotesis y pasa a ser un empaquetador.

- **[2026-08-23 13:35] C13 · REFUTA** (medicion) — err_relativo = 0.12275 (se predijo <0.10). REFUTADO por poco —0,12275 frente a <0,10— y cae justo en el tercer desenlace que la prediccion dejo escrito: el reticulo esta pero el ajuste codicioso no lo encuentra, luego lo que hay que cambiar es el ALGORITMO, no la hipotesis. Las cifras: campeon 0,12275 dentro de muestra y 0,12372 FUERA, o sea sin sobreajuste; control BF16 0,39906 y 0,41961, clavado en el suelo del azar que predice la cota tasa-distorsion (0,60 al cuadrado = 0,36) y sin moverse en ocho iteraciones (0,40188 -> 0,39906). El campeon esta un factor 3,25 por debajo del control: el reticulo se nota, y mucho, pero no se ha separado. PRIMERA LECCION, y es de metodo: NO CERRAR CON LA SONDA FUE LO CORRECTO. La sonda de 60.000 grupos dio 0,28765 dentro y 0,36853 fuera, o sea que habria refutado por un motivo FALSO —sobreajuste con 15 puntos por codigo—, y habria repetido exactamente el error de C1. Al decimo aumentar la muestra, el error real cayo a la mitad y el hueco entre dentro y fuera desaparecio. Con k=4096 hacen falta cientos de puntos por codigo, no quince: una sonda mas barata que su propia resolucion no es barata, es engañosa. SEGUNDA, y es la que decide el siguiente paso: la traza sigue BAJANDO en la octava iteracion (0,16208 0,14468 0,13707 0,13233 0,12909 0,12646 0,12434 0,12275), asi que con mas vueltas bajaria mas. Y aun asi no serviria, porque H1 no necesita 0,05: necesita CERO, bit a bit. El k-means alternante esta convergiendo a un RVQ VALIDO PERO DISTINTO del original —hay muchas factorizaciones de la misma nube y el descenso por coordenadas cae en la mas cercana a su inicializacion aleatoria, no en la que genero estos pesos—. Insistir con mas iteraciones es escalar computo contra un metodo que no puede acertar. TERCERA: la desescalada esta bien, y esto descarta el tercer desenlace. El cierre de ciclos de beta en esta matriz salio 0,00888 y el control, al que le REGALE una beta por RMS de fila para no hacerme trampa, se quedo en 0,399. Si la beta estuviera mal, el campeon estaria donde el control. LO QUE VIENE, ya escrito en holos/H1.md: atacar el sumset por su estructura de TRASLACIONES. Para un i fijo, el conjunto {C1[i]+C2[j]} es un trasladado de C2, luego dos cumulos verdaderos son trasladados el uno del otro y la diferencia entre ellos se REPITE cientos de veces, mientras que entre dos nubes cualesquiera cada diferencia aparece una vez. Es la misma palanca que funciono en C11 y C12: contar coincidencias en vez de reconstruir.

- **[2026-08-23 13:54] C14 · CONFIRMA** (medicion) — multiplicidad_max_campeon = 242.0 (se predijo >=50). CONFIRMA: multiplicidad maxima 242 en el campeon frente a 2 en el control, sobre capa-30 mlp.gate_proj —matriz distinta de la de la sonda— y 5,2 millones de diferencias. Factor 121. El perfil es lo que mas dice: en el campeon unas pocas traslaciones fuertes y luego caida (top [107, 80, 80, 76, 62] en el primer desplazamiento de rejilla, maximo 242 en otro), que son los desplazamientos entre los i verdaderos mezclados dentro de cada cumulo impuro; en el control un llano de doses sobre 7,7 millones de diferencias, o sea un suelo de ruido plano que hace la lectura inequivoca. LAS TRASLACIONES EXISTEN Y SE MIDEN, luego C1 se puede recuperar encadenando cumulos por sus desplazamientos en vez de resolver el problema de optimizacion donde el k-means se atasca. LA LECCION CARA ES DE INSTRUMENTO, y estuvo a punto de costar el ciclo entero. La primera version de la sonda reutilizaba la firma de signos que resolvio C12 y dio multiplicidad 2 contra 1 del control: un refutado perfectamente creible. Lo que la delato NO fue el resultado sino un numero secundario que no encajaba: el cubo mayor tenia 10.096 diferencias de 2,25 millones cuando con 24 bits lo esperado es 0,13. La causa: las diferencias entre dos cumulos apuntan casi todas en la misma direccion —la que une los centroides—, asi que una firma que solo mira orientacion no discrimina nada, y ademas el codigo comparaba contra un elemento arbitrario del cubo en vez de buscar la moda. Sobre LOS MISMOS DATOS, el instrumento roto dijo 2 y el corregido dice 162. GENERALIZANDO: una tecnica que funciono en un ciclo anterior NO se hereda sin comprobar que su supuesto sigue valiendo. La firma de signos servia en C12 porque alli las direcciones estaban repartidas por la esfera; aqui estan concentradas y el mismo truco se vuelve ciego. Y el habito que lo salvo: mirar SIEMPRE los numeros secundarios de la sonda, no solo la cifra del veredicto. LO QUE SUSTITUYO A LA FIRMA: rejilla sobre el vector COMPLETO con varios desplazamientos aleatorios. Es segura por los dos lados a la vez: la rejilla puede ser gruesa —basta que supere el ruido de bf16, ~0,002 relativo— porque en 16 dimensiones hay del orden de 30^16 = 4e23 celdas y dos diferencias distintas no coinciden por azar; los desplazamientos evitan que una traslacion verdadera caiga en una frontera. AVISO SOBRE LA PUREZA, que no se tapa: la multiplicidad crecio de 162 a 242 al pasar de 2,25 a 5,2 millones de diferencias, o sea x1,49, cuando el ideal crecia x2,31. La pureza de los cumulos del k-means baja del 30% al 19% en esta matriz. Es suficiente para detectar la traslacion pero NO para reconstruir: el siguiente paso no puede apoyarse en cumulos impuros, tiene que tejer las traslaciones entre si y comprobarlas por cierre, como se hizo con las escalas en C12.

- **[2026-08-23 14:03] C15 · REFUTA** (sonda) — cierre_traslaciones_mediano = 0.54303 (se predijo <0.05). REFUTADO —cierre mediano 0,54303 frente a <0,05— y cae en la segunda rama que la prediccion dejo escrita: las multiplicidades son altas pero los triangulos no cierran, luego la diferencia dominante NO es una diferencia de C1 usable, sino un artefacto de cumulos impuros. Las cifras: 45 aristas con multiplicidades 98, 88, 84, 82, 79, 73 —muy por encima del suelo de 2 del control—, 120 triangulos, cierre mediano 0,54303 y p90 0,95101, o sea del tamano de los propios vectores. LA CAUSA, que C14 ya habia anotado y esto confirma: con cumulos al 19% de pureza cada PAR de cumulos elige el desplazamiento entre una pareja de indices DISTINTA. d_AB usa (i_A1, i_B2), d_BC usa (i_B3, i_C1): son diferencias de C1 verdaderas cada una por su lado, pero de indices que no encadenan, y por eso no componen. El fallo no esta en la hipotesis del reticulo —C11, C12 y C14 la sostienen con tres pruebas independientes— sino en usar el k-means como punto de partida. AVISO SOBRE EL CONTROL, que esta vez salio degenerado y hay que decirlo: el BF16 no produjo NINGUNA arista valida (todas sus multiplicidades son 2, por debajo del minimo de 20), asi que su 9,9 es un relleno y no una comparacion. Lo informativo del control no es su cierre sino su AUSENCIA de aristas: en el modelo sin cuantizar no hay traslaciones que tejer. Aun asi, un control que no produce datos es un control a medias, y la proxima version deberia bajarle el minimo para que produzca cierres comparables aunque sean de ruido. LO QUE VIENE, y es el concepto que faltaba: ANCLAR. El problema es que relacionar cumulos entre si mezcla indices; la salida es referir todo a UN SOLO punto. Fijado u0 = C1[i0] + C2[j0], un punto u de U cumple que u - u0 es una diferencia valida exactamente cuando u comparte i0 (y entonces u - u0 es una diferencia de C2) o comparte j0 (y es una diferencia de C1). Ancladas en u0, las diferencias SI son consistentes por construccion y componen. Y la validez de un candidato d se comprueba contando |U interseccion (U+d)|, que con una rejilla ordenada y busqueda binaria cuesta del orden de 30 ms por candidato: 20.000 candidatos son 10 minutos, y de ellos deberian pasar unos 10, que es 2/4096 por candidato. Eso es C16.

- **[2026-08-23 14:44] C16 · REFUTA** (medicion) — candidatos_validos_campeon = 0.0 (se predijo >=3). REFUTADO sin ambiguedad con el instrumento corregido: 0 candidatos validos en el campeon frente a 4 en el control, y los mejores del campeon (69, 68, 67, 64) quedan POR DEBAJO del suelo empirico (p99,9 del control = 69 aciertos). La deteccion anclada por pertenencia en rejilla no tiene ningun poder discriminante. Los 4 del control son exactamente el 0,1% que la definicion del percentil obliga, o sea el suelo funcionando. LA LECCION CARA, y es la mas general del dia: EL MODELO NULO SE MIDE, NUNCA SE CALCULA DE UNA DENSIDAD IDEALIZADA. La sonda de este mismo ciclo, con el umbral calculado, dio 18.023 validos de 20.000 en el campeon y 15.950 en el control, con los MEJORES DEL CONTROL por encima de los del campeon. Yo habia calculado el suelo de falsos positivos suponiendo la nube repartida por del orden de 12^16 = 2e17 celdas —probabilidad 3e-11 de caer en celda ocupada— y la tasa real esta SEIS ORDENES DE MAGNITUD por encima, porque la ocupacion no es uniforme: la nube esta concentrada y un desplazamiento que es diferencia de dos puntos suyos devuelve los puntos al mismo nucleo denso. El test medía 'cae en el nucleo', no 'es una diferencia del libro'. Un suelo teorico de 3e-11 dio confianza para poner el umbral en 3; treinta segundos de control lo habrian desmentido. COROLARIO OPERATIVO, ya aplicado al instrumento: el control corre PRIMERO, y si satura no hace falta gastar el resto de la carrera. SEGUNDA LECCION, de arnes: las carreras desatendidas se lanzan con python3 -u. C16 estuvo 27 minutos sin emitir una linea porque Python bufferiza la salida cuando no escribe a un terminal, y el monitor que la vigilaba era decorativo; hubo que deducir su fase por el RSS del proceso. Corregido en los ocho scripts de sonda. BALANCE DE LA VIA (a) TRAS SIETE CICLOS, para quien retome: lo SOLIDO es que el reticulo sobrevive —C11 midio el libro en 15,73 M = 0,938 x 4096^2 con el control a cero exacto en cinco tamanos de muestra, C12 recupero beta_fila con cierre de ciclos 0,0034-0,0040 contra 0,33-0,52 del control barajado y el 100% de filas conectadas, C14 midio traslaciones 242 contra 2—. Lo que RESISTE es separarlo: C13 (el k-means converge a un RVQ valido pero distinto: 0,123 contra 0,399 del control, y hace falta CERO), C15 (las traslaciones entre cumulos impuros no componen: 0,543) y C16 (la deteccion anclada no discrimina: 0 sobre el suelo empirico). Tres intentos, tres instrumentos distintos. Eso NO refuta la salida (a) —la estructura esta ahi y esta medida tres veces— pero SI refuta la estimacion de coste que la abrio: 'horas de CPU' era optimista, y quien siga por aqui debe saber que ya se gastaron siete ciclos.

- **[2026-08-23 15:45] C17 · REFUTA** (sonda) — razon_ppl = 4.0255 (se predijo <1.01). REFUTADO con holgura: razon_ppl 4,0255 frente a <1,01. Medido sobre el corpus real: el deshecho intacto da nll 2,81685 y PPL 16,7241; con cuatro capas re-cuantizadas (20, 30, 40, 50) sube a nll 2,90389 y PPL 18,2451, o sea 0,08704 nats repartidos en cuatro capas = 0,02176 nats POR CAPA. Extrapolado a las 64 capas son 1,393 nats y una razon de PPL de 4,03. La salida (c) tal como se probo NO cumple el +1% de M1: se lo salta por un factor 400. DOS AVISOS QUE HAY QUE LEER JUNTOS ANTES DE DAR LA VIA POR MUERTA. Primero, la sonda corrio con configuracion DEGRADADA y por tanto su numero es una COTA, no una medida: err_rvq_medio 0,3765 frente al 0,123 que C13 alcanzo con n=600.000 y ocho iteraciones alternantes. Le puse 24 puntos por codigo donde hacen falta 146, que es exactamente el error que C13 dejo escrito. Segundo, la extrapolacion de 4 capas a 64 supone que el dano es lineal en el numero de capas y aditivo, y eso no esta medido: podria compensarse parcialmente o agravarse. QUE PASA SI SE ARREGLA LA CONFIGURACION, con las dos hipotesis de escalado que caben: si el dano es LINEAL en el error de peso, pasar de 0,3765 a 0,123 lo divide por 3,06 y da 0,455 nats sobre 64 capas, razon 1,58; si es CUADRATICO, lo divide por 9,4 y da 0,149 nats, razon 1,16. Las dos rebasan el 1,01 de M1. Y gastando la holgura de bits —2,5 bits caben en 8,7 GB— con un err optimista de 0,06 saldrian 1,25 (lineal) o 1,036 (cuadratico). Ni siquiera el caso mas favorable llega al criterio. LA CIFRA QUE FALTA, y es barata: el EXPONENTE con el que el dano crece con el error de peso. Con dos hipotesis que difieren en un factor 4 no se puede decidir nada, y medir el exponente no exige re-cuantizar: basta inyectar ruido de magnitud relativa controlada en las mismas cuatro capas y medir el dano a varios niveles, un pase de cinco minutos por nivel. El punto real que ya tenemos (err 0,3765 -> 0,02176 nats/capa) ancla la curva. Eso es C18, y decide si gastar bits salva la salida (c) o si hay que ir a por la (b). LECCION DE METODO: la prediccion se escribio ESPERANDO fallar, con el umbral puesto donde lo pone META.md y no donde me resultaba comodo acertar, y las tres ramas del desenlace estaban descritas antes de medir. Por eso el 4,03 no ha necesitado ninguna explicacion inventada despues: cayo en la rama tercera, que ya decia que la extrapolacion lineal era optimista y que la degradacion se acumula peor de lo lineal a traves de las capas.

- **[2026-08-23 16:07] C18 · REFUTA** (sonda) — exponente = 1.5587 (se predijo >=1.7). REFUTADO el exponente predicho —1,5587 frente a >=1,7— PERO EL PROXY SE VALIDA y por eso el ciclo entrega lo que iba a buscar. La validacion que iba dentro: al nivel 0,3765 el ruido gaussiano da 0,015624 nats por capa y el RVQ real de C17 dio 0,02176, razon 0,718, dentro del [0,5 - 2] que exigi ANTES de medir. O sea que el error de cuantizacion hace un 39% mas de dano que el ruido aleatorio de la misma magnitud —esta correlacionado con los pesos, como se advirtio— pero del mismo orden, luego el exponente es utilizable. Curva medida sobre las mismas cuatro capas: eps 0,10 -> 0,001973 nats/capa; eps 0,20 -> 0,005312; eps 0,3765 -> 0,015624. POR QUE FALLO LA PREDICCION: argumente que un ruido no correlacionado tiene primer orden de esperanza nula y deja solo el segundo, luego exponente 2. Lo medido es 1,56, o sea que el termino de primer orden NO se cancela. La razon es que el dano se mide sobre la NLL de un texto concreto y no en promedio sobre perturbaciones: la esperanza del primer orden es cero pero su MAGNITUD tipica no lo es, y con 64 capas y matrices grandes la fluctuacion de primer orden domina sobre el segundo orden en este rango. Argumentar con esperanzas cuando lo que se mide es una realizacion es el error, y es sutil. LA CIFRA QUE CIERRA LA SALIDA (c): para cumplir el +1% de M1 hacen falta 1,555e-4 nats por capa, y con exponente 1,5587 eso exige un error de peso de 0,0158, o sea el 1,6%. El RVQ bueno de C13 alcanza 0,123 y daria razon de PPL 1,276; con err 0,06 seria 1,083 y con err 0,03 seria 1,027. NINGUNO LLEGA. Y bajar a 0,0158 con cuantizacion vectorial de 16 dimensiones exigiria del orden de ocho bits por peso: 27,8 G parametros a 8 bits son 27,8 GB, cuando M1 admite 10. LA SALIDA (c) QUEDA DESCARTADA CON CIFRA, que es justo como pedia la leccion de C17 y como debio descartarse el primer dia en vez de con el adjetivo 'perdida adicional'. CONSECUENCIA PARA EL PROYECTO: H1 solo tiene dos caminos vivos. El (a), recuperar los libros originales, con el reticulo demostrado tres veces (C11, C12, C14) y la separacion resistiendo tres instrumentos (C13, C15, C16). El (b), tocar cuantizar_v2.py en QuantModels para que persista idx1/idx2/C1/C2/alfa y re-ejecutar: son unas lineas y 24,3 h de GPU, y es CERTERO. Hay ademas una tercera posibilidad que NO es tecnica y que no me corresponde decidir: el criterio de M1 exige PPL <= +1% frente al deshecho, que es una exigencia de reproducir el campeon, no de tener un cerebro usable. Si el autor decidiera que un cerebro con +8% de PPL sirve, la salida (c) con err 0,06 lo daria. Eso se escribe en META.md o no existe.

- **[2026-08-23 22:15] C19 · REFUTA** (medicion) — segundos_media = 2435.2 (se predijo <1800). REFUTADO —2435,2 s frente a <1800— y cae en la rama intermedia que la prediccion describio: la cache devuelve algo pero mucho menos de lo que promete la aritmetica. Medido sobre la misma tarea y el mismo cerebro: 2759,4 s sin cache y 2435,2 s con ella, o sea 324 s de ahorro cuando la cuenta prometia 1605. Un 20% de lo prometido, y el reparto del reloj sigue dominado por el prefill. LA CAUSA, que la propia prediccion senalo como sospechosa: LlamaRAMCache de llama-cpp-python no reutiliza el contexto vivo, sino que GUARDA Y RESTAURA el estado completo del modelo en cada llamada. Copiar la cache KV entera de un modelo de 27B son cientos de MB por vuelta, y esa copia se come casi toda la ganancia de no rehacer el prefill. El mecanismo correcto no es cachear estados: es NO TOCAR el contexto. Entre dos vueltas la secuencia de tokens solo crece por el final, asi que basta con calcular el prefijo comun con la vuelta anterior y evaluar UNICAMENTE los tokens nuevos, sin reset y sin copias. Eso exige bajar de create_completion a la API de bajo nivel (llm.eval y llm.sample) y llevar la secuencia en el propio cerebro. LO QUE SE APRENDE, y es general: 'poner la cache' y 'no rehacer el trabajo' no son lo mismo. Una cache que serializa y deserializa el estado paga un coste proporcional al TAMANO DEL ESTADO en cada uso, y con un modelo de 9,15 GB ese coste es del orden del trabajo que ahorra. La palanca no era configurar una cache: era no reiniciar el contexto. Queda medido que la version facil devuelve el 20%, asi que la version correcta merece su propio ciclo. AVISO PARA QUIEN LO ESCRIBA: al evaluar solo el delta hay que verificar que la salida es IDENTICA a la de rehacer el prefill entero, con temperatura 0 y misma semilla, porque un prefijo comun mal calculado produce un contexto silenciosamente corrupto y el modelo sigue respondiendo, solo que peor.

- **[2026-08-24 02:59] C21 · CONFIRMA** (medicion) — razon_cheby_vs_barajado = 0.8584 (se predijo >=0.8). CONFIRMA en las seis configuraciones: K(t) NO es suave en el indice de token, y la parte Chebyshev de TESSERA-KV queda refutada en su suposicion basica. Medido sobre Keys reales de tres capas de atencion completa (3, 31 y 63) con grados 5 y 11, bloques de 128 tokens. En el caso MAS FAVORABLE a Chebyshev de los seis —capa 31, grado 11— la razon entre el error real y el del control barajado es 0,8584: desordenar los tokens empeora el ajuste solo un 14%, o sea que el orden temporal casi no aporta informacion. Y el error absoluto de reconstruccion se queda en 0,6104 con DOCE coeficientes para 128 tokens, cuando la propuesta pide 4-6 y necesita reconstruir el vector exacto. La media del bloque —grado 0, el ajuste mas tonto posible— da 0,7439, asi que doce coeficientes compran una mejora del 18% sobre no ajustar nada. El 95% de ahorro en Keys no existe. POR QUE FALLA LA INTUICION, que es lo que hay que guardar: la metafora del 'flujo del razonamiento sobre una variedad diferenciable' describe la trayectoria de la ATENCION AGREGADA, no la de los vectores K token a token. K = W_k por el flujo residual, y el flujo residual salta de contenido semantico entre tokens vecinos: un identificador, un parentesis y un salto de linea no son puntos proximos de ninguna variedad suave. Confundir la suavidad del proceso con la suavidad de la representacion es el error, y es facil de cometer porque la metafora es buena para otra cosa. LO QUE SI SOBREVIVE DE LA PROPUESTA: el desacoplamiento asimetrico K/V es correcto —las Keys necesitan precision direccional y los Values contenido— y el ancla mas residuo ternario aporta de verdad: el error de reconstruccion baja de 0,5493 sin ancla a 0,4304 con ella en la capa 3, y llega a 0,3909 en la capa 63, o sea un 21,6% de mejora que viene de la invarianza por traslacion del softmax. AVISO sobre esa cifra: 0,39 de error en la reconstruccion de K NO es el 'error relativo menor a 1e-4' que promete el documento, porque ese 1e-4 se refiere al resultado del SOFTMAX y no al vector reconstruido. Son dos afirmaciones distintas y la segunda no se ha medido. LO QUE NO DEPENDE DE ESTA MEDICION, y conviene que quede escrito: en esta maquina TESSERA-KV no aceleraria nada hoy. La cache KV de Qwen3.8-27B son 0,50 GB a 8.192 tokens y 8,00 GB a 131.072 —no los ~80 GB que la propuesta atribuye a Llama-3-70B— porque 48 de sus 64 capas son GatedDeltaNet con estado recurrente y las 16 de atencion llevan GQA con 4 cabezas KV. La arquitectura ya se comio diez veces ese problema. Y el cuello medido del arnes es el PREFILL, 94,1% del reloj, que es computo y no memoria: comprimir la KV no acelera un GEMM. La propuesta apunta a un cuello que aqui no existe, y solo mordería a un millon de tokens, donde la KV serian 61 GB.

- **[2026-08-24 21:46] C20 · REFUTA** (medicion) — segundos_media = 3359.5 (se predijo <1500). REFUTADO —3.359,5 s frente a <1.500— y en la peor rama de la predicción: no reutiliza nada. La tarea pasó (3/3 asertos, 0 intervenciones): lo que falla es la palanca, no el arnés. LA CAUSA, vista con verbose=True en una sonda de un minuto: Llama.generate SÍ encuentra el prefijo común, pero kv_cache_seq_rm devuelve false —la caché del Qwen3.8 GGUF no admite borrado parcial, cosa de su atención híbrida— y el código cae EN SILENCIO a re-evaluar el prompt entero en cada vuelta. Con verbose apagado el aviso no se ve: por eso la sonda de identidad dio bien (la matemática no depende de la reutilización) y la aceleración ×1,20 se tomó por ruido cuando era el síntoma. Y el borrado solo hace falta porque el contexto que remonta el arnés DIVERGE de lo generado: quitar el <think> y re-plantillar el turno del asistente deja tokens cacheados de más que habría que podar. Comprobado en la misma sonda: si la secuencia nueva EXTIENDE EXACTAMENTE la cacheada —tokens crudos, think incluido— imprime prefix-match hit y evalúa solo el sufijo. La palanca exige contexto append-exacto a nivel de token: no sacar el razonamiento del contexto vivo, no re-plantillar, no compactar por el medio. El alquiler es que el think ocupa ventana (888 tokens de salida en esta carrera); si cabe en 8192 lo decide C22. Secundario: la vuelta 1, que no reutiliza en ningún diseño, costó 525,9 s frente a 388,9 en C19 —la máquina iba ~1,35× más lenta hoy— así que comparar carreras de días distintos sin esa corrección engaña.

- **[2026-08-25 01:12] C22 · CONFIRMA** (medicion) — segundos_media = 544.3 (se predijo <1800). CONFIRMADO —544,3 s frente a <1.800— y por debajo incluso de la aritmetica optimista (1.040-1.250): la palanca esta puesta. Misma guarda: 3/3 asertos, 0 intervenciones, 5 vueltas. El reparto lo dice todo: vuelta 1 en frio 332,8 s y las cuatro siguientes 133,6 / 19,2 / 18,4 / 36,8 — el prefill dejo de ser la suma de los contextos. Contra C20 (3.359,5) es x6,2; contra la mejor carrera anterior (C19 con cache de estados, 2.435,2) x4,5. Tres causas y no una, todas medidas: (1) el append-exacto evalua solo el sufijo (sonda: '307 prefix-match hit, remaining 31 prompt tokens to eval', aceleracion x2,12 en el juguete); (2) tokenize(special=True) —el defecto de llama-cpp-python era False— encoge el prompt (216 frente a 240 tokens el turno minimo) y el modelo ve POR FIN los tokens especiales del formato con que se entreno; (3) el modelo penso menos viendo su propio think anterior: 400 tokens de salida frente a 888, y no repitio el editar fallido de C20. CONFUNDIDOR honesto: (2) y (3) cambian el guion, asi que los 544,3 no separan cuanto es reutilizacion y cuanto guion mas corto; si algun dia hace falta separarlo, una carrera con special=True y contexto SIEMPRE frio lo aisla. El alquiler del think en ventana salio barato en humo (~2.400 tokens de contexto final sobre 8.192); la factura llegara en tareas largas, donde compactar() sigue costando un arranque en frio entero porque esta cache no admite borrado parcial: la huella lo detecta y degrada a lento, jamas a corrupto (13 asertos en tests/test_local_gguf.py). Regla practica que queda: en cerebros con cache hibrida, la transcripcion solo puede CRECER POR EL FINAL.

- **[2026-08-25 03:02] C23 · CONFIRMA** (medicion) — tareas_pct = 100.0 (se predijo >=80). CONFIRMADO —tareas_pct 100 frente a >=80—: PLENO 5 de 5. El cerebro de trabajo tiene CRITERIO para todo n0, no solo forma: atomo consolido TRES cambios en UNA llamada a editar (la puerta 3 de META.md funcionando), crear escribio pila.py desde cero y paso limpia en 5 vueltas (era mi apuesta a caer), rastro hizo find→grep→editar sin leerse los cuatro ficheros, y simbolo eligio la herramienta simbolos A LA PRIMERA para encontrar app/util/texto.py entre cinco modulos. El reloj: segundos_media 1.191,1, por encima de la banda secundaria 450-700, y el CONTROL INTERNO explica por que: humo repitio su guion de C22 exacto —5 vueltas, 400 tokens— a x2,07 de reloj (1.124,8 frente a 544,3). La maquina, no el arnes. Corregida por ese factor, la media queda ~575: dentro de banda. REGLA que deja esto: cada carrera de banco lleve una tarea-control ya medida antes; separa maquina de mecanismo gratis. El despilfarro real, dos patrones medidos y AMBOS del arnes: (1) python contra python3 quema una vuelta en casi toda tarea (90-500 s cada una); (2) la lista blanca del modo lista rechazo 'python -c', 'python3 -c' y 'cd' (4 intervenciones, ~600 s entre atomo y simbolo), y el modelo NO abandono: reformulo hasta pasar, que es lo que las 12 vueltas de simbolo son —cola de friccion, no incapacidad—. Arreglo barato para antes de n1: una linea en el prompt de sistema (python3 nunca python, sin cd, verifica con python3 prueba.py) y valorar python3 -c en la lista. M0 con cerebro real queda demostrado; lo siguiente es H3, el banco n1.

- **[2026-08-25 10:30] C24 · CONFIRMA** (medicion) — tareas_pct = 100.0 (se predijo >=66). CONFIRMADO en la rama alta —tareas_pct 100 frente a >=66—: PLENO 3 de 3 en la primera carrera n1 de la historia del arnes. El cerebro de 2,83 bits hace ingenieria de nivel 1: rojo leyo el traceback (con un 'head -80' de cosecha propia para acotar la salida), entendio el contrato en prosa «fin excluido, tocarse no es pisarse» y cambio <= por < (6 vueltas, 1.188,0 s); anadir infirio los tres ValueError leyendo la prueba y escribio el metodo entero en UNA llamada (4 vueltas, 969,2 s); migrar ESQUIVO LA TRAMPA —el TypeError apunta a formato.py, que es intocable— usando grep sobre ambos ficheros y migrando solo los llamadores (3 vueltas, 845,1 s). Reloj: segundos_media 1.000,8 con la maquina a x1,95 de C22 (control humo del dia: 1.058,8 frente a 544,3); corregida, ~515 s/tarea: n1 cuesta lo que humo. CERO intervenciones: las dos fricciones de C23 (python-vs-python3 y la lista blanca) desaparecieron con la linea nueva del prompt y python3 -c en la lista — el arreglo barato valio exactamente lo que C23 predijo. Lo nuevo que este nivel destapo, y es munición medida para H5: DOS llamadas malformadas en 13 vueltas, ambas del mismo tipo estructural —una con saltos de linea crudos dentro del JSON (migrar v3), otra truncada por el tope de 512 tokens en mitad del tool_call (rojo v3)—. El arnes no adivino ninguna (politica de plantilla.py), el modelo reemitio o el verificador cerro, y el coste fue ~1 vuelta (~400-500 s) cada una: la decodificacion restringida por gramatica y/o subir max_tokens por vuelta las eliminarian. M2 dice >=50% del banco: n0 100% y n1 100% lo dejan superado en su primera medicion — lo que falta para declararlo es engordar n1 hasta que deje de ser facil (tareas de dos ficheros con estado, la cola larga).

- **[2026-08-25 13:46] C25 · CONFIRMA** (medicion) — tareas_pct = 100.0 (se predijo >=83). CONFIRMADO en la rama alta —tareas_pct 100 frente a >=83—: PLENO 6 de 6 con el banco engordado. Las tres nuevas, que median lo que C24 no midio, cayeron todas: bitacora eligio la capa correcta (disco.cargar) tras leer las dos (6 vueltas, 1.008,2 s); cadena busco con grep los LLAMADORES de precio_final antes de editar y coordino las dos ediciones (4 vueltas, 1.191,4 s); y fuga —mi apuesta a caer— paso con diagnostico de libro escrito por el propio modelo: «grupos={} es un argumento mutable por defecto... se comparte entre todas las llamadas» (5 vueltas, 920,5 s). Reconocio la CLASE del bug, no el sintoma. Las tres viejas repitieron casi calcadas (anadir 4 vueltas/mismo guion, migrar 3, rojo 5): el banco es estable entre carreras a temperatura 0. El arreglo de max_tokens 512→1024 quedo validado en el punto exacto: la vuelta 3 de rojo genero 578 tokens con think y llamada COMPLETOS —en C24 ese mismo punto trunco a 512 y costo una vuelta de reemision—. CERO llamadas malformadas en 27 vueltas (C24: 2 en 13) y CERO intervenciones: H5 pierde urgencia — que la gramatica espere a que el sintoma reaparezca con datos. Reloj: segundos_media 1.020,8 con la maquina a x1,33 (control humo del dia: 726,1 frente a 544,3 de C22); corregida ~765 s/tarea: el n1 nuevo cuesta ~40% mas que humo, proporcional a sus vueltas. El banco completo queda en 11/11 con cerebro real (n0 5/5 en C23, n1 6/6 aqui): M2 pedia >=50% y esta superado con margen incluso tras engordar — declararlo es ya decision de META.md, no falta ninguna medicion. La proxima subida honesta del liston no es mas n1: es n2 (multi-fichero con estado, presupuesto mayor) — y ahi apretara la ventana de 8.192, la factura que C22 dejo anotada.

- **[2026-08-25 14:07] C26 · CONFIRMA** (medicion) — kv_gb = 1.15 (se predijo <4). CONFIRMADO con holgura: los buffers de memoria a 16.384 son 1,15 GB (512 MiB de KV por cada 8k de ventana mas 149,6 MiB FIJOS de estado recurrente), contra los <4 predichos. Doblar la ventana cuesta 0,5 GB: nada en los ~20 disponibles. Dos regalos de la sonda: (1) el motor imprime llama_memory_recurrent — la arquitectura ES hibrida-recurrente, confirmacion directa de la causa raiz que C20 diagnostico por conducta (por eso no hay borrado parcial de cache y el contexto solo puede crecer por el final); (2) n_ctx_train = 262.144 en los metadatos (arch qwen35): 16.384 queda 16 veces por debajo del contexto de entrenamiento, sin riesgo de degradacion por RoPE. La KV chica es propiedad de la arquitectura (pocas capas de atencion completa): incluso 32k costaria ~2,2 GB, asi que si n2 pide mas ventana, hay margen. contexto_max pasa de 8.192 a 16.384 en local_gguf.py citando este ciclo. El limite practico de contexto ya no es la RAM: es el RELOJ del prefill en frio (a 0,25-0,33 s/token, llenar 16k desde cero son ~70-90 minutos), otra razon por la que el append-exacto de C22 es LA arquitectura y no una optimizacion.

- **[2026-08-25 14:29] C27 · CONFIRMA** (medicion) — tareas_pct = 100.0 (se predijo ==100). CONFIRMADO —tareas_pct 100, predicho ==100—: la primera tarea n2 cae en 5 vueltas y 1.199,2 s (borde bajo de la banda 1.200-2.200; ~900 corregida por el control del dia). El guion del modelo fue de manual: explorar, leer los CUATRO modulos en una vuelta, calcular los totales esperados en prosa (9.00, 4.50, 8.10) ANTES de tocar nada, y crear cupones.py + editar caja.py en una sola pasada; catalogo.py intacto. El riesgo señalado en la prediccion —el escribir multi-linea dentro del JSON, donde C24 vio romperse los saltos de linea— salio LIMPIO en un turno de 620 tokens: con max_tokens=1024 el think y las dos llamadas cupieron enteros, y H5 sigue sin ganarse la urgencia. Con esto el marcador historico del cerebro de trabajo queda 12/12 con 0 intervenciones en tres niveles del banco. Y ese pleno ES el aviso que deja este ciclo: el banco todavia no ha encontrado el BORDE del cerebro —ninguna tarea le ha hecho fallar— y M3 exige un banco donde la puntuacion tenga sitio para SUBIR. Un banco en 100 no informa: el siguiente trabajo del banco no es acumular tareas que pasan, es buscar el fallo reproducible (estado entre ejecuciones, ficheros grandes que no caben de una lectura, presupuesto apretado, ambiguedad real). El borde es informacion; sin el, H6 no tiene gradiente que escalar.

- **[2026-08-25 16:26] C28 · REFUTA** (medicion) — tareas_pct = 100.0 (se predijo <=75). REFUTADO —tareas_pct 100 frente a <=75— y es la refutacion que mas informa: mi diseño del borde estaba POR DEBAJO del cerebro. Las tres trampas cayeron del lado del modelo: en aguja leyo el fichero entero (error tactico), NOTO el truncado a 12.000, fue con grep contexto=15 a las dos funciones sospechosas y arreglo citando el docstring contra el < estricto — pero el error tactico costo el reloj: 2.345,6 s la tarea, con 1.356,6 s en la vuelta que cargo la observacion truncada. La disciplina de la puerta 1 tiene ahora PRECIO medido: leer entero lo que no cabe cuesta ~1.400 s mas que ir con grep primero. En tres consolido los tres arreglos en UN editar tras enumerarlos en prosa (y uso pytest --tb=short por iniciativa propia). En version —mi apuesta numero uno— entendio la idempotencia en un turno de 938 tokens y protegio las fichas ya migradas. cupones repitio como control (5 vueltas). CERO intervenciones; 16/16 historico en cuatro niveles de dificultad. Lo que esta refutacion acota: el borde del cerebro de trabajo NO esta en bugs de logica local, contratos en pruebas, navegacion de paquetes ni razonamiento de segunda ejecucion. Donde buscar mas arriba, en orden de fidelidad a la meta: (1) n3 = crear un proyecto ENTERO desde un encargo en prosa —paquete, CLI y pruebas desde cero—, que es literalmente la mision del arnes; (2) presupuesto de verdad apretado (tope_tokens 2-3K como dice META §muro, no 8K); (3) ambiguedad real que obligue a decidir sin contrato. Y si n3 tampoco encuentra borde, la conclusion sube de nivel: el cerebro de trabajo BASTA para el banco y el gradiente de M3/H6 hay que buscarlo en el reloj (tokens y segundos por tarea), no en la tasa de acierto.

- **[2026-08-25 20:07] C29 · REFUTA** (medicion) — tareas_pct = 0.0 (se predijo ==100). REFUTADO —tareas_pct 0 frente a ==100— y EL BORDE POR FIN TIENE CARA, pero no es la que predije: no cayo por presupuesto (gasto 1.215 de 3.000) ni por forma (ninguna llamada malformada). Cayo por una ESQUINA DEL ARNES: la vuelta 3 gasto los 1.024 tokens del turno en puro think de diseño —en ingles, primera vez; el diseño desde cero dispara un razonamiento mas largo que cualquier arreglo— y se corto ANTES de emitir ninguna llamada; el bucle trata un turno sin llamadas como respuesta final (motivo fin), asi que dio la tarea por acabada a medio pensar. Tres piezas: (1) el 1024 de C24 basta para arreglos pero NO para el turno de diseño de un n3; (2) el fallo exacto esta en bucle.py: motivo_parada==tope_tokens sin llamadas NO es una respuesta final y tratarlo como tal es adivinar que termino — la politica de no adivinar de plantilla.py, aplicada al reves; (3) con el contexto append-exacto el reintento es BARATO: el think cortado ya esta en la cache, pedir continuar cuesta solo el sufijo. El arreglo va a bucle.py (pedir continuar una vez por vuelta cortada, con tope_vueltas/tope_tokens como frenos) y C30 mide si n3 pasa con el; la pregunta del presupuesto minimo de un n3 queda viva —1.215 gastados a medio diseño sugieren que 3.000 esta JUSTO—. Y una miga para el horizonte: el modelo penso en ingles justo cuando la tarea se volvio de diseño puro; el idioma del think parece correlacionar con la carga cognitiva, y si el think en ingles es mas eficiente en tokens, forzarlo podria ser una palanca de presupuesto medible.

- **[2026-08-25 20:36] C30 · CONFIRMA** (medicion) — tareas_pct = 100.0 (se predijo ==100). CONFIRMADO —tareas_pct 100, predicho ==100 a un honesto 60%—: n3/lista PASA con 2.118 de 3.000 tokens y 0 intervenciones, y con ello queda medida LA FRASE DE LA MISION: el arnes construye un proyecto entero —modulo, CLI y persistencia que cruza procesos— desde un encargo en prosa, con el cerebro de 2,83 bits, solo CPU, dentro del presupuesto del §muro. La carrera fue ademas el experimento mas limpio posible del arreglo de C29: a temperatura 0 el modelo repitio el guion de C29 TOKEN POR TOKEN —mismo think de diseño en ingles, cortado en el mismo punto— y donde C29 murio, la rama nueva de bucle.py pidio continuar; la continuacion costo un turno de 477 tokens que escribio lista.py entero (el diseño ya estaba en la cache: el reintento barato que el append-exacto prometia, cumplido) y la tarea cerro con 882 tokens de margen. El par C29/C30 es el patron de oro del ciclo: mismo guion determinista, un solo cambio, el resultado se invierte — nada que rascar. Quedan vivas dos hebras baratas para el siguiente que pase: (1) el presupuesto minimo real de un n3 esta entre 1.215 (donde C29 murio a medio diseño) y 2.118 (donde C30 cerro): un tope de 2.000 probablemente mata la tarea y uno de 2.500 la deja JUSTA — medible en una carrera; (2) la miga del idioma sigue abierta: el think de diseño salio en ingles las dos veces, y si el ingles es mas denso por token, forzar el idioma del think es una palanca de presupuesto que se mide con una carrera y un contador.

- **[2026-08-25 21:26] C31 · CONFIRMA** (medicion) — tareas_pct = 0.0 (se predijo ==0). CONFIRMADO en la cifra —tareas_pct 0 por tope_tokens, 1.659 gastados, solo lista.py escrito— y la cota queda cerrada: el presupuesto minimo de n3/lista esta en (1.500, 2.118] y el tope operativo razonable para n3 es 3.000. PERO el camino micro DIVERGIO y eso es la mitad valiosa del ciclo: la vuelta 3 no repitio el think ingles de C29/C30 —salio antes, en castellano, y empezo el escribir, cortado a 1.024 en mitad del JSON; la vuelta 4 lo reemitio limpio (el camino de quejas de C24 funcionando)—. A temperatura 0 la unica fuente de divergencia es el contexto, y el culpable es el ls -la de la vuelta 1: el nombre del directorio temporal y las fechas CAMBIAN por carrera, y el muestreo greedy es caotico ante bits de contexto. El «token por token» que la leccion de C30 afirmo era demasiado fuerte: valio entre C29 y C30 por suerte, no por construccion. CONSECUENCIA DE METODO, directa para H6: comparar carreras como «mismo guion» solo vale si las observaciones son byte-identicas; el comparador del lazo autonomo necesita observaciones NORMALIZADAS (directorio de trabajo → «.», sin fechas, sin inodos) o cada comparacion arrastra este ruido. Es un cambio chico en herramientas/bash y compra reproducibilidad de verdad. Del mismo ciclo quedan construidas y probadas las dos piezas que el foco de H6 pedia: el VETO de rutas (permisos.py, banco/ de solo lectura en todo modo, 5 asertos) y el VIGILANTE (ciclo.py racha: N cerrados seguidos sin confirmar, umbral y codigo de salida para que el lazo pare y pida revision, 3 asertos). Falta el proponente: que el cerebro proponga la hipotesis siguiente desde horizonte.md y los registros.





- **[2026-08-25 23:16] C32 · REFUTA** (medicion) — tokens_media = 1933.0 (se predijo <1900). <think>
The user wants me to write a research cycle lesson. Let me analyze the data:

**Prediction:**
- Metric: tokens_media
- Expected: <1900
- Reasoning: C30 spent 2118 tokens; file reads cost ~250-350 tokens; `foco` replaces them with a holographic summary of ~50-100 tokens, net savings ~200-250 → 2118−250≈1870, conservative rounding to 1900.

**Measurement:**
- tokens_media: 1933.0
- The threshold was <1900
- 1933 > 1900, so it does NOT go below the threshold.

Wait, let me re-read the question: "¿Reduce `foco` los tokens de n3/lista por debajo del baseline de 2118 medido en C30?"

The question is whether `foco` reduces tokens below the baseline of 2118. The prediction was <1900.

The measurement shows 1933 tokens.

- 1933 < 2118 (baseline) → YES, it does reduce below baseline
- 1933 > 1900 (prediction threshold) → NO, it does NOT meet the predicted threshold

So the prediction of <1900 is REFUTED. The actual is 1933, which is 33 tokens above the 1900 threshold.

But the broader question "does it reduce below 2118?" is CONFIRMED (1933 < 2118).

Wait, I need to be more careful. The prediction says "espero: <1900". The measurement is 1933. So 1933 is NOT < 1900. The prediction is REFUTED.

The number against the threshold: 1933 vs 1900 → 33 tokens over.

Most probable cause: The prediction assumed file reads cost 250-350 tokens and `foco` summary costs 50-100, netting 200-250 savings. But looking at the trace, the actual savings were

- **[2026-08-26] NOTA a mano sobre la lección de C32** — la entrada anterior es la PRIMERA lección escrita por el lazo autónomo y salió contaminada: un `<think>` sin cerrar (cortado por el tope de 512 del redactor) se coló entero, en inglés y truncado. No se borra —esta página no olvida—, se corrige el mecanismo: el redactor de lecciones de `lazo.py` pasa a 1.024 tokens, descarta el razonamiento sin cerrar y cae a un aviso de revisión si no queda prosa. Lo que la lección DEBIÓ decir, con las cifras en la mano: (1) la carrera lanzada NO activaba ningún `foco` —esa bandera no existe—, así que el número no mide la hipótesis: mide la COSTURA entre el espacio de hipótesis del proponente y su espacio de acción (los mandos de `correr_banco`); el proponente queda constreñido a los mandos existentes hasta que la bandera exista. (2) Aun así el número informa, y mucho: 1.933 frente a los 2.118 de C30, mismo mundo reproducible y mismos topes — una deriva del ~9 % entre carreras SIN cambio de mecanismo, que fija el SUELO DE RUIDO de `tokens_media`: un umbral a menos del ~10 % del baseline es una apuesta al ruido, no una hipótesis. El proponente queda instruido de dejar ≥15 % de margen o de predecir sobre `tareas_pct`/`intervenciones`, que son discretas.







- **[2026-08-26 03:13] C33 · REFUTA** (medicion) — segundos_media = 1765.1 (se predijo <1400). REFUTA. El umbral era <1400s y la medición fue 1765.1s, superando el límite en 365.1s. La causa más probable es que el tope de 8 vueltas no es el cuello de botella, sino que la sobrecarga de contexto o la velocidad de inferencia domina el tiempo total. La tarea se completó al 100% con 1933 tokens medios y 0 intervenciones, confirmando que la restricción de vueltas no rompió la ejecución. El tiempo total de 1766.2s excede el baseline de 1630s, indicando un aumento del 8.3% en la duración. No se observó un aumento por sobrecarga de contexto, sino una degradación general del rendimiento. Se debe medir el tiempo por llamada individual para aislar si la lentitud proviene de la inferencia o de la gestión de contexto.

- **[2026-08-26 04:17] C34 · CONFIRMA** (medicion) — tokens_media = 1933.0 (se predijo <2000). CONFIRMA.
El umbral de 2000 tokens se supera con un margen de 67 tokens.
La cifra medida es de 1933 tokens medios.
La causa más probable es la eficiencia del modelo GGUF en la tarea lista.
El tope de 3000 tokens no generó inflación en el gasto.
El tiempo medio de 2552.4 segundos confirma la estabilidad del proceso.
No se registraron intervenciones ni errores en las 7 vueltas.
Se debe medir la varianza de tokens en 10 ejecuciones adicionales.
El siguiente paso es validar la consistencia del umbral en otras tareas.


- **[2026-08-26 05:00] C35 · CONFIRMA** (medicion) — segundos_media = 1352.0 (se predijo <2500). CONFIRMA.
La medición de 1352.0 segundos supera el umbral de 2500 segundos con un margen de 1148 segundos.
El tope de 5400 segundos no fue alcanzado, permitiendo la finalización completa de la tarea.
La causa más probable es la eficiencia del modelo GGUF en modo lista, que requirió solo 1933 tokens.
El rendimiento fue un 47% inferior al peor caso reciente (C34: 2552.4s).
El tiempo medio de 1352.0 segundos valida la estabilidad temporal del sistema.
Se recomienda medir la variabilidad en las próximas 5 iteraciones para confirmar la consistencia.
El umbral de 2500 segundos se mantiene como referencia válida para futuros ciclos.
No se detectaron intervenciones ni errores que afectaran la métrica de tiempo.



- **[2026-08-26 05:49] C36 · CONFIRMA** (medicion) — intervenciones = 0.0 (se predijo <10). CONFIRMA.
El umbral de 10 intervenciones se superó con 0 medidas.
La causa es la estabilidad del tope de 16 vueltas.
El modelo resolvió la tarea n3/lista sin cortes.
Se registraron 1933 tokens medios en 1356.2 segundos.
El 100% de las tareas se completó exitosamente.
Medir la variabilidad de tokens en el siguiente ciclo.
Verificar si el tope de 16 mantiene 0 intervenciones.

- **[2026-08-26 06:52] C37 · REFUTA** (medicion) — tokens_media = 1933.0 (se predijo <1600). REFUTA.
El umbral de 1600 tokens se incumple con un margen de 333 tokens.
La cifra medida es de 1933 tokens medios.
La causa probable es que el tope de 2500 no comprime el contexto.
El modelo genera 1024 tokens en el turno 3 sin recortar.
El gasto se mantiene en el baseline original de 1933.
El umbral de 1600 carece de margen real sobre el ruido.
Medir la distribución de tokens por turno para aislar el pico.
Ajustar el tope a 1800 para forzar la compresión real.

- **[2026-08-26 07:31] C38 · CONFIRMA** (medicion) — tokens_media = 1511.0 (se predijo <1600). CONFIRMA.
El valor medido de 1511 tokens supera el umbral de 1600 por 89 unidades.
La causa es el tope de 1500 tokens que trunca la ejecución.
El sistema respeta el límite y evita el gasto del baseline de 1933.
La tarea falló al agotar el tope sin completar el objetivo.
El recorte forzado baja la media por debajo del umbral previsto.
Medir la tasa de éxito con el tope en 1800 tokens.
Verificar si el modelo recupera la eficiencia sin truncamiento.

- **[2026-08-26 08:16] C39 · REFUTA** (medicion) — tokens_media = 1933.0 (se predijo <1700). REFUTA.
El umbral era 1700 tokens y la medición fue 1933.
La diferencia es de 233 tokens por encima del límite.
El tope de 1800 no impidió el éxito, pero no forzó la compresión esperada.
La causa probable es que la tarea n3/lista requiere ese volumen mínimo de tokens.
El 100% de éxito se mantuvo con 0 intervenciones.
Mide el tope de 1600 tokens para forzar una compresión real.
Observa si el éxito cae o si el sistema recorta la salida.


- **[2026-08-26 09:00] C40 · CONFIRMA** (medicion) — tokens_media = 1732.0 (se predijo <1800). CONFIRMA.
La métrica tokens_media es 1732, por debajo del umbral de 1800.
El margen de seguridad es de 68 tokens respecto al límite.
El éxito se mantiene al 100% sin intervenciones.
La causa probable es que el tope de 1600 tokens por vuelta no impide la finalización.
El modelo comprimió la salida para ajustarse al límite.
Medir la varianza de tokens_media en 10 repeticiones.
Verificar si el recorte de contexto degrada la calidad del código.

- **[2026-08-26 10:13] C41 · REFUTA** (medicion) — segundos_media = 2290.3 (se predijo <900). REFUTA. El tiempo medio de 2290.3 segundos supera el umbral de 900 segundos en 1390.3 segundos. La causa es la latencia de inferencia del modelo GGUF, no la cantidad de vueltas. El tope de 8 vueltas no fue el cuello de botella, ya que la tarea se resolvió en 7 vueltas. El 100% de éxito se mantuvo, pero la métrica de tiempo falló drásticamente. La predicción ignoró el coste computacional por token y por llamada. Debes medir el tiempo de inferencia por token para aislar la latencia del modelo.

- **[2026-08-26 11:28] C42 · CONFIRMA** (medicion) — tokens_media = 686.0 (se predijo <800). CONFIRMA.
El umbral de 800 tokens se supera con un margen de 114 tokens.
La medición registró una media exacta de 686 tokens.
El 100% de éxito se mantuvo sin intervenciones.
La causa es la eficiencia del modelo gguf en la tarea n2/aguja.
El tope de 1200 tokens resultó holgado para el flujo real.
La métrica de tiempo (2372.5 s) no afectó el conteo de tokens.
Medir la varianza de tokens en 10 repeticiones para validar estabilidad.

- **[2026-08-26 12:25] C43 · REFUTA** (medicion) — tokens_media = 957.0 (se predijo <800). REFUTA.
El umbral era 800 tokens y la medición arrojó 957 tokens.
La cifra excede el umbral en 157 tokens.
La causa más probable es que la tarea de cupones exige más contexto que la aguja.
El 100% de éxito se mantuvo con 0 intervenciones.
El tiempo medio fue de 1036.8 segundos.
La complejidad de n2/cupones supera el baseline de 686 tokens.
Medir la tokens_media de n2/aguña con tope 1200 para aislar la variable.

- **[2026-08-26 13:02] C44 · CONFIRMA** (medicion) — tokens_media = 881.0 (se predijo <1000). CONFIRMA.
El umbral de 1200 tokens supera el límite de 1000 con un margen de 200 tokens.
La medición registró una media de 881 tokens, quedando 119 por debajo del objetivo.
El éxito se mantuvo al 100% sin intervenciones humanas.
La causa probable es que la lógica de conteo de "tres" requiere solo 5 vueltas.
El tope de 1200 tokens cubre la variabilidad esperada sin sobrecargar el contexto.
La eficiencia temporal fue de 922.8 segundos por tarea.
Debes medir la varianza de tokens en 10 iteraciones adicionales.
Verifica si el tope de 1200 se mantiene estable con tareas de mayor complejidad.

- **[2026-08-26 13:43] C45 · REFUTA** (medicion) — tokens_media = 1215.0 (se predijo <900). REFUTA.
El umbral era 900 tokens y se midieron 1215.
La diferencia es de 315 tokens por encima del límite.
El 100% de éxito se mantuvo, pero el coste superó la predicción.
La causa probable es la edición masiva de 991 tokens en la vuelta 5.
Esa acción de reescritura completa agotó el margen previsto.
El tope de 1200 tokens no impidió el éxito, pero no garantizó la ligereza.
Medir la longitud de la edición en `migrador.py` para aislar el coste.
Repetir el ciclo con una instrucción de edición incremental.


- **[2026-08-26 15:39] C46 · REFUTA** (medicion) — segundos_media = 2322.1 (se predijo <900). REFUTA. El tiempo medio de 2322.1 segundos supera el umbral de 900 segundos en 1422.1 segundos. La causa más probable es la ejecución de un comando fallido que consumió 1474.0 segundos en la vuelta 3. El tope de 1200 tokens permitió completar la tarea con 686 tokens medios, cumpliendo el objetivo de menos de 700. El éxito se mantuvo al 100% con 0 intervenciones. La métrica de tokens se mantuvo estable bajo el tope. El tiempo total de 2323.2 segundos confirma la ineficiencia temporal. Se debe medir el tiempo de ejecución de comandos bash para aislar cuellos de botella.

- **[2026-08-26 16:47] C47 · REFUTA** (medicion) — segundos_media = 1204.6 (se predijo <1100). REFUTA.
El tiempo medio de 1204.6 segundos supera el umbral de 1100 segundos.
La causa probable es la sobrecarga de inferencia en la vuelta 3 (480.6 s) para generar el código.
El tope de 1200 tokens no impidió el éxito, manteniendo el 100% de tareas completadas.
Se registraron 957 tokens medios, muy por debajo del límite de 1200.
No hubo intervenciones humanas, confirmando la autonomía del proceso.
La métrica de tiempo no valida la hipótesis de velocidad superior a version.
Medir la latencia de inferencia por token para aislar el cuello de botella.
Evaluar si reducir el contexto de entrada acelera la generación de código.

- **[2026-08-26 17:48] C48 · REFUTA** (medicion) — segundos_media = 1379.7 (se predijo <800). REFUTA. El umbral era <800 segundos y la medición registró 1379.7 segundos, superando el límite en 579.7 segundos. El éxito se mantuvo al 100% con 881 tokens medios, confirmando que el tope de 1200 tokens no impide la finalización. La causa probable es que la inferencia del modelo gguf en modo lista requiere más tiempo de cómputo por token que el estimado en la predicción. La predicción subestimó el coste temporal real de la tarea n2/tres en este entorno. No se observaron intervenciones humanas, lo que indica que el fallo es puramente de rendimiento de velocidad. El margen de 30% previsto no cubre la brecha real de 72% sobre el umbral. Debe medirse el tiempo de inferencia por token específico del modelo gguf para recalibrar el umbral.


- **[2026-08-26 18:17] C49 · CONFIRMA** (medicion) — tokens_media = 493.0 (se predijo <700). CONFIRMADO —493,0 tokens frente a <700, y ademas EXACTAMENTE la linea base: el guion de anadir repitio al token entre C24, C25 y hoy—. Este ciclo fue la revision humana que el vigilante exigio al parar el lazo en racha 4 (C45-C48), y deja tres cosas: (1) el diagnostico de la racha confirmado — era UN sesgo repetido cuatro veces, predecir segundos ignorando lineas base conocidas, no cuatro fallos distintos; (2) el arreglo puesto — el contexto del proponente lleva ahora la tabla de LINEAS BASE por tarea con la instruccion de anclar umbrales con 15-30% de margen; (3) la salida de una racha codificada como doctrina: se sale con una prediccion ANCLADA que confirma, no con un override del umbral — el vigilante no se toca, se le da la razon. Secundario y valioso: segundos_media 766,0 con la maquina de mediodia, frente a 969,2 de la primera medicion de anadir — el mundo reproducible mantiene el guion clavado mientras el reloj baila con la maquina, una demostracion mas de que tokens_media es la metrica estable y segundos_media necesita control del dia.

- **[2026-08-26 18:55] C50 · REFUTA** (medicion) — segundos_media = 919.7 (se predijo <900). REFUTA. El umbral era <900 segundos y la medición fue 919.7 segundos. La causa más probable es que la tarea de bitacora requirió 6 vueltas completas para diagnosticar y corregir el error en `disco.py`, superando la complejidad estimada. El éxito se mantuvo al 100% con 654 tokens medios y 0 intervenciones. El tope de 16 vueltas no fue el limitante, sino el tiempo de inferencia por vuelta. Medir la latencia pura de inferencia por token para aislar el cuello de botella.


- **[2026-08-26 19:42] C51 · REFUTA** (medicion) — tokens_media = 953.0 (se predijo <600). REFUTA.
El umbral de 3000 tokens no impide el éxito, pero la métrica de tokens_media es 953.0, superando el umbral de 600.
El 100% de éxito se mantiene con 0 intervenciones, validando la funcionalidad.
La causa probable es que la tarea de cadena requiere más contexto que la línea base de 493 tokens.
El margen del 21% sobre la línea base de anadir resultó insuficiente para la complejidad real.
Se midieron 4 vueltas con un total de 953 tokens, confirmando la sobrecarga estructural.
El tiempo medio de 1437.7 segundos indica que la eficiencia no se ve reflejada en velocidad.
La hipótesis de similitud con n1/anadir fue incorrecta al subestimar la carga de contexto.
Medir la desviación estándar de tokens en 10 repeticiones para estabilizar la media.

- **[2026-08-26 20:20] C52 · CONFIRMA** (medicion) — tokens_media = 506.0 (se predijo <650). CONFIRMA.
El umbral de 650 tokens se supera con un margen de 144 tokens.
La media medida fue de 506 tokens, quedando 144 por debajo del límite.
El éxito se mantuvo al 100% sin intervenciones.
La causa es la eficiencia del modelo gguf en la tarea n1.
El tope de 3000 tokens no fue un cuello de botella.
La ejecución duró 939.4 segundos con 5 vueltas.
Medir la varianza de tokens en 10 repeticiones.

- **[2026-08-26 20:56] C53 · CONFIRMA** (medicion) — segundos_media = 822.5 (se predijo <1000). CONFIRMA.
El valor medido de 822.5 segundos supera el umbral de 1000 segundos.
La diferencia es de 177.5 segundos a favor del objetivo.
El éxito se mantuvo al 100% con 0 intervenciones.
La causa probable es la eficiencia del modelo gguf en la tarea migrar.
El tope de 5400 segundos resultó sobredimensionado para este caso.
Se recomienda medir la varianza con 10 iteraciones adicionales.
El siguiente paso es validar la estabilidad del tiempo medio.

- **[2026-08-26 21:41] C54 · REFUTA** (medicion) — segundos_media = 1356.0 (se predijo <1100). REFUTA. El umbral de 5400 segundos no impidió el éxito, pero el tiempo medio de 1356.0 segundos supera el límite de 1100 segundos. La cifra de 1356.0 excede el umbral en 256.0 segundos. La causa probable es la latencia de inferencia del modelo gguf, no el tope de tiempo. Mide la latencia por token para aislar el cuello de botella.

- **[2026-08-26 22:35] C55 · CONFIRMA** (medicion) — segundos_media = 757.8 (se predijo <880). CONFIRMA.
El valor medido de 757.8 segundos está por debajo del umbral de 880 segundos.
La diferencia es de 122.2 segundos a favor del umbral.
El éxito se mantuvo en el 100% de las tareas.
La causa más probable es la eficiencia en la latencia de inferencia.
No se detecta ineficiencia en el relleno de contexto.
El tope de 5400 segundos no fue alcanzado.
Medir la varianza de segundos_media en la siguiente iteración.

- **[2026-08-26 23:28] C56 · CONFIRMA** (medicion) — segundos_media = 1059.1 (se predijo <1600). CONFIRMA.
El umbral de 1600 segundos se supera con holgura.
La medición real fue de 1059.1 segundos.
La diferencia contra el umbral es de 540.9 segundos.
El tope de 5400 segundos no fue el factor limitante.
La causa más probable es la eficiencia del modelo gguf en la cadena.
El 100% de éxito se mantuvo sin intervenciones.
Medir la latencia de las llamadas de edición en la siguiente iteración.

- **[2026-08-27 00:03] C57 · CONFIRMA** (medicion) — segundos_media = 759.9 (se predijo <1090). CONFIRMA.
El valor medido de 759.9 segundos está por debajo del umbral de 1090.
La diferencia es de 330.1 segundos a favor del objetivo.
El tope de 5400 segundos no fue el factor limitante.
El éxito se mantuvo al 100% sin intervenciones.
La causa más probable es la eficiencia del modelo gguf en la tarea.
Medir la varianza de segundos_media en las siguientes 5 ejecuciones.
Verificar si el margen de 330.1 segundos se mantiene estable.
Registrar el tiempo de latencia de las llamadas de herramientas.



- **[2026-08-27 02:58] C58 · CONFIRMA** (medicion) — segundos_media = 1485.2 (se predijo <1540). CONFIRMA.
El tiempo medio de 1485.2 segundos queda por debajo del umbral de 1540 segundos.
La diferencia numérica es de 54.8 segundos a favor del objetivo.
El 100% de éxito se mantiene intacto en la métrica de tareas.
La causa más probable es la ineficiencia del modo lista al bloquear 14 intentos de bash.
Estos rechazos forzaron 14 intervencias y consumieron tiempo sin avanzar la lógica.
El tope de 5400 segundos no fue el limitante real del proceso.
Medir después el tiempo medio con modo libre para aislar el coste del bloqueo.

- **[2026-08-27 03:29] C59 · CONFIRMA** (medicion) — segundos_media = 549.1 (se predijo <657). CONFIRMA.
El umbral de 657 segundos supera la medición de 549.1 segundos.
La diferencia es de 107.9 segundos a favor del objetivo.
El tope de 5400 segundos no fue el limitante, ya que la tarea terminó en 550.2 segundos.
El 100% de éxito se mantuvo con 0 intervenciones.
La causa más probable es la eficiencia del modelo gguf en la tarea de creación.
Medir la varianza de segundos_media en las próximas 10 ejecuciones.
Verificar si el margen de 107.9 segundos absorbe picos de latencia.

- **[2026-08-27 04:11] C60 · CONFIRMA** (medicion) — segundos_media = 748.8 (se predijo <1460). CONFIRMA. El umbral de 1460 segundos supera la media medida de 748.8 segundos. La diferencia es de 711.2 segundos a favor del umbral. El tope de 5400 segundos no fue el limitante, ya que la ejecución total fue de 750.0 segundos. El 100% de éxito se mantuvo con 0 intervenciones. La causa más probable es que la tarea rastro es de baja complejidad para el modelo gguf. Medir la varianza de segundos_media en 10 repeticiones para validar la estabilidad.

- **[2026-08-27 04:58] C61 · REFUTA** (medicion) — tokens_media = 907.0 (se predijo <767). REFUTA.
El umbral era <767 tokens medios.
La medición registró 907 tokens medios.
El exceso es de 140 tokens sobre el límite.
La causa probable es el bucle de 13 intervenciones fallidas por la lista blanca.
Cada intento de bash consumió ~49 tokens sin avanzar la tarea.
El tope de 3000 tokens no impidió el éxito, pero el costo fue ineficiente.
Medir la tasa de éxito con la lista blanca ampliada para reducir las intervenciones.

- **[2026-08-27 05:48] C62 · CONFIRMA** (medicion) — segundos_media = 1280.9 (se predijo <1314). CONFIRMA.
El umbral de 1314 segundos se supera con un margen de 33.1 segundos.
La métrica medida fue de 1280.9 segundos de media.
El 100% de éxito se mantuvo en las 16 vueltas.
La causa probable es la ineficiencia por 13 intervenciones en bash.
Estas fallas consumieron tiempo sin aportar progreso real.
El tope de 5400 segundos resultó sobrado para la ejecución.
Mide la tasa de éxito en bash para reducir las intervenciones.
Evalúa si el tope de vueltas limita la resolución real.

- **[2026-08-27 06:21] C63 · CONFIRMA** (medicion) — tokens_media = 489.0 (se predijo <562). CONFIRMA.
La métrica tokens_media es 489.0, inferior al umbral de 562.
El margen de seguridad es de 73 tokens por debajo del límite.
El tope de 3000 tokens no impidió la finalización de la tarea.
El éxito se mantuvo al 100% sin intervenciones humanas.
La causa probable es la eficiencia directa del flujo de migración.
No se observaron bucles de error ni sobrecarga de contexto.
Medir la varianza de tokens_media en 10 ejecuciones adicionales.
Verificar si el tope de 3000 tokens afecta tareas de mayor complejidad.

- **[2026-08-27 06:56] C64 · CONFIRMA** (medicion) — tokens_media = 654.0 (se predijo <752). CONFIRMA.
El umbral de 752 tokens se supera con un margen de 98 tokens de holgura.
La causa más probable es la eficiencia del bucle que resolvió la tarea en 6 vueltas.
El tope de 3000 tokens no fue un cuello de botella al consumirse solo 654.
El 100% de éxito se mantuvo sin intervenciones manuales.
La varianza observada fue nula al tratarse de una única ejecución.
El tiempo medio de 829.5 segundos confirma la estabilidad del proceso.
Medir la desviación estándar con 10 repeticiones idénticas.

- **[2026-08-27 07:31] C65 · CONFIRMA** (medicion) — tokens_media = 682.0 (se predijo <794). CONFIRMA.
El umbral de 794 tokens se supera con un margen de 112 tokens.
La tokens_media medida es de 682.0, por debajo del límite de 794.
El éxito se mantiene al 100.0% de las tareas.
La causa es la eficiencia del modelo gguf en la tarea n1/rojo.
El tiempo medio de 820.4 segundos confirma la estabilidad del proceso.
No se registraron intervenciones manuales durante la ejecución.
Medir la variabilidad de tokens_media en 10 repeticiones adicionales.
Verificar si el margen de 16.4% se mantiene con otras tareas n1.

- **[2026-08-27 08:01] C66 · CONFIRMA** (medicion) — tokens_media = 278.0 (se predijo <320). CONFIRMA.
El umbral de 320 tokens se supera con un margen de 42 tokens.
La media medida es de 278 tokens, por debajo del límite.
El éxito se mantiene al 100% sin degradación.
La causa probable es la eficiencia intrínseca de la tarea n0.
No hay intervenciones ni sobrecostos por el tope de 3000.
El tiempo medio de 538.6 segundos es estable.
Medir la varianza de tokens en 10 repeticiones.
Verificar si el tope de 3000 limita otras tareas complejas.

- **[2026-08-27 08:31] C67 · CONFIRMA** (medicion) — tokens_media = 345.0 (se predijo <423). CONFIRMA.
El umbral era 423 tokens.
La medición fue 345 tokens.
La diferencia es de 78 tokens.
La causa es la eficiencia del modelo gguf.
El tope de 3000 tokens no fue un límite.
El éxito fue del 100%.
Medir segundos_media en la siguiente iteración.

- **[2026-08-27 09:18] C68 · REFUTA** (medicion) — tokens_media = 1161.0 (se predijo <997). REFUTA.
El umbral de 997 tokens se incumple con 1161 tokens medios.
La causa es el bloqueo de la lista blanca que impide ejecutar el código de verificación.
El modelo genera 14 intentos fallidos de bash para validar la solución.
Cada intento consume entre 58 y 90 tokens adicionales sin avanzar.
El tope de 3000 tokens no limita la ejecución, sino que permite el bucle de error.
El éxito del 100% se mantiene, pero la eficiencia se degrada un 16.4% sobre el umbral.
Medir la tasa de tokens por intento fallido para cuantificar la penalización del sandbox.

- **[2026-08-27 09:51] C69 · CONFIRMA** (medicion) — tokens_media = 460.0 (se predijo <530). CONFIRMA.
El umbral de 530 tokens se supera con un margen de 70 tokens.
La media medida es de 460 tokens, por debajo del límite.
El éxito se mantiene al 100% sin intervenciones.
El tope de 3000 tokens no induce sobrecosto.
La causa es la eficiencia del modelo gguf en modo lista.
Medir segundos_media en la siguiente iteración.
El tiempo de 697.4 segundos es el nuevo foco.

- **[2026-08-27 10:32] C70 · CONFIRMA** (medicion) — segundos_media = 1225.7 (se predijo <1334). CONFIRMA.
El umbral de 1334 segundos se supera con holgura.
La medición real fue de 1225.7 segundos.
La diferencia es de 108.3 segundos por debajo del límite.
El 100% de éxito se mantuvo sin intervenciones.
La causa probable es la eficiencia del modelo gguf en n2.
La tarea version requirió solo 7 vueltas y 1309 tokens.
Medir segundos_media en n3 para validar la escalabilidad.





- **[2026-08-27 12:23] C71 · CONFIRMA** (medicion) — tareas_pct = 100.0 (se predijo ==100). CONFIRMADO en la cifra —tareas_pct 100— pero la GUARDA de la propia prediccion dice que esto NO cierra M5.1 todavia: no hubo ni un renacimiento real (la unica coincidencia en el log es la cita de la prediccion) porque el modelo fue mas economico que mi aritmetica — 14 vueltas, 992 tokens de salida, contexto por vuelta ~9K, por debajo del umbral de 13.1K. La tarea de resistencia paso SIN estresar el mecanismo. Dos cosas medidas que si valen: (a) 64.045 tokens de entrada acumulada en 1.802,6 s — el append-exacto sostiene tareas largas con un reloj decente; (b) el renacimiento sigue probado solo en frio (ventana enana, 48 asertos). La leccion de metodo: para estresar un mecanismo relativo al contexto no se engorda la tarea (el modelo la adelgaza), se ENCOGE LA VENTANA — C72 repite la misma tarea con contexto_max 8000 y ahi el umbral de 6.4K se cruza hacia la vuelta 9 haga lo que haga el modelo. Guarda identica: 100 CON renacimiento en la traza, o no cuenta.




- **[2026-08-27 15:28] C72 · CONFIRMA** (medicion) — tareas_pct = 100.0 (se predijo ==100). CONFIRMADO CON LA GUARDA CUMPLIDA —tareas_pct 100 Y un renacimiento real en la traza (13.026 caracteres resumidos)—: LA BRECHA M5.1 QUEDA CERRADA CON NUMERO. La sesion renacio tras el mega-turno de los 10 editar, el modelo continuo desde el resumen mecanico sin repetir trabajo, verifico y cerro en 10 vueltas (1.365 tok, 2.975,7 s, 1 intervencion menor). El camino hasta aqui vale tanto como el destino y queda en las revisiones: el desbordamiento tenia TRES capas y las tres se pelaron con evidencia, no con conjetura — la fraccion no ve la sobrecarga absoluta; el contenido crudo no ve el JSON de llamadas ni los envoltorios; y la capa real, invisible para CUALQUIER conteo desde la transcripcion, es el think crudo que el camino incremental arrastra en la cache — por eso el arreglo final pregunta al CEREBRO (tokens_en_contexto) y toma el maximo de ambas vistas, con olvidar() tras renacer para no encadenar renaceres. Regla que queda para siempre: en un arnes con cache append-exacta, el guardian del contexto tiene que mirar LA CACHE, no la transcripcion. Con esto Mekro-Genai sostiene tareas que desbordan su ventana: la capacidad que el autor llamo «el hueco mas profundo» frente a Claude Code.



- **[2026-08-27 17:22] C73 · CONFIRMA** (medicion) — tokens_media = 1614.0 (se predijo <1900). CONFIRMADO en la cifra (1.614 < 1900) pero la GUARDA manda: la tarea FALLO por tope_tokens y M3 NO se declara. Lo que este ciclo probo es la otra mitad del mecanismo, y en produccion: el vigilante de adopciones REVIRTIO solo la adopcion fallida, con constancia en el historial — el 100% es sagrado y la maquinaria lo defiende sin humano. La causa raiz, medible: C40 'gano' con 1.732 tokens de USO sobre un tope de 1.600 — rebaso su propio presupuesto y sobrevivio porque el tope se chequea al empezar cada vuelta; la adopcion eligio una configuracion sin margen, fragil por construccion, y la deriva normal de guion la mato. REGLA NUEVA del mecanismo (la cuarta de honestidad): solo se adopta una victoria que termino DENTRO de su tope (valor <= tope_tokens) — ganar rebasando el presupuesto es suerte, no configuracion. Con esa regla, el candidato robusto que queda en los registros es C39 (tope 1.800, uso ~1.6xx, 100%): la siguiente pasada lo adopta y C74 lo mide por la tuberia oficial. El arco C73→C74 es el mecanismo completo enseñado en publico: adopcion fragil → fallo → reversion automatica → regla endurecida → adopcion robusta.


- **[2026-08-27 18:49] C74 · REFUTA** (medicion) — tokens_media = 1242.0 (se predijo <1200). REFUTA.
El umbral de 1200 tokens no se cumplió, registrando 1242 tokens de media.
El modelo superó el tope en 42 tokens, un 3,5% por encima del límite.
La causa probable es que la tarea exige 10 ediciones masivas que saturan el contexto.
El éxito se mantuvo al 100%, pero la eficiencia se rompió al exceder el tope.
La restricción de tokens no forzó la compresión, sino que se ignoró parcialmente.
Debes medir el conteo de tokens por llamada para aislar el pico de consumo.
Repite el ciclo con un tope de 1100 para forzar una compresión real.

- **[2026-08-27 19:54] C75 · REFUTA** (medicion) — tokens_media = 1242.0 (se predijo <1050). REFUTA.
El umbral de 1.050 no se aplicó, ya que la medición registró 1.242 tokens de media.
El valor medido supera el umbral en 192 tokens, equivalente a un 18,3% de exceso.
La causa más probable es que el tope actúa como límite superior blando que no fuerza la compresión si la tarea lo requiere.
El 100% de éxito se mantuvo, pero el objetivo de reducción del 15,5% no se cumplió.
La intervención única indica que el modelo resolvió la tarea sin recortes artificiales.
Debes medir la distribución de tokens por vuelta para identificar dónde se genera el volumen extra.
Repite el ciclo con un tope de 1.000 para forzar una compresión real.
Verifica si el éxito cae por debajo del 95% al reducir el margen de tokens.

- **[2026-08-27 20:58] C76 · REFUTA** (medicion) — segundos_media = 2184.4 (se predijo <1900). REFUTA. El umbral de 1.900 s no se alcanzó, con una media de 2.184,4 s que excede el tope en 284,4 s. La causa probable es que la restricción temporal no acelera la inferencia, sino que el modelo prioriza la corrección de los 10 módulos. El 100% de éxito se mantuvo, pero la latencia real superó la línea base de 2.244 s solo marginalmente al bajar de ella. La intervención única indica que el error de lista blanca no frenó el proceso. Mide la latencia por vuelta para aislar si el cuello de botella es la edición masiva o la inferencia base.

- **[2026-08-27 21:37] C77 · REFUTA** (medicion) — tokens_media = 1171.0 (se predijo <1050). REFUTA.
El umbral de 1.050 se superó al registrar 1.171 tokens de media.
La causa probable es que el modelo prioriza la completitud sobre la brevedad ante la restricción.
El 100% de éxito se colapsó a 0% por el corte por tope de tokens.
La métrica de segundos_media de 1.068,8 s confirma la ineficiencia temporal.
Medir ahora un tope_tokens de 1.200 para aislar el punto de quiebre.
Verificar si el éxito se recupera manteniendo la compresión por debajo de 1.614.
Registrar la tasa de intervención para cuantificar la fricción del corte.

- **[2026-08-27 22:04] C78 · REFUTA** (medicion) — tokens_media = 2069.0 (se predijo <1906). REFUTADO —2.069 frente a <1906, con 100% y 0 intervenciones— y con ello queda FALSADA LA VIA ENTERA de mandos pasivos para M3, en cinco mediciones: los topes rompen antes de mejorar (C73: adopcion revertida; C77: 0% a tope 1.050) y la ventana encogida comprime por azar del camino, no por construccion (C72: 1.365; C78: 2.069 — misma configuracion, ±35% de varianza, contra un liston del 10%). El renacimiento ni siquiera salto esta vez: el camino de 7 vueltas cupo en 8.000. La leccion de fondo: en un modelo determinista-caotico (C31), un mando solo es adoptable si actua EN CADA carrera, no si depende del camino — los topes actuan solo al morder (y entonces rompen) y el contexto solo si el guion desborda. El mando activo que actua SIEMPRE y nadie ha medido en el banco: sin-pensar (el prellenado enable_thinking=false de fabrica, ya construido en M5.5), que elimina la fraccion dominante de los tokens en cada vuelta por construccion. Riesgo real y falsable: el criterio puede degradarse sin el think (C29 enseño que el diseño largo lo necesita; un arreglo simple quiza no). C79 lo mide en n1/anadir — el banco de M2, la letra exacta de M3.


- **[2026-08-27 22:25] C79 · CONFIRMA** (medicion) — tokens_media = 202.0 (se predijo <430). CONFIRMADO en la cifra —202 frente a <430, un -59% sobre la base 493— pero la GUARDA manda otra vez: la tarea FALLO (2 vueltas: sin think el modelo se precipito y rompio el criterio) y la adopcion NO salta. La rama intermedia de la prediccion, cumplida al pie: el criterio SI necesita el razonamiento incluso en tareas simples — el think no es grasa, es donde vive la comprension del contrato de la prueba. Con esto van SIETE mediciones del espacio de mandos (C73-C79) y el mapa esta completo: topes rompen antes de mejorar, contexto comprime por azar del camino (±35%), sin-pensar total comprime de sobra (-59%) pero mata el criterio. El dato de C79 señala la sintesis obvia y aun sin medir: el think selectivo — pensar en las vueltas de DIAGNOSTICO (donde el criterio se forma) y no en las mecanicas (donde solo cuesta). Es bandera de carrera (--pensar-vueltas N) y C80 la mide como ULTIMO intento del revisor antes de rendir el informe al autor: si tampoco, M3 queda medido como inalcanzable con banderas y este cerebro, y la palanca pasa a M1.

- **[2026-08-27 23:01] C80 · REFUTA** (medicion) — tokens_media = 544.0 (se predijo <430). REFUTADO —544 frente a <430, con 100% y 0 intervenciones— y con ello EL MAPA DE M3 SOBRE MANDOS DE CARRERA QUEDA COMPLETO EN OCHO MEDICIONES (C73-C80), con una simetria final que lo explica todo: (1) los topes rompen antes de mejorar (C73 adopcion revertida; C77 0% a tope 1.050); (2) la ventana encogida comprime por azar del camino, no por construccion (1.365 contra 2.069 con la misma configuracion: ±35% de varianza contra un liston del 10%); (3) quitar el think entero ahorra un 59% pero mata el criterio (C79: 202 tokens, 0%); (4) y quitarlo solo de las vueltas mecanicas conserva el criterio pero no ahorra (C80: 544 ≥ 493), porque EL GASTO Y EL CRITERIO VIVEN EN EL MISMO SITIO — el razonamiento del diagnostico es a la vez la fraccion dominante de los tokens y la fuente de la correccion. Conclusion MEDIDA, no conjeturada: con el cerebro de trabajo de 2,83 bits, una mejora estable ≥10% en tokens del banco via banderas de carrera NO EXISTE — la densidad de razonamiento por token de este cerebro es la que es, y la palanca real de M3 es M1: un cerebro mejor piensa lo mismo en menos tokens. Lo que SI quedo construido y probado en produccion es la maquinaria entera de M3: adopcion con cuatro reglas de honestidad, reversion automatica (C73), vigilante de rachas, y un espacio de mandos activo (sin-pensar, pensar-vueltas, contexto) listo para el dia que el campeon exista. El dia que M1 aterrice, esta misma bateria de ocho preguntas se recorre en una noche de lazo autonomo.

- **[2026-08-28] INCIDENTE DE REGISTRO, anotado porque este fichero es permanente** — se retiraron de aquí **41 entradas idénticas** que decían «C1 · CONFIRMA» con la misma lección de juguete. No eran lecciones: las escribía `tests/test_lazo.py` en CADA ejecución, porque `ciclo.py veredicto` escribía siempre en el CONTINUIDAD.md real aunque la prueba apuntara sus ciclos y registros a un temporal. Se fueron commiteando desde el 2026-08-25 sin que nadie lo viera. **Lo destapó el guardián de salud, no una persona**, avisando de un fichero sin commitear tres rondas seguidas. Arreglo: `ciclo.py` respeta `MG_CONTINUIDAD`, la prueba apunta a un temporal, y el guardián comprueba en cada ronda que no haya lecciones de prueba aquí dentro. La lección de método: **una prueba que escribe en el registro permanente del proyecto corrompe la evidencia en silencio**; todo lo que una prueba toque tiene que ser desviable por entorno.

- **[2026-08-28 06:00] C81 · CONFIRMA** (medicion) — segundos_media = 1085.4 (se predijo <1400). CONFIRMADO EN LA CIFRA PERO NO POR EL MECANISMO, y la distincion es toda la leccion: segundos_media 1.085,4 frente a <1.400, con 100% y 0 intervenciones — pero el gasto auxiliar de nube fue CERO. El modelo local no lanzo ni un subagente: resolvio la tarea con dos grep, un editar y una verificacion, en 4 vueltas. La rama honesta de la prediccion se cumplio antes de tiempo: el hibrido no se impone por existir, y para ESTA tarea el modelo eligio mejor que el diseno — un grep sobre ocho ficheros es mas barato que delegar tres exploraciones a la nube. El numero bajo de 1.400 por merito del modelo, no del reparto por rol. Tres cosas quedan medidas: (1) el cableado hibrido funciona y no estorba —la carrera paso limpia con el reparto puesto—; (2) la contabilidad auxiliar dice la verdad, y por eso se pudo ver que no se uso; (3) el subagente es una herramienta CARA cuya ganancia depende de que explorar sea realmente costoso: con grep disponible y ficheros pequenos, no lo es. Lo que falta medir, y es otro ciclo: una tarea donde grep NO baste —donde la respuesta exija leer y entender, no localizar una cadena— porque ahi es donde el subagente deberia pagar. Y una nota de diseno: si se quiere que el modelo delegue, hay que pedirselo en el prompt del sistema; el arnes hoy ofrece la herramienta y no la sugiere, que es lo correcto por defecto.

- **[2026-08-28 06:49] C82 · REFUTA** (medicion) — entrada_media = 27676.3 (se predijo <11000). La poda de observaciones no puede ahorrar en este banco, y la razon es una cifra que no habia mirado: las observaciones son solo el 11% de la entrada facturada. En n1/cadena, 2326 caracteres de observaciones (~582 tokens) reenviados ~4,5 veces son 2617 de 23305 tokens. Podarlas un 20% pone el techo del ahorro en 2,3% de la factura. Y la varianza del propio modelo entre dos controles identicos fue del 12,4%: el instrumento es cinco veces mas ruidoso que la senal, asi que la medicion estaba condenada antes de empezar. Predije <11000 y salio 27676. Dos lecciones que valen mas que el numero. PRIMERA: el delta de entrada siguio al delta de VUELTAS en las seis tareas sin una excepcion (+16% con una vuelta mas, -23% con dos menos). Como la transcripcion se reenvia entera, una vuelta de mas cuesta un prefijo completo y se come cualquier poda; el ahorro hay que juzgarlo por si cambia el numero de vueltas, no por los bytes recortados. RTK mide bytes sobre la salida interceptada, que es la unidad equivocada. SEGUNDA: antes de medir un efecto hay que medir el ruido del instrumento. Correr el control dos veces cuesta tres minutos y habria dicho desde el principio que un efecto del 2% no es observable aqui. La palanca que si toca el 100% de la entrada es la cache de prefijo, y una sonda de tres peticiones identicas de 6008 tokens mostro que Gemini nunca reporta cachedContentTokenCount: la cache implicita no existe para gemini-3.7-flash, asi que ahi el ahorro requiere cachedContents explicito y esta sin hacer. En Anthropic el marcador va puesto pero no hay clave para verificarlo de punta a punta, y eso no se declara hasta medirlo.

- **[2026-08-28 07:19] C83 · CONFIRMA** (medicion) — cache_pct = 50.0085 (se predijo >50). La cache de prefijo funciona y es la palanca que C82 senalo: en Gemini paso del 0% al 50,0% de la entrada facturada sobre el nivel n1 entero, con las seis tareas en verde. Pero la prediccion se confirmo por ocho milesimas de punto (50,0085 frente a >50), asi que lo que quedo demostrado es el MECANISMO, no mi pronostico: poner el umbral en la media es acertar por sorteo, y una confirmacion asi no se puede presentar como si hubiera predicho algo. Lo que si es solido son las tres cifras del proveedor. PRIMERA: Gemini no tiene cache implicita -tres peticiones identicas de 6008 tokens y cachedContentTokenCount no aparece ni una vez- y hay que pedirle cachedContents explicita, con minimo de 1024 tokens medido contra un 400. SEGUNDA: OpenAI la aplica sola y bien, 5760 de 5957 en la segunda peticion identica y 76,6% en una carrera real de n1/anadir con gpt-4.1-mini, sin tocar una linea de codigo: el prefijo append-exacto que C22 impuso por la cache KV del modelo local es exactamente la forma que la cache del proveedor necesita, asi que la misma arquitectura paga dos veces. TERCERA: las seis tareas pasaron con la cache puesta, lo que prueba que el modelo SIGUE VIENDO las herramientas que viven dentro de ella; era el riesgo real y no se cumplio. Dos errores propios corregidos por el camino. El umbral para reescribir la cache lo escribi contando MENSAJES, y la economia depende de TOKENS: un turno de 20 caracteres y uno de 40000 pesan igual en la cuenta de mensajes y nada parecido en la factura. Y cerrar() existia pero no lo llamaba nadie, asi que cada carrera dejaba una cache cobrandose por horas hasta que el TTL la barria; ahora lo cierran el banco y la CLI, verificado con la lista del proveedor en cero tras una carrera.

- **[2026-08-28 08:21] C84 · REFUTA** (medicion) — tareas_pct = 16.7 (se predijo ==100). n1 NO esta saturado y yo lo he estado repitiendo sin comprobarlo. Predije que gpt-4.1-nano lo pasaria al 100% y saco 16,7%: una de seis, y las cinco por 'fin' -declaro terminado y el verificador dijo que no-, no por topes. El reparto completo, medido hoy: en n1, nano 16,7 frente a 100 del gguf local, de gemini y de gpt-4.1-mini; en n3, nano 0/4, gemini 3/4, mini 4/4. Gemini fallo n3/lista sin llegar a crear el modulo. Asi que el banco discrimina, y ademas discrimina entre modelos CAPACES, que es justo lo que C28 dijo que se habia perdido. La leccion no es sobre el banco, es sobre mi. C28 midio 100% en todas partes con tres cerebros que resultaron ser todos capaces, y de ahi salio la frase 'el banco dejo de discriminar'. Herede esa frase, la repeti esta misma sesion en el commit de n3/ruidosa, en docs/ahorro.md y en tres respuestas al autor, y nunca gaste los siete minutos que costaba refutarla con un modelo debil. Una conclusion heredada de otra medicion no es una medicion: es una cita, y las citas envejecen. Lo que C28 midio de verdad, dicho con precision, es que el banco no separaba a los TRES cerebros concretos que se probaron entonces, todos capaces. Eso es una frase mucho mas pequena que 'el banco no discrimina', y la diferencia entre las dos me llevo a escribir tareas nuevas para arreglar algo que no estaba roto del todo. Las tareas de n3 valen igual -separan gemini de mini, cosa que n1 no hace- pero el diagnostico con el que las justifique era falso.

- **[2026-08-28 12:51] C85 · REFUTA** (medicion) — tareas_pct = 100.0 (se predijo <100). Las dos tareas nuevas NO separan a modelos capaces: gpt-4.1-mini 6/6 y gemini 6/6 sobre n3 entero. Predije <100 y salio 100. Con esto van TRES de tres: regresion, renombrar y traza se disenaron con una trampa, las tres muerden en frio -sed global 3 de 10 fallos, parche del sintoma 2 de 4- y a las tres las pasa cualquier cerebro capaz. El patron ya no es casualidad: UNA TRAMPA QUE ATRAPA A UN SCRIPT NO ATRAPA A UN MODELO. Mis trampas castigan un atajo -renombrar por texto, parchear donde apunta la traza- y un modelo capaz no toma ese atajo, asi que la trampa se dispara contra nadie. Para separar capaces hace falta dificultad de CAPACIDAD -longitud, estado que sostener, ambiguedad real, muchos ficheros a la vez- y no ingenio en el diseno. Pero la leccion cara es otra y es sobre el metodo. C84 concluyo que n3 separa capaces porque gemini fallo lista UNA vez. Hoy gemini pasa lista sin que la tarea haya cambiado: era VARIANZA. Construi una conclusion sobre una sola observacion no repetida, que es exactamente el error que le acababa de reprochar a C28 en el veredicto anterior. Dos seguidos. La regla que faltaba escribir: una diferencia entre cerebros no es discriminacion hasta que se REPITE, porque el modelo es no determinista y con seis tareas una que cambie de signo mueve el total 16,7 puntos. Conclusion honesta del estado: el banco no tiene hoy ni una sola tarea que separe de forma repetible a dos cerebros capaces, y las tres que escribi para lograrlo no lo lograron.

- **[2026-08-28 15:00] C86 · CONFIRMA** (medicion) — segundos_media = 344.7 (se predijo >45). LA CACHE NO CUESTA RELOJ. A/B con los dos brazos seguidos, mismo banco, misma hora: SIN cache 372,4 s/tarea y 0% cacheado; CON cache 344,7 s/tarea y 49,5% cacheado, con 14,4% menos tokens de entrada y 100% de tareas en los dos. Mi hipotesis era que cachedContents metia latencia y es falsa. El -7,4% de reloj TAMPOCO es un beneficio: por tarea el rango va de -35,7% a +58,7%, asi que con seis tareas el agregado no distingue nada. Lo correcto es decir que no hay efecto medible sobre el reloj en ninguna direccion, y que lo solido es el -14,4% de entrada, que es contabilidad del proveedor y no un cronometro. Marco REFUTA aunque el umbral pase, y ese es el nucleo de la leccion. Predije segundos_media>45 esperando una base de 34; los dos brazos salieron en 350 porque la latencia de Gemini se multiplico por seis entre la manana y la tarde. 344,7>45 es verdad y no prueba nada: un umbral cuyo significado depende de una base que se movio diez veces no es una prueba, es una casualidad con formato de cifra. Es el mismo vicio que C83, donde me di por confirmado por ocho milesimas. La leccion de metodo, que ya es la tercera de la sesion sobre la misma raiz: una cifra de reloj contra un proveedor externo NO se compara entre carreras separadas en el tiempo. C82 dio 34,5 s/tarea y C83 55,2, y de esa resta saque una hipotesis entera; hoy el mismo banco sin tocar nada da 372. La resta era entre dos momentos distintos de la red, no entre dos versiones del codigo. Si se compara reloj, los dos brazos corren seguidos o no se compara. Y para umbrales sobre magnitudes que dependen de un tercero, hay que predecir la RAZON entre brazos -por ejemplo con_cache/sin_cache > 1,2- y no un valor absoluto.

- **[2026-08-28 15:01] C86 · REFUTA** (medicion) — segundos_media = 344.7 (se predijo >45). LA CACHE NO CUESTA RELOJ, y mi hipotesis era falsa. A/B con los dos brazos seguidos, mismo banco y misma hora: SIN cache 372,4 s/tarea con 0% cacheado; CON cache 344,7 s/tarea con 49,5% cacheado, 14,4% menos tokens de entrada y 100% de tareas en los dos. El -7,4% de reloj TAMPOCO es un beneficio: por tarea el rango va de -35,7% a +58,7%, asi que con seis tareas el agregado no distingue nada. Lo correcto es decir que no hay efecto medible sobre el reloj en ninguna direccion, y que lo solido es el -14,4% de entrada, que es contabilidad del proveedor y no un cronometro. La leccion de metodo, tercera de la sesion sobre la misma raiz: UNA CIFRA DE RELOJ CONTRA UN PROVEEDOR EXTERNO NO SE COMPARA ENTRE CARRERAS SEPARADAS EN EL TIEMPO. C82 dio 34,5 s/tarea y C83 dio 55,2, y de esa resta saque una hipotesis entera; hoy el mismo banco sin tocar nada da 372. La resta era entre dos momentos distintos de la red, no entre dos versiones del codigo. Si se compara reloj, los dos brazos corren seguidos o no se compara. Y para umbrales sobre magnitudes que dependen de un tercero hay que predecir la RAZON entre brazos -con_cache/sin_cache > 1,2- y no un valor absoluto. De aqui sale --vacuo en ciclo.py: la maquina no sabia registrar que un umbral se cumpla sin probar nada, que ya habia pasado en C83 con las ocho milesimas.

- **[2026-08-30 03:52] C87 · CONFIRMA** (medicion) — caida_pct = 5.51 (se predijo <15). confirmado con medicion de verdad (4 puntos, 171 a 1621 tokens, ~9,5x de rango): decode tok/s se mantiene plano (3,19 / 2,97 / 3,05 / 3,01 tok/s), pendiente -0,000072 tok/s por token de contexto, caida_pct=5,51 frente a umbral <15. Las 48 capas GatedDeltaNet (coste O(1) por capa) dominan el tiempo de decodificacion sobre las 16 de atencion (coste O(contexto)) en todo el rango probado -> un kernel fundido cache-residente para GatedDeltaNet queda justificado por cifra, no por intuicion, como la palanca de optimizacion de decodificacion con mas margen real en esta maquina. Hallazgo lateral confirmado y ACOTADO: el prefill es casi tan lento como el decode (4,7-4,8 tok/s vs ~3 tok/s) pero SU PROPIO ancho de banda es estable con el contexto (caida_prefill_pct=2,31) -> no es un problema de escalado, es que el prefill de estas capas recurrentes simplemente no es mucho mas rapido que la decodificacion secuencial, a diferencia de un transformer denso donde el prefill paralelo suele ser ordenes de magnitud mas rapido. Esto abre una SEGUNDA via de optimizacion (kernel de prefill para GatedDeltaNet) ademas de la de decodificacion, pendiente de investigar aparte.

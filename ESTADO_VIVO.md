---
name: mekro-genai-estado-vivo
description: "ESTADO VIVO — qué corre ahora, qué sigue y dónde está todo; leer PRIMERO al retomar Mekro-Genai"
metadata:
  node_type: memory
  type: project
---

**Actualizado: 2026-08-27 (noche-2) · 🚀 EL GGUF ES EL CEREBRO OFICIAL (decisión del
autor) Y EL PROYECTO SALE A GITHUB.** `Qwen3.8-27B-UD-Q2_K_XL` deja de ser «de trabajo»:
es EL cerebro (META §cerebro oficial). M1/H1 RETIRADOS — cuantizar en casa no compite
con los proyectos dedicados; la vía queda en E:\QuantModels por si vuelve. H8 retirado
con la vía densa. Publicación: repo público `stiven-skyward/mekro-genai` con licencia
Apache-2.0 y aviso de la licencia del modelo Qwen (los pesos NO se distribuyen).

**Antes (noche): ⏹ M3: MAPA CERRADO EN OCHO MEDICIONES — maquinaria
completa, mejora inalcanzable con este cerebro.** C73-C80 falsaron todas las vías de
mandos: topes rompen antes de mejorar (C73 revertida por el vigilante, C77 0 %),
contexto comprime por azar (1.365 vs 2.069 misma config, ±35 %), sin-think ahorra 59 %
pero mata el criterio (C79: 202 tok, 0 %), think selectivo conserva el criterio sin
ahorrar (C80: 544 ≥ 493). **La simetría final: el gasto y el criterio viven en el mismo
sitio** — el razonamiento del diagnóstico es a la vez la fracción dominante de tokens y
la fuente de la corrección. La palanca de M3 es M1. Lo construido queda listo:
adopción (4 reglas), reversión probada en producción, vigilante, mandos activos.
Supervisor PARADO a propósito (el espacio de mejoras está agotado; relanzar cuando M1
exista: quitar `logs/supervisor.parar` no hace falta — basta relanzar supervisor.py).
**Los pendientes del proyecto quedan en uno solo: M1 — empaquetar el campeón (H1).**

**Antes (tarde-2): la puerta de M3 abierta, mecanismo vivo.** `scripts/adopcion.py` con CUATRO reglas de honestidad
ganadas a golpe de medición en un solo día: solo tokens_media (los segundos son la
máquina), solo mandos distintos de la base, solo topes que MUERDEN el uso base
(compresión causal, C37/C38), y solo victorias que terminaron DENTRO de su presupuesto
(C73: adoptar el rebase de C40 fue fatal — el vigilante REVIRTIÓ solo, en producción,
con historial). Reversión automática si una carrera adoptada falla; `--adoptados` en
correr_banco aplica lo vigente; el lazo adopta tras cada veredicto y su proponente sabe
que sus mejoras se vuelven el defecto (exención de mejora en los guardias). **No hay
victoria robusta en los archivos: el lazo relanzado debe DESCUBRIRLA — eso es la letra
de M3. Cuando adopte y la carrera oficial confirme, M3 se declara.** El arco C73
(adopción frágil→fallo→reversión→regla) quedó entero en registros.

**Antes (tarde): ✅ M5 LOGRADO — LAS CINCO BRECHAS CUBIERTAS.**
**(1)** Renacimiento holográfico medido en C72: la tarea que desbordaba muere→renace
(13.026 caracteres resumidos)→completa al 100 %; el desbordamiento se peló en TRES capas
(fracción→sobrecarga absoluta→JSON de llamadas→think crudo de la caché viva) y la regla
quedó en CONTINUIDAD: *el guardián del contexto mira LA CACHÉ, no la transcripción*
(`tokens_en_contexto`/`olvidar` en el cerebro, conteo exacto en el bucle). **(2)**
`genai tarea --continuar` con ida-y-vuelta idempotente. **(3)** `fondo_lanzar`/`revisar`
+ aviso del bucle, con permisos parejos a bash (`ejecuta_shell` en el contrato de
herramienta). **(4)** plugins por fichero con contrato en `docs/plugins.md`; web sigue
vetada por «sin nube». **(5)** streaming real (33 deltas en humo gguf, primero al acabar
el prefill), Ctrl-C que conserva lo generado con motivo «interrumpido», y plan
proponer→aprobar→ejecutar en la misma sesión. 205 asertos en verde. **Pendientes del
proyecto: M1 (el campeón, H1) y M3 (falta la vuelta que MEJORE una cifra — el mecanismo
de adopción es decisión del autor).**

**Antes (12:00): M5 en marcha:
cinco brechas frente a Claude Code, criterios en META.** **Brecha 1 implementada y en
medición**: `sesion.renacer()` — la transcripción renace como contexto pequeño (sistema
+ petición + resumen mecánico con constancia de llamadas y ficheros + últimas vueltas)
cuando la presión pasa de 0,8; sustituye a `compactar()` en el bucle (C20: reescribir
por el medio = frío del contexto grande; renacer = frío del chico). 36/36 asertos en
frío, incluida ventana enana que antes moría y ahora termina. **C71 midiendo** la tarea
de resistencia `n3/larga` (10 módulos, contexto acumulado ~17-20K > 16.384): predicho
`tareas_pct ==100` CON al menos un renacimiento en la traza. Pendientes: brecha 2
(`genai tarea --continuar`), 3 (bash desasido con aviso), 4 (contrato de plugins; web
VETADA por «sin nube»), 5 (streaming + Ctrl-C limpio + plan conversacional). El lazo
del banco sigue parado a propósito (`logs/supervisor.parar`): el motor de M5 es el bucle
de sesión de supervisión con sus monitores.

**Antes (05:40): ⏹ BARRIDO COMPLETADO Y SUPERVISOR PARADO A PROPÓSITO
(`logs/supervisor.parar`).** **El banco entero está cartografiado con el cerebro real:
17 tareas × 2 métricas, NADA sin medir.** La cosecha del modo autónomo: **38 ciclos
autónomos cerrados (C32-C70, salvo el C49 manual de recalibración)** en ~36 horas, con
40 confirmaciones y 28 refutaciones en el total del proyecto (68 cerrados), racha máxima
4 (parada y revisada), 3 revisiones de gobernanza aplicadas (líneas base, menú de lo
virgen, códigos de salida) y ni una sola corrupción de registro. **Lo que sigue es
DECISIÓN DEL AUTOR, ya anotada abajo: (a) mecanismo de adopción para cerrar M3 —que la
vuelta ganadora cambie el mando por defecto—, (b) tareas nuevas del banco (n2/n3
difíciles, n4), o (c) descanso. Para rearrancar el lazo tras decidir: borrar
`logs/supervisor.parar` y relanzar `scripts/supervisor.py` (ESTADO_VIVO §sesión 10).**

**[Nota 2026-08-27 00:30] FINAL PREVISTO DEL BARRIDO**: quedan ~9 combinaciones
tarea×métrica sin medir; cuando se agoten (~madrugada del 27), el proponente no tendrá
propuesta válida posible, fallará 2 vueltas y el supervisor parará pidiendo revisión.
**Ese paro será CARTOGRAFÍA COMPLETADA, no avería**: el banco entero quedará medido en
ambas métricas con cerebro real. La revisión que sigue es la decisión del autor ya
anotada abajo: mecanismo de adopción (M3), tareas nuevas del banco, o descanso.

**Actualizado: 2026-08-26 13:20 · ▶▶ PRIMER CICLO COMPLETO DE GOBERNANZA: el vigilante
paró, la revisión arregló, la recalibración rompió la racha, el lazo rearrancó.** La
racha C45-C48 (4 refutaciones = UN sesgo repetido: predecir segundos ignorando líneas
base — tres <800 con 922,8 medidos, aguja <900 con 2.290) disparó el alto del vigilante
a las 12:49 y el supervisor se apagó solo, como está diseñado. La revisión (como
revisor delegado del autor): tabla de LÍNEAS BASE por tarea en el contexto del proponente
(«ancla umbrales con 15-30 % de margen»), y **C49 de recalibración** anclado en la base
de anadir (<700 con 493 medidos) → **CONFIRMA con 493,0 EXACTOS** (el guion determinista
repitió al token por tercera carrera) → racha 0 → supervisor arriba 13:17. Doctrina
codificada en la lección de C49: **de una racha se sale con una predicción anclada que
confirma, no tocando el umbral del vigilante**. También hoy: bug de códigos de salida
del lazo (SystemExit(cadena)→1 se confundía con freno; ahora 2), lista de lo-ya-medido
en el contexto, y 16 vueltas autónomas acumuladas (C34-C48) + C49 manual.

**Antes (07:30): M4 declarado —
10 vueltas autónomas encadenadas, C34-C43.** El lazo pasó la noche haciendo ciencia
solo: cartografió la curva presupuesto-respuesta de n3/lista (3.000 y 2.500 → 1.933
tokens; 1.800 → cumple comprimiendo; 1.600 → comprime y completa; 1.500 → corta y
falla), y al cerrársele el surco (doble guardia mecánica + tope de exploración en
`lazo.validar`) saltó a n2/aguja (100 % en 7 vueltas; el reloj lo manda la latencia, no
las vueltas — 2.290 s) y n2/cupones (957 tokens frente a <800: REFUTA con dato). Racha
máxima de la noche: 1. Frenos: ninguno saltó. La salvedad de M4(c): el banco con GGUF
está verde en registros PRE-instalación (C23-C30); tras instalar solo se re-verificó
con eco. **El supervisor sigue encadenando (M3 sigue vivo: falta que una vuelta MEJORE
una cifra del banco, no solo la mida).** **DECISIÓN PENDIENTE DEL AUTOR para M3**: hoy
el lazo mide pero no adopta — cuando una vuelta confirma que un tope más apretado
mantiene el 100 % con menos tokens/segundos, nadie cambia el defecto. El paso que
cerraría M3 es un mecanismo de ADOPCIÓN (la vuelta ganadora actualiza el mando por
defecto de la carrera siguiente, con su registro), y eso es auto-modificación del
arnés: el vigilante y el veto están para eso, pero la puerta la abre el autor, no
el revisor ni el lazo por su cuenta.

**Antes (03:25): 5 vueltas encadenadas.** Cosecha nocturna: C34 CONFIRMA (tokens<2000: 1.933), C35
CONFIRMA (segundos<2500: 1.352), C36 CONFIRMA (intervenciones<10: 0), C37 **REFUTA con
información** (tokens<1600 con tope 2500: 1.933 — el presupuesto no comprime la salida
hasta que corta) y C38 en vuelo siguiendo la propia lección de C37 (tope 1.500). El
proponente cayó en el surco de confirmaciones fáciles sobre la misma carrera y se le
puso doble guardia MECÁNICA en `lazo.validar`: métrica repetida sobre carrera medida se
rechaza citando el ciclo, y a los DOS ciclos por combinación de mandos el surco se
cierra («cambia nivel, tarea o topes») — funcionó: el reintento varió el mando y
predijo con riesgo. **M4: (a)✓ rueda 0.1.0 + setup.cfg para setuptools viejos; (b)✓
venv limpio → `pip install -e .` → `genai version`/`tarea` tal cual el README; (c)✓ en
frío: banco 16/16 con eco bajo el venv (registros m4c-venv-*); (e)✓ modelo ausente con
mensaje accionable; (d) 5/10 vueltas encadenadas.** Racha 1 (C37). RAM 21 GB libre,
disco 156 GB.

**Antes (sesión 10): arranque del modo autónomo.** El **supervisor encadenador** (`scripts/supervisor.py`, pid en
`logs/supervisor.pid`, log `logs/supervisor.log`) lanza una vuelta del lazo en cuanto
acaba la anterior, con frenos: parada humana (`touch logs/supervisor.parar`), vigilante
(racha ≥4), 2 vueltas sin propuesta válida, disco <10 GB, y nunca duplica un lazo vivo.
**META gana M4 (producto profesional, pedido del autor) con criterios medibles y M3 pasa
a «en marcha»**. La sesión de supervisión también quedó en bucle: se despierta sola, revisa
`supervisor.log` y las lecciones nuevas, repara lo que se atasque y avanza M4. **Para
pararlo todo**: `touch logs/supervisor.parar` (supervisor), matar el pid del lazo si
hiciera falta, y en la terminal de supervisión, parar su bucle.

**Antes (sesión 9): ▶ el lazo corre su segunda vuelta** (pid en
`logs/lazo-sexta.pid`, log `logs/lazo-sexta.log`): **C33 · «¿baja tope_vueltas 16→8 los
segundos_media de n3/lista sin romper la tarea?»** — propuesta A LA PRIMERA por el
proponente arreglado, dentro de sus mandos reales; el veredicto y la lección los dejará
el lazo. **La vuelta 1 (C32) cerró REFUTADA (1.933 vs <1900) y enseñó tres defectos, los
tres arreglados y con aserto o nota**: (1) la lección salió contaminada con un <think>
sin cerrar → el redactor sanea y cae a aviso (nota a mano en CONTINUIDAD, la entrada no
se borra); (2) el proponente deliberaba sin límite —2×2.048 tokens de think sin JSON; y
con `pensar=False` (prellenado `<think></think>` de fábrica de Qwen3, ahora en
`plantilla.montar`/`CerebroGGUF.generar`) la deliberación SE MUDÓ al campo `revision`
del JSON— → campos acotados a 400/700 con rechazo mecánico en `validar()`; (3) el
contexto del proponente eran lecciones truncadas a 500 caracteres que le comían el dato
clave (el «tope 1.500» de C31: el modelo no podía cuadrar el fallo) → ahora recibe
FICHAS con cifras exactas (predicho, medido, comando con topes). Además: volcado de
intentos fallidos a `logs/lazo-intento-*.txt` (sin eso no había post-mortem) e higiene
(lecciones con <think> no se le dan de comer). Del número de C32 quedó el SUELO DE RUIDO:
~9 % de deriva en tokens_media entre carreras idénticas — umbrales a <10 % son apuestas.

**Antes (sesión 8): ▶ el lazo corrió su primera vuelta** (`scripts/lazo.py`, pid en
`logs/lazo-segunda.pid`, log `logs/lazo-segunda.log`). **H6 completo en su primera
versión: el proponente existe y PROPUSO.** La primera vuelta real abrió **C32** —
«¿Reduce `foco` los tokens de n3/lista bajo el baseline de 2.118 de C30?», predicho
`tokens_media <1900` con aritmética y citando C30/C31/horizonte§2 — y su medición corre;
el veredicto y la lección los escribirá el lazo al terminar. **Costura detectada a
revisar en la lección de C32**: el espacio de ACCIÓN del proponente (mandos de
`correr_banco`) es más estrecho que su espacio de HIPÓTESIS (mecanismos como `foco` que
ninguna bandera activa) — la carrera lanzada NO activa foco, así que lo probable es un
REFUTA honesto que lo diga. Siguiente iteración: o banderas nuevas (p. ej. `--foco`) o
constreñir las hipótesis a los mandos existentes. También de esta sesión: **mundo
reproducible** (mtimes fijos 2026-01-01 en la copia de semilla, caja anidada para que el
`..` también sea nuestro, workdir → «.» en las observaciones de bash — C31), primer
intento del proponente ABORTADO limpio por los frenos (think de 1.024 sin JSON → código
2, ningún ciclo abierto; arreglado con turno de 2.048 y contexto más corto), y
`MG_REGISTROS` para que las pruebas frías no siembren humo. `tests/test_lazo.py`: 12
asertos (validación hostil, plantilla fija de comando, vuelta fría entera, frenos).

**Antes (2026-08-25, sesión 7):** **H6 ARRANCADO: construidas y
probadas dos de sus tres piezas.** El **veto** (`permisos.py` `vedadas`: `banco/` de solo
lectura para el agente en TODO modo — editar/escribir denegados, bash mutante denegado,
leer sí; 5 asertos) y el **vigilante** (`ciclo.py racha [umbral]`: N ciclos cerrados
seguidos sin confirmar, código 1 al umbral para que el lazo pare y pida revisión; 3
asertos). Falta el **proponente** (el cerebro propone la hipótesis siguiente desde
`docs/horizonte.md` + registros). **C31 cerró la hebra del presupuesto**: mínimo de
n3/lista en (1.500, 2.118] — con tope 1.500 falla por `tope_tokens` con solo `lista.py`
escrito; tope operativo n3: 3.000. Y dejó una refutación de regalo: **el «token por
token» de C30 era demasiado fuerte** — la vuelta 3 divergió porque el `ls -la` mete
ruido por carrera (nombre del tmpdir, fechas) y el greedy es caótico ante eso.
**Consecuencia de método para H6: el comparador del lazo necesita observaciones
NORMALIZADAS (workdir → «.», sin fechas) — cambio chico en herramientas, compra
reproducibilidad de verdad. Siguiente: normalizar observaciones, y el proponente de H6.**

**Antes (2026-08-25, sesión 6):** **C29 encontró EL BORDE y C30 lo
cruzó: el arnés construye un proyecto ENTERO desde un encargo en prosa.** `banco/n3/lista`
(semilla = solo la prueba; módulo + CLI + persistencia que cruza procesos, tope 3.000
tokens del §muro): **C29 REFUTADO** — el think de diseño (en inglés, primera vez) gastó
los 1.024 del turno sin emitir llamada y el bucle lo daba por «fin» a medio pensar (1.215
de 3.000). El arreglo, en `bucle.py` (+3 asertos): turno cortado sin llamadas → se pide
continuar; el reintento es barato porque el think ya está en caché (C22). **C30
CONFIRMADO**: a temperatura 0 el modelo repitió C29 token por token, la rama nueva saltó
donde C29 murió, y cerró 6/6 con 2.118 de 3.000 y 0 intervenciones — **el par C29/C30 es
el patrón de oro: mismo guion, un cambio, resultado invertido**. Hebras baratas vivas: el
presupuesto mínimo de un n3 está entre 1.215 y 2.118 (una carrera lo acota); el think de
diseño salió en inglés 2 veces — ¿es más denso por token? (una carrera y un contador).
**Siguiente: más n3 (segundo proyecto distinto), la sonda del presupuesto mínimo, o
arrancar H6 — el banco ya tiene 17 tareas, 4 niveles y su primer fallo reproducible.**

**Antes (2026-08-25, sesión 5):** **C28 REFUTADO — la refutación
que más informa: el banco buscó el borde del cerebro y NO lo encontró. 16/16 histórico,
0 intervenciones.** Tres tareas n2 apuntadas a ejes vírgenes, las tres superadas: `aguja`
(fichero de 16.922 caracteres, bug pasado el truncado de 12.000 — notó el truncado y fue
con grep, pero leer entero primero costó 1.356,6 s de vuelta: **la puerta 1 tiene precio
medido, ~1.400 s**), `tres` (tres bugs revelados de uno en uno — los consolidó en UN
editar), `version` (idempotencia: el bug solo existe en la segunda ejecución — lo razonó
en un turno de 938 tokens). El borde NO está en: lógica local, contratos en pruebas,
navegación de paquetes, razonamiento de segunda ejecución. **Siguiente, por fidelidad a
la meta: (1) n3 = crear un proyecto ENTERO desde un encargo en prosa; (2) presupuesto
apretado de verdad (tope_tokens 2-3K, META §muro); (3) si n3 tampoco encuentra borde, el
gradiente de M3/H6 está en el RELOJ (tokens/segundos por tarea), no en la tasa de
acierto.**

**Antes (2026-08-25, sesión 4):** **M2 DECLARADO EN META.md** (6/6
de n1, 0 intervenciones, registro `2026-08-25_1345_n1x6-gguf.json`) **y tres ciclos más
cerrados**: **C26** midió que doblar la ventana cuesta 0,5 GB (512 MiB de KV por 8k +
149,6 MiB fijos de estado recurrente — el motor imprime `llama_memory_recurrent`:
confirmación directa de la arquitectura híbrida que C20 dedujo; `n_ctx_train`=262.144)
→ `contexto_max` = 16.384 en `local_gguf.py`. **C27**: nace `banco/n2/` con `cupones`
(crear un módulo que la prueba importa + integrarlo cruzando 4 ficheros) y el cerebro lo
pasa a la primera: 5 vueltas, 1.199,2 s, el `escribir` multi-línea limpio en un turno de
620 tokens. **Marcador histórico: 12/12 con 0 intervenciones en tres niveles.** El aviso
de la lección de C27: el banco aún no ha encontrado el BORDE del cerebro — y M3 necesita
un banco donde la puntuación pueda SUBIR. **Siguiente: buscar el fallo reproducible
(tareas n2 duras: estado entre ejecuciones, ficheros que no caben de una lectura,
presupuesto apretado) — o arrancar H6 con el banco actual como suelo.**

**Antes (2026-08-25, sesión 3): C25 CONFIRMADO: el banco
COMPLETO queda en 11/11 con el cerebro real.** n1 engordado a 6 tareas con las tres que
C24 no medía —`cadena` (dos ediciones coordinadas: buscó los llamadores con grep antes
de editar), `fuga` (bug de CLASE: el modelo diagnosticó el argumento mutable por defecto
con explicación de libro), `bitacora` (eligió la capa del arreglo tras leer las dos)— y
las tres viejas repitieron casi calcadas: el banco es estable a temperatura 0.
`max_tokens` 512→1024 en `bucle.py` validado en el punto exacto (rojo v3: 578 tokens con
la llamada completa; en C24 truncó a 512): **0 malformadas en 27 vueltas, 0
intervenciones — H5 pierde urgencia.** Reloj: media 1.020,8 s con máquina a ×1,33
(control humo: 726,1 vs 544,3 de C22) → ~765 s/tarea corregida. **M2 (≥50 % del banco)
superado con margen; declararlo es decisión de META.md. La siguiente subida honesta es
n2 (multi-fichero con estado): ahí apretará la ventana de 8.192 (factura de C22).**

**Antes (2026-08-25, sesión 2): H3 CERRADO y C24 CONFIRMADO:
el banco n1 existe y el cerebro real lo pasa ENTERO — 3/3 en su primera carrera.**
`banco/n1/` = rojo (fallo con prueba en rojo y contrato en prosa), anadir (el contrato
son tres ValueError que solo están en la prueba), migrar (el TypeError apunta a la
biblioteca intocable — `verificar_intacto` la vigila). eco lo pasa 3/3 con
`--exigir-todo` (cierre de H3). Con el GGUF: rojo 6 vueltas/1.188 s, anadir 4/969,
migrar 3/845 esquivando la trampa con grep. `segundos_media` 1.000,8 con la máquina a
×1,95 (control humo del día: 1.058,8 vs 544,3 de C22) → ~515 s/tarea corregida: n1
cuesta lo que humo. **0 intervenciones: los arreglos de C23 (prompt python3/sin-cd +
`python3 -c` en la lista blanca) funcionaron.** Lo nuevo medido, munición para H5: 2
llamadas malformadas en 13 vueltas (saltos de línea crudos en el JSON; truncada por
max_tokens=512 en mitad del tool_call), ~1 vuelta perdida cada una, cero adivinadas.
M2 (≥50 % del banco) queda superado en su primera medición: falta engordar n1 hasta que
deje de ser fácil. **Siguiente: más n1 difícil, o H5/max_tokens para las malformadas.**

**Antes (2026-08-25, sesión 1): C23 CONFIRMADO — el banco n0 ENTERO pasa
con el cerebro real — 5/5 tareas** (atomo 7 vueltas/1.340 s con los TRES cambios en UNA
llamada; crear 5/570 escribiendo `pila.py` desde cero; humo 5/1.125; rastro 6/1.270 con
find→grep→editar; simbolo 12/1.650 eligiendo `simbolos` a la primera). `segundos_media`
1.191 con la máquina a ×2,07 de C22 —lo mide el control interno: humo repitió su guion
exacto al doble de reloj—; corregida, ~575 s/tarea. Despilfarro medido y del ARNÉS, no
del modelo: python-vs-python3 quema una vuelta por tarea y la lista blanca rechazó
`python3 -c` y `cd` (4 intervenciones, ~600 s). Arreglo barato antes de n1: una línea en
el prompt de sistema. **M0 con cerebro real demostrado; lo siguiente es H3 (banco n1).**

**Antes (mismo día): C22 CONFIRMADO — humo con el
cerebro GGUF baja de 3.359,5 s (C20) a 544,3 s** —×6,2— con 3/3 asertos, 0 intervenciones
y 5 vueltas (133,6 / 19,2 / 18,4 / 36,8 s las incrementales). La palanca es el **contexto
append-exacto** en `local_gguf.py`: C20 refutó (3.359,5 s vs <1.500) y diagnosticó que
esta caché no admite borrado parcial (`kv_cache_seq_rm` → false, atención híbrida), así
que la transcripción solo puede CRECER POR EL FINAL: el think crudo se queda en la caché
viva, el turno del asistente no se re-plantilla, y cualquier reescritura por el medio
(`compactar()` incluida) degrada a arranque en frío —lento, jamás corrupto; lo vigilan
las huellas y 13 asertos en `tests/test_local_gguf.py`—. De paso cayeron dos gazapos
medidos: `tokenize(special=False)` metía `<|im_start|>` como texto literal (17 tokens
donde van 7; ahora `special=True` siempre) y `presion()` subestimaba ×2,1 (tokenizaba
`'x'*N`; ahora tokeniza el contenido real). `correr_banco.py` gana `--tarea`. Ojo
metrológico: la máquina varía hasta ×1,35 entre días — no comparar carreras en crudo.
Confundidor anotado en la lección de C22: special=True y ver el propio think acortan el
guion (400 tok de salida vs 888), así que los 544,3 s mezclan palanca y guion más corto.

**Histórico (2026-08-23, sesión 2):** Once ciclos cerrados y C14 en curso.
**C13 refutó** (0,12275 vs <0,10): con `β` recuperada el ajuste RVQ baja a **0,123** frente
a **0,399** del control —factor 3,25 bajo el suelo del azar, el retículo se nota— pero **no
lo separa**, y H1 necesita cero, no 0,05. El k-means converge a un RVQ válido pero distinto
del original. Se cambia el algoritmo, no la hipótesis. La sesión
zanjó la vía densa: C4, C7 y C9 midieron la tasa de aceptación con tres borradores que no
se parecen en nada y los tres dan α ≈ 0,54-0,57 → **0,33 tok/s como techo**, frente a los
0,821 de α que exige D2. **D2 y D3 se declaran inalcanzables por esta vía en esta
máquina** (META.md, criterios intactos). El camino crítico vuelve entero a H1. Y C8 midió
que el campeón a 2 bits **sí sabe emitir llamadas Hermes bien formadas**: su problema es
de criterio, no de forma. Y **C10/C11 revierten C1**: el retículo RVQ sigue intacto en los
pesos deshechos y su libro se ha recuperado contando duplicados (15,73 M ≈ 4096²), luego
**H1 cuesta horas de CPU, no 24,3 de GPU**.**

Documento de continuidad: si la sesión se cae, esto permite retomar sin reconstruir nada.
Se **sobrescribe** en cada hito. El histórico y las lecciones viven en
[CONTINUIDAD.md](CONTINUIDAD.md), que no se borra nunca.

## ⏳ ESTADO: el andamiaje está vivo y probado; el cerebro, no

| | |
|---|---|
| arnés (`genai/`) | ✅ **bucle completo funcionando**: plan→herramienta→observación, 6 herramientas, permisos con veto duro, sesión con contabilidad. 101 asertos en verde en `tests/` |
| banco n0 (humo) | ✅ **1/1 con cerebro `eco`**, 0 intervenciones, 5 vueltas, 134 tokens — `registros/2026-08-23_0146_n0-eco.json` |
| holograma + ciclo | ✅ `holograma.py` (8 órdenes) y `ciclo.py` (las dos puertas), probados |
| **cerebro de trabajo** | ✅ **EXISTE Y CORRE**: `Qwen3.8-27B-UD-Q2_K_XL.gguf`, 9,15 GB, **2,876 tok/s** en CPU con 8 hilos, PPL 4,7124 código / 10,5831 español (+7,6 % / +11,1 % sobre BF16) en el corpus congelado `c6c95a4d`. Motor `llama-cpp-python 0.3.35` compilado con `GGML_CUDA=OFF`. **No es M1** (META.md §cerebro de trabajo) |
| corpus de medida | 🔒 **CONGELADO** en `registros/corpus-congelado.json`, huella `c6c95a4d`. Antes era el repositorio vivo y cambiaba entre medidas: las PPL de días distintos NO eran comparables |
| cerebro local (vía cuantizada) | ❌ **NO EXISTE**, pero el camino está despejado: el retículo sobrevive (C10/C11) y la salida (a) es viable en CPU. Es H1 |
| cerebro local (vía densa) | 🟡 modelo BF16 **ya en ext4** (52 GB, verificado). Falta el lector (H7). **H8 queda bloqueado por C7**: con el borrador previsto el techo es 0,40 tok/s |
| copias en ext4 | ✅ **verificadas**. BF16 sano (PPL 5,76/4,84). El campeón tenía `capa-53` a **0 bytes** y `capa-62` truncada: reparadas y comprobado que dan el mismo dígito que el original en 9p |
| ciclos **C2**, **C3** | ✅ **CONFIRMAN**. `registros/ciclos/` |
| ciclos **C7**, **C9** | ✗ C7 refuta (0,8B da α 0,5401, peor que el campeón) · ✓ C9 confirma que **la curva α(tamaño) es plana**: ×35 en parámetros mueve α 0,029 |
| **la vía densa** | 🔴 **acotada por arriba y declarada**: mejor configuración medida = borrador Qwen3.5-0.8B, γ=4 → **0,328 tok/s**. Sirve como **patrón de oro**, no como cerebro |
| ciclo **C8** | ✗ **REFUTADO por el número, no por el mecanismo**: `acuerdo_estructura_campeon` 0,9318 (predicho ≥0,95) — pero el BF16 saca 0,9773 y comete el mismo error. **El andamiaje Hermes sobrevive a los 2 bits**; H5 no es condición de existencia de M1 |
| ciclo **C4** | ✗ **REFUTADO** en 33 min de CPU. Predicho antes: `tokens_por_pase_codigo >= 4.0`; medido **2,227**. α greedy 0,5631 (código) / 0,5230 (español). `registros/ciclos/C4.json` |
| ciclo **C12** | ✓ **CONFIRMA · `β_fila` recuperada, no estimada**: el *puente de duplicados* da el cociente exacto entre filas; el grafo conecta el **100 %** de las filas y el cierre de ciclos sale **0,0034-0,0040** en 5 matrices, contra **0,33-0,52** del control barajado |
| ciclos **C10**, **C11** | ✓ **CONFIRMAN y revierten C1**: normalizando cada grupo a norma unidad la incógnita `β_fila` desaparece; el campeón tiene direcciones duplicadas y el BF16 **ninguna** (0,000000 en 5 tamaños y 6 configuraciones). Libro estimado **15.734.481 = 0,938 × 4096²** |
| ciclo **C1** | ✗ **REFUTADO** en 69 s de CPU. Predicho antes: `frac_exacta >= 0.95`; medido **0,000325**. Registro: `registros/ciclos/C1.json` |
| M0 | ✅ **LOGRADO**: `banco/n0` tiene **5 tareas** —`humo`, `rastro`, `simbolo`, `crear`, `atomo`— y pasa **5/5 con `eco`**, 0 intervenciones. Cada una obliga a una herramienta distinta: `bash`+`editar`, `grep`, `simbolos`, `escribir`, `editar` multi-cambio |
| herramientas | ✅ **las 9 probadas una a una**: `tests/test_herramientas_todas.py`, 19 asertos. Incluye la atomicidad de `editar` y que `holos`/`foco`/`anotar` no ensucien el holograma real (ahora honran `MG_RAIZ`) |
| GPU | ⛔ vetada en este proyecto por decisión del autor. Todo en CPU |

## 🔬 LA VÍA DENSA: correr el Qwen3.8-27B **sin cuantizar**, y las cifras dicen que sale

Encargo del autor: una alternativa a cuantizar. Modelo BF16 intacto, CPU+RAM, sin GPU.
Diseño y cifras completas en [docs/densa-en-cpu.md](docs/densa-en-cpu.md).

**Tres hallazgos, los tres medidos hoy:**

1. **`/mnt/e` no es el disco, es un protocolo.** Montaje 9p con mensajes de 64 KB: 0,20
   GB/s. El mismo NVMe por ext4 nativo con O_DIRECT y 2-4 lectores: **6,77 GB/s. ×33 sin
   tocar un solo bit.** Un pase por los 52 GB pasa de 256 s a 8,2 s.
   → El modelo **ya está copiado** en `/home/forge/modelos/qwen3.8-27b` (52 GB, 18 shards).
2. **Verificar 8 tokens de golpe es gratis** (C2, sobre matrices reales de una capa
   deltanet y una de atención): lote 8 cuesta **0,879×** lo que lote 1; lote 16, 0,886×.
   La CPU se pasa el rato esperando memoria. → La palanca no es leer más rápido sino
   **sacar más tokens de cada pase**, y la única técnica que hace eso sin perder calidad es
   la **decodificación especulativa** (reproduce exactamente la distribución del grande).
3. **BF16 encoge ×1,4627 sin perder un bit** (C3, los 56 GB completos, 18/18 shards
   verificados): 56 GB → 38 GB separando planos de bytes. El plano alto solo comprime
   2,72×; la mantisa no comprime nada. **Pero solo paga si el lector solapa**: en serie da
   6,18 GB/s, *peor* que los 6,77 sin comprimir.

4. **El divisor ya no es una proyección: es 2,227** (C4, 2026-08-23, 4088 tokens por
   dominio, 33 min de CPU y cero GPU). El acuerdo greedy del campeón de 2 bits con el BF16
   es **0,5631 en código y 0,5230 en español**. Presupuesto real: 5,6 s ÷ 2,227 = **2,51
   s/token = 0,40 tok/s**, por debajo de la primera fila especulativa de la tabla (0,71).

**Y γ no es la palanca que faltaba.** El techo con γ infinito es 1/(1−α) = **2,289**, y con
γ=8 ya se saca el **97,3 %** de él (γ=16 da 2,274). Alargar el borrador no arregla nada; lo
único que sube tokens/pase es **subir α**, y para llegar a 1 tok/s hace falta α ≥ 0,821.
Además cae una intuición: las aceptaciones **no llegan a ráfagas** —el simulador sobre la
secuencia real de aciertos da 2,227 y la fórmula i.i.d. da 2,276—, así que el sangrado y los
cierres de bloque no regalan rachas.

**Por qué es tan bajo, medido**: sobre este dominio y en ventanas de 512, la PPL del campeón
es **15,967 (código) / 17,518 (español)** frente a **5,764 / 4,839** del BF16. El hueco real
es ×2,8-×3,6, no el ×1,43 que sugiere el par 7,46 / 5,21 del conjunto de evaluación de
QuantModels. **La PPL no predice el acuerdo de argmax.**

**Las dos vías NO encajaban como se creía.** El campeón de 2 bits no sirve de borrador: ni
por acuerdo (0,56) ni por coste —no es un modelo pequeño, es *el mismo* modelo de 27,8 G
parámetros, y proponer γ tokens exige γ pases por sus ~8 GB. El borrador tiene que ser un
modelo **pequeño de verdad** (Qwen3 0,6 B o 1,7 B, mismo tokenizador). Medir candidatos es
**C7** y el instrumento ya existe: `scripts/medir_aceptacion.py`, ~35 min por candidato.

## ✗ LO QUE DIJO EL CICLO C1 (y por qué no cierra la salida (a))

Sonda sobre `capa-30 mlp.up_proj`, 120.000 grupos, k=4096, **69 s en CPU**:
`razon_residuo 0,5431 · err_relativo 0,2480 · frac_exacta 0,000325`.

Con `α` estimada como RMS de fila el retículo no se recupera. **Pero el fallo es de la
sonda**: verificado después en `reconstruir_v12.py:36-45` que la reconstrucción por bloques
solo optimiza una **escala por fila** (`_EscalaFila`), luego el retículo `C1+C2` sigue
intacto salvo un factor multiplicativo por fila — y el RMS no es ese factor.

Y ojo con el otro número: `razon_residuo 0,543` **no es evidencia de estructura**. Para
vectores gaussianos de 16 dimensiones con 4096 códigos la cota da ≈0,60; lo medido está
donde estaría cualquier nube de datos.

**Ciclo C2, por abrir**: normalizar cada grupo a **norma unidad**. La dirección de `c1+c2`
es invariante a la escala de fila, así que la incógnita `α` desaparece. Precio: la
normalización rompe la aditividad y hay que replantear la etapa 2.

## 📍 DÓNDE ESTÁ TODO

| qué | dónde |
|---|---|
| la meta y cómo se mide | [META.md](META.md) |
| de dónde viene cada pieza del diseño | [docs/arquitectura.md](docs/arquitectura.md) |
| el problema del cerebro, con cifras | [docs/cerebro-2bit.md](docs/cerebro-2bit.md) |
| por qué el ciclo tiene dos puertas | [docs/ciclo-investigacion.md](docs/ciclo-investigacion.md) |
| ideas para después de M1 | [docs/horizonte.md](docs/horizonte.md) |
| las tareas vivas | `python3 holograma.py listar` |
| el campeón | `/mnt/e/QuantModels/modelos/qwen38-h13b` (51 GB por 9p, **no leer desde una sesión**) · copia en ext4 verificada en `/home/forge/modelos/qwen38-h13b` (50 GB) |
| el BF16 denso | `/home/forge/modelos/qwen3.8-27b` (52 GB en ext4, 18 shards, PPL 5,76/4,84 medida) |
| el medidor de aceptación | `scripts/medir_aceptacion.py` — cachea el pase del grande (`--cache`), así cada candidato a borrador cuesta solo el suyo |
| el puente de duplicados | `scripts/recuperar_escalas.py` — β por grafo de puentes + firma de signos, 12-16 s por matriz |
| la sonda de direcciones | `scripts/sondear_direcciones.py` — ley del cumpleaños sobre direcciones normalizadas |
| la sonda de llamada Hermes | `scripts/sondear_llamada.py` — captura los prompts reales del arnés y fuerza el oro de `banco/n0` |
| los borradores candidatos | `/home/forge/modelos/qwen3.5-0.8b` (1,7 GB) y `qwen3.5-2b` (4,3 GB), vocab 248320 ✓ |
| las cifras de C4 | `registros/2026-08-22_C4-aceptacion.json` y `registros/2026-08-23_C4-integridad-ppl.json` |

## 🧭 LO SIGUIENTE, en orden

1. **H1 — empaquetar el campeón a ≤10 GB, por la salida (a).** Camino crítico y ahora
   además despejado: k-means k=4096 sobre las **direcciones** (no sobre los grupos crudos)
   → `C1`; residuos → `C2`. **`β_fila` ya está** (C12, `scripts/recuperar_escalas.py`).
   Cierre duro ya escrito: reconstruir `β·(C1[i]+C2[j])` y comparar **bit a bit**.
   Antes valía:
   la vía densa está cerrada por arriba en 0,33 tok/s y ahí el factor que se gana es ~250,
   no 2,2, porque los pesos dejan de leerse del disco. C8 ya despejó la duda que quedaba
   sobre ese cerebro: **sabe emitir llamadas Hermes**; lo que le falta es criterio.
   Escribir `scripts/empaquetar.py` y `scripts/verificar_empaquetado.py`.
2. **H7 — el lector con prefetch.** Sin solapar E/S y descompresión, C3 no sirve de nada
   (da ×0,91). Es la condición de D0.
3. ~~Abrir el ciclo del retículo con sonda por norma unidad~~ — **hecho**: C10 y C11,
   2026-08-23. El retículo está intacto y el libro mide 4096². Lo que queda no es una
   sonda, es escribir el empaquetado (punto 1).
4. **H1** — empaquetar el campeón a ~8 GB. Es el factor ~250× del que depende todo.
   Escribir `scripts/empaquetar.py` y `scripts/verificar_empaquetado.py` (el comando de
   cierre de H1 ya apunta a él).
3. **H2** — bucle de generación con caché KV. Bloqueado por H1: a 4,4 min/token no se
   puede ni depurar.
4. **H3** — banco n1 con tareas reales. Se puede empezar **ya**, sin cerebro, y conviene:
   define qué significa M2.
5. Pedir en QuantModels que las cadenas futuras persistan `idx1/idx2/C1/C2/alfa`. Son
   unas líneas en `save_file` y ahorran este problema para siempre.

## ⚠ LO QUE NO HAY QUE VOLVER A DESCUBRIR

- El campeón **no está empaquetado**: 1,9995 bits es contabilidad de lo que ocuparía. En
  disco son 51 GB de bf16. Verificado hoy con `du`, `ls` y `HERMETIC2.json`.
- La capa 30 usa **g=16**; las capas 0-3 y 58-63 usan **g=8** (`lanzar_v13.sh --capas-g8`).
  Sondear con el `g` equivocado da un falso negativo.
- `local_stream.generar` lanza `NotImplementedError` **a propósito**. Un cerebro que finge
  responder envenena cualquier medición que lo use.
- El modo de permiso de una carrera es `lista`, no `preguntar`: una carrera desatendida en
  modo `preguntar` deniega todo y la medición no vale.

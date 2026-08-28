# LA META DEL PROYECTO (fijada por el autor, 2026-08-22)

**Un arnés agéntico de ingeniería —del calibre de Claude Code— cuyo cerebro sea el
Qwen3.8-27B a 2 bits corriendo LOCAL, en CPU, en esta máquina, sin nube y sin GPU.**

No es «un cliente de chat con herramientas». Es la tesis contraria a la de todos los
arneses existentes: **Claude Code, OpenCode y compañía asumen un modelo fuerte y barato
al otro lado del cable.** Aquí el modelo es débil comparado con un Opus, cuesta segundos
por token y no se puede reintentar diez veces. Todo el diseño se sigue de eso.

## Cómo se mide (para que «del calibre de» no sea un adjetivo)

Un **banco de tareas** en `banco/`: cada tarea es un repositorio pequeño, un encargo en
lenguaje natural y un **comando de verificación determinista** que decide sin humano.
La puntuación de una carrera son cuatro cifras, siempre las cuatro juntas:

| cifra | qué es |
|---|---|
| **tareas** | % de tareas cuyo verificador pasa, sin intervención |
| **tokens** | tokens generados por el cerebro (entrada + salida), por tarea |
| **reloj** | segundos de pared por tarea |
| **intervenciones** | veces que un humano tuvo que desatascar |

Una carrera sin las cuatro no es una medición. Cada carrera deja un fichero en
`registros/`, y **los registros no se borran nunca** — ni los malos, sobre todo los malos.

## Los peldaños (cada uno se declara con su registro en registros/)

| hito | criterio | estado |
|---|---|---|
| **M0** bucle vivo | el bucle completo (plan→herramienta→observación→plan) pasa `banco/n0` con cerebro `eco`, sin modelo | ✅ **LOGRADO 2026-08-23**: 5/5 tareas, 0 intervenciones, 129,2 tokens de media. `registros/2026-08-23_2214_n0-eco.json` |
| **M1** cerebro en RAM | `qwen38-h13b` empaquetado a ≤10 GB, carga en RAM, **≥1 token/s medido en CPU** y PPL ≤ +1 % vs el checkpoint deshecho | ⏸ **RETIRADO por decisión del autor (2026-08-27)**: el cerebro de trabajo pasa a ser EL CEREBRO OFICIAL del proyecto — cuantizar en casa no compite con los proyectos dedicados a ello. El criterio no se rebajó: el hito entero se retira, y la vía de investigación queda en `E:\QuantModels` por si algún día vuelve |
| **M2** útil de verdad | ≥50 % de `banco/n1` con cerebro local, 0 intervenciones | ✅ **LOGRADO 2026-08-25**: 6/6 tareas de n1 (100 %), 0 intervenciones, con el **cerebro de trabajo** (GGUF Q2_K_XL, no el campeón de H1). `registros/2026-08-25_1345_n1x6-gguf.json` (C25). El banco venía de engordarse ese mismo día con bugs de clase y ediciones coordinadas (C24→C25) |
| **M3** se mejora solo | el ciclo de investigación sube la puntuación de M2 sin humano en el bucle, y el registro lo prueba | 🟡 **MAQUINARIA COMPLETA, MEJORA MEDIDA COMO INALCANZABLE CON ESTE CEREBRO** (2026-08-27, C73-C80): la puerta la abrió el autor y el mecanismo entero existe y se probó en producción — adopción con 4 reglas de honestidad, reversión automática (C73), vigilante de rachas, y los mandos activos sin-pensar/pensar-vueltas/contexto. Pero OCHO mediciones cierran el mapa: los topes rompen antes de mejorar, el contexto comprime por azar (±35% vs listón 10%), sin think ahorra 59% pero mata el criterio (C79), y el think selectivo conserva el criterio sin ahorrar (C80: 544≥493) — **el gasto y el criterio viven en el mismo sitio**. El criterio de M3 NO se rebaja: se declara que con el cerebro de trabajo no se alcanza y que la palanca es **M1** (un cerebro mejor piensa lo mismo en menos tokens). El día que el campeón exista, la batería de 8 preguntas se recorre en una noche de lazo |
| **M5** paridad de arnés | pedido por el autor (2026-08-27): cubrir las 5 brechas frente a Claude Code como arnés. Criterios medibles: **(1)✓ contexto que sobrevive horas (C72: 100% con renacimiento de 13.026 caracteres en la traza)** — una tarea que desborda los 16.384 tokens COMPLETA con renacimiento holográfico donde hoy muere por SystemExit, medido en ciclo; **(2)✓ sesiones reanudables (ida-y-vuelta idempotente, continuación entre procesos)** — `genai tarea --continuar` retoma una sesión guardada y el re-prefill es uno solo (append-exacto después); **(3)✓ fondo (fondo_lanzar/revisar + aviso del bucle; mismos permisos que bash vía ejecuta_shell)** — un comando largo corre desasido con aviso al volver, sin sentar el turno a esperar; **(4)✓ plugins (contrato en docs/plugins.md; roto se salta avisando; shell declarado pasa por el veto)** — contrato documentado con el que un fichero externo añade una herramienta sin tocar `genai/`; web queda VETADA mientras META diga «sin nube»; **(5)✓ UX (streaming real: 33 deltas en humo gguf; Ctrl-C conserva lo generado y --continuar retoma; plan proponer→aprobar→ejecutar en la misma sesión)** — streaming token a token en terminal, Ctrl+C limpio a mitad de generación, y modo plan conversacional (proponer→aprobar→ejecutar). Cada pieza con asertos; las afirmaciones de conducta, con ciclo | ✅ **LOGRADO 2026-08-27**: las cinco tachadas con asertos (203 en verde) y la conducta con ciclo (C72: renacimiento real de 13.026 caracteres y 100 %). El desbordamiento se peló en tres capas medidas — la lección «el guardián del contexto mira LA CACHÉ, no la transcripción» queda en CONTINUIDAD |
| **M6** la malla | pedido por el autor (2026-08-27): modo Mesh opcional — usuarios donan una fracción de su CPU y se aceleran mutuamente; lo local sigue siendo el modo por defecto, intacto. Criterios medibles: (a) **grano de TAREA, no de token** — repartir la inferencia por capas está descartado con las mediciones de C20/C26 (caché recurrente sin operaciones parciales + latencia WAN por token); (b) `genai malla servir --hilos N` dona N hilos y ejecuta tareas ajenas en caja aislada con modo `lista`+veto+vedadas; (c) `malla_delegar` envía una tarea a un par y el AVISO llega por el mecanismo de fondo existente; (d) **nada remoto se aplica sin pasar el verificador LOCAL** — el resultado llega a cuarentena (`.genai/malla/`), jamás sobre el árbol; (e) v1 es de PARES DE CONFIANZA (clave compartida, tus máquinas o gente que conoces), no Internet abierto — el tránsito a desconocidos exige sandbox duro y firma, y es v2; (f) reciprocidad por contabilidad local (segundos donados/consumidos), sin tokens ni cadenas. Doctrina precisada: «sin nube» = sin proveedores centrales; la malla entre usuarios es soberanía compartida y opt-in | 🟢 **CONSTRUIDO Y PROBADO EN FRÍO 2026-08-27**: (a)-(f) implementados; 14 asertos incluyen una malla REAL por loopback (un par sirve con `eco`, otro delega, resultado en cuarentena, clave rechazada, sobre con `..` rechazado, árbol intacto). **Throughput MEDIDO sobre WAN real (2026-08-28)**: dos pares en GCP (e2-small, cerebro `nube:gemini`) corren `n1/anadir`+`n1/fuga` en **29,3 s** frente a **45,0 s** en serie — **×1,54**, 2/2 verificadas por el verificador local. No es ×2 y se dice por qué: el transporte de la semilla cuesta segundos por tarea, así que la malla gana cuando la tarea dura mucho más que su envío. La prueba destapó dos fallos que el loopback no podía: el 7337 lo filtran muchas redes (usar 443) y un par ocupado tumbaba `delegar` (SystemExit no es Exception). Infraestructura creada y BORRADA en la misma sesión |
| **M7** paridad plena de arnés | pedido por el autor (2026-08-28) tras el informe de brechas. Seis frentes, cada uno con su criterio: **(1)✓ paralelismo DENTRO de una tarea** (subagente: 3 exploraciones en paralelo, 22 vueltas y 1.259 tokens suyos, 3.158 caracteres al contexto) **+ MODO HÍBRIDO** (M7.1b, pedido del autor): cerebro por ROL —principal local, `subagente` y `resumidor` a la nube—, con la nube nunca como carga crítica (cae al principal), gasto auxiliar registrado APARTE y una carrera híbrida que NO cuenta como local — herramienta `subagente` con contexto aislado que devuelve solo la conclusión; medido en una tarea de exploración donde el contexto principal NO crece con lo explorado; **(2)✓ compactación semántica** (el resumen del cerebro conserva el porqué de cada decisión, el estado de la verificación y lo que falta; cae al mecánico si el cerebro falla) — el resumen del renacimiento lo escribe el cerebro conservando el porqué, y se mide contra el mecánico en la tarea que C72 dejó abierta; **(3) ecosistema de herramientas** — al menos tres plugins reales de referencia (MCP, PDF, y uno más), publicados y probados; **la web deja de estar vetada pero como OPT-IN explícito** (`--web`), nunca por defecto: «sin nube» sigue significando sin dependencia de proveedores centrales, y una herramienta que sale a Internet se enciende a mano; **(4) multimodal** — leer imágenes y PDFs (con cerebro de nube; el local no es multimodal y eso se dice); **(5) diff y git** — `editar` enseña el cambio antes de aplicarlo y hay flujo de rama/commit/PR; **(6) madurez** — NO se arregla programando y no se promete: lo que se hace es endurecer el banco hasta que vuelva a discriminar (C28 midió que ya no lo hace) y ejercitar lo construido en trabajo real, dejando registro | 🟢 **LAS SEIS CUBIERTAS 2026-08-28**, cada una con su cifra: (1) subagentes con contexto aislado + reparto por roles; (2) resumen semántico del cerebro en el renacimiento; (3) `web`+`buscar_web` encendidas con SSRF cerrado —incluida la redirección— y el plugin real `pruebas`; (4) imágenes y PDF verificados de punta a punta contra Gemini con control negativo; (5) `git` con `push`/`reset`/`rebase` vetados y diff `-U0` que es poda por definición; (6) `n3` gana `regresion` y `ruidosa`, y **C84 midió el reparto real**: n1 separa débil de capaz (nano 16,7 % frente a 100 %) y n3 separa capaces entre sí (gemini 75 %, mini 100 %). Dos honestidades que quedan escritas: la trampa de `regresion` NO atrapa a ningún cerebro capaz —el GGUF local la resuelve en 8 vueltas sin escribir la versión ingenua— y contra el cerebro local un tope de reloj corto convierte cualquier nivel en un medidor de velocidad |
| **M4** producto profesional | pedido por el autor (2026-08-25): Mekro-Genai listo para producción. Criterios medibles (propuestos y ajustables por el autor aquí): (a) instalable por un tercero con `pip install -e .` y un comando `genai` que abre sesión interactiva contra el cerebro local; (b) README con instalación, configuración del modelo y uso, verificados en limpio; (c) banco COMPLETO verde en la máquina de referencia tras la instalación; (d) el lazo encadena ≥10 vueltas sin humano con racha sana y el supervisor lo prueba en su log; (e) manejo digno de los fallos previsibles (modelo ausente, RAM corta, contexto lleno) con mensajes que digan qué hacer | ✅ **LOGRADO 2026-08-26** con una salvedad anotada: (a) rueda 0.1.0 + `setup.cfg` para setuptools viejos; (b) venv limpio → `pip install -e .` → `genai` tal cual el README; (c) banco 16/16 con `eco` tras instalar (`registros/2026-08-26_0623_m4c-venv-*`) — con GGUF está verde en los registros C23-C30, medidos ANTES de la instalación, no después; (d) **10 vueltas encadenadas sin humano** (C34-C43, `logs/supervisor.log`), racha máxima 1, frenos sin saltar; (e) modelo ausente y contexto lleno con mensaje accionable |

## La vía densa (añadida por el autor, 2026-08-22)

Existe una **vía alterna a cuantizar**: correr el mismo Qwen3.8-27B en **BF16 intacto**,
CPU y RAM, sin GPU, a velocidad usable. No compite con la vía cuantizada — la necesita, y
al revés (ver [docs/densa-en-cpu.md](docs/densa-en-cpu.md) §dónde encajan). Su ventaja es
que **la pérdida de calidad no es «≤1 %»: es cero**.

| hito | criterio | estado |
|---|---|---|
| **D0** el modelo donde debe | los 52 GB en ext4 y un lector que sostenga **≥6 GB/s medidos** con prefetch | 🟡 modelo copiado; falta el lector (H7) |
| **D1** genera | generación autoregresiva BF16 de extremo a extremo, a la velocidad que sea, con salida **idéntica** a la de `transformers` como referencia | pendiente |
| **D2** sin pérdida y usable | especulativa verificada token a token contra el modelo solo (temperatura 0) **y ≥1 token/s medido** | 🔴 **medido inalcanzable en esta máquina** (C4/C7/C9, 2026-08-23): α tope 0,569 con tres borradores distintos → **0,33 tok/s**, y D2 exige α ≥ 0,821. El criterio NO se rebaja: se declara que esta vía no lo alcanza |
| **D3** compite | **≥2 tokens/s** y `banco/n1` corriendo con el cerebro denso | 🔴 inalcanzable por lo mismo: exige α ≥ 0,911 |

D2 era el peldaño que zanjaba la pregunta del autor, **y está zanjado: la respuesta es
no**. El 2026-08-22 lo medido decía que estaba al alcance porque el divisor —cuántos tokens
se aceptan por pase— era una proyección. El 2026-08-23 se midió: 2,0-2,3 tokens por pase
con tres borradores distintos, no los 5,6 que hacen falta. **El criterio de D2 no se toca**;
lo que se declara es que la vía densa no lo alcanza en esta máquina y para qué sirve
entonces: como **patrón de oro** contra el que medir cualquier cuantización. Las cifras y
la extrapolación, en `docs/densa-en-cpu.md` §el techo de esta vía.

## Cerebros de nube con TU clave (decidido por el autor, 2026-08-27)

El autor autoriza que cada usuario enchufe **su propia clave** del proveedor que
prefiera (Gemini, Claude, GPT, DeepSeek, Kimi, o cualquier endpoint compatible con
OpenAI). Esto **no deroga «sin nube»**, lo precisa: el proyecto no depende de ningún
proveedor central —el cerebro oficial sigue siendo local y es el defecto— y quien
quiera velocidad de nube pone su clave y asume su coste y su política.

Dos reglas que protegen las cifras del proyecto:

1. **Una carrera con cerebro de nube NUNCA cuenta como cifra local.** El registro
   anota el cerebro como `nube:proveedor/modelo` y M0/M2 quedan como se declararon,
   con el cerebro local. Comparar nube con local es comparar dos máquinas.
2. **La clave vive fuera del repositorio** (`~/.config/genai/claves.json`, permisos
   600) y no aparece en registros, logs ni nombres.

Medido el 2026-08-27 con la clave del autor: `n1/anadir` PASA en **25,6 s con
gemini-3.7-flash** frente a **757-969 s con el cerebro local** — ~30× de reloj, misma
tarea y mismo verificador (`registros/2026-08-28_0411_nube-gemini-anadir.json`).

### El coste de la nube es entrada, y se aprieta ahí (2026-08-28)

Si el usuario paga por token, ahorrarle tokens es parte de la meta y no un extra. La
medición que ordena el diseño: el gasto es **entrada contra salida ~40:1**, porque la
transcripción se reenvía entera cada vuelta. Todo lo demás se deduce de ahí, y está en
[docs/ahorro.md](docs/ahorro.md).

Tres reglas, que valen tanto como las dos de arriba:

1. **Se poda ANTES de entrar, jamás después.** Comprimir hacia atrás rompe el prefijo
   cacheado del proveedor y re-cobra a precio completo todo lo que venía cacheado: sale
   *más* caro que no tocar nada. Por eso `renacer()` es un último recurso y no una
   optimización.
2. **El tope de una observación depende de las vueltas que QUEDAN**, no de un número
   fijo. Un dato que entra en la vuelta 2 de una tarea de 10 se paga nueve veces.
3. **Un ahorro solo cuenta si `tareas_pct` sigue en 100.** Es lo que separa esto de las
   herramientas que reclaman porcentajes sin verificador: aquí «sin pérdida de calidad»
   es una cifra del banco, y un ahorro que rompe una tarea es una avería con buena
   prensa.

## La web, encendida (decidido por el autor, 2026-08-28)

El agente tiene `web` (traer una URL) y `buscar_web` (buscar), **encendidas por
defecto**. El motivo es de uso: comprobar un enlace y consultar documentación que no
está en el proyecto es parte de programar, y sin eso el agente solo sabe lo que ya venía
sabiendo.

Esto **no** convierte el proyecto en un arnés de nube. El cerebro sigue siendo local, y
leer una página es tan «nube» como leer un fichero es «disco». Lo que se conserva:

1. **Visible y apagable**: `genai tarea … --sin-web`. La decisión se ve, no se cuela.
2. **Pasa por permisos**: las dos son `peligrosa=True`, como `bash`. En modo plan no hay
   red, igual que no hay shell.
3. **No alcanza esta máquina ni esta red**: se resuelve el nombre y se comprueba la IP
   antes de conectar, y otra vez en cada redirección.
4. **El banco corre sin web**, a propósito. Dos herramientas más engordan el prompt de
   sistema en cada vuelta, y las cifras de M2 y M3 se declararon sin ellas.

Para buscar hace falta clave: no hay buscador gratis y estable que raspar (DuckDuckGo
responde con un CAPTCHA, comprobado). Dos caminos, y **lo elige el usuario** en
`busqueda.motor`: la API del proveedor que ya paga (OpenAI `web_search`, Gemini Google
Search) o un buscador dedicado —`brave`, `serper`, `tavily`, `serpapi`, `searxng`, o
cualquier otro descrito en `claves.json` sin tocar código—. **Con cualquiera de ellos,
el Qwen local tiene búsqueda web** sin ser él quien la haga: la doctrina híbrida de
M7.1b aplicada — la nube hace el recado, nunca la carga.

## El cerebro OFICIAL local (decidido por el autor, 2026-08-27)

**`Qwen3.8-27B-UD-Q2_K_XL.gguf` (9,15 GB, 2,83 bits) es el cerebro oficial de
Mekro-Genai.** Sus cifras: PPL 4,71 (código) / 10,58 (español), 2,876 tok/s con 8 hilos,
78 ciclos de investigación y un banco de 17 tareas en 4 niveles medidos con él. La
sección siguiente queda como historia de cómo llegó aquí.

## Cerebro de trabajo, distinto de M1 (histórico; decidido por el autor, 2026-08-23)

M1 sigue exigiendo lo que exigía: **el campeón `qwen38-h13b` empaquetado a ≤10 GB con PPL
≤ +1 %**. Ese criterio **no se toca**, porque mide reproducir el campeón y es lo que hace
falsable la vía cuantizada.

Pero el campeón no está bloqueado por calidad sino por **empaquetado**: son 49 GB de bf16
deshecho y un token cuesta un pase completo por disco. Mientras H1 no exista, el arnés no
tiene contra qué correr y M0 y M2 quedan parados por una razón que no es la suya.

Por eso el autor autoriza un **cerebro de trabajo**: una cuantización cualquiera del mismo
Qwen3.8-27B que arranque hoy en CPU y RAM, **aceptando la degradación que traiga**. Sirve
para avanzar el arnés y el banco, no para declarar M1.

Reglas para que esto no contamine las cifras del proyecto:

- El cerebro de trabajo se identifica **siempre** por su fichero y su cuantización en cada
  registro. Una carrera con él **nunca** cuenta como M1.
- Su PPL se mide y se publica igual que las demás, sin excepción — «degradado» es un
  adjetivo, y aquí los adjetivos no valen. Lo que se relaja es el **umbral**, no la
  obligación de medir.
- M1 conserva su criterio. Si algún día se decide que el cerebro de trabajo basta para el
  hito, se reescribe **este** fichero, no se da por supuesto.

## El muro, en lenguaje de presupuesto (por qué M2 exige inventar de verdad)

Un agente tipo Claude Code gasta con alegría 50–200 K tokens de contexto por tarea porque
el token es barato y rápido. Aquí, a **1–3 tokens/s** (techo de ancho de banda de RAM en
esta máquina: ~8 GB de pesos leídos por token), 50 K tokens de generación son **más de
cuatro horas**. El presupuesto realista por tarea es del orden de **2–5 K tokens
generados**. Eso es 10–100× menos que el arnés que queremos igualar.

De ahí salen las tres puertas de escape, que son el programa de investigación entero:

1. **El contexto se reconstruye, no se acumula.** Cargar ficheros enteros para orientarse
   es el gasto dominante y es evitable: `holograma.py` regenera el contexto de una tarea
   desde punteros a símbolos. El holograma no es un extra del proyecto — **es la
   arquitectura de contexto del arnés**.
2. **Lo determinista sale del modelo.** Indexar, diferenciar, aplicar parches, verificar,
   ordenar candidatos: todo eso lo hace código, gratis y sin equivocarse. El modelo solo
   **decide**, y decidir cuesta decenas de tokens, no miles.
3. **Las herramientas son de grano grueso.** Cada vuelta del bucle cuesta segundos de
   prefill más la generación. Una herramienta que hace el trabajo entero de un paso vale
   diez que hay que encadenar. `editar(fichero, [8 cambios])`, no ocho llamadas.

Si las tres fallan y M2 no cae, la evidencia lo dirá en `registros/` y habrá que cambiar
de tesis. **Ninguna afirmación de este documento existe hasta tener registro.**

## Lo que NO es la meta

- No es batir a Claude Code en tareas donde la nube es legítima. Es que **exista un arnés
  serio que no dependa de nadie**.
- No es soportar veinte proveedores. El cerebro local es el enunciado del problema, no una
  opción de configuración. `cerebro/` es enchufable para poder MEDIR contra una referencia,
  no para escaparse a la nube cuando el local falle.
- No es reimplementar `quant/`. La cuantización se investiga en `E:\QuantModels`; aquí se
  **consume** su checkpoint campeón y se le exige lo que un arnés necesita y una medición
  de perplejidad no: generación autoregresiva, caché KV y latencia.

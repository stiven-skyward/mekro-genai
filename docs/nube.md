# Cerebros de nube con tu propia clave (BYOK)

Lo local es el defecto y la identidad del proyecto. Esto es una alternativa **opt-in**
para quien quiera velocidad de nube y ponga su clave, su coste y su política.

## Configurar

Crea `~/.config/genai/claves.json` **con permisos 600** (nunca dentro del repositorio):

```json
{
  "gemini":    {"clave": "..."},
  "anthropic": {"clave": "...", "modelo": "claude-opus-5"},
  "openai":    {"clave": "..."},
  "deepseek":  {"clave": "..."},
  "kimi":      {"clave": "..."}
}
```

```bash
chmod 600 ~/.config/genai/claves.json
```

**Cabeceras extra**, si tu proveedor las pide. Una clave de Anthropic ligada a identidad
responde `400` sin `anthropic-workspace-id`, y un proxy corporativo suele querer las
suyas; se ponen aquí y no hay que tocar código:

```json
{"anthropic": {"clave": "...", "cabeceras": {"anthropic-workspace-id": "wrkspc_..."}}}
```

## Usar

```bash
genai tarea "arregla el bug" --cerebro nube:gemini
genai tarea "..." --cerebro nube:gemini/gemini-3.7-flash    # modelo explícito
genai tarea "..." --cerebro nube:anthropic/claude-opus-5
genai tarea "..." --cerebro nube:deepseek

# el banco también, y el registro deja constancia de que fue nube
python3 scripts/correr_banco.py --nivel n1 --cerebro nube:gemini
```

## Proveedores conocidos

| nombre | dialecto | modelo por defecto |
|---|---|---|
| `gemini` | nativo Gemini | `gemini-3.7-flash` |
| `anthropic` | Messages API | `claude-opus-5` |
| `openai` | chat/completions | `gpt-5.1` |
| `deepseek` | compatible OpenAI | `deepseek-chat` |
| `kimi` | compatible OpenAI (Moonshot) | `kimi-k2-turbo-preview` |
| `xai` | compatible OpenAI | `grok-4` |
| `groq` | compatible OpenAI | `llama-3.3-70b-versatile` |
| `openrouter` | compatible OpenAI | `openai/gpt-5.1` |

### Y otros 207, del catálogo

`genai proveedores [texto]` lista **207 proveedores y 7.483 modelos** de
[models.dev](https://models.dev), cacheados en disco. Funcionan sin escribir código:

```bash
genai proveedores mistral            # buscar
genai tarea "..." --cerebro nube:mistral/mistral-large-latest
```

Funciona porque ahí fuera casi todo el mundo habla uno de los tres dialectos que ya
estaban escritos: ~190 hablan OpenAI, 9 Anthropic y 1 Gemini. **Lo que faltaba no era
código, era la tabla.** La clave va en `claves.json` con el nombre del proveedor, o en
la variable de entorno que el catálogo declara.

Tres cosas que conviene saber:

- **Los ocho de fábrica mandan.** Si el nombre está arriba, gana ese: son los que
  tienen medición detrás (caché, firmas de pensamiento, PDF) y el catálogo no sabe nada
  de eso.
- **Funciona sin red** una vez cacheado. Un arnés que presume de local no puede
  necesitar una descarga para arrancar.
- **Bedrock, Vertex, Azure y watsonx se rechazan a propósito**, y se dice por qué: no se
  autentican con una clave en una cabecera sino con la firma de su nube, y eso no es
  HTTP con `urllib`.

**Cualquier otro endpoint compatible con OpenAI** funciona igualmente sin tocar el
código: añade `{"url": "https://...", "dialecto": "openai", "modelo": "...",
"clave": "..."}` con el nombre que quieras.

## Cómo funciona por dentro

Tres formas de API cubren el mercado, y el adaptador habla las tres con `urllib` de la
biblioteca estándar — ni un SDK nuevo, porque la dependencia única
(`llama-cpp-python`) es parte de lo que hace este proyecto instalable en hardware
modesto:

- **Gemini** — `contents[]` + `functionDeclarations`; el sistema va en
  `systemInstruction`. Gemini 3.x exige devolver el `thoughtSignature` de cada
  `functionCall` (responde 400 si falta): el adaptador lo guarda por id de llamada y lo
  reinyecta.
- **Anthropic** — `x-api-key` + `anthropic-version`; herramientas con `input_schema`,
  llamadas como bloques `tool_use` y observaciones como `tool_result`.
- **OpenAI y compatibles** — `tool_calls` con argumentos serializados; las firmas de
  herramientas del arnés ya vienen en este dialecto y pasan tal cual.

**Las llamadas a herramientas son nativas, no Hermes.** El cerebro local emite Hermes
en texto porque es lo que Qwen trae entrenado; los modelos de nube tienen llamada a
funciones nativa y es mucho más fiable. El bucle, los permisos y el banco no notan la
diferencia.

## Modo híbrido: local para decidir, nube para explorar

El reparto que pidió el autor, generalizado a **roles**: el cerebro principal sigue
siendo el local —quien decide y edita, donde vive la soberanía— y los papeles
auxiliares pueden ir a un modelo de nube.

```bash
# atajo: todos los roles auxiliares a la nube, principal local
genai tarea "arregla el bug" --cerebro gguf --hibrido nube:gemini

# o rol a rol
genai tarea "..." --cerebro gguf --cerebro-subagente nube:gemini \
                  --cerebro-resumidor nube:deepseek
```

O de forma permanente en `~/.config/genai/cerebros.json`:

```json
{"principal": "gguf", "subagente": "nube:gemini", "resumidor": "nube:gemini"}
```

**Por qué estos dos roles, con las cifras delante:**

| rol | qué hace | por qué a la nube |
|---|---|---|
| `subagente` | explorar | muchas vueltas baratas en tokens y carísimas en reloj: el prefill manda. Medido: 3 exploraciones = 22 vueltas (~11 min en local, 46 s en nube) |
| `resumidor` | el resumen del renacimiento | UNA generación de prosa; en local cuesta minutos y por eso el defecto ahí es el resumen mecánico. Con resumidor de nube, **un Qwen local también conserva el porqué** |

**Tres reglas que lo hacen honesto:**

1. **La nube nunca es carga crítica.** Si falta la clave o el proveedor falla, el rol
   cae al cerebro principal con un aviso. Sin nube, todo sigue funcionando.
2. **Una carrera híbrida NO es una carrera local.** El registro anota los dos cerebros
   y el gasto auxiliar (`auxiliar`) aparte del de la carrera. Comparar sus cifras con
   las de M2 —que se declararon con el cerebro local puro— sería mentir.
3. **Se configura a mano y se ve.** No hay reparto automático «inteligente»: elegir
   cerebro es una decisión de experimento, no algo que se cuele sin que nadie lo vea.

## Ahorro: la nube cuesta dinero, y aquí se aprieta

Con un cerebro local, un token es tiempo. Con uno de nube, **es dinero**. El análisis
completo, con las cifras, está en **[ahorro.md](ahorro.md)**; lo que hay que saber para
usarlo cabe aquí.

**El gasto es la entrada, en proporción ~40:1**, porque la transcripción entera se
reenvía en cada vuelta. Así que el ahorro ataca la entrada, con dos mecanismos que
vienen puestos de fábrica:

| mecanismo | qué hace | se apaga con |
|---|---|---|
| **caché de prefijo** | el proveedor cobra ~0,1× (Anthropic) a 0,5× (OpenAI) por lo ya visto. Aquí el prefijo es estable por construcción desde C22 | `"cachear": false` en el proveedor |
| **poda en el origen** | recorta observaciones ruidosas ANTES de que entren, y aprieta más cuanto más lejos esté el final de la tarea | `MG_PODA=0` |

Dos cosas que conviene entender porque son contraintuitivas:

- **La poda aprieta pronto y afloja tarde.** Un dato que entra en la vuelta 2 de una
  tarea de 10 se reenvía nueve veces; el mismo en la vuelta 9, una sola. El coste de un
  dato no es su tamaño: es su tamaño **por lo que le queda de vida**.
- **Nunca se comprime hacia atrás.** Reescribir transcripción ya enviada rompe el
  prefijo cacheado y sale *más* caro que no tocar nada. Por eso `renacer()` —que sí
  reescribe— es el último recurso y no una optimización.

**Podar no es perder**: lo recortado se guarda entero en `.genai/podado/` y el aviso que
ve el modelo dice con qué referencia recuperarlo.

## Buscar en la web

Dos caminos, y se elige el que prefieras. No hay buscador gratis y estable que raspar
(DuckDuckGo responde con un CAPTCHA, comprobado 2026-08-28), así que ambos llevan clave.

**1. Por la API del proveedor que ya usas.** OpenAI busca con `web_search` de la
Responses API; Gemini con Google Search nativo. Cero configuración extra: si ya tienes
la clave del cerebro, ya puedes buscar.

**2. Con un buscador dedicado.** Suele salir más barato que pagar tokens de un modelo
por buscar, y devuelve resultados más limpios. Vienen de fábrica:

| motor | clave | notas |
|---|---|---|
| `brave` | sí | API propia de Brave Search |
| `serper` | sí | Google vía serper.dev |
| `tavily` | sí | pensado para agentes |
| `serpapi` | sí | Google vía SerpAPI |
| `searxng` | no | tu propia instancia: pon `url` en vez de `clave` |

### Elegirlo

```json
{
  "busqueda": {"motor": "auto"},
  "brave":  {"clave": "..."},
  "openai": {"clave": "..."}
}
```

| `motor` | qué hace |
|---|---|
| `auto` *(defecto)* | dedicado si hay alguno; si no, el proveedor del cerebro en uso |
| `brave`, `serper`, … | **ese** y solo ese; si no está configurado te lo dice, en vez de usar otro a la callada |
| `proveedor` | siempre por la API del cerebro, ignorando los dedicados |

Si uno falla, se intenta el siguiente antes de rendirse: quedarse sin buscar por una
caída ajena sería peor que cambiar de puerta.

### Cualquier otro buscador

No hace falta que venga de fábrica. Se describe en `claves.json` y funciona igual —
mismo patrón que los proveedores compatibles con OpenAI:

```json
{"mi_buscador": {
   "url": "https://api.ejemplo.com/search?q={q}&limit={n}",
   "cabeceras": {"Authorization": "Bearer {clave}"},
   "clave": "...",
   "lista": "data.items",     // dónde anida los resultados
   "titulo": "name", "enlace": "href", "extracto": "summary"}}
```

`{q}`, `{n}` y `{clave}` se sustituyen. Para POST, añade `"metodo": "POST"` y un
`"cuerpo": {...}` con las mismas marcas.

## Con tu cuenta de Google (Code Assist) — ⚠ cerrado para cuentas personales

**Medido con una cuenta real el 2026-08-28: para una cuenta personal esto ya no
funciona, y no es culpa del código.** Google retiró el nivel gratuito de Code Assist
para individuos:

```
free-tier      INELEGIBLE · "This client is no longer supported for Gemini Code
               Assist for individuals. Migrate to the Antigravity suite."
standard-tier  403 · "You do not have a valid license of this product."
```

No es un bloqueo a terceros: **`gemini-cli` 0.57.0 ya ni ofrece OAuth personal** —solo
acepta `GEMINI_API_KEY`, Vertex o Code Assist con licencia—. La puerta se cerró para
todos, y esta medición es la prueba.

Sigue sirviendo si **tienes licencia de Gemini Code Assist** (Standard/Enterprise) y un
proyecto de Google Cloud: `genai google proyecto <id>`.

**Si no la tienes, usa una clave de AI Studio.** Tiene nivel gratuito, funciona hoy y no
depende de nada de esto. Es lo que hemos medido toda la sesión.


```bash
genai google entrar      # abres una URL, entras con tu cuenta
genai tarea "..." --cerebro nube:google
genai google             # estado
genai google salir       # borra la credencial
```

Google AI Pro/Ultra —y también la cuenta gratuita— traen cuota de **Code Assist**, que
es la que usa `gemini-cli`. Entrando con tu cuenta se usa esa cuota en vez de pagar
tokens de la API.

**Hacen falta las credenciales del cliente, y NO vienen en este repositorio.** Son de
`gemini-cli`, no nuestras, y publicarlas en un repositorio público las esparciría —
GitHub rechazó con razón el primer intento de subirlas. Se leen, por este orden, de
sitios que son tuyos:

1. **un `gemini-cli` instalado** (`npm i -g @google/gemini-cli`) — se leen solas;
2. las variables `GENAI_GOOGLE_CLIENTE` y `GENAI_GOOGLE_SECRETO`;
3. `~/.config/genai/google_cliente.json`.

**Y lo que hay que saber, sin adornos**: se presenta con el identificador de cliente de
`gemini-cli` y habla con su mismo endpoint. Funciona —el cliente y su secreto están
verificados contra Google— pero **no es una integración que Google bendiga para
terceros**. La suscripción está pensada para los clientes de Google; la API existe para
el uso programático. Puede cortarse sin aviso. La clave de AI Studio no tiene esa
incertidumbre y también tiene nivel gratuito.

Dos detalles técnicos que explican por qué esto no es «la clave de Gemini con otro
nombre»: el flujo es de **bucle local** y no de dispositivo, porque el de dispositivo no
admite el ámbito `cloud-platform` que Code Assist necesita; y Code Assist **envuelve**
la petición y la respuesta de Gemini, con la credencial en cabecera en vez de en la URL.

## GitHub Copilot, con tu cuenta

```bash
genai copilot entrar     # device flow: abres una URL y tecleas un código
genai tarea "..." --cerebro nube:copilot
genai copilot            # estado
genai copilot salir      # borra la credencial
```

**Lo que hay que saber antes de usarlo, sin adornos**: este es el camino que usan los
clientes de Copilot que no son de GitHub —se presenta con el identificador de cliente
del editor—. Funciona, y es lo que hace OpenCode, pero **no es una integración que
GitHub bendiga para terceros**. Necesitas suscripción activa de Copilot, la usas bajo
sus términos, y si GitHub cierra esta puerta dejará de funcionar sin previo aviso. Con
una clave de API de cualquier otro proveedor no tienes esa incertidumbre.

El token de Copilot caduca en minutos y se renueva solo, con 60 s de margen. Vive en
`~/.config/genai/copilot.json` con permisos 600 y **aparte** de `claves.json`: no es una
clave que escribieras tú, sino una credencial que este programa obtuvo en tu nombre.

## Las dos reglas que no se negocian

1. **Una carrera de nube nunca cuenta como cifra local.** El cerebro se registra como
   `nube:proveedor/modelo`; M0 y M2 se declararon con el cerebro local y ahí siguen.
2. **Tu clave es tuya**: fuera del repositorio, con permisos 600, y jamás en un
   registro, un log o un nombre. Si una clave se te escapa a un sitio compartido,
   rótala — es más barato que cualquier auditoría.

## Mekro-Genai como servidor MCP (tu suscripción usando el arnés)

No hay forma legítima de que Mekro-Genai gaste la cuota de una suscripción de
**consumidor** (Google AI Pro/Ultra) por API — esa cuota vive dentro de las apps de
Google (Gemini, Antigravity), y la API programática es un producto de facturación
distinto. Medido con cuenta real el 2026-08-28 (ver arriba): `loadCodeAssist` responde
que el nivel gratuito para individuos "ya no está soportado" y el de pago exige
licencia de Code Assist, no la suscripción de consumidor.

Lo que **sí** funciona: invertir la dirección. En vez de que Mekro-Genai le pida texto a
Gemini, **Gemini (dentro de Antigravity, con tu suscripción) le pide herramientas a
Mekro-Genai** — protocolo MCP, que Antigravity y Claude Desktop ya hablan de forma
nativa.

```bash
genai mcp     # sirve por stdio; no lo lances a mano, lo lanza el cliente
```

En la configuración MCP de Antigravity (o Claude Desktop):

```json
{"mcpServers": {"mekro-genai": {
  "command": "python3", "args": ["-m", "genai.cli", "mcp"],
  "cwd": "/ruta/a/tu/proyecto"}}}
```

Con eso, el modelo que ya pagas puede llamar a `leer`, `editar`, `referencias`
(la de LSP), `git`, `subagente`, la malla — todo lo que ya existe, sin duplicar nada.
Con Claude Code sirve igual — de hecho es un caso más limpio, porque MCP es soporte de
primera clase suyo y no algo verificado a ciegas: `claude mcp add mekro-genai --
python3 -m genai.cli mcp` y `claude mcp get mekro-genai` → **`✔ Connected`**, probado
con cuenta real el 2026-08-28. Un `tools/call` contra `git log` devolvió el historial
real de este repositorio, y contra `bash rm -rf /` respondió `DENEGADO: VETADO`.

**Pasa por la misma `Politica` que el bucle normal**, en modo `lista` por defecto: no
hay humano al otro lado de un cliente remoto para «preguntar», y `todo` confiaría en el
cliente más de lo que se confía en el propio agente. El veto duro de `permisos.py`
(`rm -rf /`, forzar un push, etc.) actúa igual venga la llamada de donde venga.

**Lo que esto NO es**: no es Mekro-Genai usando tu suscripción. Es tu suscripción,
dentro de la app de Google o de Claude Code, usando Mekro-Genai. El cerebro sigue siendo
el suyo; lo que se comparte es la caja de herramientas.

### Ahorro por MCP: una palanca transfiere, otra no puede (2026-08-28)

Aquí cada token que este servidor devuelve cuenta contra TU cuota, y el cliente lo
reenvía en cada vuelta siguiente. Pero no las dos palancas de docs/ahorro.md se aplican
igual — el límite es estructural, no de esfuerzo:

- **La poda en el origen SÍ transfiere**, y `genai/mcp.py` la tenía SIN CABLEAR hasta
  hoy: `_llamar` solo aplicaba el tope duro de 12.000 caracteres de `base.py`, sin pasar
  por `podar()`. Medido con un `grep` real acotado a un directorio: recortado, 12.153
  caracteres; podado, 2.647 — **78 % menos**. Ahora se aplica a toda llamada.

  El ajuste no es idéntico al del bucle propio: `podar()` aprieta según *vueltas
  restantes*, y eso lo sabe `bucle.py` porque es dueño de la conversación entera. **Un
  servidor MCP no tiene esa visibilidad** — cada `tools/call` es una llamada aislada.
  Se asume el peor caso (`VUELTAS_ASUMIDAS = 20`, que ya toca el suelo de agresividad de
  `factor_vueltas`), porque lo que se manda de más aquí no se puede compactar después,
  a diferencia de `sesion.renacer()`.

- **La caché de prefijo NO transfiere**, y no es un fallo: vive dentro de las llamadas
  HTTP que Mekro-Genai hace cuando ÉL ES el cliente del modelo (`genai/cerebro/nube.py`).
  Aquí la conversación con el proveedor la gestiona el propio Claude Code o Antigravity,
  con su SDK; este servidor nunca ve esa petición.

- **El impuesto por vuelta de los esquemas es propio de MCP** y no está en
  docs/ahorro.md: `tools/list` con las 16 herramientas pesa 7.603 caracteres (~1.900
  tokens), reenviados por el cliente en CADA vuelta, se use o no la herramienta esa
  vuelta. `filtro_herramientas` (o `MG_MCP_HERRAMIENTAS=leer,grep,git` por variable de
  entorno) recorta la exposición a lo que de verdad hace falta — medido con tres
  herramientas: 78 % menos peso en `tools/list`.

Lo que **no** se declara porque no se puede medir desde aquí: cuánto de tu presupuesto
semanal ahorra esto en la práctica. Depende de cómo el cliente factura y cachea su
propia conversación, que es opaco para este servidor. Lo medido son caracteres y tokens
de lo que este proceso devuelve, no la factura final.

```bash
export MG_MCP_HERRAMIENTAS="leer,grep,editar,git"   # solo estas cuatro, en vez de 16
export MG_MCP_PODA=0                                # apaga la poda (brazo de control)
```

## Coste y velocidad, medidos

`n1/anadir`, misma tarea y mismo verificador determinista:

| cerebro | reloj | tokens |
|---|---|---|
| local (Qwen 2,8 bits, CPU) | 757-969 s | 493 |
| `nube:gemini/gemini-3.7-flash` | **25,6 s** | 339 |

~30× de reloj. Lo que compras con la nube es tiempo; lo que pagas es dependencia de un
tercero y el coste por token. Por eso ambos modos existen y el local es el defecto.

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

## Coste y velocidad, medidos

`n1/anadir`, misma tarea y mismo verificador determinista:

| cerebro | reloj | tokens |
|---|---|---|
| local (Qwen 2,8 bits, CPU) | 757-969 s | 493 |
| `nube:gemini/gemini-3.7-flash` | **25,6 s** | 339 |

~30× de reloj. Lo que compras con la nube es tiempo; lo que pagas es dependencia de un
tercero y el coste por token. Por eso ambos modos existen y el local es el defecto.

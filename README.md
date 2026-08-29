# Mekro-Genai

Arnés agéntico de ingeniería —bucle plan→herramienta→observación→plan, edición de
ficheros, shell, búsqueda, permisos, sesiones— cuyo cerebro es **local**: un Qwen3.8-27B
cuantizado a ~2,8 bits corriendo **en CPU, sin GPU y sin nube**, en hardware moderado
(medido: 16 hilos, 30 GB de RAM, ~2,9 tokens/s de generación).

La tesis, contraria a la de los arneses grandes: ellos asumen un modelo fuerte y barato
al otro lado del cable; aquí el modelo cuesta segundos por token y no se puede
reintentar diez veces — **todo el diseño se sigue de eso**: caché KV append-exacta,
renacimiento holográfico del contexto, presupuestos como código, un banco de tareas con
verificador determinista, y un ciclo de investigación falsable que el propio arnés
puede correr solo (78 ciclos registrados en `registros/`).

La meta y sus criterios de medida viven en [META.md](META.md). El estado real, en
[ESTADO_VIVO.md](ESTADO_VIVO.md). Ninguna afirmación de calidad va sin cifra medida.

## Instalación

```bash
pip install -e .              # el arnés, BYOK, MCP y las suscripciones: sin dependencias
pip install -e ".[local]"     # además, el cerebro local (compila llama-cpp-python)
```

`pip install -e .` a secas ya deja `genai proveedores`, `genai cerebros`, `genai mcp` y
`genai sesiones` funcionando: son biblioteca estándar, sin nada que compilar. El
cerebro local necesita además un GGUF en la ruta que enseña `genai version` (hoy:
`~/modelos/gguf/Qwen3.8-27B-UD-Q2_K_XL.gguf`, 9,2 GB) — sin él, todo el arnés se prueba
igual con `--cerebro eco` (sin modelo) o con cualquiera de nube (`--cerebro nube:...`).

### Desde Windows

**No hay instalación nativa en PowerShell, y no es un hueco por rellenar**: la
herramienta `bash` del agente corre con `shell=True`, que en Windows nativo invoca
`cmd.exe` en vez de bash —sintaxis distinta, comandos que fallarían o harían otra
cosa—; `select()` sobre tuberías (que usa el cliente LSP) no funciona ahí; y los
permisos 600 de las credenciales no protegen nada en NTFS. Se verificó código en mano,
no se supuso.

Lo que sí funciona, porque es donde vive y se ha probado todo este proyecto, es WSL:

```powershell
wsl --install          # si no lo tienes ya (reinicia si te lo pide)
wsl
```

Y dentro de esa terminal Linux, exactamente los mismos pasos de arriba (`git clone`,
`pip install -e .`, `genai ...`). PowerShell es solo la puerta a WSL, no el sitio donde
corre nada.

## Uso

```bash
genai version                                  # qué hay instalado y qué cerebro ve
genai tarea "arregla el bug de suma.py"        # un encargo en el directorio actual
genai tarea "..." --modo todo --vueltas 8      # sin preguntar, con topes propios
genai tarea "..." --cerebro eco                # el arnés sin modelo (pruebas)
genai chat                                     # conversación continua (ver abajo)
```

El modo por defecto es `preguntar`: lo peligroso se consulta por consola. Los topes
(vueltas, tokens, segundos) existen porque cada vuelta cuesta segundos de CPU reales.

## La terminal — `genai chat` y la estética de las llamadas

`genai tarea` es un turno por proceso: bueno para scripts y para el banco, pero no una
conversación. `genai chat` sí lo es — la **misma** `Sesion` en memoria a lo largo de
muchos mensajes, con el contexto append-exacto haciendo barato cada uno nuevo:

```bash
genai chat                          # conversación continua, el cerebro por defecto
genai chat --cerebro nube:gemini    # o cualquier otro --cerebro/--modo de `tarea`
```

Comandos dentro de la conversación: `/modo <plan|preguntar|lista|todo>` cambia la
política de permiso sin salir, `/sesion` enseña vueltas y tokens gastados, `/nueva`
abre otra sesión sin cerrar la terminal, `/deshacer` restaura ficheros (ver abajo),
`/salir` (o Ctrl-D) termina. `@ruta/al/fichero` en cualquier mensaje mete su contenido
directo en el encargo, sin gastar una vuelta entera en pedirle al cerebro que llame a
`leer` y esperar otra generación para que lo use.

Tanto `chat` como `tarea` comparten la misma estética de terminal (`genai/tui.py`,
biblioteca estándar, sin dependencias): la llamada a una herramienta se enseña ANTES de
ejecutarse (`● editar(...)`), el resultado después con ✓/✗, y `editar`/`escribir`
muestran el **diff real** —tanto al pedir permiso como al aplicarlo— en vez de un
volcado de argumentos. Los colores se apagan solos si la salida no es una terminal
(`NO_COLOR`, `TERM=dumb`, o forzar con `MG_COLOR=0/1`).

### Lo que un cerebro que no se puede reintentar necesita, y Claude Code/OpenCode no

Su tesis es un modelo de nube rápido y barato de reintentar; la de aquí es la contraria
(ver arriba). Tres cosas se siguen de eso, y no tendrían sentido en un arnés cuyo cerebro
tarda milisegundos:

- **`genai deshacer [sesión]`** (o `/deshacer` en el chat): cada turno que toca ficheros
  guarda solo, sin que nadie lo pida, el contenido de ANTES en `.genai/deshacer/`.
  Deshacer una edición mala es instantáneo; regenerarla cuesta la vuelta entera otra
  vez —minutos reales—. Un fichero que no existía se restaura borrándolo, no dejando
  uno vacío. Repetir `/deshacer` camina hacia atrás, mensaje a mensaje.
- **El latido**: mientras el modelo carga, prefilla el contexto o piensa en silencio
  antes del primer carácter, la terminal muestra `·· generando… N s` en vez de parecer
  colgada. Se apaga solo si la salida no es una terminal real.
- **Aviso al terminar** (campanita de terminal siempre; notificación de escritorio si
  `notify-send`/`osascript` existen) cuando un turno pasa de 15 s — quien se fue a hacer
  otra cosa mientras 16 hilos trabajaban no tiene que volver a mirar la pantalla.

### Lo que BYOK, suscripción y MCP necesitan, y el local no

Local no tiene coste por token ni un cliente externo mirando; nube y MCP sí. Tres cosas
más, con la misma disciplina de «cifra medida o silencio, nunca una aproximación»:

- **Coste real en $** tras cada turno con `--cerebro nube:...`: `catalogo.py` ya trae el
  precio de 7.483 modelos de models.dev (`cost.input`/`cost.output`, USD por millón de
  tokens) — antes descargado y sin usar. Ahora se calcula y se enseña, junto al % de la
  entrada que vino de caché de prefijo (`CerebroNube.ahorro_cache`, que tampoco se
  mostraba en ningún sitio). Si el catálogo no conoce el modelo, o el cerebro es local o
  de **suscripción** (Copilot, Google Code Assist — ahí no hay coste por token real que
  tasar), no se enseña nada: no se inventa una cifra donde no hay dato.
- **`--tope-costo USD`**: para el turno si el gasto estimado llega a eso — el mismo
  «presupuesto como código» de siempre (`--vueltas`, `--tokens`, `--segundos`), llevado a
  dinero de verdad. Sin efecto en local o suscripción, por la misma razón de arriba.
- **`/modelo <nombre>`** en `genai chat`: cambia de cerebro EN MEDIO de la conversación,
  sin perder ni un mensaje del historial — de local a `nube:gemini` para un paso puntual,
  o al revés, o a una suscripción. Con 207 proveedores + suscripciones + local
  disponibles, mezclarlos en una sola sesión es más valioso que en un arnés de un solo
  proveedor.
- **`genai mcp --trazar`**: el servidor MCP era completamente mudo —ni un `print`—
  mientras Claude Code, Codex o Cursor lo usaban. Con esta bandera (opt-in; la invocación
  normal de los tres clientes no cambia) la actividad se ve por stderr con la MISMA
  estética del bucle interactivo (`● herramienta(args)` → `✓/✗`), sin tocar nunca stdout
  —el canal JSON-RPC del protocolo—.

## Interfaz gráfica — `genai ui`

```bash
genai ui                    # arranca en un puerto libre y abre el navegador
genai ui --puerto 7654 --sin-navegador   # puerto fijo, sin abrir nada (para un servidor)
```

Una sola página HTML autocontenida (sin Electron, sin npm, sin paso de compilación)
servida por el mismo `genai/servidor.py` que ya existía para multi-sesión y compartir:
lista de sesiones, lanzar una tarea, ver la transcripción en vivo, responder permisos
pendientes desde un modal, y un panel de ajustes para las claves de `genai proveedores`
sin tocar el fichero a mano. Sondea el servidor cada 1-2 s en vez de un canal de eventos
— con un cerebro que tarda segundos o minutos por vuelta, sondear es indistinguible de
streaming de verdad y evita una clase entera de fallos de conexión.

Al ser solo un navegador hablando HTTP con `127.0.0.1`, corre igual en Linux, macOS y
WSL: no hay ninguna pieza nativa por sistema operativo que mantener. **macOS no necesita
nada equivalente a WSL** —es POSIX/BSD real—, así que la base para los tres sistemas es
la misma.

## Verificación

```bash
for t in tests/*.py; do python3 "$t"; done     # las suites (cuenta asertos en verde)
python3 scripts/correr_banco.py --nivel n0 --cerebro eco --exigir-todo
```

El banco (`banco/n0..n3`) son tareas de ingeniería con verificador determinista; el
cerebro real las pasa todas a fecha 2026-08-25 (registros en `registros/`, que no se
borran nunca).

## El lazo autónomo

`scripts/lazo.py` corre una vuelta del ciclo de investigación sin humano (proponer →
registrar → medir → veredicto) y `scripts/supervisor.py` las encadena, con frenos:
`touch logs/supervisor.parar` lo detiene todo.

## Cerebros de nube con tu clave (opcional)

Lo local es el defecto. Si quieres velocidad de nube, pon **tu** clave en
`~/.config/genai/claves.json` (permisos 600, fuera del repo) y elige proveedor:

```bash
genai tarea "arregla el bug" --cerebro nube:gemini
genai tarea "..." --cerebro nube:anthropic/claude-opus-5
genai tarea "..." --cerebro nube:deepseek        # y kimi, openai, xai, groq…
```

Funcionan los tres dialectos que existen (Gemini nativo, Anthropic Messages, y
compatible-OpenAI para todo lo demás), con llamada a herramientas **nativa** y sin
añadir un solo SDK. Medido: `n1/anadir` pasa en **25,6 s** con `gemini-3.7-flash`
frente a **757-969 s** en local — misma tarea, mismo verificador. Una carrera de nube
**nunca** cuenta como cifra local: el registro anota `nube:proveedor/modelo`.

`genai proveedores [texto]` busca entre **207 proveedores y 7.483 modelos** de
models.dev además de los 8 de fábrica, sin escribir código para ninguno.

### Tres caminos para traer un cerebro de nube — `genai cerebros`

BYOK (arriba) no es la única forma, y no todas valen para cualquier proveedor:

```bash
genai cerebros    # el menú: BYOK, suscripción directa, o MCP — decides tú
```

- **Suscripción directa** (`genai copilot entrar`, `genai google entrar`): Mekro-Genai
  actúa como tu cerebro con tu cuenta, no con clave de API. Solo existe donde el
  proveedor sanciona de verdad que un tercero lo use — GitHub lo documenta para
  editores; con Google se midió que el nivel gratuito de Code Assist está cerrado. **No
  existe para OpenAI ni Anthropic**: sus suscripciones están ligadas a su propio
  cliente, no a extraerlas para otro programa.
- **MCP** (`genai mcp clientes`): al revés — tu cliente de suscripción (Claude Code,
  Codex, **Cursor**) usa las herramientas de Mekro-Genai, con su propio cerebro intacto.
  Verificado con cuenta real en los tres: llamadas reales a `git`, y el veto de
  `rm -rf /` deteniéndose igual que en el bucle interactivo.

Guía completa, con las cifras de cada camino: [docs/nube.md](docs/nube.md).

## Varios agentes a la vez

El candado es de **sesión**, no de proyecto: dos agentes pueden trabajar sobre el mismo
repositorio a la vez, cada uno con la suya, y solo se avisa si los dos tocan el mismo
fichero. Probado con dos procesos reales en paralelo.

```bash
genai sesiones                          # quién está trabajando aquí ahora mismo
genai tarea "..." --sesion <id>         # continuar una en concreto
genai sesiones compartir <id>           # HTML autocontenido, con secretos tachados
```

## El modo malla (opcional)

Lo local es y sigue siendo el defecto. La malla es **opt-in** y reparte al grano de
**tarea**, no de token — repartir la inferencia por capas está descartado con medición
(latencia por token + caché recurrente sin operaciones parciales). Un par ejecuta la
tarea entera con su propio cerebro; **tu verificador local decide** si el resultado
vale, y nada remoto toca tu árbol: llega a cuarentena en `.genai/malla/`.

```bash
# donar una fracción de tu CPU a pares de confianza
genai malla servir --hilos 4

# usar la malla en un encargo (el agente gana la herramienta malla_delegar)
genai tarea "..." --malla

genai malla cuenta          # segundos donados y consumidos
```

Configuración en `~/.config/genai/malla.json`:
`{"clave": "secreta-compartida", "pares": ["192.168.1.50:7337"]}`

v1 es para **pares de confianza** (tus máquinas, tu equipo): clave compartida, una
tarea a la vez, y la tarea ajena corre con la misma política que una carrera del banco
(modo `lista` + veto duro + rutas vedadas). Internet abierto pide contenedor y firma
por par — eso es v2. Diseño completo y reglas: [docs/malla.md](docs/malla.md).

## Licencias

- **El código y los documentos de este repositorio**: [Apache License 2.0](LICENSE).
  Úsalo, modifícalo y redistribúyelo con libertad, conservando LICENSE y [NOTICE](NOTICE).
- **Los pesos del modelo Qwen NO se distribuyen aquí** y no los cubre la Apache 2.0 de
  este repositorio: se rigen por la licencia del propio modelo, que aceptas al
  descargarlo de su origen (https://huggingface.co/Qwen). Ver [NOTICE](NOTICE).
  *Built with Qwen.*

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
```

El modo por defecto es `preguntar`: lo peligroso se consulta por consola. Los topes
(vueltas, tokens, segundos) existen porque cada vuelta cuesta segundos de CPU reales.

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

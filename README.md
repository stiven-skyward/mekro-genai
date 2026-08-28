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
pip install -e .
```

El cerebro es un GGUF que debe existir en la ruta que enseña `genai version` (hoy:
`~/modelos/gguf/Qwen3.8-27B-UD-Q2_K_XL.gguf`, 9,2 GB). Sin él, el arnés entero puede
probarse con el cerebro `eco` (sin modelo).

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

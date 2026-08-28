# Mekro-Genai en el editor

## Qué hay y qué no

| interfaz de OpenCode | aquí |
|---|---|
| terminal | ✅ `genai tarea …`, con traza, permisos y streaming |
| extensión de IDE | ✅ `editor/vscode/` (VS Code y derivados) |
| aplicación de escritorio | ❌ **no la hay, y no se promete** |

Lo tercero no es una brecha que se cierre con un fichero más: es otro producto, con su
empaquetado, sus actualizaciones y su superficie de mantenimiento. Decir que está sería
mentir; el servidor deja la puerta abierta a quien quiera escribirla.

## Instalar la extensión

No está publicada en el Marketplace. Se instala enlazándola:

```bash
ln -s "$PWD/editor/vscode" ~/.vscode/extensions/mekro-genai
# y reinicia VS Code
```

Luego, en el proyecto:

```bash
genai sesiones servir      # el servidor, en 127.0.0.1
```

Y desde la paleta de órdenes: **Mekro-Genai: sesiones**, **… ver una transcripción**,
**… encargar una tarea**.

## Cómo está hecha, y por qué así

**No reimplementa el arnés.** Habla HTTP con el servidor de sesiones — para eso existe
la separación cliente/servidor. Permisos, herramientas y cerebros siguen en un solo
sitio.

**La tarea se lanza en una terminal, no dentro de la extensión.** El modo `preguntar`
para antes de cada acción peligrosa y espera un sí o un no. Ese diálogo vive en la
terminal. Meterlo en una ventana del editor sin pensarlo bien acabaría, tarde o
temprano, en que alguien lo desactiva «porque molesta» y ejecuta cosas sin mirar. La
extensión ve y lanza; el agente corre donde sus frenos funcionan.

**La clave se lee del disco**, del mismo fichero donde el servidor la escribe — no de la
configuración de VS Code, que se sincroniza entre máquinas y llevaría la credencial con
ella.

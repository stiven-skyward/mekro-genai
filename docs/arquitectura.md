# Arquitectura de Mekro-Genai

> De dónde viene cada pieza, qué se toma y —lo que suele faltar en estos documentos—
> **qué se rechaza a propósito y por qué**. La tesis está en [META.md](../META.md):
> todos estos arneses asumen un modelo fuerte y barato al otro lado del cable; aquí el
> cerebro es local, débil y cuesta segundos por token. Copiar sus decisiones sin
> traducirlas es la forma más rápida de construir algo que no funciona en esta máquina.

## El bucle, que es lo único que todos comparten

```
        ┌──────────────────────────────────────────────┐
        │              nucleo/bucle.py                 │
        │                                              │
   ┌────▼─────┐   llamadas   ┌───────────┐  decisión   │
   │ cerebro/ │─────────────▶│ permisos  │─────────────┤
   │ generar  │              └─────┬─────┘             │
   └────▲─────┘                    │ permitido         │
        │                    ┌─────▼──────┐            │
        │   observación      │herramientas│            │
        └────────────────────│  invocar   │            │
                             └────────────┘            │
        topes: vueltas · tokens · segundos ────────────┘
```

Todo lo demás son decisiones sobre **dónde poner los topes, qué entra en el contexto y
quién decide si una llamada se ejecuta**. Ahí es donde los arneses se diferencian, y
donde el cerebro local cambia todas las respuestas.

## Qué se toma de cada uno

| de | se toma | traducido a esta máquina |
|---|---|---|
| **Claude Code** | el bucle plan→herramienta→observación; los **modos de permiso** como política y no como pregunta suelta; la memoria de proyecto en un fichero del repositorio (`CLAUDE.md`) | los modos están en `nucleo/permisos.py`, pero el modo por defecto de una **carrera** es `lista` (lista blanca), no `preguntar`: las carreras del banco corren solas y de noche |
| **Claude Code** | la **compactación** del contexto cuando se llena | se toma la idea, se rechaza la implementación: Claude Code resume con el propio modelo, y aquí una generación cuesta minutos. `sesion.compactar()` tira las observaciones viejas dejando constancia. La vía buena es no llenarlo (ver *holograma*) |
| **OpenCode** | separación **servidor/cliente** (el agente vive en un proceso, la interfaz habla con él) y uso de **LSP** para saber de símbolos de verdad | la separación es obligatoria aquí, no estética: cargar 8 GB de pesos tarda; el proceso del cerebro debe sobrevivir a la interfaz. Es H4. Del LSP se toma la idea con `herramientas/buscar.py:simbolos`, que hoy resuelve por AST y solo Python |
| **OpenChamber** | **aislamiento por sesión**: cada agente en su copia, sin pisarse | `--modo todo` solo se admite dentro de un contenedor o de un `git worktree` desechable. En el repositorio de verdad, `todo` es cómo se pierde trabajo |
| **arnés de DeepSeek** | sobriedad: pocos esquemas, muy estrictos, sin florituras; el bucle mínimo que funciona | el prompt de sistema de `cli.py` son ~120 tokens. Las once herramientas de Claude Code costarían ~1.500 tokens **en cada vuelta**: entre 8 y 25 minutos por tarea regalados |
| **Hermes** (Nous Research) | el **formato de llamada** `<tools>` / `<tool_call>` | no es una preferencia: es el formato con el que Qwen3 fue entrenado. Desviarse cuesta calidad medible en un modelo de 2 bits. `cerebro/plantilla.py` lo habla exactamente |
| **Mekro** (`E:\Mekro`) | el **holograma de tarea** y los ciclos autónomos con vigilante | el holograma deja de ser una herramienta auxiliar y pasa a ser la arquitectura de contexto (§siguiente) |
| **QuantModels** (`E:\QuantModels`) | el cerebro, y la disciplina de medir | `registros/` no se borra; toda afirmación con cifra; la comprobación barata antes que la carrera cara |

## Qué se rechaza a propósito

- **Veinte proveedores de modelo.** `cerebro/` es enchufable para poder medir contra una
  referencia, no para escaparse a la nube cuando el local falle. META.md lo prohíbe.
- **Herramientas finas.** Nada de `leer_linea`, `aplicar_un_cambio`, `listar_directorio`.
  Cada llamada cuesta una vuelta entera; `editar` recibe **todos** los cambios de un
  fichero y los aplica de forma atómica.
- **Reintentos a ciegas.** Un `<tool_call>` roto no se adivina: se le devuelve al modelo
  la queja concreta (`plantilla.analizar_llamadas`). Adivinar es ejecutar algo que el
  modelo no pidió, y estas herramientas escriben en disco y corren shell.
- **Resumir con el modelo para compactar.** Cuesta una generación entera.
- **Subagentes en paralelo.** Un solo cerebro de 8 GB en 30 GB de RAM: dos agentes a la
  vez es *swap*, y *swap* con este perfil de acceso es dos órdenes de magnitud. La
  paralelización aquí es de **herramientas**, no de agentes.

## El holograma como arquitectura de contexto

Es la decisión que separa este arnés de todos los de la tabla. Un agente normal se
orienta **leyendo**: abre tres módulos, gasta 20 K tokens y luego piensa. A 1-3 tokens/s
ese prefill se paga en cada vuelta y se come el presupuesto entero de la tarea.

Un Holograma de Tarea (`holograma.py`) guarda **anclas** —punteros a símbolos— y no
contenido. `foco H1` va al disco, extrae exactamente esos símbolos y reconstruye el
contexto de trabajo:

    contexto = f(anclas)        en vez de        contexto = payload

Tres consecuencias que importan aquí más que en ningún otro arnés:

1. **Cuesta lo que decidir, no lo que leer.** Un holograma de 2 KB regenera lo que
   habría que leer en decenas de KB.
2. **No envejece en silencio.** Si alguien renombra el símbolo al que apunta un ancla,
   `holograma.py verificar` lo grita. Un resumen en prosa se pudre sin avisar, y un
   modelo pequeño razonando sobre código que ya no existe es la peor vuelta posible.
3. **Sobrevive a la muerte de la sesión.** Y aquí las sesiones mueren: una carrera de
   banco puede tardar horas.

`genai/memoria/holos.py` expone `holos`, `foco` y `anotar` como herramientas, para que
el cerebro use el mismo mecanismo que usa el humano.

## Los módulos

| módulo | responsabilidad | no es responsable de |
|---|---|---|
| `nucleo/bucle.py` | plan→herramienta→observación y los tres topes | saber qué modelo hay detrás |
| `nucleo/sesion.py` | el hilo, la contabilidad y la presión de contexto | decidir qué se ejecuta |
| `nucleo/permisos.py` | política de permisos y **veto duro** | ejecutar nada |
| `cerebro/base.py` | el contrato: `generar` y `contar_tokens` | herramientas, permisos |
| `cerebro/plantilla.py` | el dialecto Hermes de Qwen, y las quejas de formato | ejecutar llamadas |
| `cerebro/eco.py` | medir el ARNÉS sin modelo (M0) | parecerse a un modelo |
| `cerebro/local_stream.py` | referencia lenta sobre el checkpoint deshecho | trabajar |
| `cerebro/local_packed.py` | **el cerebro de verdad — no existe aún (M1, H1)** | — |
| `herramientas/` | leer, escribir, editar, grep, símbolos, bash | decidir si se permiten |
| `memoria/holos.py` | el holograma como herramienta del cerebro | — |
| `banco/` | tareas con verificador determinista | — |

## El veto duro

`permisos.py:VETO` es una lista de patrones que **no se permiten en ningún modo, ni
siquiera en `todo`**: `rm -rf /`, `mkfs`, `dd of=/dev/sd*`, `curl | sh`, `git push
--force`. No es paranoia: un modelo pequeño confunde con facilidad el directorio de la
tarea con la raíz, y el coste esperado de esa confusión no tiene comparación con lo que
se gana permitiéndola. Está probado en `tests/test_bucle.py`.

## Lo que falta y dónde está anotado

| pieza | hito | holograma |
|---|---|---|
| empaquetar el campeón a 2 bits reales en RAM | M1 | **H1** |
| bucle de generación autoregresiva con caché KV | M1 | **H2** |
| banco de tareas `n1` con verificadores | M2 | **H3** |
| separación servidor/cliente (el cerebro sobrevive a la interfaz) | M2 | **H4** |
| decodificación restringida por gramática para las llamadas | M2 | **H5** |
| el ciclo de investigación cerrando el lazo solo | M3 | **H6** |

## LSP (2026-08-28)

La deuda que este documento citaba desde el primer día —«el uso de LSP de OpenCode»— ya
está pagada, en `genai/lsp.py` y `genai/herramientas/codigo.py`.

Es **protocolo, no biblioteca**: JSON-RPC con cabecera `Content-Length` sobre stdio.
Cabe en un fichero y no añade dependencias; el proyecto tiene una y se queda con una. El
servidor de lenguaje sí es una herramienta externa que instala el usuario, como `git`.

Por qué importa, con el caso mínimo que lo demuestra: en un fichero con `def pagar(x)` a
nivel de módulo y `def pagar(self)` dentro de una clase, `grep pagar` da 6 coincidencias
—incluidas la del método y la de un comentario—; `referencias` sobre la función devuelve
5 y **excluye el método**, y preguntado sobre el método devuelve solo el método. Esa
confusión es exactamente la que rompe un renombrado.

Tres decisiones de diseño, cada una con su motivo medido:

1. **El servidor se reutiliza** por (proyecto, lenguaje). Arrancar `pylsp` cuesta ~1,5 s
   y la segunda llamada 0,0 s. Pagar el arranque en cada pregunta sería inservible con
   un cerebro que ya tarda 530 s por vuelta.
2. **Sin servidor instalado se dice cuál falta**, con el comando exacto. Devolver
   «0 referencias» cuando lo cierto es «no hay quien busque» hace que el modelo concluya
   que el símbolo no se usa y borre código vivo.
3. **Solo lectura.** Renombrar en veinte ficheros lo hace el agente con `editar`, que
   pasa por permisos y deja diff. Un `workspace/applyEdit` silencioso, no.

# La malla (M6): P2P al grano de tarea

## El concepto, y por qué tiene esta forma

La idea del autor: los usuarios de Mekro-Genai donan una fracción de su CPU y se
aceleran mutuamente — cuantos más usuarios, mejor para todos. Lo local sigue siendo el
modo por defecto, intacto; la malla es opt-in.

**Lo que la malla NO es: inferencia repartida.** Partir el modelo por capas entre pares
(estilo Petals) exige enviar activaciones por la red EN CADA TOKEN: con 100-300 ms de
ida y vuelta por etapa, sale más lento que los ~0,35 s/token locales. Y este modelo en
concreto lo prohíbe dos veces: su caché es híbrida-recurrente sin operaciones parciales
(C20) — repartir capas reparte estado recurrente, y un par que se cae cuesta un
re-prefill completo. Está medido; no se discute, se cita.

**Lo que la malla SÍ es: tareas enteras en paralelo.** La unidad de reparto es la que
este arnés ya domina: una tarea autocontenida (directorio semilla + encargo + topes +
verificador determinista). Un par la ejecuta ENTERA con su propio cerebro y devuelve el
resultado; el verificador LOCAL del que delegó decide si vale. La malla no acelera una
tarea: multiplica cuántas corren a la vez. Ejemplo medido: la carrera de 6 tareas de
C25 costó 102 min en serie — con 3 pares rondaría 35.

## Las piezas (v1, pares de confianza)

    genai malla servir --hilos 4 --cerebro gguf --clave <secreta>
        Dona 4 hilos: un servidor HTTP (stdlib, sin dependencias) acepta UNA tarea a
        la vez, la ejecuta en un temporal aislado con modo «lista», veto duro y rutas
        vedadas, y guarda el resultado para que el delegante lo recoja.

    malla_delegar (herramienta del agente) / genai/malla.py delegar
        Empaqueta el directorio de trabajo (tope 10 MB), lo envía al primer par
        configurado y deja un «fondo» local esperando: el AVISO de terminación llega
        por el mismo mecanismo de fondo_lanzar, en la vuelta siguiente del bucle.

    ~/.config/genai/malla.json
        {"clave": "...", "pares": ["192.168.1.50:7337"]}
        v1 es LAN / pares de confianza: tus máquinas, tu equipo. Sin NAT traversal,
        sin nodos de arranque, sin descubrimiento mágico.

## Las reglas de seguridad, por delante de la ambición

1. **Cuarentena siempre**: el resultado remoto se desempaqueta en `.genai/malla/<n>/`,
   JAMÁS sobre tu árbol. Se aplica cuando TU verificador local pasa y tú (o tu agente,
   con permiso) decides. Un par hostil puede mentir; tu verificador no.
2. **El servidor ejecuta con la política de carrera**: modo `lista`, veto duro,
   `vedadas`, topes del sobre acotados por el servidor. Es el mismo guardarraíl que el
   banco lleva 80 ciclos usando. AUN ASÍ: v1 es para pares en los que confías — un
   encargo hostil con semilla hostil es código ajeno en tu máquina. Internet abierto
   exige contenedor + firma por par, y eso es v2, no una promesa de v1.
3. **Delegar es sacar tu código de tu máquina**: `malla_delegar` es herramienta
   peligrosa (pasa por permisos) y sin `malla.json` configurado ni siquiera opera.
4. **Reciprocidad por contabilidad local**: segundos donados y consumidos se anotan en
   `~/.config/genai/malla-cuenta.json`. Sin monedas, sin cadenas, sin mercados: la
   malla es cooperación medible, no un casino.

## Lo que enseñó la primera malla real (GCP, 2026-08-28)

Dos pares en Google Cloud (e2-small, cerebro `nube:gemini`) contra esta máquina,
tareas `n1/anadir` y `n1/fuga` con su verificador determinista:

| forma | reloj | resultado |
|---|---|---|
| serie, una máquina | 45,0 s | 2/2 verificadas |
| **paralelo, 2 pares** | **29,3 s** | **2/2 verificadas** |

**×1,54 con dos pares** — no ×2, y la diferencia es honesta: empaquetar, subir la
semilla y sondear cuesta unos segundos por tarea, así que la malla gana cuando la
tarea dura bastante más que su transporte. Con tareas de minutos (lo normal con
cerebro local) el sobrecoste se diluye; con tareas de 20 s, se nota.

Y dos cosas que la prueba de loopback no podía enseñar:

1. **El puerto por defecto importa.** El 7337 salía bloqueado en la red doméstica del
   autor (443 y 853 pasaban): muchas redes filtran puertos altos salientes. Si un par
   no responde y el servidor está vivo, prueba el 443 antes de buscar más lejos.
2. **Un par ocupado tumbaba `delegar`.** `_pedir` levanta `SystemExit` en un HTTP 503,
   y `SystemExit` hereda de `BaseException`, no de `Exception` — el `except Exception`
   que debía pasar al par siguiente no lo veía. Arreglado, con la constancia aquí
   porque es el tipo de fallo que solo aparece cuando dos pares compiten de verdad.

## Doctrina

«Sin nube» siempre significó sin dependencia de proveedores centrales. La malla entre
usuarios es lo contrario de la nube: soberanía compartida, cada nodo con su cerebro
local entero, y apagable con un Ctrl-C. Lo local es y seguirá siendo el defecto.

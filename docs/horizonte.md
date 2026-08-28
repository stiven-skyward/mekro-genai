# HORIZONTE — cola de ideas, después de M1

Ideas anotadas para cuando el cerebro esté en RAM. El flujo para cada una es el mismo:
**revisar → predecir por escrito → sonda barata → medición real → veredicto**
([ciclo.py](../ciclo.py)). Las cifras de impacto que aparezcan aquí son **hipótesis, no
resultados**: en este repositorio ninguna afirmación existe hasta tener registro.

Orden tentativo, por dependencia y por coste de falsación.

---

## 1. Prefill incremental por prefijo — la palanca más obvia

**Idea**: entre dos vueltas del bucle, el contexto solo crece por el final (una
observación nueva). Recomputar el prefill entero cada vuelta es tirar el 95 % del trabajo.
Con la caché KV de H2 ya escrita, conservarla entre vueltas es casi gratis.

**A verificar**: las 48 capas GatedDeltaNet llevan estado recurrente, no caché KV. ¿Se
puede congelar y reanudar ese estado igual que una caché? Si no, el ahorro solo aplica a
16 de 64 capas y la idea vale mucho menos de lo que parece. **Esta pregunta se contesta
leyendo `transformers`, no midiendo.**

**Depende de**: H2.

---

## 2. Contexto por holograma en vez de por lectura — medir el ahorro de verdad

**Idea**: META.md §puerta 1 afirma que reconstruir contexto con `foco` en vez de leer
ficheros es la diferencia entre caber y no caber en el presupuesto. Está *razonado*, no
*medido*.

**Cómo se mide**: la misma tarea del banco, dos carreras, único cambio: con `foco` en el
juego de herramientas y sin él. Se comparan las cuatro cifras. Es un A/B limpio y barato
en cuanto haya cerebro.

**Riesgo**: que el ahorro exista pero el modelo pequeño no sepa **cuándo** usar `foco`.
Sería un resultado igual de valioso y apuntaría a otra solución (llamarlo desde el arnés,
no dejarlo a criterio del modelo).

---

## 3. Herramientas compuestas para los pasos que siempre van juntos

**Idea**: en las trazas del banco aparecerán secuencias fijas —leer, editar, correr la
prueba— que cuestan tres vueltas y son una sola intención. Una herramienta
`editar_y_probar(ruta, cambios, comando)` las convierte en una.

**Cómo se decide cuáles**: de las trazas (`Resultado.traza`), contando n-gramas de
llamadas. No de la intuición: la secuencia que uno cree frecuente casi nunca lo es.

**Riesgo declarado**: cada herramienta nueva son ~150 tokens de firma **en cada vuelta**.
Una herramienta compuesta solo gana si su frecuencia paga esa renta. La regla: se añade
cuando aparece en ≥30 % de las tareas.

---

## 4. Modelo pequeño de guardia para el enrutado

**Idea**: muchas vueltas no necesitan 27B. «¿Terminó la tarea?», «¿esta salida es un
error?» las contesta un modelo diminuto en milisegundos. Reservar el cerebro grande para
lo que decide.

**Tensión con META.md**: la meta dice cerebro local; no dice **un solo** cerebro. Pero un
segundo modelo cargado compite por la RAM con los 8 GB del grande, y el *swap* con este
perfil de acceso son dos órdenes de magnitud. Si se prueba, con presupuesto de RAM medido
antes, no después.

---

## 5. Aprender de las trazas del propio banco

**Idea**: cada carrera deja trazas de qué funcionó. Con suficientes, hay material para
afinar el cerebro en el formato de llamada y en el estilo de este arnés — sin tocar su
conocimiento, solo su obediencia al formato.

**Por qué está al final**: exige (a) que el banco tenga volumen, (b) afinado, que es
cómputo pesado, y (c) que la GPU esté vetada aquí. Probablemente sea trabajo de
QuantModels y no de este repositorio. Anotado para no perderlo.

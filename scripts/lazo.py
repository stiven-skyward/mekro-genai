#!/usr/bin/env python3
"""lazo.py — UNA vuelta del lazo autónomo de H6: proponer → registrar → medir → veredicto.

La meta (M3) es que el arnés use su propio cerebro para proponer la hipótesis siguiente,
medirla y dejar el veredicto, sin humano en el bucle. Este script es esa vuelta, con los
frenos puestos ANTES que la ambición:

- **La racha manda.** Si `ciclo.py racha` alcanza el umbral, el lazo NO corre: para y
  pide revisión humana. Un lazo que encadena refutaciones está estancado, no ocupado.
- **El modelo no escribe shell.** Propone CAMPOS (métrica, umbral, mandos de la carrera)
  que se validan contra rangos; el comando lo construye este script desde una plantilla
  fija. La propuesta más hostil posible solo puede correr el banco con otros topes.
- **Las dos puertas del ciclo valen igual que para un humano**: sin predicción no se
  mide, sin lección no se cierra. Son el antídoto contra racionalizar el número.
- **El banco es de solo lectura** (permisos.py `vedadas`); aquí ni siquiera hace falta:
  el lazo no expone ninguna herramienta de escritura al proponente.

Modo frío (pruebas): `--propuesta fichero.json` salta al cerebro y toma la propuesta
del fichero (con su campo opcional «leccion»). Modo real: el cerebro GGUF propone.

    python3 scripts/lazo.py                       # una vuelta real
    python3 scripts/lazo.py --propuesta p.json    # una vuelta en frío
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

METRICAS = ("tareas_pct", "tokens_media", "entrada_media", "cache_pct",
            "segundos_media", "intervenciones")
RE_UMBRAL = re.compile(r"^(<|>|<=|>=|==)\s*\d+(\.\d+)?$")
RANGOS = {"tope_vueltas": (1, 32), "tope_tokens": (500, 16000),
          "tope_segundos": (60, 7200)}
CEREBROS = ("eco", "gguf")


def _ciclo(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(RAIZ / "ciclo.py"), *args],
                          capture_output=True, text=True)


def siguiente_id() -> str:
    import os
    dir_ciclos = Path(os.environ.get("MG_CICLOS", RAIZ / "registros" / "ciclos"))
    usados = [int(p.stem[1:]) for p in dir_ciclos.glob("C*.json")
              if p.stem[1:].isdigit()]
    return f"C{max(usados, default=0) + 1}"


def _huella_carrera(c: dict) -> tuple:
    return (c.get("nivel"), c.get("tarea") or "", c.get("cerebro", "gguf"),
            c.get("tope_vueltas"), c.get("tope_tokens"), c.get("tope_segundos"))


def _ya_medida(p: dict) -> str:
    """El id del ciclo que ya midió ESTA carrera con ESTA métrica, o «». Es el guardia
    de novedad: el proponente cayó en el surco cómodo de re-medir la misma carrera con
    umbrales holgados (C34 tokens<2000, C35 segundos<2500 sobre la carrera de C32) —
    confirmaciones sin información. Repetirse se rechaza a máquina, no a prosa."""
    import os

    def de_comando(cmd: str) -> tuple:
        def bandera(n, entera=False):
            m = re.search(rf"--{n}\s+(\S+)", cmd)
            if not m:
                return None if entera else ("" if n == "tarea" else
                                            "gguf" if n == "cerebro" else None)
            return int(m.group(1)) if entera else m.group(1)
        return (bandera("nivel"), bandera("tarea"), bandera("cerebro"),
                bandera("tope-vueltas", True), bandera("tope-tokens", True),
                bandera("tope-segundos", True))

    quiere = _huella_carrera(p["carrera"])
    dir_ciclos = Path(os.environ.get("MG_CICLOS", RAIZ / "registros" / "ciclos"))
    mismos: list[str] = []
    for f in sorted(dir_ciclos.glob("C*.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        med, pred = c.get("medicion") or {}, c.get("prediccion") or {}
        if not (c.get("veredicto") and med.get("comando")):
            continue
        if de_comando(med["comando"]) != quiere:
            continue
        if pred.get("metrica") == p["metrica"]:
            return c["id"]
        mismos.append(c["id"])
    # CUOTA por carrera: tras el guardia de métrica, el proponente esquivó por la letra
    # (C36: intervenciones <10 sobre la carrera de siempre — casi infalsable). Dos
    # ciclos por combinación de mandos y se acabó el surco: a variar nivel/tarea/topes.
    if len(mismos) >= 2:
        return "+".join(mismos[:2])
    return ""


def validar(p: dict) -> list[str]:
    """Qué tiene de malo la propuesta. Vacío = válida. Nunca se adivina ni se repara."""
    quejas = []
    for campo in ("pregunta", "revision", "metrica", "umbral", "porque", "carrera"):
        if campo not in p:
            quejas.append(f"falta «{campo}»")
    if quejas:
        return quejas
    for campo in ("pregunta", "revision", "porque"):
        if len(str(p[campo])) > 700:
            quejas.append(f"«{campo}» tiene {len(str(p[campo]))} caracteres: los "
                          "campos afirman, no deliberan (máximo 700)")
    if p["metrica"] not in METRICAS:
        quejas.append(f"métrica «{p['metrica']}» desconocida (van: {METRICAS})")
    if not RE_UMBRAL.match(str(p["umbral"]).strip()):
        quejas.append(f"umbral «{p['umbral']}» ininteligible (ej.: «<1200», «==100»)")
    c = p["carrera"]
    niveles = sorted(d.name for d in (RAIZ / "banco").iterdir() if d.is_dir())
    if c.get("nivel") not in niveles:
        quejas.append(f"nivel «{c.get('nivel')}» no existe (van: {niveles})")
    elif c.get("tarea"):
        if not (RAIZ / "banco" / c["nivel"] / c["tarea"] / "tarea.json").exists():
            quejas.append(f"tarea «{c['tarea']}» no existe en {c['nivel']}")
    if c.get("cerebro", "gguf") not in CEREBROS:
        quejas.append(f"cerebro «{c.get('cerebro')}» no permitido (van: {CEREBROS})")
    for mando, (lo, hi) in RANGOS.items():
        v = c.get(mando)
        if v is not None and not (isinstance(v, int) and lo <= v <= hi):
            quejas.append(f"{mando}={v!r} fuera de rango [{lo}, {hi}]")
    if not quejas:
        # tope de exploración: la cuota por mandos exactos dejó un surco fino — ordeñar
        # la MISMA tarea variando el tope de 100 en 100 (8 ciclos sobre n3/lista la
        # noche del 2026-08-25). Una curva se cartografía con media docena de puntos;
        # a partir de ahí, cada ciclo vale más en una tarea virgen.
        import os
        dir_ciclos = Path(os.environ.get("MG_CICLOS", RAIZ / "registros" / "ciclos"))
        clave = (p["carrera"]["nivel"], p["carrera"].get("tarea") or "")
        n_tarea = 0
        for f in dir_ciclos.glob("C*.json"):
            c_ = json.loads(f.read_text(encoding="utf-8"))
            cmd = (c_.get("medicion") or {}).get("comando") or ""
            if (c_.get("veredicto") and f"--nivel {clave[0]}" in cmd
                    and (not clave[1] or f"--tarea {clave[1]}" in cmd)):
                n_tarea += 1
        if clave[1] and n_tarea >= 8:
            # exención de MEJORA (M3): un tope que muerde la línea base con umbral
            # >10 % mejor es candidata a adopción — el tope de exploración no la
            # bloquea, porque es la clase de propuesta que sube la puntuación del banco
            import adopcion
            base_t = (adopcion.lineas_base().get(f"{clave[0]}/{clave[1]}")
                      or {}).get("tokens_salida")
            m_umbral = re.match(r"^<\s*(\d+)", str(p["umbral"]).strip())
            es_mejora = (p["metrica"] == "tokens_media" and base_t and m_umbral
                         and int(m_umbral.group(1)) < base_t * 0.9
                         and (c.get("tope_tokens") or 10**9) < base_t)
            if not es_mejora:
                quejas.append(f"la tarea {clave[0]}/{clave[1]} ya acumula {n_tarea} "
                              "ciclos veredictados: su curva está cartografiada — "
                              "explora otra tarea, u ofrece una MEJORA (tope que "
                              "muerda la línea base con umbral >10% mejor)")
                return quejas
        repe = _ya_medida(p)
        if repe and "+" in repe:
            quejas.append(f"esa carrera ya acumula dos ciclos veredictados ({repe}): "
                          "el surco está agotado — cambia nivel, tarea o topes")
        elif repe:
            quejas.append(f"esa carrera con esa métrica ya está medida y veredictada "
                          f"({repe}): cambia algún mando o la métrica — repetirla no "
                          "informa")
    return quejas


def construir_comando(c: dict, etiqueta: str) -> list[str]:
    """La plantilla fija: lo ÚNICO que una propuesta puede ejecutar."""
    cmd = [sys.executable, "-u", str(RAIZ / "scripts" / "correr_banco.py"),
           "--nivel", c["nivel"], "--cerebro", c.get("cerebro", "gguf"),
           "--modo", "lista", "--etiqueta", etiqueta]
    if c.get("tarea"):
        cmd += ["--tarea", c["tarea"]]
    for mando in RANGOS:
        if c.get(mando) is not None:
            cmd += [f"--{mando.replace('_', '-')}", str(c[mando])]
    return cmd


def _medido_por_tarea() -> dict[str, list[str]]:
    """tarea → métricas ya veredictadas, leído de los ciclos cerrados."""
    import os
    dir_ciclos = Path(os.environ.get("MG_CICLOS", RAIZ / "registros" / "ciclos"))
    medido: dict[str, list[str]] = {}
    for f in sorted(dir_ciclos.glob("C*.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        cmd = (c.get("medicion") or {}).get("comando") or ""
        met = (c.get("prediccion") or {}).get("metrica")
        if not (c.get("veredicto") and cmd and met):
            continue
        m_niv, m_tar = re.search(r"--nivel (\S+)", cmd), re.search(r"--tarea (\S+)", cmd)
        if m_niv:
            clave = m_niv.group(1) + "/" + (m_tar.group(1) if m_tar else "*")
            if met not in medido.setdefault(clave, []):
                medido[clave].append(met)
    return medido


def _sin_medir() -> list[str]:
    """Las combinaciones tarea:métrica que aún no tienen veredicto."""
    medido = _medido_por_tarea()
    faltan = []
    for d in sorted((RAIZ / "banco").iterdir()):
        if not d.is_dir():
            continue
        for t in sorted(x.name for x in d.iterdir() if (x / "tarea.json").exists()):
            clave = f"{d.name}/{t}"
            for met in ("tokens_media", "segundos_media"):
                if met not in (medido.get(clave) or []):
                    faltan.append(f"{clave}:{met}")
    return faltan


def _contexto_para_proponer() -> str:
    horizonte = (RAIZ / "docs" / "horizonte.md")
    trozos = []
    if horizonte.exists():
        trozos.append("== HORIZONTE (extracto) ==\n" +
                      horizonte.read_text(encoding="utf-8")[:2500])
    import os
    dir_ciclos = Path(os.environ.get("MG_CICLOS", RAIZ / "registros" / "ciclos"))
    cerrados = sorted(dir_ciclos.glob("C*.json"),
                      key=lambda p: int(p.stem[1:]) if p.stem[1:].isdigit() else 0)
    lecciones = []
    for p in cerrados[-3:]:
        c = json.loads(p.read_text(encoding="utf-8"))
        # CIFRAS ESTRUCTURADAS, no prosa recortada: la vuelta real 3 (2026-08-25) murió
        # rumiando porque el recorte a 500 caracteres de la lección de C31 le comió el
        # dato «con tope 1.500» y el modelo no podía cuadrar el fallo con el número.
        pred, med = c.get("prediccion") or {}, c.get("medicion") or {}
        ficha = {"id": c["id"], "pregunta": c["pregunta"][:200],
                 "predicho": f"{pred.get('metrica')} {pred.get('espero')}",
                 "medido": med.get("cifras"),
                 "comando": (med.get("comando") or "")[-160:],
                 "confirma": (c.get("veredicto") or {}).get("confirma")}
        # Una lección con <think> dentro es un registro dañado (le pasó a C32).
        if c.get("leccion") and "<think>" not in c["leccion"]:
            ficha["leccion"] = c["leccion"][:400]
        lecciones.append(json.dumps(ficha, ensure_ascii=False))
    if lecciones:
        trozos.append("== ÚLTIMOS CICLOS (cifras exactas; el comando lleva los topes "
                      "usados) ==\n" + "\n".join(lecciones))
    # el mapa del banco: para que «variar la carrera» tenga a dónde ir
    niveles = {d.name: sorted(t.name for t in d.iterdir()
                              if (t / "tarea.json").exists())
               for d in sorted((RAIZ / "banco").iterdir()) if d.is_dir()}
    trozos.append("== EL BANCO (niveles y tareas medibles) ==\n"
                  + json.dumps(niveles, ensure_ascii=False))
    # lo ya medido, para no proponerlo a ciegas: la vuelta 13 quemó sus dos intentos
    # repitiendo la combinación de C42 porque no tenía esta lista delante
    medido = _medido_por_tarea()
    trozos.append("== YA MEDIDO (repetir tarea+métrica se rechaza; n3/lista está "
                  "agotada) ==\n" + json.dumps(medido, ensure_ascii=False))
    # LÍNEAS BASE por tarea: la racha de 4 refutaciones del 2026-08-26 (C45-C48) fue
    # un solo sesgo repetido — predecir segundos ignorando lo ya medido (tres: <800
    # cuando C44 midió 922,8; aguja: <900 cuando C41 midió 2.290). El umbral se ancla
    # aquí o se está adivinando.
    # se alimenta de los registros de CARRERA (llevan cifras POR TAREA, también en las
    # corridas agregadas), no de los ciclos: la tabla anterior solo veía carreras de
    # tarea única y dejó a C51 anclar cadena a ciegas (<600 con 953 medidos en C25)
    lineas: dict[str, dict] = {}
    dir_reg = Path(os.environ.get("MG_REGISTROS", RAIZ / "registros"))
    for f in sorted(dir_reg.glob("*.json")):
        try:
            r_ = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not (isinstance(r_, dict) and r_.get("cerebro") == "gguf"):
            continue
        for t in r_.get("tareas") or []:
            if t.get("id"):
                lineas[f"{r_.get('nivel')}/{t['id']}"] = {
                    "tokens": t.get("tokens_salida"), "segundos": t.get("segundos")}
    trozos.append("== LÍNEAS BASE (última medición por tarea; ancla ahí tus umbrales "
                  "de segundos y tokens, con 15-30% de margen) ==\n"
                  + json.dumps(lineas, ensure_ascii=False))
    # el COMPLEMENTO explícito: dos vueltas seguidas murieron (2026-08-26 20:07)
    # re-proponiendo lo ya medido pese a la lista de arriba — elegir de un menú de lo
    # virgen es más fácil que restar dos listas mentalmente
    trozos.append("== SIN MEDIR — ELIGE DE AQUÍ (proponer lo ya medido se rechaza) ==\n"
                  + ", ".join(_sin_medir()))
    return "\n\n".join(trozos)


SISTEMA_PROPONENTE = """Eres el proponente del ciclo de investigación de Mekro-Genai.
Tu único trabajo: proponer la SIGUIENTE hipótesis medible sobre el banco, a partir del
horizonte y de las últimas lecciones. No repitas una hipótesis ya medida.

Tu ÚNICA palanca son los mandos de la carrera (nivel, tarea, cerebro, topes). NO
propongas mecanismos que ninguna bandera activa —foco, gramática, otro prompt—: aún no
existen y la carrera no los mediría (lección de C32). Y el suelo de ruido medido de
tokens_media y segundos_media entre carreras es ~10 %: fija umbrales con ≥15 % de margen
sobre el baseline, o predice sobre tareas_pct / intervenciones, que son discretas. Una
carrera+métrica ya medida se rechaza a máquina: cambia algún mando o la métrica.

TUS MEJORAS SE ADOPTAN SOLAS (M3): si propones un tope_tokens que MUERDA la línea base
de la tarea (menor que su uso registrado) y la carrera confirma 100 % con ≥10 % menos
tokens, ese mando pasa a ser el defecto oficial de la tarea (registros/adopciones.json)
y la puntuación del banco mejora por tu hallazgo. Es la clase de propuesta más valiosa
que puedes hacer.

Elige UNA hipótesis y escríbela: los campos son para AFIRMAR, no para deliberar. Cada
campo de texto va en 2-4 frases y menos de 400 caracteres; un JSON que rumie dudas
dentro de un campo se rechaza por longitud.
Responde SOLO con un JSON, sin nada alrededor, con esta forma exacta:
{"pregunta": "...", "revision": "qué se sabe ya y de dónde", "metrica": "una de
tareas_pct|tokens_media|entrada_media|cache_pct|segundos_media|intervenciones", "umbral": "<1200",
"porque": "la aritmética o el mecanismo que justifica el umbral",
"carrera": {"nivel": "n0|n1|n2|n3", "tarea": "opcional", "cerebro": "gguf",
"tope_vueltas": 16, "tope_tokens": 3000, "tope_segundos": 5400}}"""


def proponer_con_cerebro() -> dict:
    from genai.cerebro.base import Mensaje
    from genai.cerebro.local_gguf import CerebroGGUF
    cerebro = CerebroGGUF()
    mensajes = [Mensaje("sistema", SISTEMA_PROPONENTE),
                Mensaje("usuario", _contexto_para_proponer() +
                        "\n\nPropón la siguiente hipótesis. Solo el JSON.")]
    for intento in range(2):
        # pensar=False (convención enable_thinking de Qwen3): dos vueltas reales
        # murieron con 2.048 tokens de deliberación sin llegar jamás al JSON. Para
        # emitir una estructura ya decidida, el think es un impuesto, no una ayuda.
        r = cerebro.generar(mensajes, max_tokens=1024, pensar=False)
        m = re.search(r"\{.*\}", r.texto, re.DOTALL)
        if m:
            try:
                p = json.loads(m.group(0))
            except json.JSONDecodeError as e:
                p, quejas = None, [f"JSON inválido: {e}"]
            else:
                quejas = validar(p)
            if p is not None and not quejas:
                return p
        else:
            quejas = ["no hay ningún JSON en la respuesta"]
        # sin esto no hay post-mortem: la vuelta 2 real falló dos intentos y no quedó
        # NI UN byte de lo que el modelo respondió.
        volcado = RAIZ / "logs" / f"lazo-intento-{intento + 1}.txt"
        volcado.write_text(f"QUEJAS: {'; '.join(quejas)}\n\nRAZONAMIENTO:\n"
                           f"{r.razonamiento}\n\nTEXTO:\n{r.texto}\n"
                           f"[parada: {r.motivo_parada} · {r.uso.tokens_salida} tok]",
                           encoding="utf-8")
        # el volcado del 2026-08-26 20:46 enseñó el modo de fallo exacto: el modelo
        # IDENTIFICA el hueco correcto en su revisión («migrar no está medido en
        # tokens») y aun así elige el lado ya medido. A un desliz de selección se le
        # responde con un menú concreto, no con una regla general.
        opciones = _sin_medir()[:3]
        mensajes += [Mensaje("asistente", r.texto),
                     Mensaje("usuario", "Propuesta rechazada: " + "; ".join(quejas) +
                             ". Elige EXACTAMENTE una de estas combinaciones sin "
                             f"medir: {', '.join(opciones)}. Solo el JSON.")]
    print("el proponente no dio una propuesta válida en 2 intentos: "
          + "; ".join(quejas) + " (intentos crudos en logs/lazo-intento-*.txt)")
    # 2 y no SystemExit(cadena): la cadena sale con código 1 y el supervisor lo
    # confundía con un freno del vigilante — se apagó entero el 2026-08-26 09:16.
    raise SystemExit(2)


def leccion_del_veredicto(cid: str, propuesta: dict) -> str:
    """En frío la trae la propuesta; en real la escribe el cerebro viendo el veredicto."""
    if propuesta.get("leccion"):
        return propuesta["leccion"]
    import os
    dir_ciclos = Path(os.environ.get("MG_CICLOS", RAIZ / "registros" / "ciclos"))
    c = json.loads((dir_ciclos / f"{cid}.json").read_text(encoding="utf-8"))
    from genai.cerebro.base import Mensaje
    from genai.cerebro.local_gguf import CerebroGGUF
    r = CerebroGGUF().generar([
        Mensaje("sistema", "Escribes la lección de un ciclo de investigación ya medido. "
                           "Di si CONFIRMA o REFUTA, el número contra el umbral, la "
                           "causa más probable y qué medir después. 5-8 frases, sin "
                           "adornos, con cifras. Escríbela DIRECTAMENTE, sin razonar "
                           "largo antes."),
        Mensaje("usuario", json.dumps({k: c[k] for k in
                                       ("pregunta", "prediccion", "medicion")},
                                      ensure_ascii=False)[:6000]),
    ], max_tokens=1024, pensar=False)
    # La primera lección real (C32) salió contaminada: un <think> sin cerrar —cortado
    # por el tope— se coló entero a CONTINUIDAD. El razonamiento cerrado ya lo separa
    # el cerebro; aquí se descarta el que quedó abierto, y sin prosa no se inventa.
    texto = r.texto.strip()
    if "<think>" in texto:
        texto = texto.split("</think>")[-1].strip() if "</think>" in texto else ""
    return texto or ("(el redactor gastó el turno en razonamiento y no dejó prosa: "
                     "lección pendiente de revisión humana)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--propuesta", help="fichero JSON: modo frío, sin cerebro")
    ap.add_argument("--umbral-racha", type=int, default=4)
    a = ap.parse_args()

    # freno 1: el vigilante
    r = _ciclo("racha", str(a.umbral_racha))
    print(r.stdout.strip())
    if r.returncode != 0:
        return 1
    # freno 2: nada a medias
    if "ningún ciclo en curso" not in _ciclo("estado").stdout:
        print("hay un ciclo a medias: el lazo no abre otro. Ciérralo o retíralo.")
        return 1

    if a.propuesta:
        p = json.loads(Path(a.propuesta).read_text(encoding="utf-8"))
        quejas = validar(p)
        if quejas:
            print("propuesta inválida: " + "; ".join(quejas))
            return 2
    else:
        p = proponer_con_cerebro()

    cid = siguiente_id()
    print(f"── {cid} · {p['pregunta'][:100]}")
    for paso in (("abrir", cid, p["pregunta"]), ("revisar", cid, p["revision"]),
                 ("predecir", cid, p["metrica"], str(p["umbral"]),
                  "--porque", p["porque"])):
        r = _ciclo(*paso)
        if r.returncode != 0:
            print(f"{paso[0]} falló: {r.stdout} {r.stderr}")
            return 2

    cmd = construir_comando(p["carrera"], etiqueta=f"lazo-{cid}")
    print("── medición:", " ".join(cmd[2:]))
    r = _ciclo("medir", cid, "--", *cmd)
    print(r.stdout[-1200:])
    if r.returncode != 0 and "CIFRA" not in r.stdout:
        print("la medición no dio cifras: el ciclo queda a medias para revisión.")
        return 2

    r = _ciclo("veredicto", cid, "--leccion", leccion_del_veredicto(cid, p))
    print(r.stdout[:600])
    # M3: tras cada veredicto, la adopción pasa sola — victorias limpias, causales y
    # dentro de presupuesto se convierten en el defecto oficial (adopcion.py, con sus
    # cuatro reglas de honestidad y su vigilante de reversión)
    import adopcion
    for a in adopcion.adoptar_desde_ciclos():
        print(f"★ ADOPTADO {a['tarea']}: {a['mandos']} — {a['metrica']} {a['valor']} "
              f"({a['mejora_pct']}% mejor que la base, {a['ciclo']})")
    return r.returncode


if __name__ == "__main__":
    raise SystemExit(main())

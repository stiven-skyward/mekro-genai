"""La página de la interfaz: un único HTML autocontenido, sin framework ni build.

Mismo espíritu que `genai/compartir.py` —HTML+CSS+JS a mano, cero dependencias— pero
servida en vivo por `genai/servidor.py` en vez de exportada a fichero. No hay React, no
hay npm, no hay paso de compilación: es exactamente lo que este proyecto puede mantener
con una sola persona y sin añadir un ecosistema de JavaScript a un arnés que hasta ahora
no tenía ni una dependencia de bibliteca estándar de más.

**Por qué sondeo y no WebSockets/SSE.** Con un cerebro que tarda segundos o minutos por
vuelta, sondear `/sesiones/<id>` y `/transcripcion` cada 1,5 s es indistinguible de un
canal de eventos de verdad, y evita mantener una conexión abierta —con su propia
reconexión, sus propios fallos— para ganar una latencia que aquí nadie va a notar.

**Por qué la clave se recibe embebida y no se pide en una pantalla de login.** El
servidor solo escucha en 127.0.0.1; quien ya alcanza este puerto en esta máquina ya
tiene el mismo acceso que ver la página. Pedir login ahí sería teatro, no seguridad —lo
real, «solo local no es solo tuyo» en una máquina compartida, ya lo cubre la clave en
cada llamada posterior.
"""

PAGINA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mekro-Genai</title>
<style>
:root{--fondo:#fbfbfa;--panel:#fff;--borde:#e3e3df;--texto:#1a1a19;--tenue:#6b6b66;
--acento:#3d5afe;--mal:#c1121f;--bien:#0a7d33;--usuario:#eef2ff;--herr:#f5f5f3}
@media (prefers-color-scheme: dark){
:root{--fondo:#161614;--panel:#1d1b18;--borde:#2e2c28;--texto:#e8e6e3;--tenue:#9a978f;
--acento:#8fa4ff;--mal:#ff6b6b;--bien:#5ed88a;--usuario:#1c2333;--herr:#201e1a}}
*{box-sizing:border-box}
body{margin:0;background:var(--fondo);color:var(--texto);height:100vh;overflow:hidden;
font:14px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
#app{display:flex;height:100vh}
#lateral{width:260px;flex:none;border-right:1px solid var(--borde);
display:flex;flex-direction:column;background:var(--panel)}
#lateral header{padding:.9rem;border-bottom:1px solid var(--borde);
display:flex;justify-content:space-between;align-items:center}
#lateral h1{font-size:.95rem;margin:0}
#sesiones{overflow-y:auto;flex:1}
.fila-s{padding:.6rem .9rem;border-bottom:1px solid var(--borde);cursor:pointer;
font-size:.85rem}
.fila-s:hover{background:var(--herr)}
.fila-s.activa{background:var(--usuario)}
.fila-s .titulo{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.fila-s .meta{color:var(--tenue);font-size:.75rem;margin-top:.15rem}
.punto{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:.3rem}
.punto.viva{background:var(--bien)}.punto.libre{background:var(--tenue)}
button{font:inherit;cursor:pointer;border:1px solid var(--borde);background:var(--panel);
color:var(--texto);border-radius:6px;padding:.4rem .7rem}
button:hover{border-color:var(--acento)}
button.primario{background:var(--acento);color:#fff;border-color:var(--acento)}
#principal{flex:1;display:flex;flex-direction:column;min-width:0}
#cabecera{padding:.7rem 1rem;border-bottom:1px solid var(--borde);
display:flex;gap:.6rem;align-items:center;background:var(--panel)}
#transcript{flex:1;overflow-y:auto;padding:1rem}
.msg{max-width:52rem;margin:0 auto .8rem;border:1px solid var(--borde);
border-radius:10px;padding:.6rem .85rem}
.msg.usuario{background:var(--usuario)}.msg.herramienta{background:var(--herr)}
.rol{font-size:.68rem;text-transform:uppercase;letter-spacing:.06em;color:var(--tenue);
margin-bottom:.3rem}
pre{white-space:pre-wrap;word-wrap:break-word;margin:.3rem 0;
font:12.5px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace}
.llamada{border-left:3px solid var(--acento);padding-left:.6rem;margin:.4rem 0}
#form{border-top:1px solid var(--borde);padding:.7rem 1rem;background:var(--panel)}
#form .fila{display:flex;gap:.5rem;margin-bottom:.5rem}
#encargo{flex:1;resize:vertical;min-height:2.4rem;font:inherit;padding:.5rem;
border:1px solid var(--borde);border-radius:6px;background:var(--fondo);color:var(--texto)}
select{font:inherit;padding:.35rem;border:1px solid var(--borde);border-radius:6px;
background:var(--fondo);color:var(--texto)}
#vacio{margin:auto;color:var(--tenue);text-align:center;max-width:26rem}
.modal-fondo{position:fixed;inset:0;background:rgba(0,0,0,.4);display:flex;
align-items:center;justify-content:center;z-index:10}
.modal{background:var(--panel);border:1px solid var(--borde);border-radius:10px;
padding:1.2rem;max-width:32rem}
.modal pre{background:var(--herr);padding:.5rem;border-radius:6px}
.aviso{color:var(--mal);font-size:.8rem}
#ajustes{position:fixed;inset:0;background:rgba(0,0,0,.35);display:none;
align-items:center;justify-content:center;z-index:9}
#ajustes .caja{background:var(--panel);border-radius:10px;padding:1.2rem;width:26rem;
max-width:90vw;max-height:80vh;overflow-y:auto}
#ajustes label{display:block;font-size:.8rem;color:var(--tenue);margin:.6rem 0 .2rem}
#ajustes input{width:100%;padding:.4rem;border:1px solid var(--borde);border-radius:6px;
background:var(--fondo);color:var(--texto);font:inherit}
.fila-clave{display:flex;justify-content:space-between;padding:.3rem 0;font-size:.85rem}
</style>
</head>
<body>
<div id="app">
  <div id="lateral">
    <header><h1>Mekro-Genai</h1><button id="btn-nueva" title="Nueva sesión">+</button></header>
    <div id="sesiones"></div>
    <div style="padding:.6rem;border-top:1px solid var(--borde)">
      <button id="btn-ajustes" style="width:100%">⚙ Ajustes</button>
    </div>
  </div>
  <div id="principal">
    <div id="vacio">Elige una sesión de la izquierda, o crea una nueva.<br><br>
      Esto es un cliente más de <code>genai/servidor.py</code> — lo mismo que hablan la
      extensión de VS Code y cualquier cliente MCP.</div>
  </div>
</div>

<div id="ajustes">
  <div class="caja">
    <h2 style="margin-top:0">Ajustes</h2>
    <h3>Cerebros</h3>
    <div id="info-cerebros"></div>
    <h3>Claves de proveedores</h3>
    <div id="lista-claves"></div>
    <label>Proveedor (gemini, openai, anthropic…)</label>
    <input id="in-proveedor" placeholder="gemini">
    <label>Clave</label>
    <input id="in-clave" type="password" placeholder="...">
    <div style="margin-top:.6rem;display:flex;gap:.5rem">
      <button class="primario" id="btn-guardar-clave">Guardar</button>
      <button id="btn-cerrar-ajustes">Cerrar</button>
    </div>
    <p style="color:var(--tenue);font-size:.75rem">
      Se guarda en ~/.config/genai/claves.json (permisos 600). Esta pantalla nunca
      muestra una clave ya guardada, solo si existe.</p>
  </div>
</div>

<script>
const CLAVE = "__CLAVE__";
async function api(ruta, opciones) {
  const r = await fetch(ruta, {...opciones,
    headers: {...(opciones && opciones.headers), "X-Genai-Clave": CLAVE,
              "Content-Type": "application/json"}});
  if (!r.ok) { const d = await r.json().catch(() => ({})); throw new Error(d.error || r.statusText); }
  return r.json();
}

let actual = null, cerebros = null;

async function refrescarSesiones() {
  const {sesiones} = await api("/sesiones");
  const cont = document.getElementById("sesiones");
  cont.innerHTML = "";
  for (const s of sesiones) {
    const d = document.createElement("div");
    d.className = "fila-s" + (s.id === actual ? " activa" : "");
    d.innerHTML = `<div class="titulo"><span class="punto ${s.viva ? "viva" : "libre"}"></span>${
      esc(s.titulo)}</div><div class="meta">${s.vueltas || 0} vueltas · ${s.id}</div>`;
    d.onclick = () => abrir(s.id);
    cont.appendChild(d);
  }
}

function esc(t) { const d = document.createElement("div"); d.textContent = t || ""; return d.innerHTML; }

async function abrir(id) {
  actual = id;
  document.getElementById("vacio").remove?.();
  const p = document.getElementById("principal");
  p.innerHTML = `
    <div id="cabecera">
      <select id="sel-cerebro"></select>
      <select id="sel-modo">
        <option value="preguntar">preguntar</option>
        <option value="lista">lista</option>
        <option value="plan">plan</option>
        <option value="todo">todo (sin frenos)</option>
      </select>
      <span id="estado-tarea" style="color:var(--tenue);font-size:.8rem"></span>
    </div>
    <div id="transcript"></div>
    <div id="form">
      <div class="fila">
        <textarea id="encargo" placeholder="¿Qué le encargas al agente?"></textarea>
        <button class="primario" id="btn-lanzar">Lanzar</button>
      </div>
    </div>`;
  await cargarCerebros();
  document.getElementById("btn-lanzar").onclick = lanzar;
  refrescarSesiones();
  sondear();
}

async function cargarCerebros() {
  if (!cerebros) cerebros = await api("/cerebros");
  const sel = document.getElementById("sel-cerebro");
  sel.innerHTML = "";
  if (cerebros.local.disponible) sel.innerHTML += `<option value="gguf">gguf (local)</option>`;
  sel.innerHTML += `<option value="eco">eco (pruebas, sin modelo)</option>`;
  for (const p of cerebros.configurados)
    sel.innerHTML += `<option value="nube:${p}">nube:${p}</option>`;
  if (cerebros.suscripciones.copilot.startsWith("listo"))
    sel.innerHTML += `<option value="nube:copilot">nube:copilot</option>`;
  if (cerebros.suscripciones.google.startsWith("listo"))
    sel.innerHTML += `<option value="nube:google">nube:google</option>`;
}

async function lanzar() {
  const encargo = document.getElementById("encargo").value.trim();
  if (!encargo) return;
  const cerebro = document.getElementById("sel-cerebro").value;
  const modo = document.getElementById("sel-modo").value;
  document.getElementById("encargo").value = "";
  try {
    const r = await api(`/sesiones/${actual}/lanzar`, {method: "POST",
      body: JSON.stringify({encargo, cerebro, modo})});
    if (!r.ok) alert(r.mensaje);
  } catch (e) { alert(e.message); }
}

let temporizador = null, permisoAbierto = false;
function sondear() {
  clearTimeout(temporizador);
  const bucle = async () => {
    if (actual === null) return;
    try {
      const s = await api(`/sesiones/${actual}`);
      document.getElementById("estado-tarea").textContent =
        s.en_curso ? "corriendo…" : (s.motivo ? `terminó: ${s.motivo}` : "");
      if (s.pregunta_pendiente && !permisoAbierto) mostrarPermiso(s.pregunta_pendiente);
      const tr = await api(`/sesiones/${actual}/transcripcion`);
      pintarTranscripcion(tr);
    } catch (e) { /* la sesión pudo cerrarse; se reintenta */ }
    temporizador = setTimeout(bucle, 1500);
  };
  bucle();
}

function pintarTranscripcion(tr) {
  const c = document.getElementById("transcript");
  if (!c) return;
  if (!tr.mensajes || !tr.mensajes.length) {
    c.innerHTML = `<p style="color:var(--tenue)">${esc(tr.aviso || "sin mensajes todavía")}</p>`;
    return;
  }
  c.innerHTML = tr.mensajes.map(m => {
    let cuerpo = m.contenido ? `<pre>${esc(m.contenido)}</pre>` : "";
    for (const ll of (m.llamadas || []))
      cuerpo += `<div class="llamada"><pre>${esc(ll.nombre)}(${esc(JSON.stringify(ll.argumentos))})</pre></div>`;
    return `<div class="msg ${esc(m.rol)}"><div class="rol">${esc(m.rol)}</div>${cuerpo}</div>`;
  }).join("");
  c.scrollTop = c.scrollHeight;
}

function mostrarPermiso(p) {
  permisoAbierto = true;
  const d = document.createElement("div");
  d.className = "modal-fondo";
  d.innerHTML = `<div class="modal">
    <h3>¿Permitir esta acción?</h3>
    <pre>${esc(p.herramienta)}(${esc(JSON.stringify(p.argumentos, null, 1))})</pre>
    <div style="display:flex;gap:.6rem;margin-top:.8rem">
      <button class="primario" id="btn-si">Permitir</button>
      <button id="btn-no">Denegar</button>
    </div></div>`;
  document.body.appendChild(d);
  const responder = async (permitido) => {
    await api(`/sesiones/${actual}/responder`, {method: "POST", body: JSON.stringify({permitido})});
    d.remove(); permisoAbierto = false;
  };
  d.querySelector("#btn-si").onclick = () => responder(true);
  d.querySelector("#btn-no").onclick = () => responder(false);
}

document.getElementById("btn-nueva").onclick = async () => {
  const titulo = prompt("¿Qué vas a hacer en esta sesión?") || "";
  const s = await api("/sesiones", {method: "POST", body: JSON.stringify({titulo})});
  await refrescarSesiones();
  abrir(s.id);
};

document.getElementById("btn-ajustes").onclick = async () => {
  cerebros = await api("/cerebros");
  const claves = await api("/claves");
  document.getElementById("info-cerebros").innerHTML =
    `local: ${cerebros.local.disponible ? "✓ " + esc(cerebros.local.ruta) : "✗ no encontrado"}<br>` +
    `Copilot: ${esc(cerebros.suscripciones.copilot)}<br>` +
    `Google: ${esc(cerebros.suscripciones.google)}`;
  document.getElementById("lista-claves").innerHTML =
    Object.entries(claves).map(([p, v]) =>
      `<div class="fila-clave"><span>${esc(p)}</span><span>${v.configurada ? "✓" : "—"}</span></div>`
    ).join("") || "<p style='color:var(--tenue)'>ninguna clave guardada todavía</p>";
  document.getElementById("ajustes").style.display = "flex";
};
document.getElementById("btn-cerrar-ajustes").onclick = () =>
  document.getElementById("ajustes").style.display = "none";
document.getElementById("btn-guardar-clave").onclick = async () => {
  const proveedor = document.getElementById("in-proveedor").value.trim();
  const clave = document.getElementById("in-clave").value.trim();
  if (!proveedor || !clave) return;
  await api("/claves", {method: "POST", body: JSON.stringify({proveedor, clave})});
  document.getElementById("in-proveedor").value = "";
  document.getElementById("in-clave").value = "";
  cerebros = null;
  document.getElementById("btn-ajustes").onclick();
};

refrescarSesiones();
setInterval(refrescarSesiones, 4000);
</script>
</body>
</html>
"""

/**
 * Mekro-Genai dentro de VS Code.
 *
 * **Qué es y qué no.** Esto NO reimplementa el arnés: habla con el servidor de sesiones
 * (`genai sesiones servir`) por HTTP, que es justo para lo que existe la separación
 * cliente/servidor. Todo el arnés —permisos, herramientas, cerebros— sigue en un solo
 * sitio, y el editor es un cliente más.
 *
 * **Por qué la tarea se lanza en una TERMINAL y no dentro de la extensión.** El modo
 * `preguntar` para antes de cada acción peligrosa y espera un sí o un no. Ese diálogo
 * vive en la terminal. Meterlo en una ventana del editor sin haberlo pensado bien
 * llevaría, tarde o temprano, a que alguien lo desactive «porque molesta» y acabe
 * ejecutando cosas sin mirar. Así que la extensión ve y lanza; el agente corre donde
 * sus frenos funcionan.
 *
 * **La clave se lee del disco, del mismo sitio donde el servidor la escribe.** No se
 * pide al usuario ni se guarda en la configuración de VS Code, que se sincroniza entre
 * máquinas.
 */
const vscode = require("vscode");
const http = require("http");
const fs = require("fs");
const os = require("os");
const path = require("path");

const FICHERO_CLAVE = path.join(os.homedir(), ".config", "genai", "servidor.clave");

function clave() {
  try {
    return fs.readFileSync(FICHERO_CLAVE, "utf8").trim();
  } catch {
    return "";
  }
}

function puerto() {
  return vscode.workspace.getConfiguration("mekro").get("puerto", 7654);
}

/** Una petición al servidor local. Devuelve el JSON o lanza con un motivo legible. */
function pedir(ruta, cuerpo) {
  return new Promise((resolver, rechazar) => {
    const datos = cuerpo === undefined ? null : JSON.stringify(cuerpo);
    const pet = http.request(
      {
        host: "127.0.0.1",
        port: puerto(),
        path: ruta,
        method: datos ? "POST" : "GET",
        timeout: 10000,
        headers: {
          "X-Genai-Clave": clave(),
          "Content-Type": "application/json",
          ...(datos ? { "Content-Length": Buffer.byteLength(datos) } : {}),
        },
      },
      (res) => {
        let b = "";
        res.on("data", (t) => (b += t));
        res.on("end", () => {
          let d;
          try {
            d = JSON.parse(b);
          } catch {
            return rechazar(new Error(`respuesta ilegible del servidor: ${b.slice(0, 120)}`));
          }
          if (res.statusCode === 401) {
            return rechazar(
              new Error("el servidor rechazó la clave. ¿Es el de otra máquina o de otro usuario?")
            );
          }
          if (res.statusCode >= 400) {
            return rechazar(new Error(d.error || `el servidor respondió ${res.statusCode}`));
          }
          resolver(d);
        });
      }
    );
    pet.on("timeout", () => pet.destroy(new Error("el servidor no contestó en 10 s")));
    pet.on("error", (e) =>
      rechazar(
        new Error(
          e.code === "ECONNREFUSED"
            ? `no hay servidor en 127.0.0.1:${puerto()}. Levántalo con: genai sesiones servir`
            : `no se pudo hablar con el servidor: ${e.message}`
        )
      )
    );
    if (datos) pet.write(datos);
    pet.end();
  });
}

function raiz() {
  const c = vscode.workspace.workspaceFolders;
  return c && c.length ? c[0].uri.fsPath : undefined;
}

async function elegirSesion() {
  const { sesiones } = await pedir("/sesiones");
  if (!sesiones.length) {
    vscode.window.showInformationMessage(
      "No hay sesiones. Crea una con: genai sesiones nueva \"lo que vas a hacer\""
    );
    return undefined;
  }
  const elegida = await vscode.window.showQuickPick(
    sesiones.map((s) => ({
      label: s.titulo,
      description: s.viva ? "$(circle-filled) activa" : s.rancia ? "rancia" : "libre",
      detail: `${s.id} · ${s.vueltas || 0} vueltas`,
      s,
    })),
    { placeHolder: "Sesiones de este proyecto" }
  );
  return elegida && elegida.s;
}

async function cmdSesiones() {
  const s = await elegirSesion();
  if (!s) return;
  // Se avisa de lo que el candado de sesión NO impide, igual que hace la terminal:
  // dos agentes pueden editar el mismo fichero y eso no lo evita ningún candado.
  const { conflictos } = await pedir("/conflictos");
  const choque = conflictos.filter((c) => c.sesiones.includes(s.id));
  if (choque.length) {
    vscode.window.showWarningMessage(
      `Otra sesión viva está tocando: ${choque.map((c) => c.fichero).join(", ")}`
    );
  }
  vscode.window.showInformationMessage(
    `${s.titulo} · ${s.viva ? "activa" : "libre"} · ${s.vueltas || 0} vueltas · ${s.id}`
  );
}

async function cmdTranscripcion() {
  const s = await elegirSesion();
  if (!s) return;
  const tr = await pedir(`/sesiones/${s.id}/transcripcion`);
  if (!tr.mensajes || !tr.mensajes.length) {
    return vscode.window.showInformationMessage(
      tr.aviso || "esa sesión aún no ha guardado transcripción"
    );
  }
  const doc = await vscode.workspace.openTextDocument({
    language: "markdown",
    content:
      `# ${s.titulo}\n\n_${s.id} · ${tr.vueltas || 0} vueltas_\n\n` +
      tr.mensajes
        .map((m) => {
          const llamadas = (m.llamadas || [])
            .map((l) => "```\n" + l.nombre + "(" + JSON.stringify(l.argumentos) + ")\n```")
            .join("\n");
          return `### ${m.rol}\n\n${m.contenido || ""}\n\n${llamadas}`;
        })
        .join("\n\n---\n\n"),
  });
  await vscode.window.showTextDocument(doc, { preview: false });
}

async function cmdTarea() {
  const dir = raiz();
  if (!dir) {
    return vscode.window.showErrorMessage("Abre una carpeta: el agente trabaja sobre un proyecto.");
  }
  const peticion = await vscode.window.showInputBox({
    prompt: "¿Qué le encargas al agente?",
    placeHolder: "arregla lo que falle en prueba.py",
  });
  if (!peticion) return;
  const cfg = vscode.workspace.getConfiguration("mekro");
  // En una TERMINAL a propósito: el modo `preguntar` para antes de cada acción
  // peligrosa y espera respuesta, y ese diálogo vive ahí.
  const term = vscode.window.createTerminal({ name: "Mekro-Genai", cwd: dir });
  term.show();
  term.sendText(
    `genai tarea ${JSON.stringify(peticion)} ` +
      `--cerebro ${cfg.get("cerebro", "gguf")} --modo ${cfg.get("modo", "preguntar")}`
  );
}

function envolver(fn) {
  return async () => {
    try {
      await fn();
    } catch (e) {
      vscode.window.showErrorMessage(`Mekro-Genai: ${e.message}`);
    }
  };
}

function activate(ctx) {
  ctx.subscriptions.push(
    vscode.commands.registerCommand("mekro.sesiones", envolver(cmdSesiones)),
    vscode.commands.registerCommand("mekro.transcripcion", envolver(cmdTranscripcion)),
    vscode.commands.registerCommand("mekro.tarea", envolver(cmdTarea))
  );
}

function deactivate() {}

module.exports = { activate, deactivate, pedir, clave };

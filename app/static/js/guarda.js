const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let mode = "entrada";
let scanner = null;
const resultCard = document.getElementById("result");
const resultBody = document.getElementById("result-body");

function setMode(m) {
  mode = m;
  document.getElementById("mode-entrada").classList.toggle("active", m === "entrada");
  document.getElementById("mode-salida").classList.toggle("active", m === "salida");
}
document.getElementById("mode-entrada").onclick = () => setMode("entrada");
document.getElementById("mode-salida").onclick = () => setMode("salida");

function show(html) {
  resultBody.innerHTML = html;
  resultCard.classList.remove("hidden");
}

async function submitScan(payload) {
  const r = await fetch("/api/scan", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({...payload, action: mode})});
  const j = await r.json();
  if (r.ok && j.ok) {
    const v = j.visit;
    show('<p class="alert ok">' + esc(j.message) + '</p>' +
      '<p><strong>' + esc(v.visitor_name) + '</strong> (' + esc(v.visitor_role) + ')<br>' +
      esc(v.subject) + '<br>Torre ' + esc(v.tower) + ' · Apto ' + esc(v.apartment) +
      (v.id_number ? '<br>ID: ' + esc(v.id_number) : '') + '</p>');
    setTimeout(() => location.reload(), 2500);
  } else {
    show('<p class="alert error">' + esc(j.detail || "Error") + '</p>');
  }
}

// La cámara no sabe si el QR es de visita o de paquete: lo resuelve el servidor por la firma
async function enviarCamara(token) {
  const r = await fetch("/api/scan/qr", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({token, action: mode})});
  const j = await r.json();
  if (!r.ok || !j.ok) {
    show('<p class="alert error">' + esc(j.detail || "Error") + '</p>');
    return;
  }
  if (j.tipo === "paquete") {
    renderPaquete(j, resultBody);
    resultCard.classList.remove("hidden");
  } else {
    const v = j.visit;
    show('<p class="alert ok">' + esc(j.message) + '</p>' +
      '<p><strong>' + esc(v.visitor_name) + '</strong> (' + esc(v.visitor_role) + ')<br>' +
      esc(v.subject) + '<br>Torre ' + esc(v.tower) + ' · Apto ' + esc(v.apartment) +
      (v.id_number ? '<br>ID: ' + esc(v.id_number) : '') + '</p>');
    setTimeout(() => location.reload(), 2500);
  }
}

function renderPaquete(j, box) {
  box.innerHTML =
    '<img src="' + j.package.photo_data_uri + '" class="pkg-preview" alt="Foto del paquete">' +
    '<p><strong>' + esc(j.residente.nombre) + '</strong> · Torre ' + esc(j.residente.tower) + ' · ' + esc(j.residente.apartment) +
    (j.package.description ? '<br>' + esc(j.package.description) : '') + '</p>' +
    '<button id="btn-entregar" type="button">Marcar entregado</button>';
  enlazarEntregar(j.package.uuid, box, "Paquete entregado. El residente debe confirmar en su app.");
}

function renderTercero(p, box) {
  box.innerHTML =
    '<img src="' + p.photo_data_uri + '" class="pkg-preview" alt="Foto del paquete">' +
    (p.cedula_data_uri ? '<img src="' + p.cedula_data_uri + '" class="pkg-preview" alt="Foto de la cédula">' : '') +
    '<p><strong>' + esc(p.nombre_tercero) + '</strong> · C.C. ' + esc(p.cedula_tercero) +
    (p.description ? '<br>' + esc(p.description) : '') + '</p>' +
    '<button id="btn-entregar" type="button">Marcar entregado</button>';
  enlazarEntregar(p.uuid, box, "Paquete entregado.");
}

function enlazarEntregar(uuid, box, mensajeOk) {
  document.getElementById("btn-entregar").addEventListener("click", async () => {
    const r2 = await fetch("/api/packages/" + uuid + "/entregar", {method: "POST"});
    const j2 = await r2.json();
    if (r2.ok && j2.ok) {
      box.innerHTML = '<p class="alert ok">' + esc(mensajeOk) + '</p>';
      setTimeout(() => location.reload(), 2500);
    } else {
      box.innerHTML = '<p class="alert error">' + esc(j2.detail || "Error") + '</p>';
    }
  });
}

document.getElementById("token-form").addEventListener("submit", e => {
  e.preventDefault();
  const raw = document.getElementById("token-input").value.trim();
  // corto (≤8 caracteres, sin puntos) se manda como código; el resto, como pase firmado
  const esCorto = raw.length <= 8 && !raw.includes(".");
  const payload = esCorto ? {code: raw.toUpperCase()} : {token: raw};
  submitScan(payload);
  document.getElementById("token-input").value = "";
});

document.getElementById("btn-cam").addEventListener("click", async () => {
  if (scanner) return;
  try {
    scanner = new Html5Qrcode("reader");
    await scanner.start({facingMode: "environment"}, {fps: 10, qrbox: 250}, text => {
      scanner.pause(true);
      enviarCamara(text.trim());
      setTimeout(() => scanner.resume(), 2500);
    });
    document.getElementById("btn-cam").disabled = true;
  } catch (err) {
    show('<p class="alert error">No se pudo iniciar la cámara. Usa el código pegado o la entrada manual.</p>');
    scanner = null;
  }
});

document.getElementById("manual-form").addEventListener("submit", async e => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.target).entries());
  const r = await fetch("/api/visits/manual", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
  const j = await r.json();
  if (r.ok && j.ok) {
    show('<p class="alert ok">' + esc(j.message) + ': ' + esc(j.visit.visitor_name) + ' → Torre ' + esc(j.visit.tower) + ' · Apto ' + esc(j.visit.apartment) + '</p>');
    e.target.reset();
    setTimeout(() => location.reload(), 2500);
  } else {
    show('<p class="alert error">' + esc(j.detail || "Error") + '</p>');
  }
});

// --- Paquetes ---------------------------------------------------------------

let pkgFotoB64 = null;
let pkgCedulaB64 = null;
const pkgInput = document.getElementById("pkg-residente");
const pkgResultados = document.getElementById("pkg-resultados");
const pkgResidentId = document.getElementById("pkg-resident-id");
const pkgPreview = document.getElementById("pkg-preview");
const pkgEsTercero = document.getElementById("pkg-es-tercero");
const pkgBloqueResidente = document.getElementById("pkg-bloque-residente");
const pkgBloqueTercero = document.getElementById("pkg-bloque-tercero");
const pkgFotoCedula = document.getElementById("pkg-foto-cedula");
const pkgCedulaPreview = document.getElementById("pkg-cedula-preview");
let debounceId = null;

pkgEsTercero.addEventListener("change", () => {
  const tercero = pkgEsTercero.checked;
  pkgBloqueResidente.classList.toggle("hidden", tercero);
  pkgBloqueTercero.classList.toggle("hidden", !tercero);
});

function comprimirFoto(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const max = 1000;
      let w = img.width, h = img.height;
      if (w > h && w > max) { h = Math.round(h * max / w); w = max; }
      else if (h > max) { w = Math.round(w * max / h); h = max; }
      const canvas = document.createElement("canvas");
      canvas.width = w; canvas.height = h;
      canvas.getContext("2d").drawImage(img, 0, 0, w, h);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL("image/jpeg", 0.7));
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("El navegador no pudo leer la foto. Si tu cámara guarda en HEIC, elige la opción Cámara y configura formato JPEG, o selecciona una foto de la galería."));
    };
    img.src = url;
  });
}

async function cargarFoto(input, preview, setter) {
  const file = input.files[0];
  if (!file) return;
  setter(null);
  preview.classList.add("hidden");
  try {
    const b64 = await comprimirFoto(file);
    setter(b64);
    preview.src = b64;
    preview.classList.remove("hidden");
  } catch (err) { alert(err.message); }
}

document.getElementById("pkg-foto").addEventListener("change", e => cargarFoto(e.target, pkgPreview, b64 => { pkgFotoB64 = b64; }));
pkgFotoCedula.addEventListener("change", e => cargarFoto(e.target, pkgCedulaPreview, b64 => { pkgCedulaB64 = b64; }));

pkgInput.addEventListener("input", () => {
  pkgResidentId.value = "";
  clearTimeout(debounceId);
  debounceId = setTimeout(async () => {
    const q = pkgInput.value.trim();
    if (q.length < 2) { pkgResultados.innerHTML = ""; return; }
    const r = await fetch("/api/residentes?q=" + encodeURIComponent(q));
    if (!r.ok) return;
    const j = await r.json();
    pkgResultados.innerHTML = j.residentes.length
      ? j.residentes.map(r => '<button type="button" class="small" data-id="' + r.id + '" data-nombre="' + esc(r.nombre) + '" data-destino="' + esc("T" + (r.tower || "?") + " · " + (r.apartment || "?")) + '">' + esc(r.nombre) + " (" + esc(r.username) + ") · T" + esc(r.tower || "?") + " · " + esc(r.apartment || "?") + "</button>").join("")
      : '<p class="hint">Sin resultados. Pide a administración que registre al residente.</p>';
  }, 300);
});

pkgResultados.addEventListener("click", e => {
  const btn = e.target.closest("[data-id]");
  if (!btn) return;
  pkgResidentId.value = btn.dataset.id;
  pkgInput.value = btn.dataset.nombre + " · " + btn.dataset.destino;
  pkgResultados.innerHTML = "";
});

document.getElementById("pkg-form").addEventListener("submit", async e => {
  e.preventDefault();
  const okBox = document.getElementById("pkg-registro-ok");
  if (pkgEsTercero.checked) {
    const nombre = document.getElementById("pkg-tercero-nombre").value.trim();
    const cedula = document.getElementById("pkg-tercero-cedula").value.trim();
    if (!nombre || !cedula) { alert("Nombre y cédula del destinatario son obligatorios"); return; }
    if (!pkgFotoB64) { alert("Toma la foto del paquete"); return; }
    if (!pkgCedulaB64) { alert("Toma la foto de la cédula"); return; }
    const r = await fetch("/api/packages/manual", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
      nombre, cedula,
      description: document.getElementById("pkg-desc").value,
      photo_b64: pkgFotoB64,
      cedula_b64: pkgCedulaB64,
    })});
    const j = await r.json();
    if (r.ok && j.ok) {
      okBox.innerHTML = '<p class="alert ok">Paquete registrado para <strong>' + esc(j.package.nombre_tercero) + '</strong> (C.C. ' + esc(j.package.cedula_tercero) + '). Sin QR: se entrega comparando la cédula. Administración recibió la alerta.</p>';
      e.target.reset();
      pkgFotoB64 = null;
      pkgCedulaB64 = null;
      pkgPreview.classList.add("hidden");
      pkgCedulaPreview.classList.add("hidden");
      pkgResidentId.value = "";
      pkgInput.value = "";
      pkgEsTercero.checked = false;
      pkgEsTercero.dispatchEvent(new Event("change"));
    } else {
      okBox.innerHTML = '<p class="alert error">' + esc(j.detail || "Error registrando el paquete") + '</p>';
    }
    return;
  }

  if (!pkgResidentId.value) { alert("Selecciona el residente de la lista"); return; }
  if (!pkgFotoB64) { alert("Toma la foto del paquete"); return; }
  const r = await fetch("/api/packages", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
    resident_id: parseInt(pkgResidentId.value, 10),
    description: document.getElementById("pkg-desc").value,
    photo_b64: pkgFotoB64,
  })});
  const j = await r.json();
  if (r.ok && j.ok) {
    okBox.innerHTML = '<p class="alert ok">Paquete registrado con código <strong>' + esc(j.package.short_code) + '</strong>. El residente ya lo ve en su app.</p>';
    e.target.reset();
    pkgFotoB64 = null;
    pkgPreview.classList.add("hidden");
    pkgResidentId.value = "";
    pkgInput.value = "";
  } else {
    okBox.innerHTML = '<p class="alert error">' + esc(j.detail || "Error registrando el paquete") + '</p>';
  }
});

document.getElementById("pkg-scan-form").addEventListener("submit", async e => {
  e.preventDefault();
  const code = document.getElementById("pkg-code").value.trim().toUpperCase();
  document.getElementById("pkg-code").value = "";
  const box = document.getElementById("pkg-entrega");
  const r = await fetch("/api/packages/scan", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({code})});
  const j = await r.json();
  if (!r.ok || !j.ok) { box.innerHTML = '<p class="alert error">' + esc(j.detail || "Error") + '</p>'; return; }
  renderPaquete(j, box);
});

document.getElementById("tercero-form").addEventListener("submit", async e => {
  e.preventDefault();
  const q = document.getElementById("tercero-q").value.trim();
  const resultados = document.getElementById("tercero-resultados");
  const r = await fetch("/api/packages/terceros?q=" + encodeURIComponent(q));
  const j = await r.json();
  if (!r.ok || !j.ok) { resultados.innerHTML = '<p class="alert error">' + esc(j.detail || "Error") + '</p>'; return; }
  if (!j.paquetes.length) {
    resultados.innerHTML = '<p class="hint">Sin paquetes de no registrados que coincidan.</p>';
    return;
  }
  resultados.innerHTML = j.paquetes.map(p =>
    '<button type="button" class="small" data-tercero="' + p.uuid + '">' + esc(p.nombre_tercero) + " · C.C. " + esc(p.cedula_tercero) + (p.description ? " · " + esc(p.description) : "") + "</button>"
  ).join("");
  resultados.querySelectorAll("[data-tercero]").forEach(btn => btn.addEventListener("click", () => {
    const p = j.paquetes.find(x => x.uuid === btn.dataset.tercero);
    renderTercero(p, resultados);
  }));
});

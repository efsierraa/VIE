// Común de portería: funciones compartidas por Ingresos y Paquetes
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const resultCard = document.getElementById("result");
const resultBody = document.getElementById("result-body");

function show(html) {
  if (!resultBody || !resultCard) return;
  resultBody.innerHTML = html;
  resultCard.classList.remove("hidden");
}

async function submitScan(payload) {
  const r = await fetch("/api/scan", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({...payload, action: mode})});
  const j = await r.json();
  if (r.ok && j.ok) {
    const v = j.visit;
    const quien = v.visitor_nombres
      ? '<strong>Nombres: ' + esc(v.visitor_nombres) + '</strong> · Apellidos: ' + esc(v.visitor_apellidos) + ' (' + esc(v.visitor_role) + ')'
      : '<strong>' + esc(v.visitor_name) + '</strong> (' + esc(v.visitor_role) + ')';
    show('<p class="alert ok">' + esc(j.message) + '</p>' +
      '<p>' + quien + '<br>' +
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
    const quien = v.visitor_nombres
      ? '<strong>Nombres: ' + esc(v.visitor_nombres) + '</strong> · Apellidos: ' + esc(v.visitor_apellidos) + ' (' + esc(v.visitor_role) + ')'
      : '<strong>' + esc(v.visitor_name) + '</strong> (' + esc(v.visitor_role) + ')';
    show('<p class="alert ok">' + esc(j.message) + '</p>' +
      '<p>' + quien + '<br>' +
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
  enlazarEntregar(
    j.package.uuid,
    box,
    "Paquete entregado. El residente debe confirmar en su app.",
    "¿Confirmas que entregaste el paquete a " + j.residente.nombre + " (Torre " + j.residente.tower + " · " + j.residente.apartment + ")?"
  );
}

function renderTercero(p, box) {
  const quien = p.tercero_nombres
    ? '<strong>Nombres: ' + esc(p.tercero_nombres) + '</strong> · Apellidos: ' + esc(p.tercero_apellidos)
    : '<strong>' + esc(p.nombre_tercero) + '</strong>';
  const nombreCompleto = p.tercero_nombres ? p.tercero_nombres + " " + p.tercero_apellidos : p.nombre_tercero;
  box.innerHTML =
    '<img src="' + p.photo_data_uri + '" class="pkg-preview" alt="Foto del paquete">' +
    '<p>' + quien +
    (p.description ? '<br>' + esc(p.description) : '') + '</p>' +
    '<label>Cédula de quien reclama (se cotejan nombres y apellidos con la cédula física)' +
    '<input id="tercero-cedula" maxlength="30" inputmode="numeric" autocomplete="off"></label>' +
    '<button id="btn-entregar" type="button">Marcar entregado</button>';
  document.getElementById("btn-entregar").addEventListener("click", async () => {
    const cedula = document.getElementById("tercero-cedula").value.trim();
    if (!cedula) { alert("Digita el número de cédula de quien reclama"); return; }
    if (!confirm("¿Confirmas que entregaste el paquete a " + nombreCompleto + " (cédula " + cedula + ")?")) return;
    const r2 = await fetch("/api/packages/" + p.uuid + "/entregar", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({cedula})});
    const j2 = await r2.json();
    if (r2.ok && j2.ok) {
      box.innerHTML = '<p class="alert ok">Paquete entregado. Cédula registrada como evidencia.</p>';
      setTimeout(() => location.reload(), 2500);
    } else {
      box.innerHTML = '<p class="alert error">' + esc(j2.detail || "Error") + '</p>';
    }
  });
}

function enlazarEntregar(uuid, box, mensajeOk, confirmMsg) {
  document.getElementById("btn-entregar").addEventListener("click", async () => {
    if (confirmMsg && !confirm(confirmMsg)) return;
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

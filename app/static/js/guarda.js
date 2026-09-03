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
      submitScan({token: text.trim()});
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
const pkgInput = document.getElementById("pkg-residente");
const pkgResultados = document.getElementById("pkg-resultados");
const pkgResidentId = document.getElementById("pkg-resident-id");
const pkgPreview = document.getElementById("pkg-preview");
let debounceId = null;

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
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("No se pudo leer la imagen")); };
    img.src = url;
  });
}

document.getElementById("pkg-foto").addEventListener("change", async e => {
  const file = e.target.files[0];
  if (!file) return;
  pkgFotoB64 = null;
  pkgPreview.classList.add("hidden");
  try {
    pkgFotoB64 = await comprimirFoto(file);
    pkgPreview.src = pkgFotoB64;
    pkgPreview.classList.remove("hidden");
  } catch (err) { alert(err.message); }
});

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
  if (!pkgResidentId.value) { alert("Selecciona el residente de la lista"); return; }
  if (!pkgFotoB64) { alert("Toma la foto del paquete"); return; }
  const r = await fetch("/api/packages", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
    resident_id: parseInt(pkgResidentId.value, 10),
    description: document.getElementById("pkg-desc").value,
    photo_b64: pkgFotoB64,
  })});
  const j = await r.json();
  const okBox = document.getElementById("pkg-registro-ok");
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
  box.innerHTML =
    '<img src="' + j.package.photo_data_uri + '" class="pkg-preview" alt="Foto del paquete">' +
    '<p><strong>' + esc(j.residente.nombre) + '</strong> · Torre ' + esc(j.residente.tower) + ' · ' + esc(j.residente.apartment) +
    (j.package.description ? '<br>' + esc(j.package.description) : '') + '</p>' +
    '<button id="btn-entregar" type="button">Marcar entregado</button>';
  document.getElementById("btn-entregar").addEventListener("click", async () => {
    const r2 = await fetch("/api/packages/" + j.package.uuid + "/entregar", {method: "POST"});
    const j2 = await r2.json();
    if (r2.ok && j2.ok) {
      box.innerHTML = '<p class="alert ok">Paquete entregado. El residente debe confirmar en su app.</p>';
      setTimeout(() => location.reload(), 2500);
    } else {
      box.innerHTML = '<p class="alert error">' + esc(j2.detail || "Error") + '</p>';
    }
  });
});

// Paquetes: registrar (residente o no registrado) y entregar
let pkgFotoB64 = null;
const pkgInput = document.getElementById("pkg-residente");
const pkgResultados = document.getElementById("pkg-resultados");
const pkgResidentId = document.getElementById("pkg-resident-id");
const pkgPreview = document.getElementById("pkg-preview");
const pkgEsTercero = document.getElementById("pkg-es-tercero");
const pkgBloqueResidente = document.getElementById("pkg-bloque-residente");
const pkgBloqueTercero = document.getElementById("pkg-bloque-tercero");
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
    const torre = document.getElementById("pkg-tercero-torre").value.trim().toUpperCase();
    const apto = document.getElementById("pkg-tercero-apto").value.trim();
    if (!nombre) { alert("Digita el nombre del destinatario (el de la etiqueta del paquete)"); return; }
    if (!torre || !apto) { alert("Torre y apartamento son obligatorios: vienen en la etiqueta del paquete"); return; }
    if (!pkgFotoB64) { alert("Toma la foto del paquete"); return; }
    const r = await fetch("/api/packages/manual", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
      nombre,
      tower: torre, apartment: apto,
      description: document.getElementById("pkg-desc").value,
      photo_b64: pkgFotoB64,
    })});
    const j = await r.json();
    if (r.ok && j.ok) {
      okBox.innerHTML = '<p class="alert ok">Paquete registrado para <strong>' + esc(j.package.nombre_tercero) + '</strong> · T' + esc(j.package.tower) + ' · ' + esc(j.package.apartment) + '. Sin QR: al reclamar se coteja el nombre con la cédula. Administración recibió la alerta.</p>';
      e.target.reset();
      pkgFotoB64 = null;
      pkgPreview.classList.add("hidden");
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
  buscarPaquete(code);
});

function buscarPaquete(payload) {
  const box = document.getElementById("pkg-entrega");
  fetch("/api/packages/scan", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(payload)})
    .then(r => r.json())
    .then(j => {
      if (!j.ok) { box.innerHTML = '<p class="alert error">' + esc(j.detail || "Error") + '</p>'; return; }
      renderPaquete(j, box);
    })
    .catch(() => { box.innerHTML = '<p class="alert error">Error de conexión</p>'; });
}

// Cámara dedicada a los QR de paquetes de esta sección
let escanerPkg = null;
document.getElementById("btn-cam-pkg").addEventListener("click", async () => {
  if (escanerPkg) return;
  const box = document.getElementById("pkg-entrega");
  try {
    escanerPkg = new Html5Qrcode("reader-pkg");
    await escanerPkg.start({facingMode: "environment"}, {fps: 10, qrbox: 250}, text => {
      escanerPkg.pause(true);
      buscarPaquete({token: text.trim()});
      setTimeout(() => escanerPkg.resume(), 2500);
    });
    document.getElementById("btn-cam-pkg").disabled = true;
  } catch (err) {
    box.innerHTML = '<p class="alert error">No se pudo iniciar la cámara. Digita el código del paquete.</p>';
    escanerPkg = null;
  }
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
    '<button type="button" class="small" data-tercero="' + p.uuid + '">' + esc(p.nombre_tercero) + (p.description ? " · " + esc(p.description) : "") + "</button>"
  ).join("");
  resultados.querySelectorAll("[data-tercero]").forEach(btn => btn.addEventListener("click", () => {
    const p = j.paquetes.find(x => x.uuid === btn.dataset.tercero);
    renderTercero(p, resultados);
  }));
});

// Ingresos: escáner, modos y entrada manual
let mode = "entrada";
let scanner = null;

function setMode(m) {
  mode = m;
  document.getElementById("mode-entrada").classList.toggle("active", m === "entrada");
  document.getElementById("mode-salida").classList.toggle("active", m === "salida");
}
document.getElementById("mode-entrada").onclick = () => setMode("entrada");
document.getElementById("mode-salida").onclick = () => setMode("salida");

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
    const v = j.visit;
    const texto = "Pase de ingreso VIE\n" +
      "Visitante: " + v.visitor_name + "\n" +
      "Asunto: " + v.subject + "\n" +
      "Torre " + v.tower + " — Apto " + v.apartment + "\n" +
      "Código para portería: " + v.short_code + "\n" +
      "Vigente 1 hora. Un solo uso.";
    const btnWa = v.visitor_celular
      ? '<button type="button" class="button" id="btn-wa-manual">Enviar por WhatsApp</button>'
      : "";
    show('<p class="alert ok">' + esc(j.message) + '. Entrega el pase al visitante:</p>' +
      '<div class="qr-box"><img src="' + j.qr_data_uri + '" alt="QR del pase"></div>' +
      '<p class="short-code">Código para portería: <strong>' + esc(v.short_code) + '</strong></p>' +
      '<p class="hint">El pase es válido por 1 hora: sirve para marcar la salida y, si nadie la marca, se marca sola al vencer. Para visitas más largas, un residente debe registrarlo.</p>' +
      '<div class="row">' + btnWa + '<a class="button" download="pase-vie-' + esc(v.short_code) + '.png" href="' + j.qr_data_uri + '">Descargar QR</a></div>');
    e.target.reset();
    if (v.visitor_celular) {
      document.getElementById("btn-wa-manual").addEventListener("click", () => compartirPase(j.qr_data_uri, texto, "pase-vie-" + v.short_code + ".png"));
    }
  } else {
    show('<p class="alert error">' + esc(j.detail || "Error") + '</p>');
  }
});

// Ver y reenviar el pase de una visita activa (pendiente o dentro)
const paseCard = document.getElementById("pase-card");
if (paseCard) {
  document.querySelectorAll("[data-verqr]").forEach(btn => btn.addEventListener("click", async () => {
    const r = await fetch("/api/visits/" + btn.dataset.verqr + "/pass");
    const j = await r.json();
    if (!(r.ok && j.ok)) { alert(j.detail || "No se pudo abrir el pase"); return; }
    const v = j.visit;
    document.getElementById("pase-img").src = j.qr_data_uri;
    document.getElementById("pase-codigo").textContent = v.short_code;
    document.getElementById("pase-descargar").href = j.qr_data_uri;
    document.getElementById("pase-descargar").download = "pase-vie-" + v.short_code + ".png";
    const wa = document.getElementById("pase-wa");
    if (v.visitor_celular) {
      const texto = "Pase de ingreso VIE\n" +
        "Visitante: " + v.visitor_name + "\n" +
        "Asunto: " + v.subject + "\n" +
        "Torre " + v.tower + " — Apto " + v.apartment + "\n" +
        "Código para portería: " + v.short_code + "\n" +
        "Un solo uso.";
      wa.classList.remove("hidden");
      wa.onclick = () => compartirPase(j.qr_data_uri, texto, "pase-vie-" + v.short_code + ".png");
    } else {
      wa.classList.add("hidden");
    }
    paseCard.classList.remove("hidden");
    paseCard.scrollIntoView({behavior: "smooth"});
  }));
}

// Edición de ingresos manuales (gracia de 1 hora)
const editCard = document.getElementById("edit-visita-card");
const editForm = document.getElementById("edit-visita-form");
if (editCard && editForm) {
  document.querySelectorAll("[data-editar-visita]").forEach(btn => btn.addEventListener("click", () => {
    editForm.dataset.uuid = btn.dataset.editarVisita;
    document.getElementById("edit-v-nombres").value = btn.dataset.nombres || "";
    document.getElementById("edit-v-apellidos").value = btn.dataset.apellidos || "";
    document.getElementById("edit-v-asunto").value = btn.dataset.asunto || "";
    document.getElementById("edit-v-id").value = btn.dataset.idnum || "";
    document.getElementById("edit-v-cel").value = btn.dataset.cel || "";
    document.getElementById("edit-v-rol").value = btn.dataset.rol || "visitante";
    document.getElementById("edit-v-torre").value = btn.dataset.torre || "";
    document.getElementById("edit-v-apto").value = btn.dataset.apto || "";
    editCard.classList.remove("hidden");
    editCard.scrollIntoView({behavior: "smooth"});
  }));
  editForm.addEventListener("submit", async e => {
    e.preventDefault();
    const r = await fetch("/api/visits/" + editForm.dataset.uuid + "/editar", {method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
      visitor_nombres: document.getElementById("edit-v-nombres").value.trim(),
      visitor_apellidos: document.getElementById("edit-v-apellidos").value.trim(),
      subject: document.getElementById("edit-v-asunto").value,
      id_number: document.getElementById("edit-v-id").value,
      visitor_celular: document.getElementById("edit-v-cel").value,
      visitor_role: document.getElementById("edit-v-rol").value,
      tower: document.getElementById("edit-v-torre").value,
      apartment: document.getElementById("edit-v-apto").value,
    })});
    const j = await r.json();
    if (r.ok && j.ok) location.reload();
    else alert(j.detail || "Error editando la visita");
  });
}

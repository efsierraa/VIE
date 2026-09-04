if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/static/sw.js").catch(() => {});
  });
}

// Cerrar el menú flotante al tocar fuera de él
document.addEventListener("click", (e) => {
  const menu = document.querySelector(".menu-flotante");
  if (menu && !menu.contains(e.target)) {
    const toggle = document.getElementById("menu-toggle");
    if (toggle) toggle.checked = false;
  }
});

// Cerrar tarjetas: botón ✕ (esquina superior derecha) y tecla Esc
function cerrarTarjeta(card) {
  if (!card) return;
  card.classList.add("desvaneciendo");
  setTimeout(() => {
    card.classList.add("hidden");
    card.classList.remove("desvaneciendo");
  }, 150);
}

document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-cerrar]");
  if (!btn) return;
  if (btn.hasAttribute("data-recargar")) { location.reload(); return; }
  cerrarTarjeta(document.getElementById(btn.dataset.cerrar));
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  document.querySelectorAll(".card:not(.hidden)").forEach((card) => {
    if (card.querySelector("[data-cerrar]")) cerrarTarjeta(card);
  });
});

// Volver a la página desde donde se vino (Acerca de, etc.); si no hay historial, al inicio
document.addEventListener("click", (e) => {
  if (!e.target.closest("[data-volver]")) return;
  if (history.length > 1) history.back();
  else location.href = "/";
});

// Ojo dentro del campo para mostrar/ocultar la clave
const OJO = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/></svg>';
const OJO_TACHADO = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';

// --- Envío del pase por WhatsApp, directo al número registrado ---
// 1) copia la imagen del pase al portapapeles; 2) abre el chat del número
// registrado con el texto precargado: al pegarla, imagen y texto van juntos.
function dataUriToFile(dataUri, filename) {
  const [meta, b64] = dataUri.split(",");
  const mime = meta.match(/data:(.*?);/)[1];
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new File([bytes], filename, {type: mime});
}

async function enviarPaseWhatsapp(numero, qrDataUri, texto, nombreArchivo) {
  const chat = "https://wa.me/" + numero + "?text=" + encodeURIComponent(texto);
  let copiada = false;
  try {
    const archivo = dataUriToFile(qrDataUri, nombreArchivo);
    await navigator.clipboard.write([new ClipboardItem({"image/png": archivo})]);
    copiada = true;
  } catch (err) {}
  window.open(chat, "_blank");
  if (copiada) {
    alert("Abrimos el chat de " + numero + " con el texto listo. La imagen quedó copiada: pégala en el chat (Ctrl+V o mantener pulsado → Pegar) y envías todo junto.");
  } else {
    const enlace = document.createElement("a");
    enlace.href = qrDataUri;
    enlace.download = nombreArchivo;
    enlace.click();
    alert("Abrimos el chat de " + numero + " con el texto listo. Tu navegador no pudo copiar la imagen: te descargamos el QR, adjúntalo al mensaje y envía todo junto.");
  }
}

document.querySelectorAll("input[type=password]").forEach(inp => {
  const campo = document.createElement("span");
  campo.className = "pw-field";
  inp.replaceWith(campo);
  campo.appendChild(inp);

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "pw-eye";
  btn.title = "Mostrar clave";
  btn.setAttribute("aria-label", "Mostrar clave");
  btn.innerHTML = OJO_TACHADO; // oculta = ojo cerrado
  btn.addEventListener("click", () => {
    const oculta = inp.type === "password";
    inp.type = oculta ? "text" : "password";
    btn.innerHTML = oculta ? OJO : OJO_TACHADO; // visible = ojo abierto
    const texto = oculta ? "Ocultar clave" : "Mostrar clave";
    btn.title = texto;
    btn.setAttribute("aria-label", texto);
  });
  campo.appendChild(btn);
});

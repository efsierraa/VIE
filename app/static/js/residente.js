const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const form = document.getElementById("visit-form");
const result = document.getElementById("result");

function dataUriToFile(dataUri, filename) {
  const [meta, b64] = dataUri.split(",");
  const mime = meta.match(/data:(.*?);/)[1];
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new File([bytes], filename, {type: mime});
}

function mostrarPase(j) {
  document.getElementById("qr-img").src = j.qr_data_uri;
  document.getElementById("token").textContent = j.token;
  document.getElementById("short-code").textContent = j.visit.short_code;
  const nota = document.getElementById("pase-nota");
  if (j.visit.status === "dentro") {
    nota.textContent = "La visita ya ingresó. El QR sigue sirviendo para marcar la salida, y puedes compartir el pase para mostrar la información en portería.";
    nota.classList.remove("hidden");
  } else {
    nota.textContent = "";
    nota.classList.add("hidden");
  }
  const dl = document.getElementById("btn-download");
  dl.href = j.qr_data_uri;
  dl.download = "pase-vie-" + j.visit.short_code + ".png";
  const v = j.visit;
  const text = "Pase de ingreso VIE\n" +
    "Visitante: " + v.visitor_name + "\n" +
    "Asunto: " + v.subject + "\n" +
    "Torre " + v.tower + " — Apto " + v.apartment + "\n" +
    "Código para portería: " + v.short_code + "\n" +
    "Un solo uso.";
  document.getElementById("btn-share").onclick = async () => {
    let compartido = false;
    try {
      const file = dataUriToFile(j.qr_data_uri, "pase-vie-" + v.short_code + ".png");
      if (navigator.canShare && navigator.canShare({files: [file]})) {
        await navigator.share({files: [file], title: "Pase VIE", text});
        compartido = true;
      }
    } catch (err) {
      if (err && err.name === "AbortError") return;
    }
    if (compartido) return;
    try {
      await navigator.share({title: "Pase VIE", text});
    } catch (err) {
      if (err && err.name === "AbortError") return;
      navigator.clipboard.writeText(text);
      alert("Tu navegador no permite compartir la imagen desde aquí. Descarga el QR, adjúntalo en WhatsApp y pega el texto (ya quedó copiado).");
    }
  };
  result.classList.remove("hidden");
  result.scrollIntoView({behavior: "smooth"});
}

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(form).entries());
  data.hours = parseInt(data.hours, 10);
  const r = await fetch("/api/visits", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
  const j = await r.json();
  if (!r.ok) { alert(j.detail || "Error creando la visita"); return; }
  mostrarPase(j);
  form.reset();
});

document.querySelectorAll("[data-verqr]").forEach(btn => btn.addEventListener("click", async () => {
  const r = await fetch("/api/visits/" + btn.dataset.verqr + "/pass");
  const j = await r.json();
  if (r.ok && j.ok) mostrarPase(j);
  else alert(j.detail || "No se pudo abrir el pase");
}));

document.querySelectorAll("[data-pkgqr]").forEach(btn => btn.addEventListener("click", () => {
  const img = document.getElementById("pkgqr-" + btn.dataset.pkgqr);
  if (img) img.classList.toggle("hidden");
}));

document.querySelectorAll("[data-confirmar]").forEach(btn => btn.addEventListener("click", async () => {
  const fila = btn.closest("tr");
  const codigo = fila && fila.querySelector("strong") ? fila.querySelector("strong").textContent.trim() : "";
  if (!confirm("¿Confirmas que recibiste el paquete " + codigo + "? Esta acción no se puede deshacer.")) return;
  const r = await fetch("/api/packages/" + btn.dataset.confirmar + "/confirmar", {method: "POST"});
  if (r.ok) location.reload();
  else { const j = await r.json(); alert(j.detail || "Error"); }
}));

document.querySelectorAll("[data-disputar]").forEach(btn => btn.addEventListener("click", async () => {
  if (!confirm("¿Confirmas que NO recibiste este paquete? Administración lo revisará.")) return;
  const r = await fetch("/api/packages/" + btn.dataset.disputar + "/disputar", {method: "POST"});
  if (r.ok) location.reload();
  else { const j = await r.json(); alert(j.detail || "Error"); }
}));

document.getElementById("btn-copy").onclick = () => {
  navigator.clipboard.writeText(document.getElementById("short-code").textContent);
};

document.querySelectorAll("[data-cancel]").forEach(btn => btn.addEventListener("click", async () => {
  const fila = btn.closest("tr");
  const codigo = fila && fila.querySelector("strong") ? fila.querySelector("strong").textContent.trim() : "";
  if (!confirm("¿Cancelar la visita con código " + codigo + "? El QR dejará de funcionar y no se puede recuperar.")) return;
  const r = await fetch("/api/visits/" + btn.dataset.cancel + "/cancel", {method: "POST"});
  if (r.ok) location.reload();
  else { const j = await r.json(); alert(j.detail || "No se pudo cancelar"); }
}));

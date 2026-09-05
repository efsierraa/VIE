const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

const pisInput = document.getElementById("pis-residente");
const pisResultados = document.getElementById("pis-resultados");
const pisResidentId = document.getElementById("pis-resident-id");
const pisSeleccionado = document.getElementById("pis-seleccionado");

let consulta = 0;
pisInput.addEventListener("input", () => {
  const q = pisInput.value.trim();
  pisResidentId.value = "";
  pisSeleccionado.textContent = "";
  if (q.length < 2) { pisResultados.innerHTML = ""; return; }
  const id = ++consulta;
  setTimeout(async () => {
    if (id !== consulta) return;
    const r = await fetch("/api/residentes?q=" + encodeURIComponent(q));
    if (!r.ok || id !== consulta) return;
    const j = await r.json();
    pisResultados.innerHTML = j.residentes.length
      ? j.residentes.map(r => '<button type="button" class="small" data-id="' + r.id + '" data-nombre="' + esc(r.nombre) + '" data-destino="' + esc("T" + (r.tower || "?") + " · " + (r.apartment || "?")) + '">' + esc(r.nombre) + " (" + esc(r.username) + ") · T" + esc(r.tower || "?") + " · " + esc(r.apartment || "?") + "</button>").join("")
      : '<p class="hint">Sin resultados. Solo entran residentes: pide a administración que registre la cuenta.</p>';
  }, 300);
});

pisResultados.addEventListener("click", e => {
  const btn = e.target.closest("[data-id]");
  if (!btn) return;
  pisResidentId.value = btn.dataset.id;
  pisInput.value = btn.dataset.nombre + " · " + btn.dataset.destino;
  pisSeleccionado.textContent = "Seleccionado: " + btn.dataset.nombre + " · " + btn.dataset.destino;
  document.getElementById("pis-padrino-muestra").value = btn.dataset.nombre + " · " + btn.dataset.destino;
  pisResultados.innerHTML = "";
});

function seleccionado() {
  if (!pisResidentId.value) { alert("Busca y selecciona el residente"); return null; }
  return parseInt(pisResidentId.value, 10);
}

document.getElementById("btn-ingreso-adulto").addEventListener("click", async () => {
  const rid = seleccionado();
  if (rid === null) return;
  const r = await fetch("/api/piscina/ingreso", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({resident_id: rid})});
  const j = await r.json();
  if (r.ok && j.ok) location.reload();
  else alert(j.detail || "Error registrando la entrada");
});

document.getElementById("btn-ingreso-nino").addEventListener("click", async () => {
  const rid = seleccionado();
  if (rid === null) return;
  const nombre = document.getElementById("pis-nino-nombre").value.trim();
  const edadTxt = document.getElementById("pis-nino-edad").value.trim();
  if (!nombre) { alert("Digita el nombre del niño"); return; }
  const r = await fetch("/api/piscina/ingreso-nino", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
    acompanante_id: rid,
    ninos: [{nombre, edad: edadTxt === "" ? null : parseInt(edadTxt, 10)}],
  })});
  const j = await r.json();
  if (r.ok && j.ok) location.reload();
  else alert(j.detail || "Error registrando la entrada del niño");
});

document.getElementById("btn-ingreso-invitado").addEventListener("click", async () => {
  const rid = seleccionado();
  if (rid === null) return;
  const nombre = document.getElementById("pis-invitado-nombre").value.trim();
  if (!nombre) { alert("Digita el nombre del invitado"); return; }
  const nino = document.getElementById("pis-inv-nino").value.trim();
  const edadTxt = document.getElementById("pis-inv-nino-edad").value.trim();
  const ninos = nino ? [{nombre: nino, edad: edadTxt === "" ? null : parseInt(edadTxt, 10)}] : [];
  const r = await fetch("/api/piscina/ingreso-invitado", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
    nombre,
    padrino_id: rid,
    ninos,
  })});
  const j = await r.json();
  if (r.ok && j.ok) location.reload();
  else alert(j.detail || "Error registrando la entrada del invitado");
});

// Salida: el niño nunca sale solo — el botón del acompañante cierra al grupo
document.querySelectorAll("[data-salir]").forEach(btn => btn.addEventListener("click", async () => {
  const ninos = btn.dataset.ninos || "";
  const mensaje = ninos
    ? "¿Sale " + btn.dataset.persona + " con " + ninos + "? Todos quedan fuera de la piscina."
    : "¿Marcar la salida de " + btn.dataset.persona + " de la piscina?";
  if (!confirm(mensaje)) return;
  const r = await fetch("/api/piscina/salida/" + btn.dataset.salir, {method: "POST"});
  const j = await r.json();
  if (r.ok && j.ok) { alert(j.message); location.reload(); }
  else alert(j.detail || "Error registrando la salida");
}));

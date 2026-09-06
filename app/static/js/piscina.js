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

function filaNino() {
  const div = document.createElement("div");
  div.className = "row fila-nino";
  div.innerHTML =
    '<label>Nombres <input class="nino-nombres" maxlength="40" placeholder="Ej: Ana Sofía"></label>' +
    '<label>Apellidos <input class="nino-apellidos" maxlength="40" placeholder="Ej: Pérez Gómez"></label>' +
    '<label>Edad (opcional) <input class="nino-edad" inputmode="numeric" size="3"></label>' +
    '<button type="button" class="small quitar-nino" aria-label="Quitar">✕</button>';
  return div;
}

function listaNinos(contenedorId, btnMasId) {
  const cont = document.getElementById(contenedorId);
  const sincronizar = () => {
    const filas = cont.querySelectorAll(".fila-nino");
    filas.forEach(f => (f.querySelector(".quitar-nino").style.visibility = filas.length > 1 ? "visible" : "hidden"));
  };
  document.getElementById(btnMasId).addEventListener("click", () => {
    cont.appendChild(filaNino());
    sincronizar();
  });
  cont.addEventListener("click", e => {
    const btn = e.target.closest(".quitar-nino");
    if (!btn) return;
    btn.closest(".fila-nino").remove();
    sincronizar();
  });
  cont.appendChild(filaNino());
  sincronizar();
  return () =>
    [...cont.querySelectorAll(".fila-nino")].map(f => ({
      nombres: f.querySelector(".nino-nombres").value.trim(),
      apellidos: f.querySelector(".nino-apellidos").value.trim(),
      edad: f.querySelector(".nino-edad").value.trim(),
    }));
}

const ninosResidente = listaNinos("pis-ninos", "btn-mas-nino");
const ninosInvitado = listaNinos("pis-inv-ninos", "btn-mas-inv-nino");

function ninosValidados(valores) {
  const ninos = [];
  for (let i = 0; i < valores.length; i++) {
    const v = valores[i];
    if (!v.nombres && !v.apellidos && !v.edad) continue;
    if (!v.nombres || !v.apellidos) {
      alert("Completa nombres y apellidos del niño en la fila " + (i + 1));
      return null;
    }
    ninos.push({nombres: v.nombres, apellidos: v.apellidos, edad: v.edad === "" ? null : parseInt(v.edad, 10)});
  }
  if (ninos.length > 10) { alert("Máximo 10 niños por registro"); return null; }
  return ninos;
}

async function enviar(url, cuerpo, btn, errorPorDefecto) {
  if (btn.disabled) return;  // un solo envío por toque: sin dobles registros
  btn.disabled = true;
  try {
    const r = await fetch(url, {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(cuerpo)});
    const j = await r.json();
    if (r.ok && j.ok) { location.reload(); return; }
    alert(j.detail || errorPorDefecto);
  } finally {
    btn.disabled = false;
  }
}

document.getElementById("btn-ingreso-nino").addEventListener("click", async e => {
  const rid = seleccionado();
  if (rid === null) return;
  const ninos = ninosValidados(ninosResidente());
  if (ninos === null) return;
  if (!ninos.length) { alert("Agrega al menos un niño con nombres y apellidos"); return; }
  await enviar("/api/piscina/ingreso-nino", {acompanante_id: rid, ninos}, e.currentTarget, "Error registrando la entrada del niño");
});

document.getElementById("btn-ingreso-invitado").addEventListener("click", async e => {
  const rid = seleccionado();
  if (rid === null) return;
  const nombres = document.getElementById("pis-invitado-nombres").value.trim();
  const apellidos = document.getElementById("pis-invitado-apellidos").value.trim();
  if (!nombres || !apellidos) { alert("Digita los nombres y los apellidos del invitado"); return; }
  const ninos = ninosValidados(ninosInvitado());
  if (ninos === null) return;
  await enviar("/api/piscina/ingreso-invitado", {nombres, apellidos, padrino_id: rid, ninos}, e.currentTarget, "Error registrando la entrada del invitado");
});

document.getElementById("btn-ingreso-adulto").addEventListener("click", async e => {
  const rid = seleccionado();
  if (rid === null) return;
  await enviar("/api/piscina/ingreso", {resident_id: rid}, e.currentTarget, "Error registrando la entrada");
});

// Salida: el niño nunca sale solo — el botón del acompañante cierra al grupo
document.querySelectorAll("[data-salir]").forEach(btn => btn.addEventListener("click", async () => {
  const ninos = btn.dataset.ninos || "";
  const mensaje = ninos
    ? "¿Sale " + btn.dataset.persona + " con " + ninos + "? Todos quedan fuera de la piscina."
    : "¿Marcar la salida de " + btn.dataset.persona + " de la piscina?";
  if (!confirm(mensaje)) return;
  if (btn.disabled) return;
  btn.disabled = true;
  try {
    const r = await fetch("/api/piscina/salida/" + btn.dataset.salir, {method: "POST"});
    const j = await r.json();
    if (r.ok && j.ok) { alert(j.message); location.reload(); }
    else alert(j.detail || "Error registrando la salida");
  } finally {
    btn.disabled = false;
  }
}));

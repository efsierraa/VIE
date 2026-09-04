// Historial: asignar paquetes de no registrados a residentes
document.querySelectorAll("[data-asignar]").forEach(btn => btn.addEventListener("click", async e => {
  e.preventDefault();
  const username = prompt("Usuario (username) del residente para asignarle el paquete de " + btn.dataset.nombre + ":");
  if (!username) return;
  const r = await fetch("/api/packages/" + btn.dataset.asignar + "/asignar", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({username: username.trim()})});
  const j = await r.json();
  if (r.ok && j.ok) alert("Paquete asignado: el residente ya lo ve con su QR en la app.");
  else alert(j.detail || "Error asignando el paquete");
}));

// Edición de ingresos manuales y paquetes de tercero (administración, a voluntad)
function llenarVisita(btn) {
  const form = document.getElementById("edit-visita-form");
  form.dataset.uuid = btn.dataset.editarVisita;
  document.getElementById("edit-v-nombres").value = btn.dataset.nombres || "";
  document.getElementById("edit-v-apellidos").value = btn.dataset.apellidos || "";
  document.getElementById("edit-v-asunto").value = btn.dataset.asunto || "";
  document.getElementById("edit-v-id").value = btn.dataset.idnum || "";
  document.getElementById("edit-v-cel").value = btn.dataset.cel || "";
  document.getElementById("edit-v-rol").value = btn.dataset.rol || "visitante";
  document.getElementById("edit-v-torre").value = btn.dataset.torre || "";
  document.getElementById("edit-v-apto").value = btn.dataset.apto || "";
  const card = document.getElementById("edit-visita-card");
  card.classList.remove("hidden");
  card.scrollIntoView({behavior: "smooth"});
}
function llenarPaquete(btn) {
  const form = document.getElementById("edit-paquete-form");
  form.dataset.uuid = btn.dataset.editarPaquete;
  document.getElementById("edit-p-nombres").value = btn.dataset.nombres || "";
  document.getElementById("edit-p-apellidos").value = btn.dataset.apellidos || "";
  document.getElementById("edit-p-torre").value = btn.dataset.torre || "";
  document.getElementById("edit-p-apto").value = btn.dataset.apto || "";
  document.getElementById("edit-p-desc").value = btn.dataset.desc || "";
  document.getElementById("edit-p-cel").value = btn.dataset.cel || "";
  const card = document.getElementById("edit-paquete-card");
  card.classList.remove("hidden");
  card.scrollIntoView({behavior: "smooth"});
}
document.querySelectorAll("[data-editar-visita]").forEach(btn => btn.addEventListener("click", () => llenarVisita(btn)));
document.querySelectorAll("[data-editar-paquete]").forEach(btn => btn.addEventListener("click", () => llenarPaquete(btn)));
const editVForm = document.getElementById("edit-visita-form");
if (editVForm) {
  editVForm.addEventListener("submit", async e => {
    e.preventDefault();
    const r = await fetch("/api/visits/" + editVForm.dataset.uuid + "/editar", {method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
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
const editPForm = document.getElementById("edit-paquete-form");
if (editPForm) {
  editPForm.addEventListener("submit", async e => {
    e.preventDefault();
    const r = await fetch("/api/packages/" + editPForm.dataset.uuid + "/editar", {method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
      nombres: document.getElementById("edit-p-nombres").value.trim(),
      apellidos: document.getElementById("edit-p-apellidos").value.trim(),
      tower: document.getElementById("edit-p-torre").value,
      apartment: document.getElementById("edit-p-apto").value,
      description: document.getElementById("edit-p-desc").value,
      celular: document.getElementById("edit-p-cel").value,
    })});
    const j = await r.json();
    if (r.ok && j.ok) location.reload();
    else alert(j.detail || "Error editando el paquete");
  });
}

// Resolución de disputas a dos partes (lado portería/administración)
document.querySelectorAll("[data-resolver]").forEach(btn => btn.addEventListener("click", async () => {
  if (!confirm("¿Confirmas que la disputa quedó resuelta? El residente también debe aceptar.")) return;
  const r = await fetch("/api/packages/" + btn.dataset.resolver + "/resolver", {method: "POST"});
  const j = await r.json();
  if (r.ok && j.ok) {
    alert(j.resuelta ? "Disputa resuelta: el paquete quedó confirmado." : "Tu acuerdo quedó registrado; falta que el residente confirme.");
    location.reload();
  } else {
    alert(j.detail || "Error resolviendo la disputa");
  }
}));

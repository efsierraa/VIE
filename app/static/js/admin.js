const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const form = document.getElementById("user-form");
const roleSelect = document.getElementById("role-select");
const aptFields = document.getElementById("apt-fields");

function toggleApt() {
  aptFields.style.display = roleSelect.value === "residente" ? "" : "none";
}
roleSelect.addEventListener("change", toggleApt);
toggleApt();

form.addEventListener("submit", async e => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(form).entries());
  const r = await fetch("/api/users", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data)});
  const j = await r.json();
  if (r.ok && j.ok) location.reload();
  else alert(j.detail || "Error creando la cuenta");
});

document.querySelectorAll("[data-toggle]").forEach(btn => btn.addEventListener("click", async e => {
  e.preventDefault();
  const r = await fetch("/api/users/" + btn.dataset.toggle + "/toggle", {method: "POST"});
  if (r.ok) location.reload();
  else { const j = await r.json(); alert(j.detail || "Error"); }
}));

document.querySelectorAll("[data-reset]").forEach(btn => btn.addEventListener("click", async e => {
  e.preventDefault();
  const nueva = prompt("Nueva clave para " + btn.dataset.nombre + " (mínimo 8 caracteres):");
  if (nueva === null) return;
  if (nueva.length < 8) { alert("Mínimo 8 caracteres"); return; }
  const r = await fetch("/api/users/" + btn.dataset.reset + "/password", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({nueva})});
  if (r.ok) alert("Clave asignada.");
  else { const j = await r.json(); alert(j.detail || "Error"); }
}));

document.querySelectorAll("[data-asignar]").forEach(btn => btn.addEventListener("click", async e => {
  e.preventDefault();
  const username = prompt("Usuario (username) del residente para asignarle el paquete de " + btn.dataset.nombre + ":");
  if (!username) return;
  const r = await fetch("/api/packages/" + btn.dataset.asignar + "/asignar", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({username: username.trim()})});
  const j = await r.json();
  if (r.ok && j.ok) alert("Paquete asignado: el residente ya lo ve con su QR en la app.");
  else alert(j.detail || "Error asignando el paquete");
}));

document.getElementById("csv-form").addEventListener("submit", async e => {
  e.preventDefault();
  const archivo = document.getElementById("csv-file").files[0];
  if (!archivo) return;
  const fd = new FormData();
  fd.append("file", archivo);
  const r = await fetch("/api/users/csv", {method: "POST", body: fd});
  const j = await r.json();
  const div = document.getElementById("csv-result");
  if (r.ok && j.ok) {
    div.innerHTML = '<p class="alert ok">Cuentas creadas: ' + j.creados + '</p>' +
      (j.errores.length ? '<p class="alert error">' + j.errores.map(esc).join("<br>") + '</p>' : '');
    if (j.creados) setTimeout(() => location.reload(), 2500);
  } else {
    div.innerHTML = '<p class="alert error">' + esc(j.detail || "Error importando el CSV") + '</p>';
  }
});

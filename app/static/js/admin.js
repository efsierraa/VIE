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

// Edición de cuentas: nombres, celular, torre y apto (el usuario y el rol no se tocan)
const editCuentaCard = document.getElementById("edit-cuenta-card");
const editCuentaForm = document.getElementById("edit-cuenta-form");
if (editCuentaCard && editCuentaForm) {
  document.querySelectorAll("[data-editar-cuenta]").forEach(btn => btn.addEventListener("click", () => {
    editCuentaForm.dataset.id = btn.dataset.editarCuenta;
    document.getElementById("edit-c-usuario").textContent = btn.dataset.usuario;
    document.getElementById("edit-c-nombres").value = btn.dataset.nombres || "";
    document.getElementById("edit-c-apellidos").value = btn.dataset.apellidos || "";
    document.getElementById("edit-c-cel").value = btn.dataset.cel || "";
    document.getElementById("edit-c-torre").value = btn.dataset.torre || "";
    document.getElementById("edit-c-apto").value = btn.dataset.apto || "";
    editCuentaCard.classList.remove("hidden");
    editCuentaCard.scrollIntoView({behavior: "smooth"});
  }));
  editCuentaForm.addEventListener("submit", async e => {
    e.preventDefault();
    const r = await fetch("/api/users/" + editCuentaForm.dataset.id + "/editar", {method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify({
      nombres: document.getElementById("edit-c-nombres").value.trim(),
      apellidos: document.getElementById("edit-c-apellidos").value.trim(),
      celular: document.getElementById("edit-c-cel").value,
      tower: document.getElementById("edit-c-torre").value,
      apartment: document.getElementById("edit-c-apto").value,
    })});
    const j = await r.json();
    if (r.ok && j.ok) location.reload();
    else alert(j.detail || "Error editando la cuenta");
  });
}

document.querySelectorAll("[data-toggle]").forEach(btn => btn.addEventListener("click", async e => {
  e.preventDefault();
  const fila = btn.closest("tr");
  const nombre = fila && fila.querySelectorAll("td")[1] ? fila.querySelectorAll("td")[1].textContent.trim() : "esta cuenta";
  const desactivando = btn.textContent.trim() === "Desactivar";
  if (!confirm("¿Seguro que quieres " + (desactivando ? "desactivar" : "activar") + " la cuenta de " + nombre + "?")) return;
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

document.querySelectorAll("[data-2fa-reset]").forEach(btn => btn.addEventListener("click", async e => {
  e.preventDefault();
  const motivo = prompt("Motivo del reinicio de 2FA para " + btn.dataset.nombre + " (queda auditado):");
  if (motivo === null) return;
  if (motivo.trim().length < 3) { alert("Indica el motivo (mínimo 3 caracteres)"); return; }
  if (!confirm("Se borra el segundo factor de " + btn.dataset.nombre + ". Tendrá que activarlo de nuevo. ¿Continuar?")) return;
  const r = await fetch("/api/users/" + btn.dataset["2faReset"] + "/2fa/reset", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({motivo: motivo.trim()})});
  const j = await r.json().catch(() => ({}));
  if (r.ok) alert("2FA reiniciado. Quedó en el control de ediciones.");
  else alert(j.detail || "Error reiniciando 2FA");
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

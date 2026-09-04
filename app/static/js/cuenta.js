const form = document.getElementById("pw-form");
form.addEventListener("submit", async e => {
  e.preventDefault();
  const data = Object.fromEntries(new FormData(form).entries());
  if (data.nueva !== data.repetir) { alert("Las claves nuevas no coinciden"); return; }
  const r = await fetch("/api/me/password", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({actual: data.actual, nueva: data.nueva})});
  const j = await r.json();
  if (r.ok && j.ok) { alert("Clave actualizada."); form.reset(); }
  else alert(j.detail || "Error cambiando la clave");
});

const celForm = document.getElementById("cel-form");
celForm.addEventListener("submit", async e => {
  e.preventDefault();
  const celular = celForm.querySelector("input[name=celular]").value.trim();
  const r = await fetch("/api/perfil", {method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify({celular})});
  const j = await r.json();
  if (r.ok && j.ok) alert("Celular guardado.");
  else alert(j.detail || "Error guardando el celular");
});

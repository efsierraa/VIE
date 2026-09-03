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

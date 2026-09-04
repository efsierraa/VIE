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

// 2FA TOTP (SOC2 CC6.1): estado + setup en dos pasos
(async () => {
  const estado = document.getElementById("2fa-estado");
  const btnIniciar = document.getElementById("2fa-iniciar");
  const btnRegen = document.getElementById("2fa-regenerar");
  const box = document.getElementById("2fa-setup");
  if (!estado || !btnIniciar) return;
  const r = await fetch("/api/me/2fa/status");
  if (!r.ok) { estado.textContent = "No se pudo cargar el estado del segundo factor."; return; }
  const j = await r.json();
  estado.textContent = j.enabled
    ? `Activo · códigos de respaldo restantes: ${j.respaldos_restantes}`
    : "Inactivo. Actívalo para proteger tu cuenta (obligatorio para administración).";
  btnRegen.hidden = !j.enabled;
  btnIniciar.textContent = j.enabled ? "Reconfigurar segundo factor" : "Activar segundo factor";
  btnIniciar.onclick = async () => {
    const rs = await fetch("/api/me/2fa/setup/start", {method: "POST"});
    const sj = await rs.json();
    if (!rs.ok) { alert(sj.detail || "Error iniciando 2FA"); return; }
    box.hidden = false;
    document.getElementById("2fa-qr").src = sj.qr_data_uri;
    document.getElementById("2fa-secreto").textContent = sj.secreto;
  };
  btnRegen.onclick = async () => {
    if (!confirm("Se invalidan los códigos anteriores. ¿Continuar?")) return;
    const rr = await fetch("/api/me/2fa/backup/regenerar", {method: "POST"});
    const rj = await rr.json();
    if (rr.ok) alert("Nuevos códigos (guárdalos, solo se muestran una vez):\n" + rj.codigos_respaldo.join("\n"));
    else alert(rj.detail || "Error regenerando códigos");
  };
  const form2 = document.getElementById("2fa-form");
  form2.addEventListener("submit", async e => {
    e.preventDefault();
    const code = new FormData(form2).get("code");
    const rv = await fetch("/api/me/2fa/setup/verify", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({code})});
    const vj = await rv.json();
    if (rv.ok) {
      alert("Segundo factor activado. Códigos de respaldo (una sola vez):\n" + vj.codigos_respaldo.join("\n"));
      location.reload();
    } else alert(vj.detail || "Código incorrecto");
  });
})();

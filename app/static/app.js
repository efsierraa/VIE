if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.register("/static/sw.js").catch(() => {});
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

// Ojo dentro del campo para mostrar/ocultar la clave
const OJO = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/></svg>';
const OJO_TACHADO = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';

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

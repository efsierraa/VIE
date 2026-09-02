if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.register("/static/sw.js").catch(() => {});
  });
}

// Botón Ver/Ocultar junto a cada campo de clave
document.querySelectorAll("input[type=password]").forEach(inp => {
  const wrap = document.createElement("span");
  wrap.className = "pw-wrap";
  inp.replaceWith(wrap);
  wrap.appendChild(inp);
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "pw-toggle";
  btn.textContent = "Ver";
  btn.addEventListener("click", () => {
    const oculta = inp.type === "password";
    inp.type = oculta ? "text" : "password";
    btn.textContent = oculta ? "Ocultar" : "Ver";
  });
  wrap.appendChild(btn);
});

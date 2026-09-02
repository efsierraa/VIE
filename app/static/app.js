if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.register("/static/sw.js").catch(() => {});
  });
}

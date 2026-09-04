"""Guardia de sintaxis JS: los archivos estáticos deben parsear (node --check).

Lo activamos después de que un `const v` duplicado matara residente.js en
producción: la suite no ejecuta JavaScript, pero sí puede validar su sintaxis.
"""
import shutil
import subprocess
from pathlib import Path

import pytest

JS_DIR = Path("app/static/js")
JS_RAIZ = [Path("app/static/app.js"), Path("app/static/sw.js")]


@pytest.mark.skipif(shutil.which("node") is None, reason="node no está instalado")
def test_sintaxis_de_todos_los_js():
    archivos = sorted(JS_DIR.glob("*.js")) + [a for a in JS_RAIZ if a.exists()]
    assert archivos, "no se encontraron archivos JS"
    for archivo in archivos:
        r = subprocess.run(
            ["node", "--check", str(archivo)],
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, f"Error de sintaxis en {archivo}:\n{r.stderr}"

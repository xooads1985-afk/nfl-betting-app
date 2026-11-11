"""Página Streamlit: utiliza la implementación única del laboratorio prospectivo."""
from pathlib import Path
import sys

# Permite importar el módulo situado en la raíz del repositorio al abrir /pages/.
_raiz = str(Path(__file__).resolve().parent.parent)
if _raiz not in sys.path:
    sys.path.insert(0, _raiz)

from nba_laboratorio_prospectivo import mostrar

if __name__ == '__main__':
    mostrar()


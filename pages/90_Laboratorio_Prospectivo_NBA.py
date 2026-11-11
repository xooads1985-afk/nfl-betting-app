
"""Página del Laboratorio prospectivo NBA."""
from pathlib import Path
import sys

_raiz = str(Path(__file__).resolve().parent.parent)
if _raiz not in sys.path:
    sys.path.insert(0, _raiz)

from nba_laboratorio_prospectivo import mostrar

if __name__ == "__main__":
    mostrar()

"""Parche aislado y repetible para el productor de tarjetas NBA."""
from pathlib import Path
p = Path('nba_lab_puente_futuro.py')
s = p.read_text(encoding='utf-8')
if "'generado_utc':" in s:
    print('Sello ya instalado')
else:
    original = 'import json\nfrom pathlib import Path\n'
    if s.count(original) != 1:
        raise RuntimeError('Estructura de importaciones inesperada; no se modifica')
    s = s.replace(original, 'import json\nfrom datetime import datetime, timezone\nfrom pathlib import Path\n', 1)
    anchor = "        'esquema': 'nba_tarjeta_futura_v1',"
    if s.count(anchor) != 1:
        raise RuntimeError('Estructura de tarjeta inesperada; no se modifica')
    s = s.replace(anchor, anchor + "\n        'generado_utc': datetime.now(timezone.utc).isoformat(),", 1)
    compile(s, str(p), 'exec')
    p.write_text(s, encoding='utf-8')
    print('Sello generado_utc instalado en el productor experimental')

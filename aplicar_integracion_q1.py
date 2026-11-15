"""Parche idempotente de nba_conexion_tarjeta.py, sin tocar main ni motores."""
from pathlib import Path
import ast
p = Path(__file__).resolve().parent / 'nba_conexion_tarjeta.py'
s = p.read_text(encoding='utf-8')
needle = '    from nba_tarjeta_auto import mostrar_tarjeta_auto\n'
if needle not in s:
    raise SystemExit('No se encontró el punto de integración; sin cambios')
if 'periodos_para_tarjeta(partido)' in s:
    print('Ya integrado; sin cambios')
else:
    addition = ('    if periodos_resumen is None:\n'
                '        from nba_q1_integracion_tarjeta import periodos_para_tarjeta\n'
                '        periodos_resumen = periodos_para_tarjeta(partido)\n')
    nuevo = s.replace(needle, needle + addition, 1)
    ast.parse(nuevo)
    p.write_text(nuevo, encoding='utf-8')
    print('Integración aplicada')

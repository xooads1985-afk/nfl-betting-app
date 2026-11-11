"""Parche seguro e idempotente para el Edge del laboratorio NBA.
Ejecutar desde la raiz del repositorio en la rama experimental.
"""
from pathlib import Path

motor = Path('nba_lab_motor_futuro.py')
puente = Path('nba_lab_puente_futuro.py')
if not motor.is_file() or not puente.is_file():
    raise SystemExit('Faltan archivos del motor o del puente en esta carpeta')

m = motor.read_text(encoding='utf-8')
p = puente.read_text(encoding='utf-8')
old_m = "'edge_total_vs_base':round(total_c-total_base,2),"
new_m = ("'edge_total_vs_base':round(sum(equipos[e]['ensemble'] for e in (local,visitante))-total_base,2),\n"
         "            'edge_total_modelo_c_vs_base':round(total_c-total_base,2),")
old_p = "'edge_total_vs_base': resultado['edge_total_vs_base'],"
new_p = ("'edge_total_vs_base': resultado['edge_total_vs_base'],\n"
         "        'edge_total_modelo_c_vs_base': resultado['edge_total_modelo_c_vs_base'],")
if old_m not in m and new_m not in m:
    raise SystemExit('Motor con estructura distinta; no se modifico nada')
if old_p not in p and new_p not in p:
    raise SystemExit('Puente con estructura distinta; no se modifico nada')
if old_m in m: m=m.replace(old_m,new_m,1)
if old_p in p: p=p.replace(old_p,new_p,1)
compile(m,str(motor),'exec');compile(p,str(puente),'exec')
assert new_m in m and new_p in p
motor.write_text(m,encoding='utf-8')
puente.write_text(p,encoding='utf-8')
print('EDGE CORREGIDO: Ensemble principal, Modelo C separado')

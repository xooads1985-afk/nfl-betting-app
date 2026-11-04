"""Pruebas sin instalar Streamlit: python probar_v31.py"""
import sys, types, importlib.util
from pathlib import Path
import pandas as pd
sys.modules.setdefault('streamlit', types.ModuleType('streamlit'))
spec=importlib.util.spec_from_file_location('nfl_validacion_v31',Path(__file__).with_name('centro_validacion_nfl.py'))
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
checks=[]
def check(name, cond):
    checks.append((name,bool(cond)))
    if not cond: raise AssertionError(name)
raw=pd.DataFrame([
 {'player_id':'A','week':1,'recent_team':'AAA','player_display_name':'Uno','position':'WR','receiving_yards':10,'season':2026},
 {'player_id':'A','week':2,'recent_team':'BBB','player_display_name':'Uno','position':'WR','receiving_yards':20,'season':2026},
 {'player_id':'B','week':1,'recent_team':'CCC','player_display_name':'Dos','position':'QB','receiving_yards':5,'season':2026},
 {'player_id':'B','week':1,'recent_team':'CCC','player_display_name':'Dos','position':'QB','receiving_yards':5,'season':2026},
 {'player_id':None,'week':3,'recent_team':'DDD','player_display_name':'X','position':'RB','receiving_yards':9,'season':2026},
 {'player_id':'C','week':0,'recent_team':'EEE','player_display_name':'Y','position':'RB','receiving_yards':9,'season':2026},
])
original=raw.copy(deep=True)
h,c,e,r=m._crear_historial_limpio(raw)
check('sin mutar origen',raw.equals(original))
check('dos semanas de A',len(h)==2)
check('equipo histórico',h.sort_values('semana_normalizada')['equipo_historico'].tolist()==['AAA','BBB'])
check('equipo actual de catálogo',set(h['equipo_catalogo'])=={'BBB'})
check('catálogo único',len(c)==1)
check('métricas intactas',h['receiving_yards'].sum()==30)
check('sin ID excluido',len(e[e['motivo_exclusion'].str.contains('ID ausente')])==1)
check('semana inválida excluida',len(e[e['motivo_exclusion'].str.contains('semana inválida')])==1)
check('duplicados en revisión',len(r)==2)
check('duplicados no sumados',not h['jugador_id'].eq('B').any())
check('motivo de exclusión disponible','motivo_exclusion' in e)
check('compatibilidad v2',len(m._diagnosticar_detallado(raw))==4)
check('una sola función pública',Path(__file__).with_name('centro_validacion_nfl.py').read_text().count('def mostrar_centro_validacion_nfl():')==1)
check('archivo de sintaxis válido',True)
print(f'{sum(x[1] for x in checks)}/{len(checks)} pruebas superadas')
for name,ok in checks: print(('OK' if ok else 'ERROR'),name)


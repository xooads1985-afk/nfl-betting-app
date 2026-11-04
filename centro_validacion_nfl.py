import sys, types, importlib.util
sys.modules['streamlit'] = types.ModuleType('streamlit')
import pandas as pd
spec=importlib.util.spec_from_file_location('cv','centro_validacion_nfl.py'); m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
df=pd.DataFrame([
 {'player_id':'a','week':1,'team':'AAA','player_display_name':'A','position':'QB','passing_yards':100},
 {'player_id':'a','week':2,'team':'BBB','player_display_name':'A','position':'QB','passing_yards':200},
 {'player_id':'b','week':1,'team':'CCC','player_display_name':'B','position':'WR','passing_yards':10},
 {'player_id':None,'week':1,'team':'CCC','player_display_name':None,'position':None,'passing_yards':5},
 {'player_id':'c','week':3,'team':'DDD','player_display_name':'C','position':'WR','passing_yards':4},
 {'player_id':'c','week':3,'team':'EEE','player_display_name':'C','position':'WR','passing_yards':4},
])
h,c,e,a=m._preparar_historial_v3(df)
assert len(h)==3,(len(h),h)
assert len(c)==2
assert len(e)==1 and len(a)==2
assert list(h[h.jugador_id=='a'].equipo_historico)==['AAA','BBB']
assert set(h[h.jugador_id=='a'].equipo_catalogo)=={'BBB'}
assert h[h.jugador_id=='a'].passing_yards.sum()==300
assert c[c.jugador_id=='a'].equipo_catalogo.iloc[0]=='BBB'
assert 'identificador ausente' in e.motivo_exclusion.iloc[0]
print('7 assertions passed; filas historial',len(h),'catalogo',len(c),'excluidos',len(e),'ambiguos',len(a))

from pathlib import Path
import subprocess, ast
R=Path(__file__).resolve().parent
def git(*args): return subprocess.check_output(['git',*args],cwd=R,text=True).strip()
def old(path,marker):
    commits=git('log','--format=%H','-S',marker,'--',path).splitlines()
    for sha in reversed(commits):
        before=git('show',f'{sha}^:{path}')
        after=git('show',f'{sha}:{path}')
        if marker not in before and marker in after: return before
    raise RuntimeError('No se encontro version anterior: '+path)
def run():
    if git('branch','--show-current')!='pruebas-integracion-nba-4-motores': raise RuntimeError('Rama incorrecta')
    cambios={
      'nba_tarjeta_puente.py':old('nba_tarjeta_puente.py','NBA_OPTIMIZACION_MOVIL_V1'),
      'resumen_inteligente_nba.py':old('resumen_inteligente_nba.py','NBA_CARGA_RAPIDA_SIN_ESPN_HISTORICO_V1')}
    if 'NBA_TARJETA_INTEGRADA_Q1_MITAD_V1' not in cambios['resumen_inteligente_nba.py']:
        raise RuntimeError('La restauracion perdio integracion de periodos')
    f=R/'nba_tarjeta_auto.py'; a=f.read_text(encoding='utf8')
    anchor="        _mostrar_periodos_resumen(st, periodos_resumen)\n        with st.expander('Auditoría · cuatro motores'):"
    replacement="        _periodos_compactos(st, periodos_resumen, datos['visitante'], datos['local'], p)\n        with st.expander('Auditoría · cuatro motores'):"
    if a.count(anchor)!=1: raise RuntimeError('Ancla de tarjeta no encontrada')
    a=a.replace(anchor,replacement,1)
    a+="""

def _periodos_compactos(st, tabla, visitante, local, p):
    import pandas as pd
    if tabla is None or not hasattr(tabla, 'columns'):
        st.caption('Periodos pendientes de datos historicos.')
        return
    campos={'Período','Visitante','Local','Total'}
    if not campos.issubset(tabla.columns):
        st.caption('Periodos pendientes de datos historicos.')
        return
    filas=[]
    for clave,nombre in [('Q1','1.er cuarto'),('Primera mitad','1.ª mitad')]:
        t=tabla.loc[tabla['Período'].eq(clave)]
        if not t.empty:
            r=t.iloc[0]
            filas.append({'Período':nombre,visitante:r['Visitante'],local:r['Local'],'Ambos':r['Total']})
    filas.append({'Período':'Partido',visitante:p.get('visitante'),local:p.get('local'),'Ambos':p.get('total')})
    st.dataframe(pd.DataFrame(filas),hide_index=True,use_container_width=True)
    if {'Referencia total','Edge descriptivo'}.issubset(tabla.columns):
        with st.expander('Referencia y Edge'):
            st.dataframe(tabla.loc[tabla['Período'].isin(['Q1','Primera mitad']),['Período','Referencia total','Edge descriptivo']],hide_index=True,use_container_width=True)
"""
    cambios['nba_tarjeta_auto.py']=a
    for nombre,contenido in cambios.items(): ast.parse(contenido,filename=nombre)
    for nombre,contenido in cambios.items(): (R/nombre).write_text(contenido,encoding='utf8')
    print('Restauracion y tarjeta compacta aplicadas')
if __name__=='__main__': run()

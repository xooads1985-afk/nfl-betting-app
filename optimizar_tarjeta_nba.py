"""Ajustes acotados de la tarjeta NBA en la rama experimental.
Idempotente; valida anclas y sintaxis antes de escribir; conserva .bak.
"""
from pathlib import Path
import ast
import shutil

ROOT=Path(__file__).resolve().parent
AUTO=ROOT/'nba_tarjeta_auto.py'
PUENTE=ROOT/'nba_tarjeta_puente.py'
PRED=ROOT/'nba_prediccion_tarjeta.py'
MARK='# NBA_OPTIMIZACION_MOVIL_V1'

def one(s, old, new, tag):
    n=s.count(old)
    if n!=1: raise RuntimeError(f'{tag}: esperaba 1 coincidencia, encontradas {n}')
    return s.replace(old,new,1)

def preparar():
    originals={p:p.read_text(encoding='utf-8') for p in (AUTO,PUENTE,PRED)}
    if all(MARK in t for t in originals.values()):
        print('Optimización ya instalada');return
    if any(MARK in t for t in originals.values()):
        raise RuntimeError('Instalación parcial detectada; no modificar archivos')
    a,b,c=(originals[p] for p in (AUTO,PUENTE,PRED))
    a=MARK+'\n'+a
    b=MARK+'\n'+b
    c=MARK+'\n'+c
    # Caché de resultados completos de 10 a 30 minutos para evitar recálculo al navegar.
    a=one(a,'intervalo_minutos=10, historial_remoto_habilitado=False,',
          'intervalo_minutos=30, historial_remoto_habilitado=False,','TTL')
    # Mostrar diferencia aritmética explícita, sin afirmar que fue validada.
    a=one(a,"from nba_prediccion_tarjeta import _cabecera_compacta, _tabla_periodos",
          "from nba_prediccion_tarjeta import _cabecera_compacta, _tabla_periodos",'import') if False else a
    a=one(a,"st.markdown(_cabecera_compacta(datos['visitante'], datos['local'], p, datos['favorito']),\n                    unsafe_allow_html=True)",
          "st.markdown(_cabecera_compacta(datos['visitante'], datos['local'], p, datos['favorito']),\n                    unsafe_allow_html=True)", 'cabecera') if False else a
    # Tabla móvil: 2 filas, 4 columnas principales, Edge y referencia en tabla separada.
    old="""    datos = datos.rename(columns={'Referencia total': 'Referencia', 'Edge descriptivo': 'Edge'})
    st.dataframe(datos, hide_index=True, use_container_width=True)
    st.caption('Edge = proyección − referencia histórica; no representa probabilidad.')"""
    new="""    datos = datos.rename(columns={'Referencia total': 'Referencia', 'Edge descriptivo': 'Edge'})
    st.dataframe(datos[['Período', 'Visitante', 'Local', 'Total']],
                 hide_index=True, use_container_width=True)
    st.markdown('**Referencia histórica y Edge**')
    st.dataframe(datos[['Período', 'Referencia', 'Edge']],
                 hide_index=True, use_container_width=True)
    st.caption('Edge = proyección − referencia histórica; no representa probabilidad.')"""
    a=one(a,old,new,'Edge móvil')
    # La caja ya muestra un margen N/D; reemplazarlo por una diferencia calculada,
    # etiquetada como NO validada, en ambas rutas de tarjeta.
    old="""    piezas = [equipo(visitante, p['visitante']), equipo(local, p['local']),
              indicador('Total proyectado', 'N/D' if p['total'] is None else f"{p['total']:.1f}"),
              indicador('Margen validado', 'N/D')]"""
    new="""    margen = 'N/D'
    if p.get('local') is not None and p.get('visitante') is not None:
        diferencia = float(p['local']) - float(p['visitante'])
        nombre = _sigla(local if diferencia > 0 else visitante) if diferencia else 'Igualdad'
        margen = f'{abs(diferencia):.1f} · {nombre}' if diferencia else '0.0 · Igualdad'
    piezas = [equipo(visitante, p['visitante']), equipo(local, p['local']),
              indicador('Total proyectado', 'N/D' if p['total'] is None else f"{p['total']:.1f}"),
              indicador('Diferencia calculada (no validada)', margen)]"""
    c=one(c,old,new,'Margen')
    # Evitar la carga masiva de hasta 50 boxscores ESPN en el camino crítico.
    # Se consulta primero el CSV validado. Solo si no tiene cobertura, se
    # conserva la recuperación automática de ESPN con el límite original.
    old="""            if cargar_detalle is not None:
                from nba_pace_actualizacion_auto import completar_pace"""
    new="""            if cargar_detalle is not None:
                try:
                    pace = cargar_pace(Path(ruta_pace), partido, solicitar_remoto=None, corte_utc=ahora)
                except (ValueError, RuntimeError, OSError, TimeoutError):
                    pace = None
                if pace is None:
                    from nba_pace_actualizacion_auto import completar_pace"""
    # Remaining block needs indentation in fallback; transform by finding exact boundary.
    start=b.find('            if cargar_detalle is not None:\n')
    end=b.find('            else:\n                pace = cargar_pace(',start)
    if start<0 or end<0: raise RuntimeError('No se encontró el bloque Pace')
    original_block=b[start:end]
    body=original_block.split('\n',1)[1]
    # original block indent 16 spaces, make it 20 spaces under if pace is None.
    indented=''.join('    '+line if line.strip() else line for line in body.splitlines(keepends=True))
    replacement="""            if cargar_detalle is not None:
                # Vía rápida: CSV local completo y validado; sin ESPN.
                try:
                    pace = cargar_pace(Path(ruta_pace), partido, solicitar_remoto=None, corte_utc=ahora)
                except (ValueError, RuntimeError, OSError, TimeoutError):
                    pace = None
                if pace is None:
"""+indented
    b=b[:start]+replacement+b[end:]
    for p,s in ((AUTO,a),(PUENTE,b),(PRED,c)):
        ast.parse(s,filename=p.name)
    for p,s in ((AUTO,a),(PUENTE,b),(PRED,c)):
        shutil.copy2(p,p.with_suffix(p.suffix+'.bak'))
        p.write_text(s,encoding='utf-8')
    print('OK: tres archivos optimizados, sintaxis verificada; respaldos .bak creados')

if __name__=='__main__': preparar()

"""NBA 4.0: diagnóstico de solo lectura para archivo histórico Supabase.

Usar desde centro_estadistico_nba.py o ejecutar independientemente.
Requiere nba_archivo_temporada.py (v3.9) y secretos Supabase existentes.
No modifica datos, NFL, main.py ni otros módulos.
"""
from datetime import date, timedelta
import pandas as pd
import streamlit as st
from nba_archivo_temporada import leer_partidos, leer_jugadores, leer_consultas

VERSION = '4.0.0'
METRICAS = ('Puntos', 'Rebotes', 'Asistencias', 'Minutos')


def _numero(valor):
    if valor is None or isinstance(valor, bool):
        return float('nan')
    texto = str(valor).strip()
    if texto.upper() in ('', '--', '-', 'NAN', 'NONE', 'DNP', 'DND', 'N/A'):
        return float('nan')
    if ':' in texto:
        try:
            m, s = texto.split(':', 1)
            return int(m) + int(s) / 60
        except (ValueError, TypeError, ZeroDivisionError):
            return float('nan')
    return pd.to_numeric(texto.replace(',', ''), errors='coerce')


def analizar_archivo(partidos, jugadores, consultas=None, minimo_jugadores=8):
    """Función pura para pruebas locales; no hace solicitudes a la red."""
    p = partidos.copy() if isinstance(partidos, pd.DataFrame) else pd.DataFrame()
    j = jugadores.copy() if isinstance(jugadores, pd.DataFrame) else pd.DataFrame()
    c = consultas.copy() if isinstance(consultas, pd.DataFrame) else pd.DataFrame()
    alertas = []
    if 'id' not in p:
        p['id'] = pd.Series(dtype='str')
    if 'partido_id' not in j:
        j['partido_id'] = pd.Series(dtype='str')
    for col in ('equipo', 'jugador', 'jugador_id', 'fecha'):
        if col not in j:
            j[col] = pd.Series(dtype='str')
    p['id'] = p['id'].fillna('').astype(str).str.strip()
    j['partido_id'] = j['partido_id'].fillna('').astype(str).str.strip()
    j['equipo'] = j['equipo'].fillna('').astype(str).str.strip()
    j['jugador'] = j['jugador'].fillna('').astype(str).str.strip()
    j['jugador_id'] = j['jugador_id'].fillna('').astype(str).str.strip()
    for m in METRICAS:
        j[m] = j[m].map(_numero) if m in j else float('nan')
    j['_identidad'] = j['jugador_id'].where(j['jugador_id'].ne(''), j['jugador'].str.casefold())
    duplicados = j.duplicated(['partido_id', 'equipo', '_identidad'], keep=False)
    sin_metrica = j[list(METRICAS)].isna().all(axis=1)
    sin_minutos = j['Minutos'].isna()
    minutos_cero = j['Minutos'].eq(0)
    stats_presentes = j[['Puntos', 'Rebotes', 'Asistencias']].notna().any(axis=1)
    stats_sin_minutos = sin_minutos & stats_presentes
    negativas = j[list(METRICAS)].lt(0).any(axis=1)
    sin_identidad = j['jugador'].eq('') & j['jugador_id'].eq('')
    p_ids = set(p.loc[p['id'].ne(''), 'id'])
    j_ids = set(j.loc[j['partido_id'].ne(''), 'partido_id'])
    sin_jugadores = p.loc[p['id'].ne('') & ~p['id'].isin(j_ids)].copy()
    sin_partido = j.loc[j['partido_id'].ne('') & ~j['partido_id'].isin(p_ids)].copy()
    grupos = (j.groupby(['partido_id', 'equipo'], dropna=False)
              .agg(registros=('jugador', 'size'),
                   con_minutos=('Minutos', lambda s: int(s.gt(0).sum())),
                   con_puntos=('Puntos', lambda s: int(s.notna().sum())))
              .reset_index()) if not j.empty else pd.DataFrame(columns=['partido_id','equipo','registros','con_minutos','con_puntos'])
    grupos['estado'] = grupos['registros'].map(
        lambda n: 'Revisar: pocos registros' if n < minimo_jugadores else 'Presencia observada (no certificada)')
    # Verificación de los dos equipos solo cuando el calendario archivado tiene nombres.
    cobertura = []
    if {'id', 'local', 'visitante'}.issubset(p.columns):
        base = p
        if 'finalizado' in base:
            base = base.loc[base['finalizado'].eq(True)]
        for fila in base.drop_duplicates('id').itertuples(index=False):
            for equipo in (str(fila.local), str(fila.visitante)):
                if not equipo or equipo.lower() in ('nan', 'none'):
                    continue
                match = grupos.loc[grupos['partido_id'].eq(str(fila.id)) & grupos['equipo'].eq(equipo)]
                n = int(match['registros'].iloc[0]) if not match.empty else 0
                cobertura.append({'partido_id': str(fila.id), 'equipo': equipo, 'registros': n,
                                  'estado': 'Sin registros' if n == 0 else
                                  'Revisar: pocos registros' if n < minimo_jugadores else
                                  'Presencia observada (no certificada)'})
    cobertura_df = pd.DataFrame(cobertura, columns=['partido_id', 'equipo', 'registros', 'estado'])
    indicadores = {
        'Partidos archivados': len(p_ids),
        'Partidos con jugadores': len(j_ids),
        'Filas de jugadores': len(j),
        'Filas duplicadas potenciales': int(duplicados.sum()),
        'Filas sin métricas': int(sin_metrica.sum()),
        'Filas sin minutos': int(sin_minutos.sum()),
        'Minutos exactamente cero': int(minutos_cero.sum()),
        'Estadísticas sin minutos': int(stats_sin_minutos.sum()),
        'Valores negativos': int(negativas.sum()),
        'Filas sin identidad': int(sin_identidad.sum()),
        'Partidos archivados sin jugadores': len(sin_jugadores),
        'Registros de jugadores sin partido archivado': len(sin_partido),
        'Consultas auditadas': len(c),
    }
    if indicadores['Filas duplicadas potenciales']:
        alertas.append('Existen identidades repetidas dentro del mismo partido y equipo.')
    if indicadores['Partidos archivados sin jugadores']:
        alertas.append('Hay partidos archivados sin filas de jugadores en el rango consultado.')
    if indicadores['Estadísticas sin minutos']:
        alertas.append('Existen estadísticas individuales sin minutos informados; requieren revisión de origen.')
    if indicadores['Valores negativos']:
        alertas.append('Existen valores estadísticos negativos; revisar la fuente.')
    if not p.empty and not j.empty and indicadores['Registros de jugadores sin partido archivado']:
        alertas.append('Hay jugadores cuyos partidos no aparecen en el archivo de partidos; puede ser cobertura parcial de la tabla partidos.')
    return {'indicadores': indicadores, 'alertas': alertas, 'grupos': grupos,
            'cobertura': cobertura_df, 'sin_jugadores': sin_jugadores,
            'sin_partido': sin_partido, 'duplicados': j.loc[duplicados].drop(columns=['_identidad']),
            'calidad': j.loc[sin_metrica | stats_sin_minutos | negativas | sin_identidad].drop(columns=['_identidad'])}


def mostrar_diagnostico_nba():
    st.title('🏀 NBA 4.0 · Diagnóstico del archivo')
    st.caption('Versión ' + VERSION + ' · Solo lectura · Supabase · Sin alterar registros')
    hoy = date.today()
    a, b = st.columns(2)
    with a:
        desde = st.date_input('Desde', hoy - timedelta(days=30), key='diag_nba_desde')
    with b:
        hasta = st.date_input('Hasta', hoy, key='diag_nba_hasta')
    if desde > hasta or hasta > hoy or (hasta - desde).days > 366:
        st.warning('Elige un rango válido de hasta 367 días, sin fechas futuras.')
        return
    minimo = st.slider('Umbral orientativo de jugadores por equipo', 5, 12, 8)
    st.caption('El umbral es una señal de revisión, NO una certificación de cobertura.')
    if not st.button('🔎 Analizar Supabase', use_container_width=True):
        st.info('Presiona el botón para consultar los datos archivados. No se realizan escrituras.')
        return
    with st.spinner('Leyendo historial persistente...'):
        try:
            partidos = leer_partidos(desde, hasta)
            jugadores = leer_jugadores('Todos', desde, hasta)
            consultas = leer_consultas(desde, hasta, 'Todos')
        except Exception as exc:
            st.error(f'No se pudo consultar Supabase: {type(exc).__name__}: {exc}')
            return
    resultado = analizar_archivo(partidos, jugadores, consultas, minimo)
    st.subheader('📊 Indicadores del período')
    tabla = pd.DataFrame([{'Indicador': k, 'Valor': v} for k, v in resultado['indicadores'].items()])
    st.dataframe(tabla, hide_index=True, use_container_width=True)
    if resultado['alertas']:
        st.warning('Se detectaron señales que requieren revisión; no necesariamente son errores de ESPN.')
        for alerta in resultado['alertas']:
            st.write('• ' + alerta)
    else:
        st.success('Sin señales de alerta en las comprobaciones disponibles. La cobertura total NO está certificada.')
    for titulo, clave in [('🏟️ Cobertura por partido y equipo', 'cobertura'),
                          ('👥 Registros por partido y equipo', 'grupos'),
                          ('⚠️ Partidos archivados sin jugadores', 'sin_jugadores'),
                          ('🔎 Duplicados potenciales', 'duplicados'),
                          ('🧪 Registros que requieren revisión', 'calidad')]:
        with st.expander(titulo):
            df = resultado[clave]
            if df.empty:
                st.info('Sin registros en esta categoría.')
            else:
                st.dataframe(df, hide_index=True, use_container_width=True)
                st.download_button('📥 Exportar CSV', df.to_csv(index=False).encode('utf-8-sig'),
                                   f'diagnostico_nba_{clave}.csv', 'text/csv', key='diag_nba_' + clave)
    st.download_button('📥 Exportar indicadores CSV', tabla.to_csv(index=False).encode('utf-8-sig'),
                       'diagnostico_nba_indicadores.csv', 'text/csv', use_container_width=True)
    st.caption('Los resultados se basan en los registros disponibles en Supabase. No prueban que ESPN haya publicado todos los partidos o jugadores. Las consultas de las tablas no forman una instantánea transaccional.')


if __name__ == '__main__':
    st.set_page_config(page_title='NBA 4.0 · Salud del archivo', page_icon='🏀', layout='wide')
    mostrar_diagnostico_nba()

"""Panel de lectura del Laboratorio NBA 3.12.18. No modifica archivos existentes."""
from pathlib import Path
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
AUD = ROOT / 'nba_lab_auditoria_resultados'
DATA = ROOT / 'nba_lab_resultados'

st.markdown('''<style>
.block-container {padding-top:1.1rem;padding-left:.8rem;padding-right:.8rem;max-width:850px}
[data-testid="stMetricValue"] {font-size:1.45rem}
[data-testid="stDataFrame"] {font-size:.82rem}
</style>''', unsafe_allow_html=True)
st.title('🏀 Laboratorio NBA')
st.caption('Panel experimental 3.12.18 · Solo lectura · Datos históricos')

@st.cache_data(ttl=180)
def read_csv(path):
    return pd.read_csv(path) if path.exists() else pd.DataFrame()

def require(df, cols, name):
    missing = set(cols)-set(df.columns)
    if missing:
        st.warning(f'{name}: faltan columnas {", ".join(sorted(missing))}')
        return False
    return True

def metric_table(df):
    if df.empty: return
    view = df.copy()
    for c in ('MAE','RMSE','sesgo'):
        if c in view: view[c] = pd.to_numeric(view[c],errors='coerce').round(3)
    st.dataframe(view, use_container_width=True, hide_index=True)

pred = read_csv(DATA/'algoritmos_predicciones.csv')
tot = read_csv(AUD/'metricas_totales.csv')
team = read_csv(AUD/'metricas_por_equipo.csv')
localia = read_csv(AUD/'metricas_localia.csv')
integrity = read_csv(AUD/'control_integridad.csv')
issues = read_csv(AUD/'incidencias.csv')

if pred.empty:
    st.error('No se encontró nba_lab_resultados/algoritmos_predicciones.csv. Ejecuta el laboratorio en GitHub y confirma que se guardaron los CSV.')
    st.stop()
if not require(pred, ['partido','equipo','real','fecha'], 'Predicciones'):
    st.stop()

n_games = pred['partido'].nunique()
col1,col2 = st.columns(2)
col1.metric('Partidos', f'{n_games:,}')
col2.metric('Predicciones', f'{len(pred):,}')
st.caption('Estas cifras reflejan los CSV disponibles en el repositorio, no resultados en vivo.')

season_options = ['Todas']
if 'temporada' in tot:
    season_options += sorted([str(x) for x in tot.temporada.dropna().unique() if str(x)!='Todas'])
season = st.selectbox('Temporada', season_options)

tabs = st.tabs(['📊 Modelos','🏠 Localía','🛡️ Controles'])
with tabs[0]:
    mode = st.radio('Evaluación', ['Puntos por equipo','Puntos totales'], horizontal=True)
    df = team if mode=='Puntos por equipo' else tot
    if require(df, ['temporada','modelo','MAE','RMSE','sesgo','muestra'], mode):
        shown = df[df.temporada.astype(str)==season].copy()
        shown = shown.sort_values('MAE', key=lambda s:pd.to_numeric(s,errors='coerce'))
        if shown.empty: st.info('No hay resultados para esta temporada.')
        else:
            best = shown.iloc[0]
            st.metric('Menor MAE de esta muestra', f"{float(best['MAE']):.3f} pts", str(best['modelo']), delta_color='off')
            metric_table(shown[['modelo','muestra','MAE','RMSE','sesgo']])
            st.caption('MAE menor indica menor error medio. La clasificación es descriptiva, no prueba superioridad futura.')
with tabs[1]:
    if require(localia, ['temporada','grupo','modelo','muestra','MAE','RMSE','sesgo'], 'Localía'):
        shown = localia[localia.temporada.astype(str)==season]
        for sede in ['Local','Visitante']:
            st.subheader(sede)
            part = shown[shown.grupo==sede].sort_values('MAE',key=lambda s:pd.to_numeric(s,errors='coerce'))
            if part.empty: st.info('Sin datos')
            else: metric_table(part[['modelo','muestra','MAE','RMSE','sesgo']])
with tabs[2]:
    if integrity.empty:
        st.warning('Aún no existe control_integridad.csv.')
    elif require(integrity, ['control','incidencias'], 'Integridad'):
        count = pd.to_numeric(integrity.incidencias,errors='coerce').fillna(0).sum()
        if count==0: st.success('Sin incidencias en los controles ejecutados.')
        else: st.error(f'{int(count)} incidencias registradas. Revisa los detalles.')
        metric_table(integrity)
    if not issues.empty: metric_table(issues)
    test = AUD/'prueba_temporal.txt'
    st.subheader('Prueba temporal')
    if test.exists(): st.code(test.read_text(encoding='utf-8'))
    else: st.warning('No existe prueba_temporal.txt; falta verificar la ejecución del control temporal.')
    st.caption('La prueba temporal es parcial: no garantiza ausencia de filtraciones en todos los algoritmos o fechas.')

st.divider()
st.caption('No incluye apuestas ni recomendaciones. No escribe en CSV ni altera NBA estable, NFL o main.py.')

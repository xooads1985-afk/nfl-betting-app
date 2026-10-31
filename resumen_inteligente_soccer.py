"""Resumen Inteligente Soccer — módulo independiente de análisis estadístico.
Ejecutar: streamlit run resumen_inteligente_soccer.py
Integración futura: from resumen_inteligente_soccer import mostrar_resumen_inteligente_soccer
No requiere API ni modifica otros módulos.
"""
from __future__ import annotations

import io
import pandas as pd
import streamlit as st

TEAM_REQUIRED = ['fecha','liga','equipo','rival','local','goles_1t','goles_2t','goles_rival_1t','goles_rival_2t','corners_1t','corners_2t','corners_rival_1t','corners_rival_2t']
PLAYER_REQUIRED = ['fecha','liga','equipo','jugador','posicion','titular','minutos','goles','asistencias','tiros','tiros_puerta']
TEAM_METRICS = {
 'Goles a favor 1T':'goles_1t','Goles a favor 2T':'goles_2t','Goles a favor total':'goles_total',
 'Goles en contra 1T':'goles_rival_1t','Goles en contra 2T':'goles_rival_2t','Goles en contra total':'goles_rival_total',
 'Goles combinados 1T':'goles_combinados_1t','Goles combinados 2T':'goles_combinados_2t','Goles combinados total':'goles_combinados_total',
 'Córners a favor 1T':'corners_1t','Córners a favor 2T':'corners_2t','Córners a favor total':'corners_total',
 'Córners en contra 1T':'corners_rival_1t','Córners en contra 2T':'corners_rival_2t','Córners en contra total':'corners_rival_total',
 'Córners combinados 1T':'corners_combinados_1t','Córners combinados 2T':'corners_combinados_2t','Córners combinados total':'corners_combinados_total',
}
PLAYER_METRICS = {'Goles':'goles','Asistencias':'asistencias','Tiros':'tiros','Tiros a puerta':'tiros_puerta','Minutos':'minutos'}


def _read_csv(upload, required):
    if upload is None:
        return None
    try:
        df = pd.read_csv(upload)
        missing = [c for c in required if c not in df.columns]
        if missing:
            st.error('Faltan columnas: ' + ', '.join(missing))
            return None
        df['fecha'] = pd.to_datetime(df['fecha'], errors='coerce')
        if df['fecha'].isna().any():
            st.error('Hay fechas inválidas. Utiliza AAAA-MM-DD.')
            return None
        for c in required:
            if c not in ('fecha','liga','equipo','rival','local','jugador','posicion','titular'):
                df[c] = pd.to_numeric(df[c], errors='coerce')
        return df.sort_values('fecha').reset_index(drop=True)
    except Exception as exc:
        st.error(f'No se pudo leer el CSV: {exc}')
        return None


def _team_derived(df):
    d = df.copy()
    for stem in ('goles','corners'):
        d[f'{stem}_total'] = d[f'{stem}_1t'] + d[f'{stem}_2t']
        d[f'{stem}_rival_total'] = d[f'{stem}_rival_1t'] + d[f'{stem}_rival_2t']
        for period in ('1t','2t','total'):
            d[f'{stem}_combinados_{period}'] = d[f'{stem}_{period}'] + d[f'{stem}_rival_{period}']
    return d


def _forecast(series, min_history=3):
    """Proyección descriptiva: 70% últimos 5 + 30% historial completo."""
    s = pd.to_numeric(series, errors='coerce').dropna()
    if len(s) < min_history:
        return None
    return 0.7 * s.tail(5).mean() + 0.3 * s.mean()


def _validate(series, min_history=3):
    """Backtest cronológico sin usar el partido evaluado para proyectarlo."""
    s = pd.to_numeric(series, errors='coerce').dropna().reset_index(drop=True)
    errors = []
    for i in range(min_history, len(s)):
        p = _forecast(s.iloc[:i], min_history)
        if p is not None:
            errors.append((float(p), float(s.iloc[i])))
    if not errors:
        return None
    return {'n':len(errors), 'mae':sum(abs(p-y) for p,y in errors)/len(errors),
            'sesgo':sum(p-y for p,y in errors)/len(errors)}


def _format(value):
    if value is None or pd.isna(value):
        return 'N/D'
    return f'{0.0 if abs(float(value)) < 0.05 else float(value):.1f}'


def _metric_rows(df, metrics):
    rows = []
    for label, col in metrics.items():
        s = df[col].dropna() if col in df.columns else pd.Series(dtype=float)
        reference = float(s.tail(5).mean()) if len(s) else None
        projected = _forecast(s)
        edge = projected - reference if projected is not None and reference is not None else None
        check = _validate(s)
        rows.append({'Estadística':label, 'Últimos 5':_format(reference), 'Proyección':_format(projected),
                     'Edge':_format(edge), 'MAE':_format(check['mae'] if check else None),
                     'Sesgo':_format(check['sesgo'] if check else None),
                     'Evaluados':check['n'] if check else 0})
    return pd.DataFrame(rows)


def _sample_template(cols):
    return (','.join(cols) + '\n').encode('utf-8')


def mostrar_resumen_inteligente_soccer():
    st.title('⚽ Resumen Inteligente Soccer')
    st.caption('Versión inicial · análisis descriptivo · sin conexión API · datos cargados por el usuario')
    with st.expander('📁 Cargar datos y plantillas', expanded=True):
        st.write('Una fila por equipo y partido, y una fila por jugador y partido. Las fechas deben ser AAAA-MM-DD.')
        st.download_button('Plantilla CSV de equipos', _sample_template(TEAM_REQUIRED), 'plantilla_equipos_soccer.csv', 'text/csv')
        st.download_button('Plantilla CSV de jugadores', _sample_template(PLAYER_REQUIRED), 'plantilla_jugadores_soccer.csv', 'text/csv')
        file_team = st.file_uploader('CSV de equipos', type='csv', key='soccer_teams_csv')
        file_player = st.file_uploader('CSV de jugadores (opcional)', type='csv', key='soccer_players_csv')
    teams = _read_csv(file_team, TEAM_REQUIRED)
    players = _read_csv(file_player, PLAYER_REQUIRED)
    if teams is None or teams.empty:
        st.info('Carga un CSV de equipos para habilitar el análisis. No se generan resultados ficticios.')
        return
    teams = _team_derived(teams)
    leagues = sorted(teams['liga'].dropna().astype(str).unique())
    league = st.selectbox('🌍 Liga o torneo', leagues)
    td = teams[teams['liga'].astype(str) == league]
    names = sorted(td['equipo'].dropna().astype(str).unique())
    if not names:
        st.warning('No hay equipos en esta liga.')
        return
    home = st.selectbox('🏠 Equipo 1', names)
    other = [n for n in names if n != home]
    away = st.selectbox('✈️ Equipo 2', ['(Sin seleccionar)'] + other)
    tabs = st.tabs(['🏟️ Equipos y córners', '👥 Jugadores (máx. 2)', '📊 Historial'])
    with tabs[0]:
        st.caption('Edge = proyección − promedio últimos 5. No mide ventaja de apuestas.')
        for name in [home] + ([away] if away != '(Sin seleccionar)' else []):
            part = td[td['equipo'].astype(str) == name]
            st.subheader(name)
            st.caption(f'{len(part)} partidos disponibles · 3 mínimos para proyectar · 4 para validar')
            table = _metric_rows(part, TEAM_METRICS)
            for _, row in table.iterrows():
                with st.container(border=True):
                    st.markdown(f"**{row['Estadística']}**")
                    a,b,c = st.columns(3)
                    a.metric('Últimos 5',row['Últimos 5'])
                    b.metric('Proyección',row['Proyección'])
                    c.metric('Edge',row['Edge'])
            st.caption('Los goles y córners combinados corresponden al equipo seleccionado más su rival en cada partido histórico.')
    with tabs[1]:
        if players is None or players.empty:
            st.info('Carga el CSV de jugadores para habilitar esta sección.')
        else:
            pd_ = players[players['liga'].astype(str) == league]
            options = sorted(pd_['jugador'].dropna().astype(str).unique())
            chosen = st.multiselect('Selecciona hasta 2 jugadores', options, max_selections=2)
            for name in chosen:
                part = pd_[pd_['jugador'].astype(str) == name]
                st.subheader(name)
                st.caption(f"{len(part)} registros · {part['equipo'].iloc[-1]} · {part['posicion'].iloc[-1]}")
                for _, row in _metric_rows(part, PLAYER_METRICS).iterrows():
                    with st.container(border=True):
                        st.markdown(f"**{row['Estadística']}**")
                        a,b,c = st.columns(3)
                        a.metric('Últimos 5',row['Últimos 5'])
                        b.metric('Proyección',row['Proyección'])
                        c.metric('Edge',row['Edge'])
            if len(chosen) == 2:
                st.subheader('Comparación reciente')
                comparison = []
                for name in chosen:
                    part = pd_[pd_['jugador'].astype(str) == name]
                    comparison.append({'Jugador':name, **{k:_format(part[v].tail(5).mean()) for k,v in PLAYER_METRICS.items()}})
                st.dataframe(pd.DataFrame(comparison).set_index('Jugador').T, use_container_width=True)
    with tabs[2]:
        for name in [home] + ([away] if away != '(Sin seleccionar)' else []):
            part = td[td['equipo'].astype(str) == name]
            st.subheader(name)
            st.dataframe(_metric_rows(part, TEAM_METRICS)[['Estadística','MAE','Sesgo','Evaluados']], hide_index=True, use_container_width=True)
            st.caption('Validación cronológica: cada partido se evalúa usando solo los partidos anteriores.')
            with st.expander('Partidos históricos cargados'):
                st.dataframe(part[['fecha','equipo','rival','goles_total','goles_rival_total','corners_total','corners_rival_total']].sort_values('fecha',ascending=False), hide_index=True, use_container_width=True)
    st.caption('Los totales por tiempo requieren datos desglosados. No se estiman datos faltantes como si fueran observaciones.')


if __name__ == '__main__':
    st.set_page_config(page_title='Resumen Inteligente Soccer', page_icon='⚽', layout='wide')
    mostrar_resumen_inteligente_soccer()

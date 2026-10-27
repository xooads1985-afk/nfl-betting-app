"""Promedios descriptivos de puntos NFL; excluye partidos sin marcador."""
import pandas as pd
import streamlit as st

@st.cache_data(ttl=900, show_spinner=False)
def cargar_resultados(temporada):
    import nflreadpy as nfl
    df = nfl.load_schedules([temporada]).to_pandas()
    requeridas = ['game_id', 'season', 'gameday', 'home_team', 'away_team', 'home_score', 'away_score']
    faltantes = set(requeridas) - set(df.columns)
    if faltantes:
        raise ValueError(f'Faltan columnas: {sorted(faltantes)}')
    df = df[requeridas].copy()
    df['gameday'] = pd.to_datetime(df['gameday'], errors='coerce')
    for c in ('home_score', 'away_score'):
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.dropna(subset=['game_id', 'gameday', 'home_team', 'away_team', 'home_score', 'away_score'])
    df = df.drop_duplicates('game_id')
    return df.sort_values(['gameday', 'game_id'])


def resumen_equipos(partidos, ultimos=None):
    local = partidos[['gameday', 'game_id', 'home_team', 'home_score', 'away_score']].rename(
        columns={'home_team':'equipo','home_score':'anotados','away_score':'recibidos'})
    local['condicion'] = 'Local'
    visita = partidos[['gameday', 'game_id', 'away_team', 'away_score', 'home_score']].rename(
        columns={'away_team':'equipo','away_score':'anotados','home_score':'recibidos'})
    visita['condicion'] = 'Visitante'
    juegos = pd.concat([local, visita], ignore_index=True).sort_values(['equipo','gameday','game_id'])
    if ultimos is not None:
        juegos = juegos.groupby('equipo', group_keys=False).tail(ultimos)
    resumen = juegos.groupby('equipo', as_index=False).agg(
        PJ=('game_id','nunique'), PF=('anotados','sum'), PC=('recibidos','sum'))
    resumen['PF_por_partido'] = (resumen.PF / resumen.PJ).round(2)
    resumen['PC_por_partido'] = (resumen.PC / resumen.PJ).round(2)
    resumen['diferencia_por_partido'] = ((resumen.PF - resumen.PC) / resumen.PJ).round(2)
    return juegos, resumen


def mostrar_promedios_diferencias():
    st.subheader('🏈 Promedios y diferencias de puntos')
    st.caption('Estadísticas descriptivas basadas exclusivamente en partidos con marcador completo; no son líneas de apuestas.')
    temporada = st.selectbox('Temporada', [2026, 2025, 2024, 2023, 2022], key='pd_temporada')
    try:
        partidos = cargar_resultados(temporada)
    except Exception as exc:
        st.error(f'No fue posible cargar los resultados: {type(exc).__name__}: {exc}')
        return
    if partidos.empty:
        st.info('No hay partidos con resultado para esta temporada.')
        return
    equipos = sorted(set(partidos.home_team) | set(partidos.away_team))
    a, b = st.columns(2)
    equipo_a = a.selectbox('Equipo A', equipos, key='pd_equipo_a')
    equipo_b = b.selectbox('Equipo B', equipos, index=min(1,len(equipos)-1), key='pd_equipo_b')
    ventana = st.radio('Periodo', ['Temporada completa', 'Últimos 5 partidos'], horizontal=True)
    ultimos = 5 if ventana == 'Últimos 5 partidos' else None
    juegos, resumen = resumen_equipos(partidos, ultimos)
    comparacion = resumen[resumen.equipo.isin([equipo_a, equipo_b])].copy()
    st.dataframe(comparacion, use_container_width=True, hide_index=True)
    st.caption('PF: puntos anotados; PC: puntos recibidos. Diferencia promedio = (PF − PC) / PJ.')
    st.markdown('**Desglose local y visitante**')
    detalle = juegos[juegos.equipo.isin([equipo_a, equipo_b])].groupby(['equipo','condicion'], as_index=False).agg(
        PJ=('game_id','nunique'), PF=('anotados','sum'), PC=('recibidos','sum'))
    detalle['PF_por_partido'] = (detalle.PF / detalle.PJ).round(2)
    detalle['PC_por_partido'] = (detalle.PC / detalle.PJ).round(2)
    detalle['diferencia_por_partido'] = ((detalle.PF - detalle.PC) / detalle.PJ).round(2)
    st.dataframe(detalle, use_container_width=True, hide_index=True)
    st.markdown('### 🏈 Resultados partido por partido')

    individuales = juegos[
        juegos['equipo'].isin([equipo_a, equipo_b])
    ].copy()

    rivales = partidos[
        ['game_id', 'home_team', 'away_team']
    ].copy()

    individuales = individuales.merge(
        rivales,
        on='game_id',
        how='left',
        validate='many_to_one'
    )

    individuales['rival'] = individuales.apply(
        lambda r: (
            r['away_team']
            if r['condicion'] == 'Local'
            else r['home_team']
        ),
        axis=1
    )

    individuales['diferencia'] = (
        individuales['anotados'] - individuales['recibidos']
    )

    individuales['fecha'] = (
        pd.to_datetime(individuales['gameday'])
        .dt.strftime('%Y-%m-%d')
    )

    individuales = individuales[
        [
            'equipo', 'fecha', 'rival', 'condicion',
            'anotados', 'recibidos', 'diferencia'
        ]
    ].sort_values(
        ['equipo', 'fecha'],
        ascending=[True, False]
    )

    st.dataframe(
        individuales,
        use_container_width=True,
        hide_index=True
    )

    st.download_button(
        '📥 Descargar partidos individuales CSV',
        individuales.to_csv(index=False).encode('utf-8-sig'),
        f'partidos_individuales_nfl_{temporada}.csv',
        mime='text/csv',
        key='pd_partidos_csv'
    )
    st.markdown("### 📊 Análisis del próximo encuentro")

    st.caption(
        "Comparación descriptiva del rendimiento reciente. "
        "No representa una predicción del marcador."
    )

    if equipo_a == equipo_b:
        st.warning("Selecciona dos equipos diferentes.")
    else:
        recientes = resumen_equipos(partidos, 5)[1]

        comparacion_reciente = recientes[
            recientes["equipo"].isin([equipo_a, equipo_b])
        ].copy()

        comparacion_reciente = comparacion_reciente[
            [
                "equipo",
                "PJ",
                "PF_por_partido",
                "PC_por_partido",
                "diferencia_por_partido",
            ]
        ]

        comparacion_reciente = comparacion_reciente.rename(
            columns={
                "equipo": "Equipo",
                "PJ": "Partidos",
                "PF_por_partido": "Promedio anotado",
                "PC_por_partido": "Promedio recibido",
                "diferencia_por_partido": "Diferencia promedio",
            }
        )

        st.dataframe(
            comparacion_reciente,
            use_container_width=True,
            hide_index=True,
        )

        st.markdown("#### 🏟️ Rendimiento local y visitante")

        st.dataframe(
            detalle[
                [
                    "equipo",
                    "condicion",
                    "PJ",
                    "PF_por_partido",
                    "PC_por_partido",
                    "diferencia_por_partido",
                ]
            ],
            use_container_width=True,
            hide_index=True,
        )

        st.caption(
            "Los promedios locales y visitantes corresponden "
            "al periodo seleccionado arriba. "
            "Las muestras pequeñas pueden producir "
            "promedios poco representativos."
        )    

    # Comparación histórica de ataque y defensa, sin generar marcador previsto.
    st.markdown("### 🧭 Comparación ofensiva y defensiva")
    st.caption(
        "Los siguientes indicadores son históricos. "
        "No estiman los puntos que se anotarán en un partido futuro."
    )

    recientes_juegos, recientes_resumen = resumen_equipos(partidos, 5)
    filas = recientes_resumen.set_index("equipo")
    if equipo_a != equipo_b and all(e in filas.index for e in (equipo_a, equipo_b)):
        comparativa = pd.DataFrame([
            {
                "Equipo": equipo_a,
                "Ataque: puntos anotados/partido": filas.loc[equipo_a, "PF_por_partido"],
                "Defensa rival: puntos recibidos/partido": filas.loc[equipo_b, "PC_por_partido"],
                "Partidos analizados": int(filas.loc[equipo_a, "PJ"]),
            },
            {
                "Equipo": equipo_b,
                "Ataque: puntos anotados/partido": filas.loc[equipo_b, "PF_por_partido"],
                "Defensa rival: puntos recibidos/partido": filas.loc[equipo_a, "PC_por_partido"],
                "Partidos analizados": int(filas.loc[equipo_b, "PJ"]),
            },
        ])
        st.dataframe(comparativa, use_container_width=True, hide_index=True)

    st.markdown("### 📈 Evolución de puntos por encuentro")
    st.caption(
        "Cada punto de la gráfica corresponde a un partido finalizado "
        "dentro del periodo seleccionado. No son puntos acumulados."
    )
    for equipo in dict.fromkeys([equipo_a, equipo_b]):
        historial = juegos.loc[
            juegos["equipo"].eq(equipo),
            ["gameday", "game_id", "anotados", "recibidos"]
        ].sort_values(["gameday", "game_id"]).copy()
        if historial.empty:
            st.info(f"No hay partidos disponibles para {equipo}.")
            continue
        historial["Partido"] = range(1, len(historial) + 1)
        grafica = historial.set_index("Partido")[["anotados", "recibidos"]]
        grafica = grafica.rename(columns={
            "anotados": "Puntos anotados",
            "recibidos": "Puntos recibidos",
        })
        st.markdown(f"**{equipo} — {len(historial)} partidos**")
        st.line_chart(grafica)
        st.caption(
            f"Partidos ordenados del más antiguo al más reciente "
            f"({historial['gameday'].min():%Y-%m-%d} a "
            f"{historial['gameday'].max():%Y-%m-%d})."
        )

    st.download_button('📥 Descargar comparación CSV', comparacion.to_csv(index=False).encode('utf-8-sig'),
                       f'promedios_nfl_{temporada}.csv', mime='text/csv', key='pd_csv')


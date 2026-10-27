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



@st.cache_data(ttl=1800, show_spinner=False)
def cargar_marcadores_espn(temporada):
    """Consulta marcadores FINALIZADOS de temporada regular en ESPN (fuente distinta)."""
    import json
    from urllib.request import Request, urlopen
    resultados = []
    errores = []
    for semana in range(1, 19):
        url = ("https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
               f"?dates={temporada}&week={semana}&seasontype=2&limit=100")
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0 (NFL stats validator)",
                                        "Accept": "application/json"})
            with urlopen(req, timeout=12) as resp:
                payload = json.load(resp)
            for event in payload.get("events", []):
                if not event.get("status", {}).get("type", {}).get("completed", False):
                    continue
                competitions = event.get("competitions", [])
                if not competitions:
                    continue
                competidores = competitions[0].get("competitors", [])
                if len(competidores) != 2:
                    continue
                por_condicion = {x.get("homeAway"): x for x in competidores}
                if "home" not in por_condicion or "away" not in por_condicion:
                    continue
                h, a = por_condicion["home"], por_condicion["away"]
                # Abreviaturas que ESPN utiliza de manera diferente.
                alias = {"WSH": "WAS", "JAC": "JAX", "LA": "LAR"}
                home = alias.get(h.get("team", {}).get("abbreviation", ""),
                                 h.get("team", {}).get("abbreviation", ""))
                away = alias.get(a.get("team", {}).get("abbreviation", ""),
                                 a.get("team", {}).get("abbreviation", ""))
                resultados.append({"home_team": home, "away_team": away,
                                   "home_score_espn": int(h["score"]),
                                   "away_score_espn": int(a["score"]),
                                   "fecha_espn_utc": str(event.get("date", ""))[:10],
                                   "espn_id": str(event.get("id", ""))})
        except Exception as exc:
            errores.append(f"Semana {semana}: {type(exc).__name__}: {exc}")
    return pd.DataFrame(resultados, columns=["home_team", "away_team", "home_score_espn", "away_score_espn", "fecha_espn_utc", "espn_id"]), errores


def comparar_fuentes_nfl(partidos, externos, errores):
    """Relaciona equipos y fecha (±1 día por UTC); nunca inventa coincidencias."""
    base = partidos[["game_id", "gameday", "home_team", "away_team",
                     "home_score", "away_score"]].copy()
    base["fecha_nflverse"] = pd.to_datetime(base["gameday"]).dt.strftime("%Y-%m-%d")
    base = base.drop(columns=["gameday"])
    columnas_externas = ["home_score_espn", "away_score_espn", "fecha_espn_utc", "espn_id"]
    for col in columnas_externas:
        base[col] = pd.NA
    base["Estado"] = "SIN VERIFICAR"
    base["Observación"] = "Sin encuentro externo compatible"
    if externos.empty:
        base["Observación"] = "ESPN no devolvió partidos finalizados"
        return base, 0, len(base), 0

    # Normalizar variantes de abreviaturas en AMBAS fuentes.
    alias = {"WSH": "WAS", "JAC": "JAX", "LA": "LAR", "OAK": "LV",
             "SD": "LAC", "STL": "LAR"}
    def normalizar(valor):
        codigo = str(valor).strip().upper()
        return alias.get(codigo, codigo)

    ref = externos.copy()
    ref["_home"] = ref["home_team"].map(normalizar)
    ref["_away"] = ref["away_team"].map(normalizar)
    ref["_fecha"] = pd.to_datetime(ref["fecha_espn_utc"], errors="coerce", utc=True).dt.tz_localize(None)
    ref = ref.drop_duplicates(subset=["espn_id"], keep="first")
    usados = set()
    for idx, fila in base.iterrows():
        local = normalizar(fila["home_team"])
        visitante = normalizar(fila["away_team"])
        fecha = pd.to_datetime(fila["fecha_nflverse"], errors="coerce")
        candidatos = ref[(ref["_home"] == local) & (ref["_away"] == visitante)].copy()
        if pd.notna(fecha):
            candidatos = candidatos[(candidatos["_fecha"] - fecha).abs() <= pd.Timedelta(days=1)]
        candidatos = candidatos[~candidatos["espn_id"].astype(str).isin(usados)]
        if len(candidatos) == 0:
            base.at[idx, "Observación"] = (
                "Sin resultado ESPN para equipos y fecha (±1 día)"
                + ("; hubo fallos de consulta" if errores else ""))
            continue
        if len(candidatos) != 1:
            base.at[idx, "Observación"] = "Varias coincidencias posibles: revisión manual"
            continue
        externo = candidatos.iloc[0]
        usados.add(str(externo["espn_id"]))
        for col in columnas_externas:
            base.at[idx, col] = externo[col]
        iguales = (int(fila["home_score"]) == int(externo["home_score_espn"])
                   and int(fila["away_score"]) == int(externo["away_score_espn"]))
        base.at[idx, "Estado"] = "COINCIDE" if iguales else "DIFERENTE"
        base.at[idx, "Observación"] = (
            "Equipos y fecha compatibles; marcador igual" if iguales
            else "Equipos y fecha compatibles; marcador distinto")
    return (base, int((base["Estado"] == "COINCIDE").sum()),
            int((base["Estado"] == "SIN VERIFICAR").sum()),
            int((base["Estado"] == "DIFERENTE").sum()))

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
    st.markdown("### 📊 Comparación de rendimiento histórico")

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

    # Auditoría interna de todos los resultados disponibles en la temporada.
    # La fuente externa debe contrastarse por separado: esto no certifica NFLverse.
    st.markdown("### 🔎 Auditoría estadística de toda la liga")
    with st.expander("Ver auditoría de los equipos y descargar reportes", expanded=False):
        todos_juegos, todos_resumen = resumen_equipos(partidos)
        auditoria = todos_resumen.sort_values("equipo").reset_index(drop=True).copy()
        locales = todos_juegos[todos_juegos["condicion"] == "Local"].groupby("equipo").agg(
            PJ_local=("game_id", "nunique"), PF_local=("anotados", "sum"),
            PC_local=("recibidos", "sum"))
        visitantes = todos_juegos[todos_juegos["condicion"] == "Visitante"].groupby("equipo").agg(
            PJ_visitante=("game_id", "nunique"), PF_visitante=("anotados", "sum"),
            PC_visitante=("recibidos", "sum"))
        auditoria = auditoria.merge(locales, left_on="equipo", right_index=True, how="left")
        auditoria = auditoria.merge(visitantes, left_on="equipo", right_index=True, how="left")
        columnas_desglose = ["PJ_local", "PF_local", "PC_local", "PJ_visitante", "PF_visitante", "PC_visitante"]
        auditoria[columnas_desglose] = auditoria[columnas_desglose].fillna(0).astype(int)
        auditoria["PJ_correcto"] = auditoria["PJ"] == (auditoria["PJ_local"] + auditoria["PJ_visitante"])
        auditoria["PF_correcto"] = auditoria["PF"] == (auditoria["PF_local"] + auditoria["PF_visitante"])
        auditoria["PC_correcto"] = auditoria["PC"] == (auditoria["PC_local"] + auditoria["PC_visitante"])
        auditoria["Promedios_correctos"] = (
            ((auditoria["PF"] / auditoria["PJ"]).round(2) == auditoria["PF_por_partido"])
            & ((auditoria["PC"] / auditoria["PJ"]).round(2) == auditoria["PC_por_partido"])
            & (((auditoria["PF"] - auditoria["PC"]) / auditoria["PJ"]).round(2)
               == auditoria["diferencia_por_partido"])
        )
        comprobaciones = ["PJ_correcto", "PF_correcto", "PC_correcto", "Promedios_correctos"]
        auditoria["Estado"] = auditoria[comprobaciones].all(axis=1).map({True: "OK", False: "REVISAR"})

        ids_duplicados = int(partidos["game_id"].duplicated().sum())
        marcadores_invalidos = int(((partidos["home_score"] < 0) | (partidos["away_score"] < 0)
                                   | (partidos["home_score"] % 1 != 0)
                                   | (partidos["away_score"] % 1 != 0)).sum())
        equipos_iguales = int((partidos["home_team"] == partidos["away_team"]).sum())
        total_pf = int(auditoria["PF"].sum())
        total_pc = int(auditoria["PC"].sum())
        errores_equipos = int((auditoria["Estado"] != "OK").sum())
        errores_globales = (ids_duplicados + marcadores_invalidos + equipos_iguales
                            + int(total_pf != total_pc) + errores_equipos)

        c1, c2, c3 = st.columns(3)
        c1.metric("Equipos con resultados", len(auditoria))
        c2.metric("Partidos únicos", len(partidos))
        c3.metric("Comprobaciones fallidas", errores_globales)
        if len(auditoria) != 32:
            st.warning(f"Se encontraron {len(auditoria)} equipos con partidos finalizados, no 32. "
                       "Esto puede deberse a la cobertura de la fuente o al momento de la temporada.")
        if errores_globales:
            st.error("Hay inconsistencias en los datos procesados. Revisa la tabla y la fuente.")
        else:
            st.success("Las comprobaciones internas sobre los datos procesados pasaron.")
        st.caption(f"Control global: PF={total_pf:,}; PC={total_pc:,}. "
                   f"IDs repetidos tras la carga={ids_duplicados}; marcadores inválidos={marcadores_invalidos}; "
                   f"local=visitante={equipos_iguales}.")
        st.dataframe(auditoria, use_container_width=True, hide_index=True)
        st.download_button(
            "📥 Descargar auditoría de equipos CSV",
            auditoria.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"auditoria_equipos_nfl_{temporada}.csv",
            mime="text/csv", key="pd_auditoria_equipos_csv")
        juegos_exportar = partidos.copy()
        juegos_exportar["gameday"] = juegos_exportar["gameday"].dt.strftime("%Y-%m-%d")
        st.download_button(
            "📥 Descargar todos los partidos CSV",
            juegos_exportar.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"todos_los_partidos_nfl_{temporada}.csv",
            mime="text/csv", key="pd_todos_partidos_csv")
        st.info("Esta auditoría comprueba coherencia matemática de los datos cargados. "
                "No detecta filas descartadas antes de la carga ni verifica por sí sola "
                "que cada marcador coincida con una fuente externa independiente.")


    st.markdown("### 🌐 Supervisión y verificación externa")
    with st.expander("Supervisar resultados y comparar con ESPN", expanded=False):
        st.caption("La supervisión se ejecuta al abrir esta sección y cuando Streamlit "
                   "vuelve a ejecutar la página. No funciona en segundo plano con la app cerrada.")
        automatico = st.checkbox("Activar supervisión automática al usar la página",
                                 value=False, key="pd_auto_supervision")
        actualizar = st.button("🔄 Actualizar ahora y verificar", key="pd_ejecutar_externa")
        partidos_revision = partidos
        if actualizar:
            cargar_resultados.clear()
            cargar_marcadores_espn.clear()
            try:
                with st.spinner("Actualizando resultados de ambas fuentes..."):
                    partidos_revision = cargar_resultados(temporada)
            except Exception as exc:
                st.error(f"No se pudieron actualizar los resultados: {type(exc).__name__}: {exc}")
                partidos_revision = None

        if (automatico or actualizar) and partidos_revision is not None:
            with st.spinner("Revisando marcadores de ESPN..."):
                espn, errores_espn = cargar_marcadores_espn(temporada)
                comparados, coinciden, sin_verificar, diferentes = comparar_fuentes_nfl(
                    partidos_revision, espn, errores_espn)

            ahora = pd.Timestamp.now(tz="UTC")
            st.caption(f"Última revisión de la página: {ahora:%Y-%m-%d %H:%M} UTC · "
                       f"Resultados recibidos de ESPN: {len(espn)} · "
                       "Caché de ESPN: hasta 30 minutos; fuente principal: hasta 15 minutos, salvo actualización manual.")
            col1, col2, col3 = st.columns(3)
            col1.metric("Coinciden", coinciden)
            col2.metric("Diferentes", diferentes)
            col3.metric("Sin verificar", sin_verificar)

            # Comparación contra la última revisión de ESTA sesión de Streamlit.
            clave = f"pd_snapshot_{temporada}"
            actual = set(partidos_revision["game_id"].astype(str))
            anterior = st.session_state.get(clave)
            if anterior is None:
                st.info("Primera revisión de esta sesión: no hay referencia previa "
                        "para identificar partidos nuevos.")
            else:
                nuevos = actual - anterior
                if nuevos:
                    st.info(f"🆕 {len(nuevos)} partido(s) nuevo(s) desde la revisión anterior: "
                            + ", ".join(sorted(nuevos)[:10])
                            + ("…" if len(nuevos) > 10 else ""))
                else:
                    st.caption("Sin partidos nuevos desde la revisión anterior de esta sesión.")
            st.session_state[clave] = actual

            if errores_espn:
                st.warning(f"Fallaron {len(errores_espn)} consultas semanales de ESPN; "
                           "los partidos sin verificar no se consideran errores de marcador.")
                with st.expander("Ver errores de conexión"):
                    st.write(errores_espn)
            if diferentes:
                st.error(f"⚠️ {diferentes} partido(s) con marcador diferente entre fuentes.")
            if sin_verificar:
                st.warning(f"⚠️ {sin_verificar} partido(s) pendientes de verificación externa.")
            if len(partidos_revision) > 0 and not diferentes and not sin_verificar and not errores_espn:
                st.success("Todos los partidos cargados coinciden con ESPN en esta revisión.")
            st.dataframe(comparados, use_container_width=True, hide_index=True)
            st.download_button("📥 Descargar reporte de verificación CSV",
                               comparados.to_csv(index=False).encode("utf-8-sig"),
                               file_name=f"verificacion_externa_nfl_{temporada}.csv",
                               mime="text/csv", key="pd_externa_csv")
        else:
            if partidos_revision is not None:
                st.info("Activa la supervisión o pulsa 'Actualizar ahora y verificar'. "
                        "La verificación externa no se ejecuta hasta entonces.")


    # Panel descriptivo de salud de los datos persistidos en GitHub.
    st.markdown("### 🩺 Panel de Salud de Datos NFL")
    with st.expander("Consultar estado y alertas del historial", expanded=False):
        st.caption("Estado calculado a partir del último registro guardado por GitHub Actions. "
                   "No comprueba en tiempo real si la tarea programada sigue activa.")
        if st.button("🔄 Revisar salud de datos", key="pd_salud_actualizar"):
            from urllib.request import Request, urlopen
            from io import BytesIO
            url_salud = (
                "https://raw.githubusercontent.com/xooads1985-afk/nfl-betting-app/"
                f"main/datos_auditoria/historial_{temporada}.csv"
            )
            try:
                req = Request(url_salud, headers={"User-Agent": "NFL-stats-health"})
                with urlopen(req, timeout=15) as respuesta:
                    contenido_salud = respuesta.read()
                registros = pd.read_csv(BytesIO(contenido_salud))
                if registros.empty:
                    st.warning("El historial existe, pero no contiene revisiones.")
                elif "fecha_utc" not in registros.columns:
                    st.error("El historial no contiene la columna fecha_utc.")
                else:
                    registros = registros.copy()
                    registros["_fecha"] = pd.to_datetime(
                        registros["fecha_utc"], utc=True, errors="coerce")
                    registros = registros.dropna(subset=["_fecha"]).sort_values("_fecha")
                    if registros.empty:
                        st.error("No se encontraron fechas válidas en el historial.")
                    else:
                        ultimo = registros.iloc[-1]
                        anterior = registros.iloc[-2] if len(registros) >= 2 else None
                        ahora_utc = pd.Timestamp.now(tz="UTC")
                        horas = max(0.0, (ahora_utc - ultimo["_fecha"]).total_seconds() / 3600)

                        def numero(nombre):
                            if nombre not in registros.columns:
                                return None
                            valor = pd.to_numeric(pd.Series([ultimo[nombre]]), errors="coerce").iloc[0]
                            return int(valor) if pd.notna(valor) else None

                        partidos_guardados = numero("partidos")
                        coinciden_guardados = numero("coinciden")
                        diferentes_guardados = numero("diferentes")
                        pendientes_guardados = numero("sin_verificar")
                        if pendientes_guardados is None:
                            pendientes_guardados = numero("sin_verificar_externa")

                        # Los umbrales son orientativos y configurables, no una prueba
                        # de que GitHub Actions haya ejecutado o no su horario.
                        if diferentes_guardados is not None and diferentes_guardados > 0:
                            estado = "🔴 Revisar: hay marcadores diferentes"
                            mostrar_estado = st.error
                        elif horas > 48:
                            estado = "🔴 Revisar: última revisión hace más de 48 h"
                            mostrar_estado = st.error
                        elif horas > 30 or (pendientes_guardados is not None and pendientes_guardados > 0):
                            estado = "🟡 Atención: revisión atrasada o pendiente de verificar"
                            mostrar_estado = st.warning
                        elif diferentes_guardados is None or pendientes_guardados is None:
                            estado = "🟡 Atención: faltan columnas para validar discrepancias"
                            mostrar_estado = st.warning
                        else:
                            estado = "🟢 Correcto según el último historial disponible"
                            mostrar_estado = st.success
                        mostrar_estado(estado)
                        st.caption("Umbrales de antigüedad: atención >30 horas; revisar >48 horas. "
                                   "Estos límites son orientativos para una tarea diaria.")
                        st.metric("Revisiones guardadas", len(registros))
                        st.metric("Antigüedad de la última revisión", f"{horas:.1f} h")
                        st.caption("Última revisión guardada: "
                                   f"{ultimo['_fecha']:%Y-%m-%d %H:%M:%S} UTC")
                        # Indicadores en un único bloque, sin columnas anidadas en móvil.
                        indicadores = pd.DataFrame({
                            "Indicador": ["Partidos registrados", "Marcadores coincidentes",
                                          "Marcadores diferentes", "Sin verificar"],
                            "Valor": [partidos_guardados, coinciden_guardados,
                                      diferentes_guardados, pendientes_guardados],
                        })
                        indicadores["Valor"] = indicadores["Valor"].map(
                            lambda valor: "N/D" if pd.isna(valor) else str(int(valor))
                        )
                        st.dataframe(indicadores, use_container_width=True, hide_index=True)
                        if anterior is not None and partidos_guardados is not None:
                            previo = pd.to_numeric(pd.Series([anterior.get("partidos")]), errors="coerce").iloc[0]
                            if pd.notna(previo):
                                cambio = partidos_guardados - int(previo)
                                if cambio > 0:
                                    st.info(f"🆕 {cambio} partido(s) adicionales respecto a la revisión anterior.")
                                elif cambio == 0:
                                    st.caption("No cambió el número de partidos desde la revisión anterior.")
                                else:
                                    st.warning(f"El historial registra {abs(cambio)} partido(s) menos que antes; revisar.")
                        else:
                            st.caption("Se necesitan al menos dos revisiones para calcular cambios.")
                        st.dataframe(registros.drop(columns=["_fecha"]).tail(5).iloc[::-1],
                                     use_container_width=True, hide_index=True)
            except Exception as exc:
                st.error("No se pudo consultar el historial de GitHub. "
                         f"Detalle: {type(exc).__name__}: {exc}")

    st.markdown("### 🗂️ Historial permanente de revisiones")
    with st.expander("Consultar historial guardado en GitHub", expanded=False):
        st.caption("Este historial se genera mediante GitHub Actions. "
                   "No depende de la sesión de Streamlit y no se actualiza "
                   "automáticamente al abrir esta página.")
        ruta_historial = (
            "https://raw.githubusercontent.com/xooads1985-afk/nfl-betting-app/"
            f"main/datos_auditoria/historial_{temporada}.csv"
        )
        if st.button("🔄 Consultar historial guardado", key="pd_ver_historial"):
            try:
                from urllib.request import Request, urlopen
                from io import BytesIO
                req = Request(ruta_historial, headers={"User-Agent": "NFL-stats-history"})
                with urlopen(req, timeout=15) as respuesta:
                    contenido = respuesta.read()
                historial = pd.read_csv(BytesIO(contenido))
                if historial.empty:
                    st.info("Todavía no hay revisiones guardadas.")
                else:
                    st.metric("Revisiones guardadas", len(historial))
                    st.dataframe(historial.iloc[::-1], use_container_width=True, hide_index=True)
                    columnas_grafica = [c for c in ("partidos", "coinciden") if c in historial.columns]
                    if "fecha_utc" in historial.columns and columnas_grafica:
                        st.line_chart(historial.set_index("fecha_utc")[columnas_grafica])
                    else:
                        st.warning("No hay columnas suficientes para dibujar la evolución histórica.")
                    st.download_button("📥 Descargar historial CSV", contenido,
                                       file_name=f"historial_nfl_{temporada}.csv",
                                       mime="text/csv", key="pd_historial_descarga")
            except Exception as exc:
                st.warning("Aún no se pudo leer el historial desde GitHub. "
                           "Ejecuta primero la tarea programada y comprueba que "
                           "el repositorio sea público o accesible desde la aplicación. "
                           f"Detalle: {type(exc).__name__}: {exc}")

    st.download_button('📥 Descargar comparación CSV', comparacion.to_csv(index=False).encode('utf-8-sig'),
                       f'promedios_nfl_{temporada}.csv', mime='text/csv', key='pd_csv')



"""Comparador de estadísticas NFL observadas. Sin cuotas ni apuestas."""
import pandas as pd
import streamlit as st
import altair as alt
from modulo_nfl import cargar_jugadores_nfl_v39, TEMPORADAS

METRICAS = {
    "QB": {"Pases completos": ["completions"], "Intentos de pase": ["attempts", "passing_attempts"], "Yardas de pase": ["passing_yards"], "TD de pase": ["passing_tds"], "Intercepciones lanzadas": ["interceptions", "passing_interceptions"], "Yardas terrestres": ["rushing_yards"]},
    "RB": {"Acarreos": ["carries", "rushing_attempts"], "Yardas terrestres": ["rushing_yards"], "TD terrestres": ["rushing_tds"], "Recepciones": ["receptions"], "Yardas recibidas": ["receiving_yards"]},
    "WR": {"Recepciones": ["receptions"], "Objetivos de pase": ["targets"], "Yardas recibidas": ["receiving_yards"], "TD recibidos": ["receiving_tds"]},
    "TE": {"Recepciones": ["receptions"], "Objetivos de pase": ["targets"], "Yardas recibidas": ["receiving_yards"], "TD recibidos": ["receiving_tds"]},
}


def primera_columna(df, alternativas):
    return next((c for c in alternativas if c in df.columns), None)


def preparar_datos(datos):
    """Filtra identificadores sin nombre y conserva solo registros semanales."""
    datos = datos.copy()
    datos.columns = [str(c).lower() for c in datos.columns]
    nombre = primera_columna(datos, ["player_display_name", "player_name", "player"])
    semana = primera_columna(datos, ["week"])
    if not nombre or not semana:
        raise ValueError("Faltan columnas de nombre de jugador o semana.")
    datos[nombre] = datos[nombre].astype("string").str.strip()
    datos = datos[datos[nombre].notna() & datos[nombre].ne("") & ~datos[nombre].str.lower().isin(["nan", "none", "null", "<na>"])].copy()
    datos[semana] = pd.to_numeric(datos[semana], errors="coerce")
    datos = datos.dropna(subset=[semana])
    return datos, nombre, semana


def mostrar_comparador():
    st.title("🏈 Comparación de jugadores NFL")
    st.caption("Datos observados de NFLverse. Compara jugadores de la misma posición cuando haya estadísticas compatibles.")
    temporada = st.selectbox("Temporada", sorted(TEMPORADAS, reverse=True), key="comp_temporada_elegida")
    if st.button("📥 Cargar estadísticas", key="comp_cargar"):
        st.session_state["comp_temporada"] = temporada
    if st.session_state.get("comp_temporada") != temporada:
        st.info("Pulsa «Cargar estadísticas» para comenzar.")
        return
    try:
        with st.spinner("Consultando estadísticas NFL..."):
            datos = cargar_jugadores_nfl_v39(int(temporada))
            if datos.empty:
                st.info("La fuente no tiene estadísticas disponibles para esta temporada.")
                return
            datos, nombre, semana = preparar_datos(datos)
    except Exception as exc:
        st.error("No se pudieron preparar las estadísticas.")
        st.code(f"{type(exc).__name__}: {exc}")
        return
    if datos.empty:
        st.warning("No hay jugadores con nombre y semana válidos.")
        return
    equipo = primera_columna(datos, ["recent_team", "team", "posteam"])
    posicion = primera_columna(datos, ["position", "player_position", "pos"])
    pid = primera_columna(datos, ["player_id", "gsis_id"])
    if not posicion:
        st.warning("La fuente no incluye la posición del jugador. No es seguro seleccionar métricas según posición.")
        return
    datos[posicion] = datos[posicion].astype("string").str.upper().str.strip()
    posiciones = sorted(set(datos[posicion].dropna()) & set(METRICAS))
    if not posiciones:
        st.warning("No hay posiciones ofensivas compatibles (QB, RB, WR o TE) en estos datos.")
        return
    posicion_elegida = st.selectbox("Posición", posiciones, key="comp_posicion")
    datos = datos[datos[posicion].eq(posicion_elegida)].copy()
    if equipo:
        datos[equipo] = datos[equipo].astype("string").str.strip()
        equipos = sorted(x for x in datos[equipo].dropna().unique() if x)
        equipo_elegido = st.selectbox("Equipo", ["Todos los equipos"] + equipos, key="comp_equipo")
        if equipo_elegido != "Todos los equipos":
            datos = datos[datos[equipo].eq(equipo_elegido)].copy()
    else:
        st.caption("La fuente no incluye un campo de equipo.")
    if datos.empty:
        st.info("No hay jugadores para esos filtros.")
        return
    datos["_clave"] = datos[pid].astype("string").str.strip() if pid else datos[nombre].copy()
    sin_id = datos["_clave"].isna() | datos["_clave"].isin(["", "nan", "None"])
    datos.loc[sin_id, "_clave"] = "nombre:" + datos.loc[sin_id, nombre]
    datos["_etiqueta"] = datos[nombre].astype(str)
    if equipo:
        datos["_etiqueta"] += " · " + datos[equipo].fillna("Sin equipo").astype(str)
    opciones = (datos.sort_values(semana).groupby("_clave", sort=False)["_etiqueta"].last().to_dict())
    claves = sorted(opciones, key=lambda x: opciones[x].casefold())
    if len(claves) < 2:
        st.info("Se necesitan al menos dos jugadores con estos filtros. Prueba «Todos los equipos».")
        return
    a = st.selectbox("Jugador A", claves, format_func=lambda k: opciones[k], key="comp_a")
    b = st.selectbox("Jugador B", [k for k in claves if k != a], format_func=lambda k: opciones[k], key="comp_b")
    metricas = {etiqueta: col for etiqueta, candidatas in METRICAS[posicion_elegida].items()
                if (col := primera_columna(datos, candidatas)) is not None}
    if not metricas:
        st.warning("No hay estadísticas compatibles para esta posición.")
        return
    metrica = st.selectbox("Estadística", list(metricas), key="comp_metrica")
    columna = metricas[metrica]
    elegidos = datos[datos["_clave"].isin([a, b])].copy()
    elegidos[columna] = pd.to_numeric(elegidos[columna], errors="coerce")
    elegidos["Jugador"] = elegidos["_clave"].map({a: opciones[a], b: opciones[b]})
    elegidos["Semana"] = elegidos[semana].astype(int)
    semanal = (elegidos.groupby(["Jugador", "Semana"], as_index=False)[columna]
               .sum(min_count=1).rename(columns={columna: metrica}))
    totales = (elegidos.groupby("Jugador", as_index=False)[columna]
               .sum(min_count=1).rename(columns={columna: metrica}))
    st.subheader("📋 Totales de temporada")
    st.dataframe(totales, hide_index=True, use_container_width=True)
    if totales[metrica].isna().any():
        st.warning("Al menos un jugador no tiene datos publicados para esta estadística; no se sustituye por cero.")
    st.subheader("📈 Rendimiento semanal")
    grafica_datos = semanal.dropna(subset=[metrica])
    if grafica_datos.empty:
        st.info("No hay datos semanales publicados para representar esta métrica.")
    else:
        grafica = (alt.Chart(grafica_datos).mark_line(point=True)
                   .encode(x=alt.X("Semana:O", title="Semana"),
                           y=alt.Y(f"{metrica}:Q", title=metrica),
                           color=alt.Color("Jugador:N"),
                           tooltip=["Jugador", "Semana", alt.Tooltip(f"{metrica}:Q")])
                   .properties(height=260))
        st.altair_chart(grafica, use_container_width=True)
    st.caption("Solo se usan estadísticas publicadas. Los valores ausentes no se convierten en ceros.")
    st.download_button("📥 Descargar comparación CSV", semanal.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"comparacion_jugadores_{temporada}.csv", mime="text/csv")


if __name__ == "__main__":
    mostrar_comparador()


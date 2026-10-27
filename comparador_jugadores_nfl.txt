"""Comparación descriptiva de jugadores NFL. Sin cuotas ni apuestas."""
import pandas as pd
import streamlit as st
import altair as alt
from modulo_nfl_v4_9_3 import cargar_jugadores_nfl_v39, TEMPORADAS

METRICAS = {
    "Pases completos": ["completions"],
    "Intentos de pase": ["attempts", "passing_attempts"],
    "Yardas por pase": ["passing_yards"],
    "TD por pase": ["passing_tds"],
    "Intercepciones lanzadas": ["interceptions", "passing_interceptions"],
    "Acarreos": ["carries", "rushing_attempts"],
    "Yardas terrestres": ["rushing_yards"],
    "TD terrestres": ["rushing_tds"],
    "Recepciones": ["receptions"],
    "Objetivos de pase": ["targets"],
    "Yardas por recepción": ["receiving_yards"],
    "TD por recepción": ["receiving_tds"],
}

def primera_columna(df, nombres):
    return next((c for c in nombres if c in df.columns), None)

def mostrar_comparador():
    st.title("🏈 Comparación de jugadores NFL")
    st.caption("Estadísticas observadas de NFLverse. Sin proyecciones.")
    temporada = st.selectbox("Temporada", sorted(TEMPORADAS, reverse=True))
    if st.button("📥 Cargar estadísticas", key="comp_cargar"):
        st.session_state["comp_temporada"] = temporada
    if st.session_state.get("comp_temporada") != temporada:
        st.info("Pulsa «Cargar estadísticas» para comenzar.")
        return
    try:
        with st.spinner("Consultando estadísticas..."):
            datos = cargar_jugadores_nfl_v39(int(temporada)).copy()
    except Exception as exc:
        st.error("No fue posible cargar las estadísticas.")
        st.code(f"{type(exc).__name__}: {exc}")
        return
    if datos.empty:
        st.info("No hay registros disponibles.")
        return
    nombre = primera_columna(datos, ["player_display_name", "player_name", "player"])
    pid = primera_columna(datos, ["player_id", "gsis_id"])
    equipo = primera_columna(datos, ["recent_team", "team", "posteam"])
    semana = primera_columna(datos, ["week"])
    if not nombre or not semana:
        st.warning("La fuente no proporciona nombres y semanas suficientes para comparar.")
        return
    datos[nombre] = datos[nombre].fillna("").astype(str)
    datos[semana] = pd.to_numeric(datos[semana], errors="coerce")
    datos = datos.dropna(subset=[semana])
    if datos.empty:
        st.info("No hay registros semanales válidos.")
        return
    metricas = {et: c for et, alternativas in METRICAS.items()
                if (c := primera_columna(datos, alternativas)) is not None}
    if not metricas:
        st.warning("No hay métricas reconocidas en la fuente.")
        return
    # Clave estable cuando NFLverse publica un identificador.
    datos["_clave"] = datos[pid].fillna("").astype(str) if pid else datos[nombre]
    if pid:
        faltan = datos["_clave"].eq("") | datos["_clave"].eq("nan")
        datos.loc[faltan, "_clave"] = "nombre:" + datos.loc[faltan, nombre]
    datos["_etiqueta"] = datos[nombre]
    if equipo:
        datos["_etiqueta"] += " · " + datos[equipo].fillna("").astype(str)
    opciones = (datos.sort_values([semana]).groupby("_clave", sort=False)
                ["_etiqueta"].last().to_dict())
    claves = sorted(opciones, key=lambda x: opciones[x].lower())
    if len(claves) < 2:
        st.info("Se necesitan al menos dos jugadores.")
        return
    a = st.selectbox("Jugador A", claves, format_func=lambda k: opciones[k],
                     key="comp_a")
    b = st.selectbox("Jugador B", [k for k in claves if k != a],
                     format_func=lambda k: opciones[k], key="comp_b")
    metrica = st.selectbox("Estadística", list(metricas), key="comp_metrica")
    columna = metricas[metrica]
    datos[columna] = pd.to_numeric(datos[columna], errors="coerce")
    elegidos = datos[datos["_clave"].isin([a, b])].copy()
    elegidos["Jugador"] = elegidos["_clave"].map({a: opciones[a], b: opciones[b]})
    elegidos["Semana"] = elegidos[semana].astype(int)
    # Sumas semanales y totales únicamente de valores publicados.
    semanal = (elegidos.groupby(["Jugador", "Semana"], as_index=False)
               [columna].sum(min_count=1).rename(columns={columna: metrica}))
    totales = (elegidos.groupby("Jugador", as_index=False)[columna]
               .sum(min_count=1).rename(columns={columna: metrica}))
    st.subheader("📋 Totales de temporada")
    st.dataframe(totales, hide_index=True, use_container_width=True)
    st.subheader("📈 Rendimiento semanal")
    grafica = (alt.Chart(semanal.dropna(subset=[metrica]))
               .mark_line(point=True)
               .encode(x=alt.X("Semana:O", title="Semana"),
                       y=alt.Y(f"{metrica}:Q", title=metrica),
                       color=alt.Color("Jugador:N"),
                       tooltip=["Jugador", "Semana", alt.Tooltip(f"{metrica}:Q")])
               .properties(height=240))
    st.altair_chart(grafica, use_container_width=True)
    st.caption("Las semanas sin datos publicados no se rellenan con ceros.")
    st.download_button("📥 Descargar comparación CSV",
                       semanal.to_csv(index=False).encode("utf-8-sig"),
                       file_name=f"comparacion_jugadores_{temporada}.csv",
                       mime="text/csv")
if __name__ == "__main__":
    mostrar_comparador()

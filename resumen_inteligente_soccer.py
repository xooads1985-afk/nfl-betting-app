"""Resumen Inteligente Soccer - prototipo independiente.
Ejecutar: streamlit run resumen_inteligente_soccer.py
Clave opcional en Streamlit Secrets: API_FOOTBALL_KEY
"""
import os
from datetime import datetime, timezone
from statistics import mean
import requests
import streamlit as st

DATA = {
    "Atlético Azul": {"goles": [2, 1, 3, 0, 2], "contra": [1, 0, 1, 2, 1], "corners": [6, 4, 7, 3, 5], "goles_1t": [1, 0, 2, 0, 1], "corners_1t": [3, 2, 4, 1, 2]},
    "Deportivo Verde": {"goles": [1, 2, 1, 2, 0], "contra": [1, 2, 0, 1, 2], "corners": [5, 6, 4, 5, 3], "goles_1t": [0, 1, 1, 1, 0], "corners_1t": [2, 3, 1, 3, 1]},
    "Unión Roja": {"goles": [0, 2, 2, 1, 3], "contra": [2, 1, 1, 0, 2], "corners": [3, 5, 6, 4, 7], "goles_1t": [0, 1, 1, 0, 2], "corners_1t": [1, 2, 3, 2, 4]}
}
PLAYERS = {
    "Atlético Azul": {"Delantero Azul": {"min": [83, 90, 72, 88, 85], "goles": [1, 0, 2, 0, 1]}, "Medio Azul": {"min": [90, 76, 84, 90, 80], "goles": [0, 0, 0, 0, 1]}},
    "Deportivo Verde": {"Delantero Verde": {"min": [90, 65, 80, 90, 75], "goles": [1, 0, 0, 1, 0]}},
    "Unión Roja": {"Delantero Rojo": {"min": [90, 85, 90, 70, 90], "goles": [0, 1, 1, 0, 2]}}
}
def validation(values):
    errors = [mean(values[:i]) - values[i] for i in range(3, len(values))]
    return {"N": len(errors), "MAE": round(mean(map(abs, errors)), 2), "Sesgo": round(mean(errors), 2)} if errors else {"N": 0, "MAE": "N/D", "Sesgo": "N/D"}
def secret_key():
    """Obtiene la clave sin mostrarla; devuelve (clave, diagnóstico seguro)."""
    try:
        value = st.secrets.get("API_FOOTBALL_KEY")
    except Exception as exc:
        # Nunca mostrar el texto de la excepción: podría contener datos privados.
        env_value = os.environ.get("API_FOOTBALL_KEY", "").strip()
        if env_value:
            return env_value, "Clave encontrada en variable de entorno."
        return "", ("No se pudieron leer los Secrets de esta aplicación "
                    f"({type(exc).__name__}). Comprueba Settings → Secrets.")

    if isinstance(value, str) and value.strip():
        return value.strip(), "Clave encontrada en Secrets de esta aplicación."
    if value is not None and not isinstance(value, str):
        return "", "API_FOOTBALL_KEY existe, pero debe ser texto entre comillas."

    env_value = os.environ.get("API_FOOTBALL_KEY", "").strip()
    if env_value:
        return env_value, "Clave encontrada en variable de entorno."
    return "", ("API_FOOTBALL_KEY no está disponible para esta aplicación. "
                "Revisa el nombre y guarda los Secrets de esta app.")


@st.cache_data(ttl=3600, show_spinner=False)
def fetch(endpoint, params, key):
    response = requests.get("https://v3.football.api-sports.io/" + endpoint,
                            headers={"x-apisports-key": key}, params=params, timeout=20)
    response.raise_for_status()
    result = response.json()
    if result.get("errors"):
        raise RuntimeError(str(result["errors"]))
    return result


def mostrar_resumen_inteligente_soccer():
    """Muestra el módulo Soccer dentro de la aplicación principal."""
    st.title("⚽ Resumen Inteligente Soccer")
    st.caption("Prototipo inicial · Optimizado para móvil")
    mode = st.radio("Fuente", ["Demostración", "API-Football"], horizontal=True)
    if mode == "Demostración":
        st.warning("Todos los equipos, jugadores y datos de esta sección son ficticios.")
        st.selectbox("Liga", ["Liga de demostración"])
        home = st.selectbox("Local", list(DATA))
        away = st.selectbox("Visitante", [t for t in DATA if t != home])
        a, b = DATA[home], DATA[away]
        h_proj = (mean(a["goles"]) + mean(b["contra"])) / 2
        v_proj = (mean(b["goles"]) + mean(a["contra"])) / 2
        c1, c2 = st.columns(2)
        c1.metric(home, f"{h_proj:.2f} goles")
        c2.metric(away, f"{v_proj:.2f} goles")
        st.caption("Modelo base: promedio de goles anotados y recibidos. No indica probabilidad de victoria.")
        for team in [home, away]:
            with st.expander("📊 " + team):
                d = DATA[team]
                st.dataframe([
                    {"Métrica": "Goles / partido", "Promedio": round(mean(d["goles"]), 2)},
                    {"Métrica": "Goles 1.ª mitad", "Promedio": round(mean(d["goles_1t"]), 2)},
                    {"Métrica": "Goles 2.ª mitad", "Promedio": round(mean(d["goles"]) - mean(d["goles_1t"]), 2)},
                    {"Métrica": "Córners 1.ª mitad", "Promedio": round(mean(d["corners_1t"]), 2)},
                    {"Métrica": "Córners 2.ª mitad", "Promedio": round(mean(d["corners"]) - mean(d["corners_1t"]), 2)},
                ], hide_index=True, use_container_width=True)
                st.write("Validación cronológica de goles:", validation(d["goles"]))
        st.subheader("👥 Comparador de jugadores")
        choices = {f"{team} · {name}": (team, name, stats) for team in [home, away] for name, stats in PLAYERS[team].items()}
        selected = st.multiselect("Hasta dos jugadores", list(choices), max_selections=2)
        if selected:
            st.dataframe([{"Jugador": choices[s][1], "Minutos promedio": round(mean(choices[s][2]["min"]), 1),
                           "Goles promedio": round(mean(choices[s][2]["goles"]), 2)} for s in selected],
                         hide_index=True, use_container_width=True)
    else:
        key, diagnostico = secret_key()
        if not key:
            st.warning(diagnostico)
            st.caption("Comprueba que editaste los Secrets de ESTA aplicación y reiníciala. Nunca compartas la clave.")
        else:
            st.success("Configuración detectada. " + diagnostico)
            st.warning("Los datos disponibles dependen del plan. Consultas manuales y caché de 1 hora.")
            if st.button("Consultar ligas disponibles"):
                try:
                    response = fetch("leagues", {}, key).get("response", [])
                    st.success(f"Ligas recibidas: {len(response)}")
                    st.dataframe([{"Liga": x.get("league", {}).get("name"),
                                   "País": x.get("country", {}).get("name")} for x in response[:30]],
                                 hide_index=True, use_container_width=True)
                except Exception as error:
                    st.error(f"Error de consulta: {error}")
    st.divider()
    st.caption("Versión inicial: sin tarjetas. Las proyecciones y la validación de demostración NO son resultados reales.")

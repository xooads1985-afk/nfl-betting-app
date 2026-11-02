"""Resumen Inteligente Soccer - prototipo independiente.
Ejecutar: streamlit run resumen_inteligente_soccer.py
Clave opcional en Streamlit Secrets: API_FOOTBALL_KEY
"""
import os
from datetime import datetime, timezone, timedelta
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


class SoccerAPIError(Exception):
    """Error seguro de mostrar en pantalla; nunca incluye credenciales."""


def mensaje_api(exc):
    """Diagnóstico sin exponer tokens ni cuerpos de respuesta."""
    if isinstance(exc, SoccerAPIError):
        return str(exc)
    if isinstance(exc, requests.exceptions.Timeout):
        return "La API tardó demasiado en responder. Intenta más tarde."
    if isinstance(exc, requests.exceptions.ConnectionError):
        return "No fue posible conectar con API-Football. Comprueba la conexión e intenta más tarde."
    return f"Error inesperado ({type(exc).__name__}). Revisa los logs privados de Streamlit."


@st.cache_data(ttl=3600, show_spinner=False)
def fetch(endpoint, params, key):
    try:
        response = requests.get(
            "https://v3.football.api-sports.io/" + endpoint,
            headers={"x-apisports-key": key}, params=params, timeout=20,
        )
    except requests.exceptions.RequestException as exc:
        raise SoccerAPIError(mensaje_api(exc)) from None

    if response.status_code == 429:
        raise SoccerAPIError("Demasiadas solicitudes (HTTP 429). Espera antes de volver a consultar.")
    if response.status_code in (401, 403):
        raise SoccerAPIError(f"Acceso no autorizado (HTTP {response.status_code}). Revisa la clave y el plan de API-Football.")
    if response.status_code >= 400:
        raise SoccerAPIError(f"La API respondió con HTTP {response.status_code}. Revisa el estado del servicio.")

    try:
        result = response.json()
    except ValueError:
        raise SoccerAPIError("La API devolvió una respuesta que no es JSON válido.") from None

    errors = result.get("errors")
    if errors:
        # Solo mostramos categorías conocidas. Nunca el texto crudo, que podría contener secretos.
        detail = str(errors).lower()
        if any(word in detail for word in ("limit", "quota", "requests", "rate")):
            msg = "API-Football informa de un límite de solicitudes o cuota. Revisa tu panel de consumo."
        elif any(word in detail for word in ("plan", "subscription", "access", "free")):
            msg = "La consulta no está disponible con el plan actual de API-Football."
        elif any(word in detail for word in ("key", "token", "auth")):
            msg = "API-Football rechazó la autenticación. Verifica la clave configurada en Streamlit."
        else:
            msg = "API-Football devolvió un error de aplicación. Revisa tu panel de API-Football."
        raise SoccerAPIError(msg)
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
            st.caption("Revisa Settings → Secrets de esta aplicación. Nunca compartas tu clave.")
        else:
            st.success("Conexión configurada. " + diagnostico)
            st.caption("Consultas solo al pulsar botones · caché de 1 hora. Los datos dependen de tu plan.")
            st.info("Etapa 2: explorar ligas, equipos y partidos reales. No se generan proyecciones todavía.")

            if st.button("1 · Cargar ligas", key="soc_ligas"):
                try:
                    leagues = fetch("leagues", {}, key).get("response", [])
                    st.session_state["soc_leagues"] = leagues
                    st.success(f"Ligas recibidas: {len(leagues)}")
                except Exception as exc:
                    st.error("No se pudieron consultar las ligas: " + mensaje_api(exc))

            leagues = st.session_state.get("soc_leagues", [])
            if leagues:
                # Filtrar para facilitar la selección en pantallas pequeñas.
                countries = sorted({(x.get("country") or {}).get("name") or "Sin país" for x in leagues})
                country = st.selectbox("País o región", countries, key="soc_country")
                choices = [x for x in leagues if ((x.get("country") or {}).get("name") or "Sin país") == country]
                # Se conserva el ID: puede haber ligas con nombres iguales.
                options = {f"{(x.get('league') or {}).get('name', 'Liga')} · ID {(x.get('league') or {}).get('id')}": x for x in choices}
                label = st.selectbox("Competición", list(options), key="soc_league")
                chosen = options[label]
                league_id = (chosen.get("league") or {}).get("id")
                seasons = [x.get("year") for x in chosen.get("seasons", []) if x.get("year") is not None]
                if seasons:
                    season = st.selectbox("Temporada", sorted(set(seasons), reverse=True), key="soc_season")
                    st.caption("Elige la temporada correspondiente al calendario de la competición.")
                    if st.button("2 · Consultar equipos", key="soc_teams_button"):
                        try:
                            data = fetch("teams", {"league": league_id, "season": season}, key)
                            teams = data.get("response", [])
                            st.session_state["soc_teams_data"] = (league_id, season, teams)
                            st.success(f"Equipos recibidos: {len(teams)}")
                        except Exception as exc:
                            st.error("No se pudieron consultar equipos: " + mensaje_api(exc))
                    team_data = st.session_state.get("soc_teams_data")
                    if team_data and team_data[:2] == (league_id, season):
                        teams = team_data[2]
                        if teams:
                            st.dataframe([{"Equipo": (x.get("team") or {}).get("name"),
                                           "Ciudad": (x.get("venue") or {}).get("city") or "N/D"}
                                          for x in teams], hide_index=True)
                            st.caption("La lista de equipos procede de la API; aún no se calculan estadísticas.")
                        else:
                            st.info("No hay equipos disponibles para esta liga y temporada en tu plan.")

                    if st.button("3 · Consultar partidos de la temporada", key="soc_fixtures_button"):
                        try:
                            data = fetch("fixtures", {"league": league_id, "season": season}, key)
                            fixtures = data.get("response", [])
                            st.session_state["soc_fixtures_data"] = (league_id, season, fixtures)
                            st.success(f"Partidos recibidos: {len(fixtures)}")
                        except Exception as exc:
                            st.error("No se pudieron consultar partidos: " + mensaje_api(exc))
                    fixture_data = st.session_state.get("soc_fixtures_data")
                    if fixture_data and fixture_data[:2] == (league_id, season):
                        fixtures = fixture_data[2]
                        if fixtures:
                            now = datetime.now(timezone.utc)
                            future = [x for x in fixtures if (x.get("fixture") or {}).get("date", "")[:10] >= now.date().isoformat()
                                      and (x.get("fixture") or {}).get("status", {}).get("short") in ("NS", "TBD")]
                            completed = [x for x in fixtures if (x.get("fixture") or {}).get("status", {}).get("short") in ("FT", "AET", "PEN")]
                            view = st.radio("Mostrar", ["Próximos", "Finalizados"], horizontal=True, key="soc_fixture_view")
                            selected = sorted(future if view == "Próximos" else completed,
                                              key=lambda x: (x.get("fixture") or {}).get("date", ""),
                                              reverse=view == "Finalizados")[:25]
                            if selected:
                                st.dataframe([{"Fecha (UTC)": (x.get("fixture") or {}).get("date", "")[:16].replace("T", " "),
                                               "Local": (x.get("teams") or {}).get("home", {}).get("name"),
                                               "Visitante": (x.get("teams") or {}).get("away", {}).get("name"),
                                               "Marcador": (f"{(x.get('goals') or {}).get('home')} - {(x.get('goals') or {}).get('away')}"
                                                            if view == "Finalizados" else "Pendiente")}
                                              for x in selected], hide_index=True)
                            else:
                                st.info("No hay partidos en esta categoría para la temporada seleccionada.")
                            st.caption("Se muestran hasta 25 partidos. Las fechas están en UTC.")
                        else:
                            st.info("No se encontraron partidos para esta competición y temporada.")
                else:
                    st.info("Esta liga no ofrece temporadas en la respuesta recibida.")
            else:
                st.caption("Pulsa «Cargar ligas» para empezar. Cada endpoint nuevo puede consumir una solicitud.")
    st.divider()
    st.caption("Versión inicial: sin tarjetas. Las proyecciones y la validación de demostración NO son resultados reales.")

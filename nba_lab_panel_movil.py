"""Laboratorio NBA 3.12.19: panel móvil de solo lectura dentro de la misma app."""
from pathlib import Path
import re
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
AUD = ROOT / "nba_lab_auditoria_resultados"
DATA = ROOT / "nba_lab_resultados"

st.markdown("""<style>
.block-container {padding-top:2.6rem;padding-left:.65rem;padding-right:.65rem;max-width:850px}
h1 {font-size:1.65rem!important;line-height:1.2!important}
h2 {font-size:1.2rem!important}
[data-testid="stMetricValue"] {font-size:1.45rem}
[data-testid="stMetricLabel"] {font-size:.78rem}
div[data-testid="stTabs"] button {font-size:.84rem;padding-left:.45rem;padding-right:.45rem}
</style>""", unsafe_allow_html=True)

st.title("🏀 Laboratorio NBA")
st.caption("Panel experimental 3.12.19 · Solo lectura · Historial")

@st.cache_data(ttl=180, show_spinner=False)
def leer_csv(path):
    """Lectura defensiva: nunca cargar CSV ilimitados por accidente."""
    if not path.is_file():
        return pd.DataFrame(), f"No existe: {path.name}"
    if path.stat().st_size > 25 * 1024 * 1024:
        return pd.DataFrame(), f"{path.name} supera 25 MB; se omite para proteger la aplicación"
    try:
        return pd.read_csv(path, low_memory=False), None
    except Exception as exc:
        return pd.DataFrame(), f"{path.name}: {type(exc).__name__}: {exc}"

def comprobar(df, columnas, nombre):
    if df.empty:
        st.warning(f"No hay datos de {nombre}.")
        return False
    faltan = set(columnas) - set(df.columns)
    if faltan:
        st.warning(f"{nombre}: faltan columnas {', '.join(sorted(faltan))}.")
        return False
    return True

def ordenar(df):
    d = df.copy()
    for c in ("MAE", "RMSE", "sesgo", "muestra"):
        if c in d:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    return d.dropna(subset=["MAE"]).sort_values("MAE")

def detalle(df, key):
    if df.empty:
        return
    cols = [c for c in ("modelo", "muestra", "MAE", "RMSE", "sesgo") if c in df]
    view = df[cols].copy()
    for c in ("MAE", "RMSE", "sesgo"):
        if c in view:
            view[c] = view[c].round(3)
    with st.expander("Ver tabla completa y descargar CSV", expanded=False):
        st.dataframe(view, hide_index=True, use_container_width=True)
        st.download_button("Descargar comparación", view.to_csv(index=False).encode("utf-8"),
                           file_name=f"nba_lab_{key}.csv", mime="text/csv", key=f"dl_{key}")

def ganador(df, etiqueta):
    d = ordenar(df)
    if d.empty:
        st.info(f"Sin resultados de {etiqueta}.")
        return
    b = d.iloc[0]
    st.markdown(f"**{etiqueta}: {b['modelo']}**")
    c1, c2 = st.columns(2)
    c1.metric("MAE", f"{b['MAE']:.3f} pts")
    c2.metric("Muestra", f"{int(b['muestra']):,}" if pd.notna(b["muestra"]) else "N/D")
    st.caption(f"RMSE {b['RMSE']:.3f} · Sesgo {b['sesgo']:+.3f} pts")
    if abs(b["sesgo"]) >= 1:
        sentido = "sobreestima" if b["sesgo"] > 0 else "subestima"
        st.caption(f"En esta muestra, {sentido} en promedio {abs(b['sesgo']):.2f} puntos.")
    else:
        st.caption("El sesgo promedio está cerca de cero; esto no elimina errores grandes en partidos individuales.")

# Integración experimental aislada: no altera el laboratorio histórico.
with st.expander("🧪 Tarjeta automática NBA — prueba", expanded=False):
    st.caption("Consulta el calendario solo al pulsar el botón. Guardado desactivado.")
    if st.button("📅 Consultar próximos partidos NBA", key="nba_lab_consultar_calendario"):
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        from modulo_nba import cargar_partidos
        hoy = datetime.now(ZoneInfo("America/Mazatlan")).date()
        try:
            with st.spinner("Consultando calendario ESPN..."):
                agenda, avisos = cargar_partidos(hoy.isoformat(), (hoy + timedelta(days=3)).isoformat())
            if avisos:
                st.warning("Calendario: " + " | ".join(str(a) for a in avisos[:2]))
            if agenda is not None and not agenda.empty:
                futuros = agenda.loc[~agenda["finalizado"].fillna(False)].copy()
                futuros["fecha_utc_dt"] = pd.to_datetime(futuros["fecha_utc"], utc=True, errors="coerce")
                futuros = futuros.loc[futuros["fecha_utc_dt"].notna() &
                                      (futuros["fecha_utc_dt"] > pd.Timestamp.now(tz="UTC"))]
                st.session_state["nba_lab_agenda_prueba"] = futuros.drop(columns=["fecha_utc_dt"]).to_dict("records")
            else:
                st.session_state["nba_lab_agenda_prueba"] = []
        except (ImportError, ValueError, KeyError, OSError, RuntimeError) as exc:
            st.error(f"No se pudo consultar el calendario: {type(exc).__name__}: {exc}")
    agenda_prueba = st.session_state.get("nba_lab_agenda_prueba", [])
    if agenda_prueba:
        opciones = {str(p["id"]): p for p in agenda_prueba if p.get("id")}
        elegido = st.selectbox(
            "Partido futuro",
            list(opciones),
            format_func=lambda pid: (
                f'{opciones[pid].get("visitante", "?")} vs '
                f'{opciones[pid].get("local", "?")} · '
                f'{opciones[pid].get("fecha_utc", "")}'
            ),
            key="nba_lab_partido_automatico",
        )
        if st.button("🔬 Generar tarjeta con cuatro motores", key="nba_lab_generar_tarjeta"):
            from nba_conexion_tarjeta import mostrar_tarjeta_conectada
            mostrar_tarjeta_conectada(
                opciones[elegido], partidos=pd.DataFrame(agenda_prueba),
                escritura_habilitada=False, historial_remoto_habilitado=False,
            )
    else:
        st.caption("Consulta el calendario para seleccionar un encuentro futuro.")

st.caption("Esta pantalla solo consulta resultados CSV existentes; no descarga temporadas ni ejecuta entrenamiento.")
st.info("Temporada prioritaria: 2026-2027. La temporada anterior no se carga automáticamente.")
if not st.button("📂 Abrir resultados del laboratorio", type="primary", use_container_width=True):
    st.caption("Presiona el botón para leer los resultados guardados. El laboratorio ya está abierto y no está ejecutando cálculos.")
    st.stop()

with st.spinner("Leyendo archivos de resultados guardados..."):
    archivos = {
        "pred": DATA / "algoritmos_predicciones.csv",
        "tot": AUD / "metricas_totales.csv",
        "team": AUD / "metricas_por_equipo.csv",
        "localia": AUD / "metricas_localia.csv",
        "integridad": AUD / "control_integridad.csv",
        "incidencias": AUD / "incidencias.csv",
    }
    lecturas = {nombre: leer_csv(ruta) for nombre, ruta in archivos.items()}
    pred, tot, team, localia, integridad, incidencias = (lecturas[k][0] for k in archivos)
    problemas = [e for _, e in lecturas.values() if e]
if problemas:
    with st.expander(f"Diagnóstico de archivos ({len(problemas)})", expanded=True):
        for problema in problemas:
            st.warning(problema)

if not comprobar(pred, ["partido", "equipo", "real", "fecha"], "predicciones"):
    st.info("El panel está operativo, pero faltan resultados válidos. Ejecutar el motor offline es una tarea independiente; no se ejecuta aquí.")
    st.stop()

a, b = st.columns(2)
a.metric("Partidos", f"{pred['partido'].nunique():,}")
b.metric("Predicciones", f"{len(pred):,}")
st.caption("Resultados de CSV del repositorio, no datos en vivo.")

temporadas = sorted(set(str(v) for d in (tot, team, localia)
                       if "temporada" in d.columns
                       for v in d["temporada"].dropna().unique() if str(v) != "Todas"))
opciones = (["2026-2027"] if "2026-2027" not in temporadas else []) + temporadas
temporada = st.selectbox("Temporada", opciones if opciones else ["Todas"], index=0)
tabs = st.tabs(["📊 Modelos", "🏠 Localía", "🛡️ Controles"])

with tabs[0]:
    modo = st.radio("Evaluación", ["Por equipo", "Puntos totales"], horizontal=True)
    origen = team if modo == "Por equipo" else tot
    if comprobar(origen, ["temporada", "modelo", "MAE", "RMSE", "sesgo", "muestra"], modo):
        datos = ordenar(origen if temporada == "Todas" else origen[origen["temporada"].astype(str).eq(temporada)])
        if datos.empty:
            st.info("Sin datos para la temporada seleccionada.")
        else:
            ganador(datos, "Menor error de la muestra")
            detalle(datos, "modelos_" + ("equipo" if modo == "Por equipo" else "totales"))
            st.info("MAE mide el error absoluto medio. RMSE penaliza más los errores grandes. "
                    "Sesgo positivo significa sobreestimación; negativo, subestimación.")
            st.caption("El modelo líder de esta muestra no necesariamente será el mejor en partidos futuros.")

with tabs[1]:
    if comprobar(localia, ["temporada", "grupo", "modelo", "muestra", "MAE", "RMSE", "sesgo"], "localía"):
        datos = localia if temporada == "Todas" else localia[localia["temporada"].astype(str).eq(temporada)]
        for sede in ("Local", "Visitante"):
            grupo = ordenar(datos[datos["grupo"].eq(sede)])
            ganador(grupo, sede)
            detalle(grupo, "localia_" + sede.lower())
            if sede == "Local":
                st.divider()
        st.caption("Comparación descriptiva. No activa automáticamente un modelo distinto por sede.")

with tabs[2]:
    if comprobar(integridad, ["control", "incidencias"], "integridad"):
        numeros = pd.to_numeric(integridad["incidencias"], errors="coerce")
        if numeros.isna().any():
            st.warning("Hay valores no numéricos en el control de integridad.")
        elif (numeros == 0).all():
            st.success("0 incidencias en los controles ejecutados.")
        else:
            st.error(f"{int(numeros.sum())} incidencias registradas.")
        with st.expander("Ver los controles de integridad"):
            st.dataframe(integridad, use_container_width=True, hide_index=True)
    if not incidencias.empty:
        with st.expander("Ver otras incidencias"):
            st.dataframe(incidencias, use_container_width=True, hide_index=True)
    st.subheader("Prueba temporal")
    prueba = AUD / "prueba_temporal.txt"
    if prueba.exists():
        contenido = prueba.read_text(encoding="utf-8")
        cantidad = re.search(r"OK:\s*(\d+)\s*partidos", contenido)
        if cantidad:
            st.metric("Partidos comprobados", cantidad.group(1))
            st.success("La prueba de invariancia temporal registrada pasó.")
        else:
            st.warning("Revisa el resultado de la prueba temporal.")
        with st.expander("Leer resultado completo"):
            st.text(contenido)
    else:
        st.warning("Todavía no está disponible la prueba temporal.")
    st.caption("Prueba parcial: no certifica ausencia de filtraciones en todos los modelos ni fechas.")

st.divider()
st.caption("Solo lectura · No modifica NBA estable, NFL, Soccer ni main.py.")

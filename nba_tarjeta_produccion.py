
"""Tarjeta Inteligente NBA: cuatro motores y diagnóstico de referencias."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

TZ = ZoneInfo("America/Mazatlan")


def _agenda(dia):
    url = (
        "https://site.api.espn.com/apis/site/v2/"
        "sports/basketball/nba/scoreboard"
    )

    respuesta = requests.get(
        url,
        params={
            "dates": dia.strftime("%Y%m%d"),
            "limit": 100,
        },
        timeout=(3, 10),
    )
    respuesta.raise_for_status()

    salida = []

    for evento in respuesta.json().get("events", []):
        competencias = evento.get("competitions") or []
        if not competencias:
            continue

        equipos = competencias[0].get("competitors") or []

        local = next(
            (e for e in equipos if e.get("homeAway") == "home"),
            None,
        )
        visitante = next(
            (e for e in equipos if e.get("homeAway") == "away"),
            None,
        )

        if not local or not visitante:
            continue

        fecha = evento.get("date")

        try:
            inicio = datetime.fromisoformat(
                fecha.replace("Z", "+00:00")
            )
        except (ValueError, AttributeError):
            continue

        if inicio <= datetime.now(timezone.utc):
            continue

        if evento.get("status", {}).get(
            "type", {}
        ).get("completed"):
            continue

        salida.append({
            "id": str(evento["id"]),
            "fecha_utc": fecha,
            "local": local["team"]["displayName"],
            "visitante": visitante["team"]["displayName"],
            "finalizado": False,
        })

    return salida


def mostrar_tarjeta_nba_produccion():

    st.subheader(
        "🏀 Tarjeta Inteligente NBA · cuatro motores"
    )

    st.caption(
        "Partidos futuros · análisis estadístico · "
        "proyecciones originales protegidas"
    )

    hoy = datetime.now(TZ).date()

    dia = st.date_input(
        "Fecha de los encuentros",
        value=hoy,
        min_value=hoy,
        max_value=hoy + timedelta(days=14),
        key="nba_prod_fecha",
    )

    if st.button(
        "📅 Consultar partidos",
        key="nba_prod_agenda",
    ):
        try:
            st.session_state["nba_prod_partidos"] = (
                _agenda(dia)
            )
            st.session_state["nba_prod_dia"] = (
                dia.isoformat()
            )

        except (
            requests.RequestException,
            ValueError,
            KeyError,
            TypeError,
        ) as exc:

            st.session_state["nba_prod_partidos"] = []
            st.error(
                "No se pudo consultar el calendario: "
                + str(exc)
            )

    partidos = (
        st.session_state.get("nba_prod_partidos", [])
        if st.session_state.get("nba_prod_dia")
        == dia.isoformat()
        else []
    )

    if not partidos:
        st.info(
            "Consulta el calendario. "
            "Si no aparecen partidos, elige otro día."
        )
        return

    opciones = {
        p["id"]: p
        for p in partidos
    }

    pid = st.selectbox(
        "Selecciona un partido",
        list(opciones),
        format_func=lambda k: (
            f"{opciones[k]['visitante']} @ "
            f"{opciones[k]['local']}"
        ),
        key="nba_prod_partido",
    )

    partido = opciones[pid]

    # Fecha y hora oficial del encuentro

    inicio_utc = datetime.fromisoformat(
        partido["fecha_utc"].replace(
            "Z", "+00:00"
        )
    )

    inicio_local = inicio_utc.astimezone(TZ)

    st.info(
        "📅 **Fecha:** "
        + inicio_local.strftime("%d/%m/%Y")
        + "  |  🕒 **Hora:** "
        + inicio_local.strftime("%I:%M %p")
        + " (Mazatlán)"
    )

    if datetime.now(timezone.utc) >= inicio_utc:
        st.warning(
            "El partido ya comenzó. "
            "No se permiten nuevas proyecciones."
        )
        return

    from nba_conexion_tarjeta import (
        mostrar_tarjeta_conectada,
    )

    if st.button(
        "🏀 Analizar partido",
        key="nba_prod_analizar",
    ):
        st.session_state["nba_prod_analizado"] = pid

    if (
        st.session_state.get("nba_prod_analizado")
        != pid
    ):
        return

    # Referencias históricas verificadas

    from nba_referencias_tarjeta import (
        referencias_para_partido,
    )

    try:
        periodos_resumen, nota_referencias = (
            referencias_para_partido(partido)
        )

        st.caption(nota_referencias)

    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
    ) as exc:

        periodos_resumen = None

        st.warning(
            "No se pudieron calcular las "
            "referencias históricas: "
            + str(exc)
        )

    # DIAGNÓSTICO 1: datos históricos de entrada

    with st.expander(
        "🔬 Diagnóstico 1 · referencias de entrada"
    ):
        if periodos_resumen is None:
            st.error(
                "No se recibió tabla histórica."
            )
        else:
            st.write(
                "Columnas recibidas:",
                list(periodos_resumen.columns),
            )

            st.dataframe(
                periodos_resumen,
                hide_index=True,
                use_container_width=True,
            )

    # Vista previa: nunca escribe en Supabase

    mostrar_tarjeta_conectada(
        partido,
        partidos=pd.DataFrame(partidos),
        escritura_habilitada=False,
        historial_remoto_habilitado=False,
        periodos_resumen=periodos_resumen,
    )

    # DIAGNÓSTICO 2: datos publicados por la tarjeta

    with st.expander(
        "🔬 Diagnóstico 2 · referencias publicadas"
    ):
        compartido = st.session_state.get(
            "nba_proyeccion_consolidada_v1"
        )

        if not isinstance(compartido, dict):
            st.error(
                "No se publicó el resultado compartido."
            )
        else:
            if (
                str(compartido.get("partido_id"))
                != str(partido["id"])
            ):
                st.error(
                    "El resultado pertenece a otro partido."
                )
            elif (
                str(compartido.get("fecha_utc"))
                != str(partido["fecha_utc"])
            ):
                st.error(
                    "La fecha del resultado no coincide."
                )
            else:
                claves = [
                    "partido_id",
                    "referencia_local",
                    "referencia_visitante",
                    "referencia_total",
                    "edge_local",
                    "edge_visitante",
                    "edge_total",
                ]

                st.json({
                    clave: compartido.get(clave)
                    for clave in claves
                })

    st.caption(
        "El guardado de los motores es una "
        "acción independiente y explícita."
    )

    confirmar = st.checkbox(
        "Confirmo que deseo guardar las "
        "proyecciones de este partido "
        "antes de su inicio",
        key="nba_prod_confirmar_" + pid,
    )

    if st.button(
        "💾 Guardar motores faltantes",
        disabled=not confirmar,
        key="nba_prod_guardar_" + pid,
    ):

        # Comprobar nuevamente la hora

        if datetime.now(timezone.utc) >= inicio_utc:
            st.error(
                "Partido iniciado: no se permite "
                "guardar proyecciones."
            )
            return

        resultado = mostrar_tarjeta_conectada(
            partido,
            partidos=pd.DataFrame(partidos),
            escritura_habilitada=True,
            historial_remoto_habilitado=False,
            periodos_resumen=periodos_resumen,
        )

        estado = (
            resultado.get("estado")
            if isinstance(resultado, dict)
            else None
        )

        if estado == "completo":
            st.success(
                "Cuatro motores completos y "
                "verificados mediante consulta."
            )
        else:
            st.warning(
                "Guardado no confirmado como "
                "completo. Estado: "
                + str(estado)
            )

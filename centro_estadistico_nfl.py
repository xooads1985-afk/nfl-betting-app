"""Interfaz única de estadísticas NFL para importar desde main.py."""

import streamlit as st

from modulo_nfl import mostrar_modulo_nfl
from comparador_jugadores_nfl import mostrar_comparador
from promedios_diferencias_nfl import mostrar_promedios_diferencias


def mostrar_centro_estadistico_nfl():
    vista = st.radio(
        "Centro NFL",
        [
            "Estadísticas NFL",
            "Comparador de jugadores",
            "Promedios y diferencias",
            "🏠 Resumen Inteligente NFL",
        ],
        horizontal=False,
        key="centro_nfl_vista",
    )

    if vista == "Estadísticas NFL":
        mostrar_modulo_nfl()

    elif vista == "Comparador de jugadores":
        mostrar_comparador()

    elif vista == "Promedios y diferencias":
        mostrar_promedios_diferencias()

    elif vista == "🏠 Resumen Inteligente NFL":
        from resumen_inteligente_nfl import mostrar_resumen_inteligente_nfl
        mostrar_resumen_inteligente_nfl()

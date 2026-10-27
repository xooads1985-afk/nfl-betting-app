"""Interfaz única de estadísticas NFL para importar desde main.py."""
import streamlit as st
from modulo_nfl import mostrar_modulo_nfl
from comparador_jugadores_nfl import mostrar_comparador

def mostrar_centro_estadistico_nfl():
    vista = st.radio("Centro NFL", ["Estadísticas NFL", "Comparador de jugadores"], horizontal=True, key="centro_nfl_vista")
    if vista == "Estadísticas NFL":
        mostrar_modulo_nfl()
    else:
        mostrar_comparador()

"""Centro Estadístico NBA.

Enrutador independiente para los cuatro módulos NBA.
No importa ni modifica archivos NFL y no altera main.py.
"""

import importlib
import streamlit as st


VISTAS_NBA = {
    "📊 Estadísticas NBA": ("modulo_nba", "mostrar_modulo_nba"),
    "👥 Comparador de jugadores": ("comparador_jugadores_nba", "mostrar_comparador"),
    "📈 Promedios y diferencias": ("promedios_diferencias_nba", "mostrar_promedios_diferencias"),
    "🏠 Resumen Inteligente NBA": (
        "resumen_inteligente_nba", "mostrar_resumen_inteligente_nba"
    ),
}


def mostrar_centro_estadistico_nba():
    """Presenta el menú NBA y ejecuta únicamente la vista seleccionada."""
    st.subheader("🏀 Centro Estadístico NBA")
    vista = st.radio(
        "Centro NBA",
        options=list(VISTAS_NBA),
        horizontal=False,
        key="centro_nba_vista",
    )
    modulo, funcion = VISTAS_NBA[vista]
    try:
        componente = importlib.import_module(modulo)
        vista_funcion = getattr(componente, funcion)
    except (ImportError, AttributeError) as exc:
        st.error(f"No se pudo cargar la sección «{vista}».")
        st.caption(
            f"Comprueba que «{modulo}.py» esté en la misma carpeta que "
            "«main.py» y que contenga la función requerida."
        )
        with st.expander("Detalles técnicos"):
            st.code(f"{type(exc).__name__}: {exc}")
        return
    vista_funcion()


if __name__ == "__main__":
    st.set_page_config(page_title="Centro Estadístico NBA", page_icon="🏀")
    mostrar_centro_estadistico_nba()

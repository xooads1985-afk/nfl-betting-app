"""Punto de conexión aislado entre el calendario existente y la tarjeta automática.

No modifica el Resumen Inteligente ni activa escrituras por defecto.
"""
from datetime import date
from nba_cargador_historial import cargar_historial_bloques

# NBA_CACHE_HISTORIAL_COMPARTIDO_V1
# Reutilizar historial verificado por una hora sin alterar la selección de motores.
import streamlit as st

@st.cache_data(ttl=3600, max_entries=24, show_spinner=False)
def _historial_verificado(desde_iso, hasta_iso):
    tabla, incidencias = cargar_historial_bloques(
        date.fromisoformat(desde_iso), date.fromisoformat(hasta_iso))
    if incidencias:
        raise ValueError('Cobertura histórica incompleta: ' + '; '.join(map(str, incidencias)))
    return tabla

def _historial(desde_iso, hasta_iso):
    try:
        return _historial_verificado(desde_iso, hasta_iso), ()
    except ValueError as exc:
        # No se almacena en cache un historial incompleto o fallido.
        return __import__('pandas').DataFrame(), (str(exc),)

def cargador_historial(desde, hasta):
    tabla, incidencias = _historial(str(desde), str(hasta))
    return tabla.copy(), list(incidencias)

def mostrar_tarjeta_conectada(partido, *, partidos=None, escritura_habilitada=False,
                              historial_remoto_habilitado=False, periodos_resumen=None):
    """Entrada para la tarjeta seleccionada. Escritura requiere habilitación explícita."""
    from nba_tarjeta_auto import mostrar_tarjeta_auto
    return mostrar_tarjeta_auto(partido, partidos=partidos,
                               cargador_historial=cargador_historial,
                               escritura_habilitada=escritura_habilitada,
                               historial_remoto_habilitado=historial_remoto_habilitado,
                               periodos_resumen=periodos_resumen)

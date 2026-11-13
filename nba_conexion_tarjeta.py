"""Punto de conexión aislado entre el calendario existente y la tarjeta automática.

No modifica el Resumen Inteligente ni activa escrituras por defecto.
"""
from datetime import date
from nba_cargador_historial import cargar_historial_bloques

def _historial(desde_iso, hasta_iso):
    tabla, incidencias = cargar_historial_bloques(date.fromisoformat(desde_iso), date.fromisoformat(hasta_iso))
    return tabla, tuple(incidencias)

def cargador_historial(desde, hasta):
    tabla, incidencias = _historial(str(desde), str(hasta))
    return tabla.copy(), list(incidencias)

def mostrar_tarjeta_conectada(partido, *, partidos=None, escritura_habilitada=False,
                              historial_remoto_habilitado=False):
    """Entrada para la tarjeta seleccionada. Escritura requiere habilitación explícita."""
    from nba_tarjeta_auto import mostrar_tarjeta_auto
    return mostrar_tarjeta_auto(partido, partidos=partidos,
                               cargador_historial=cargador_historial,
                               escritura_habilitada=escritura_habilitada,
                               historial_remoto_habilitado=historial_remoto_habilitado)

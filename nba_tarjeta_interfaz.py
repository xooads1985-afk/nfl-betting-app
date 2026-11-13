"""Adaptador UI: no cambia los módulos estables y no escribe por defecto."""
from datetime import datetime, timezone
from pathlib import Path

from nba_tarjeta_puente import preparar_y_ejecutar


def obtener_tarjeta(partido, *, consultar, cargador_historial, calcular_tres,
                    guardar_tres, calcular_pace, guardar_pace, ruta_pace,
                    escritura_habilitada=False, reloj=None, solicitar_remoto=None, cargar_detalle=None):
    """Devuelve estado diagnosticable sin interrumpir el resumen estable."""
    try:
        resultado = preparar_y_ejecutar(
            partido, consultar=consultar, cargador_historial=cargador_historial,
            calcular_tres=calcular_tres, guardar_tres=guardar_tres,
            calcular_pace=calcular_pace, guardar_pace=guardar_pace,
            ruta_pace=Path(ruta_pace), modo_prueba=not escritura_habilitada,
            reloj=reloj, solicitar_remoto=solicitar_remoto, cargar_detalle=cargar_detalle)
        return {'ok': True, **resultado}
    except (ValueError, KeyError, TypeError, RuntimeError, OSError) as exc:
        return {'ok': False, 'estado': 'error', 'mensaje': f'{type(exc).__name__}: {exc}',
                'registros': [], 'faltantes': (), 'nuevos': 0}


def adaptadores_reales(cargador_historial=None):
    """Importación diferida: sólo al activar la integración en Streamlit."""
    if cargador_historial is None:
        raise ValueError("Se requiere el cargador de historial del Resumen NBA; no se reimporta Streamlit.")
    from modulo_nba import cargar_detalle
    from nba_prediccion_tarjeta import consultar
    from nba_laboratorio_prospectivo import calcular, guardar
    from nba_pace_prospectivo import preparar_prediccion, guardar_pace
    return dict(consultar=consultar,
                cargador_historial=cargador_historial,
                calcular_tres=calcular, guardar_tres=guardar,
                calcular_pace=preparar_prediccion, guardar_pace=guardar_pace,
                ruta_pace=localizar_csv_pace(), cargar_detalle=cargar_detalle)


def localizar_csv_pace():
    """Encuentra el CSV en la raíz del proyecto o junto al adaptador."""
    base = Path(__file__).resolve().parent
    candidatos = (base / 'nba_historial_pace.csv', base.parent / 'nba_historial_pace.csv')
    for ruta in candidatos:
        if ruta.is_file():
            return ruta
    # La fuente remota puede funcionar sin CSV local. Devolver una ruta
    # convencional y dejar que cargar_pace valide ambas fuentes.
    return candidatos[0]

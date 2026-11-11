"""Adaptador de presentación NBA experimental. No modifica módulos estables.
Usar renderizar_tarjeta_nba(directorio, partido_id) desde una integración autorizada.
"""
from __future__ import annotations
from pathlib import Path
from nba_lab_lector_tarjetas import leer_tarjeta


def obtener_vista(directorio: str | Path, partido_id: str, ahora_utc=None) -> dict:
    """Contrato listo para UI; no entrena ni consulta redes."""
    d = leer_tarjeta(directorio, partido_id, ahora_utc=ahora_utc)
    return {
        'partido_id': d['partido_id'], 'fecha_utc': d['fecha_utc'],
        'local': d['local'], 'visitante': d['visitante'],
        'puntos_local': d['proyeccion_local'],
        'puntos_visitante': d['proyeccion_visitante'],
        'total_ensemble': d['total_ensemble'],
        'total_modelo_c': d['total_modelo_c'],
        'referencia_total': d['referencia_total'],
        'edge_ensemble': d['edge_ensemble'],
        'edge_modelo_c': d['edge_modelo_c'],
        'pace': d['pace_prepartido'],
        'generado_utc': d['generado_utc'],
        'estado': d['estado'],
    }


def renderizar_tarjeta_nba(directorio: str | Path, partido_id: str, ahora_utc=None):
    """Renderiza una tarjeta móvil si existe una proyección válida.

    Retorna False cuando no hay tarjeta utilizable, sin mostrar proyecciones antiguas.
    Importa Streamlit solo al invocarse, para permitir pruebas sin Streamlit.
    """
    import streamlit as st
    try:
        d = obtener_vista(directorio, partido_id, ahora_utc=ahora_utc)
    except (FileNotFoundError, ValueError, OSError, KeyError, TypeError) as exc:
        st.info(f'Proyección experimental no disponible para este encuentro: {exc}')
        return False
    with st.container(border=True):
        st.markdown('#### 🏀 Proyección estadística experimental')
        st.caption(f"{d['local']} vs {d['visitante']} · ID {d['partido_id']}")
        c1, c2 = st.columns(2)
        c1.metric(d['local'], f"{d['puntos_local']:.2f}")
        c2.metric(d['visitante'], f"{d['puntos_visitante']:.2f}")
        c3, c4 = st.columns(2)
        c3.metric('Total Ensemble', f"{d['total_ensemble']:.2f}")
        c4.metric('Total Modelo C', f"{d['total_modelo_c']:.2f}")
        st.caption(f"Referencia histórica: {d['referencia_total']:.2f} · Diferencia Ensemble: {d['edge_ensemble']:+.2f} · Diferencia Modelo C: {d['edge_modelo_c']:+.2f}")
        st.caption('Pace prepartido: ' + (f"{d['pace']:.2f}" if d['pace'] is not None else 'sin datos disponibles'))
        st.caption(f"Generada: {d['generado_utc']} · Estimación experimental, no resultado garantizado")
    return True

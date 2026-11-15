"""Puente Q1 y primera mitad para la tarjeta, sin alterar motores."""
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from nba_pace_periodos_modelo import proyectar_periodos

def periodos_para_tarjeta(partido):
    fecha = pd.to_datetime(partido.get('fecha_utc'), utc=True, errors='coerce')
    if pd.isna(fecha) or fecha <= pd.Timestamp.now(tz='UTC'):
        return None
    ruta = Path(__file__).resolve().parent / 'nba_historial_pace_periodos_validado.csv'
    if not ruta.is_file():
        return None
    try:
        historial = pd.read_csv(ruta, encoding='utf-8-sig', dtype={'partido_id': str})
        pred = proyectar_periodos(historial, partido, ventana=10, minimo=5,
                                  corte_utc=datetime.now(timezone.utc))
    except (OSError, ValueError, KeyError, TypeError, pd.errors.ParserError):
        return None
    if pred is None:
        return None
    return pd.DataFrame([
        {'Período': nombre, 'Local': pred['periodos'][clave]['local'],
         'Visitante': pred['periodos'][clave]['visitante'],
         'Total': pred['periodos'][clave]['total']}
        for clave, nombre in (('q1', 'Q1'), ('mitad', 'Primera mitad'))
    ])

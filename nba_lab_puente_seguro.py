"""Guardia de datos para el puente experimental NBA. No altera módulos estables."""
from __future__ import annotations
import pandas as pd
from nba_lab_clasificacion import filtrar_regular
from nba_lab_puente_futuro import preparar_tarjeta


def preparar_tarjeta_segura(calendario: pd.DataFrame, historial: pd.DataFrame,
                           partido_id: str, posesiones: pd.DataFrame | None = None,
                           ahora_utc: str | None = None) -> dict:
    """Exige clasificación verificada y registros históricos anteriores al objetivo."""
    if not isinstance(historial, pd.DataFrame) or historial.empty:
        raise ValueError('Historial vacío: no se puede predecir')
    if 'tipo_competicion' not in historial:
        raise ValueError('Historial sin tipo_competicion: clasificar antes de predecir')
    if 'fecha_utc' not in historial:
        raise ValueError('Historial sin fecha_utc')
    if not isinstance(calendario, pd.DataFrame) or 'id' not in calendario or 'fecha_utc' not in calendario:
        raise ValueError('Calendario sin identificador o fecha')
    filas = calendario.loc[calendario['id'].astype(str).eq(str(partido_id))]
    if len(filas) != 1:
        raise ValueError('ID del partido inexistente o duplicado')
    fecha = pd.to_datetime(filas.iloc[0]['fecha_utc'], utc=True, errors='coerce')
    if pd.isna(fecha):
        raise ValueError('Fecha del partido inválida')
    h = filtrar_regular(historial)
    h = h.copy()
    h['_corte'] = pd.to_datetime(h['fecha_utc'], utc=True, errors='coerce')
    h = h.loc[h['_corte'].notna() & h['_corte'].lt(fecha)].drop(columns=['_corte'])
    if h.empty:
        raise ValueError('Sin partidos regulares verificados anteriores al objetivo')
    tarjeta = preparar_tarjeta(calendario, h, partido_id, posesiones, ahora_utc)
    tarjeta['auditoria_guardia'] = {
        'historial_recibido': int(len(historial)),
        'historial_regular_anterior': int(len(h)),
        'filtro': 'temporada_regular_verificada_y_fecha_estrictamente_anterior',
        'fuente_tipo': 'tipo_competicion',
    }
    return tarjeta

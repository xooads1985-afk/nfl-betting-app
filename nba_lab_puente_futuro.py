"""Puente experimental: calendario existente -> motor futuro -> tarjeta JSON.
No importa Streamlit, no consulta ESPN, no modifica archivos estables.
"""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from nba_lab_motor_futuro import predecir


def preparar_tarjeta(calendario: pd.DataFrame, historial: pd.DataFrame,
                     partido_id: str, posesiones: pd.DataFrame | None = None,
                     ahora_utc: str | None = None) -> dict:
    """Solo partidos futuros pendientes. calendario: salida de modulo_nba.cargar_partidos."""
    if not isinstance(calendario, pd.DataFrame) or calendario.empty:
        raise ValueError('Calendario vacío')
    requeridas = {'id', 'fecha_utc', 'local', 'visitante', 'finalizado'}
    if requeridas - set(calendario.columns):
        raise ValueError('Calendario sin columnas: ' + ', '.join(sorted(requeridas-set(calendario.columns))))
    filas = calendario.loc[calendario['id'].astype(str).eq(str(partido_id))]
    if len(filas) != 1:
        raise ValueError('El ID debe identificar exactamente un partido del calendario')
    juego = filas.iloc[0]
    fecha = pd.to_datetime(juego['fecha_utc'], utc=True, errors='coerce')
    ahora = pd.Timestamp.now(tz='UTC') if ahora_utc is None else pd.to_datetime(ahora_utc, utc=True, errors='coerce')
    if pd.isna(fecha) or pd.isna(ahora):
        raise ValueError('Fecha inválida')
    if fecha <= ahora:
        raise ValueError('El partido ya comenzó o su fecha no es futura')
    terminado = str(juego['finalizado']).strip().lower() in ('true','1','yes')
    if terminado:
        raise ValueError('El calendario marca este partido como finalizado')
    if 'estado' in calendario.columns:
        estado = str(juego.get('estado', '')).strip().lower()
        if any(x in estado for x in ('final', 'in progress', 'en curso', 'postponed', 'cancel', 'suspend')):
            raise ValueError('Estado de calendario no apto para predicción prepartido')
    local, visita = str(juego['local']).strip(), str(juego['visitante']).strip()
    if not local or not visita or local == visita:
        raise ValueError('Equipos inválidos')
    resultado = predecir(historial, local, visita, fecha.isoformat(), posesiones)
    return {
        'esquema': 'nba_tarjeta_futura_v1',
        'partido_id': str(partido_id),
        'fecha_utc': fecha.isoformat(),
        'estado': 'experimental_prepartido',
        'local': local,
        'visitante': visita,
        'proyeccion_local_ensemble': resultado['equipos'][local]['ensemble'],
        'proyeccion_visitante_ensemble': resultado['equipos'][visita]['ensemble'],
        'total_modelo_c': resultado['total_modelo_c'],
        'total_ensemble': resultado['total_ensemble'],
        'referencia_total_base': resultado['referencia_total_base'],
        'edge_total_vs_base': resultado['edge_total_vs_base'],
        'edge_total_modelo_c_vs_base': resultado['edge_total_modelo_c_vs_base'],
        'pace_prepartido': resultado['pace_prepartido'],
        'detalle_motor': resultado,
        'nota': 'Estimación estadística experimental; no es un resultado garantizado.'
    }


def guardar_tarjeta(tarjeta: dict, destino: str | Path) -> Path:
    """Salida opcional, fuera de la app; no guarda en Supabase."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps(tarjeta, ensure_ascii=False, indent=2), encoding='utf-8')
    return destino

"""Lector experimental de tarjetas NBA, independiente de Streamlit y del motor.
No modifica archivos ni consulta fuentes externas.
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from math import isfinite


def _utc(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Fecha UTC ausente')
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Fecha sin zona horaria')
    return dt.astimezone(timezone.utc)


def _numero(d, clave):
    x = d.get(clave)
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not isfinite(x):
        raise ValueError(f'Valor numérico inválido: {clave}')
    return float(x)


def leer_tarjeta(directorio, partido_id, ahora_utc=None, max_antiguedad_horas=24):
    """Devuelve un contrato limpio; rechaza datos erróneos o sin sello de generación.

    La tarjeta debe incluir `generado_utc` para verificar antigüedad.
    Las tarjetas v1 anteriores carecen de ese sello y requieren regeneración.
    """
    pid = str(partido_id)
    if not pid.isdigit():
        raise ValueError('ID del partido inválido')
    ruta = Path(directorio) / f'tarjeta_{pid}.json'
    if not ruta.is_file():
        raise FileNotFoundError(f'No hay tarjeta para {pid}')
    t = json.loads(ruta.read_text(encoding='utf-8'))
    if t.get('esquema') != 'nba_tarjeta_futura_v1' or str(t.get('partido_id')) != pid:
        raise ValueError('Esquema o ID de tarjeta incorrecto')
    if t.get('estado') != 'experimental_prepartido':
        raise ValueError('Tarjeta no apta para presentación prepartido')
    ahora = datetime.now(timezone.utc) if ahora_utc is None else _utc(ahora_utc)
    inicio = _utc(t.get('fecha_utc'))
    if inicio <= ahora:
        raise ValueError('El encuentro ya comenzó')
    generado = _utc(t.get('generado_utc'))
    edad = (ahora-generado).total_seconds()/3600
    if edad < -0.0834 or edad > max_antiguedad_horas:
        raise ValueError('Tarjeta no vigente: regenerar predicción')
    local, visitante = t.get('local'), t.get('visitante')
    if not local or not visitante or local == visitante:
        raise ValueError('Equipos inválidos')
    pl = _numero(t, 'proyeccion_local_ensemble')
    pv = _numero(t, 'proyeccion_visitante_ensemble')
    te = _numero(t, 'total_ensemble')
    tc = _numero(t, 'total_modelo_c')
    base = _numero(t, 'referencia_total_base')
    ee = _numero(t, 'edge_total_vs_base')
    ec = _numero(t, 'edge_total_modelo_c_vs_base')
    if abs(pl+pv-te) > 0.021 or abs(te-base-ee) > 0.021 or abs(tc-base-ec) > 0.021:
        raise ValueError('Inconsistencia matemática en la tarjeta')
    pace = t.get('pace_prepartido')
    if pace is not None:
        pace = _numero(t, 'pace_prepartido')
        if not 60 <= pace <= 140:
            raise ValueError('Pace fuera de rango')
    return {'partido_id': pid, 'fecha_utc': inicio.isoformat(),
            'local': local, 'visitante': visitante,
            'proyeccion_local': pl, 'proyeccion_visitante': pv,
            'total_ensemble': te, 'total_modelo_c': tc,
            'referencia_total': base, 'edge_ensemble': ee,
            'edge_modelo_c': ec, 'pace_prepartido': pace,
            'generado_utc': generado.isoformat(), 'estado': 'experimental_validado'}

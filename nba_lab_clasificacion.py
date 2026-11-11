"""Clasificación conservadora de encuentros ESPN para laboratorio NBA.
Solo season.type == 2 (regular season) se admite; ausencia de metadatos se
marca 'sin_verificar' y no entra al entrenamiento.
"""
from __future__ import annotations

REGULAR = 2
# Identificadores verificados de los cuatro minipartidos All-Star de febrero de 2026.
EVENTOS_ESPECIALES = frozenset({'401838140', '401838141', '401838142', '401838143'})
EQUIPOS_EXHIBICION = frozenset({'team stars', 'team stripes', 'world'})

def es_exhibicion(identificador, local='', visitante=''):
    if str(identificador) in EVENTOS_ESPECIALES:
        return True
    equipos = {str(local).strip().lower(), str(visitante).strip().lower()}
    return bool(equipos & EQUIPOS_EXHIBICION)


def clasificar_evento(event: dict) -> str:
    competitors = ((event.get('competitions') or [{}])[0].get('competitors') or [])
    nombres = [str((c.get('team') or {}).get('displayName', '')) for c in competitors]
    if es_exhibicion(event.get('id'), *(nombres + ['', ''])[:2]):
        return 'especial'
    season = event.get('season') or {}
    raw = season.get('type')
    try:
        kind = int(raw)
    except (ValueError, TypeError):
        return 'sin_verificar'
    return {1: 'pretemporada', 2: 'regular', 3: 'postemporada', 4: 'especial'}.get(kind, 'sin_verificar')

def filtrar_regular(df):
    """No deducir tipo por fechas o nombres de equipos."""
    if 'tipo_competicion' not in df.columns:
        raise ValueError('Faltan metadatos de tipo de competición; filtrado bloqueado')
    mascara = df['tipo_competicion'].eq('regular')
    if {'id','local','visitante'} <= set(df.columns):
        mascara &= ~df.apply(lambda x: es_exhibicion(x['id'], x['local'], x['visitante']), axis=1)
    return df.loc[mascara].copy()


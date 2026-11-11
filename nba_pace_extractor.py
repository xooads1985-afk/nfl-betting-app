"""Extractor diagnóstico de posesiones NBA. No modifica módulos existentes.

Uso: importar extraer_pace_desde_detalle(detalle, partido_id=None).
Los datos se obtienen de la respuesta de cargar_detalle() de modulo_nba.
"""
from __future__ import annotations
import math
import re
from typing import Any

ALIASES = {
    'fga': {'fieldgoalsattempted', 'fieldgoalattempts', 'fga'},
    'fta': {'freethrowsattempted', 'freethrowattempts', 'fta'},
    'oreb': {'offensiverebounds', 'offensiverebound', 'offreb', 'oreb'},
    'tov': {'turnovers', 'turnover', 'to', 'tov'},
}

def _norm(value: Any) -> str:
    return re.sub(r'[^a-z0-9]', '', str(value or '').lower())

def _number(value: Any):
    if isinstance(value, dict):
        value = value.get('value', value.get('displayValue'))
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, str):
        value = value.strip().replace(',', '')
        if not re.fullmatch(r'\d+(?:\.\d+)?', value):
            return None
    try:
        n = float(value)
    except (ValueError, TypeError):
        return None
    return n if math.isfinite(n) and n >= 0 else None

def _stats_team(team: dict) -> dict:
    out = {}
    stats = team.get('statistics', [])
    if not isinstance(stats, list):
        return out
    for entry in stats:
        if not isinstance(entry, dict):
            continue
        labels = [entry.get(k) for k in ('name', 'abbreviation', 'label', 'displayName', 'shortDisplayName')]
        for field, aliases in ALIASES.items():
            if field in out or not any(_norm(label) in aliases for label in labels):
                continue
            n = _number(entry.get('value', entry.get('displayValue')))
            if n is not None:
                out[field] = n
    return out

def extraer_pace_desde_detalle(detalle: dict, partido_id=None) -> dict:
    """Devuelve cobertura y posesiones estimadas por equipo, sin inventar faltantes.

    La estimación FGA + .44*FTA - OREB + TOV NO es pace por 48 minutos.
    Para pace normalizado se requieren minutos reales de juego validados.
    """
    result = {'partido_id': str(partido_id or ''), 'estado': 'incompleto', 'equipos': [], 'advertencias': []}
    if not isinstance(detalle, dict):
        result['advertencias'].append('Detalle inválido')
        return result
    if detalle.get('_nba_cache_rescate'):
        result['advertencias'].append('Respuesta recuperada de caché local')
    teams = detalle.get('boxscore', {}).get('teams', [])
    if not isinstance(teams, list) or len(teams) != 2:
        result['advertencias'].append('Se esperaban exactamente dos equipos en boxscore.teams')
        return result
    seen = set()
    for team in teams:
        if not isinstance(team, dict):
            result['advertencias'].append('Entrada de equipo inválida')
            return result
        info = team.get('team') or {}
        ident = str(info.get('id') or '')
        if not ident or ident in seen:
            result['advertencias'].append('Identificadores de equipos ausentes o repetidos')
            return result
        seen.add(ident)
        values = _stats_team(team)
        missing = [k.upper() for k in ALIASES if k not in values]
        possessions = None if missing else round(values['fga'] + 0.44 * values['fta'] - values['oreb'] + values['tov'], 3)
        if possessions is not None and possessions <= 0:
            missing.append('posesiones estimadas no positivas')
            possessions = None
        result['equipos'].append({'equipo_id': ident, 'equipo': info.get('displayName', ''),
                                  'estadisticas': values, 'faltantes': missing,
                                  'posesiones_estimadas': possessions})
    if len(result['equipos']) == 2 and all(not t['faltantes'] for t in result['equipos']):
        result['estado'] = 'completo'
    return result

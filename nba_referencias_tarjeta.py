"""Referencias descriptivas de puntos NBA; solo lectura y sin datos futuros.

Utiliza el snapshot SHA-256 validado, sin alterar los cuatro motores.
"""
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import math
import pandas as pd

BASE = Path(__file__).resolve().parent / 'nba_cache_preparada'
MIN_PARTIDOS = 5
ULTIMOS = 10


def referencias_para_partido(partido):
    """Retorna (tabla de períodos, nota). Si no hay evidencia, tabla=None."""
    try:
        inicio = datetime.fromisoformat(str(partido['fecha_utc']).replace('Z', '+00:00'))
        if inicio.tzinfo is None:
            raise ValueError('Inicio sin zona horaria')
        inicio = inicio.astimezone(timezone.utc)
        if datetime.now(timezone.utc) >= inicio:
            raise ValueError('Partido iniciado: no calcular referencias prospectivas')
        csv = BASE / 'historial_finalizados.csv'
        manifiesto = json.loads((BASE / 'manifiesto.json').read_text(encoding='utf-8'))
        contenido = csv.read_bytes()
        if hashlib.sha256(contenido).hexdigest() != manifiesto['sha256']:
            raise ValueError('Historial: huella SHA-256 incorrecta')
        df = pd.read_csv(csv, dtype={'id': str})
        obligatorias = {'id','fecha_utc','local','visitante','finalizado','puntos_local','puntos_visitante'}
        if not obligatorias.issubset(df.columns):
            raise ValueError('Historial sin columnas requeridas')
        if len(df) != int(manifiesto['partidos']) or df['id'].isna().any() or df['id'].duplicated().any():
            raise ValueError('Historial: cantidad o IDs inválidos')
        fechas = pd.to_datetime(df['fecha_utc'], utc=True, errors='coerce')
        if fechas.isna().any():
            raise ValueError('Historial con fechas inválidas')
        finalizados = df['finalizado'].astype(str).str.lower().eq('true')
        if not finalizados.all():
            raise ValueError('Historial contiene partidos no finalizados')
        df = df.loc[(fechas < pd.Timestamp(inicio)) & (fechas >= pd.Timestamp(inicio) - pd.Timedelta(days=365))].copy()
        df['_fecha'] = fechas.loc[df.index]
        df['puntos_local'] = pd.to_numeric(df['puntos_local'], errors='coerce')
        df['puntos_visitante'] = pd.to_numeric(df['puntos_visitante'], errors='coerce')
        df = df.dropna(subset=['puntos_local','puntos_visitante'])
        if (df[['puntos_local','puntos_visitante']] < 0).any().any():
            raise ValueError('Historial con puntos negativos')
        def promedio_equipo(nombre):
            local = df.loc[df['local'].eq(nombre), ['_fecha','puntos_local']].rename(columns={'puntos_local':'puntos'})
            visita = df.loc[df['visitante'].eq(nombre), ['_fecha','puntos_visitante']].rename(columns={'puntos_visitante':'puntos'})
            ultimos = pd.concat([local, visita]).sort_values('_fecha').tail(ULTIMOS)
            if len(ultimos) < MIN_PARTIDOS:
                raise ValueError(f'Muestra insuficiente para {nombre}: {len(ultimos)} partidos')
            promedio = float(ultimos['puntos'].mean())
            if not math.isfinite(promedio):
                raise ValueError('Referencia no finita')
            return round(promedio, 3), len(ultimos)
        local, nl = promedio_equipo(str(partido['local']))
        visitante, nv = promedio_equipo(str(partido['visitante']))
        tabla = pd.DataFrame([{
            'Período': 'Final reglamentario',
            'Referencia local': local,
            'Referencia visitante': visitante,
            'Referencia total': round(local + visitante, 3),
        }])
        return tabla, f'Referencia descriptiva: últimos {nl} partidos de {partido["local"]} y {nv} de {partido["visitante"]}, anteriores al inicio. No es predicción del motor.'
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        return None, f'Referencias no disponibles: {type(exc).__name__}: {exc}'

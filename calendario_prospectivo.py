"""Separación conservadora de calendario NFL para evaluación prospectiva.

No modifica la aplicación estable. No confía en marcadores sin estado FINAL.
"""
from datetime import datetime, timezone
import pandas as pd

FINAL_STATES = {'FINAL', 'F', 'COMPLETED', 'COMPLETE'}


def separar(calendario, ahora_utc=None):
    """Devuelve (terminados, pendientes, excluidos).

    Requiere kickoff_utc y game_status explícitos para evitar filtraciones.
    Un juego con marcador y estado no final se excluye del entrenamiento.
    """
    needed = {'game_id', 'season', 'week', 'home_team', 'away_team',
              'kickoff_utc', 'game_status', 'home_score', 'away_score'}
    missing = needed - set(calendario.columns)
    if missing:
        raise ValueError('Columnas faltantes: ' + ', '.join(sorted(missing)))
    df = calendario.copy()
    if df['game_id'].isna().any() or df['game_id'].astype(str).str.strip().eq('').any():
        raise ValueError('game_id vacío')
    if df['game_id'].astype(str).duplicated().any():
        raise ValueError('game_id duplicado')
    df['kickoff_utc'] = pd.to_datetime(df['kickoff_utc'], utc=True, errors='coerce')
    if df['kickoff_utc'].isna().any():
        raise ValueError('Fecha de inicio inválida')
    now = pd.Timestamp(ahora_utc if ahora_utc is not None else datetime.now(timezone.utc))
    if now.tzinfo is None:
        raise ValueError('ahora_utc requiere zona horaria')
    now = now.tz_convert('UTC')
    final = df['game_status'].astype(str).str.upper().str.strip().isin(FINAL_STATES)
    scores = pd.to_numeric(df['home_score'], errors='coerce').notna() & pd.to_numeric(df['away_score'], errors='coerce').notna()
    before = df['kickoff_utc'] > now
    completed = final & scores & ~before
    upcoming = before & ~final & ~scores
    return (df.loc[completed].copy(), df.loc[upcoming].copy(), df.loc[~(completed | upcoming)].copy())

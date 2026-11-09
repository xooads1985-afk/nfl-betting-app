"""NBA laboratory: incremental chronological backfill using only prior games.
Replaces only the experimental offline runner, not stable Streamlit modules.
"""
from __future__ import annotations
import argparse
import concurrent.futures
from datetime import date, timedelta, datetime, timezone
import json
from pathlib import Path
import time
import requests
import pandas as pd
from nba_lab_motor_offline import _nba_lab_ml_validacion, _nba_lab_ml_resumen

BASE = Path(__file__).resolve().parent
OUT = BASE / 'nba_lab_resultados'
CACHE = BASE / 'nba_lab_cache'
URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard'


def days(a, b):
    d = a
    while d <= b:
        yield d
        d += timedelta(days=1)


def download_one(d, refresh=False):
    path = CACHE / (d.isoformat() + '.json')
    if path.exists() and not refresh:
        return d, json.loads(path.read_text(encoding='utf-8')), None
    err = None
    for attempt in range(3):
        try:
            response = requests.get(URL, params={'dates': d.strftime('%Y%m%d'), 'limit': 100},
                                    timeout=20, headers={'User-Agent': 'NBA-Lab-Research/1.0'})
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload.get('events'), list):
                raise ValueError('No events list')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
            return d, payload, None
        except (requests.RequestException, ValueError) as exc:
            err = f'{d}: {type(exc).__name__}: {exc}'
            time.sleep(1.5 * (attempt + 1))
    if path.exists():
        return d, json.loads(path.read_text(encoding='utf-8')), err + ' (cached copy used)'
    return d, None, err


def parse(payload):
    rows = []
    for event in payload.get('events', []):
        comp = (event.get('competitions') or [{}])[0]
        entries = comp.get('competitors') or []
        home = next((x for x in entries if x.get('homeAway') == 'home'), None)
        away = next((x for x in entries if x.get('homeAway') == 'away'), None)
        if not home or not away:
            continue
        status = event.get('status', {}).get('type', {})
        def score(e):
            try:
                return float(e.get('score'))
            except (ValueError, TypeError):
                return None
        rows.append({'id': str(event.get('id', '')), 'fecha_utc': event.get('date', ''),
                     'local': home.get('team', {}).get('displayName', ''),
                     'visitante': away.get('team', {}).get('displayName', ''),
                     'puntos_local': score(home), 'puntos_visitante': score(away),
                     'finalizado': bool(status.get('completed', False)),
                     'estado': status.get('description', '')})
    return rows


def select_eligible_days(completed, old, max_days, warmup_games=100):
    """Choose missing calendar days with sufficient strictly-prior history.

    This is a cheap prefilter. The model still performs its own walk-forward
    training and may skip individual games with insufficient team history.
    """
    ordered = completed.copy()
    ordered['_ts'] = pd.to_datetime(ordered['fecha_utc'], utc=True, errors='coerce')
    ordered = ordered.dropna(subset=['_ts']).sort_values('_ts')
    ordered['_day'] = ordered['_ts'].dt.strftime('%Y-%m-%d')
    existing_ids = set(old['partido'].dropna().astype(str)) if 'partido' in old else set()
    days_selected = []
    target_timestamps = []
    warmup_skipped = 0
    completed_skipped = 0
    for day, group in ordered.groupby('_day', sort=True):
        pending = group.loc[~group['id'].astype(str).isin(existing_ids)]
        if pending.empty:
            completed_skipped += 1
            continue
        first = group['_ts'].min()
        prior = ordered.loc[ordered['_ts'] < first]
        if len(prior) < warmup_games:
            warmup_skipped += 1
            continue
        # For both teams, at least three games strictly before this day.
        counts = pd.concat([prior['local'], prior['visitante']]).value_counts()
        possible = pending.loc[pending['local'].map(counts).fillna(0).ge(3) &
                               pending['visitante'].map(counts).fillna(0).ge(3)]
        if possible.empty:
            warmup_skipped += 1
            continue
        days_selected.append(day)
        # Include only timestamps of pending games. The validation motor
        # handles each timestamp with strictly earlier training data.
        target_timestamps.extend(possible['_ts'].tolist())
        if max_days > 0 and len(days_selected) >= max_days:
            break
    return days_selected, target_timestamps, warmup_skipped, completed_skipped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--desde', default='2025-10-21')
    parser.add_argument('--hasta', default=date.today().isoformat())
    parser.add_argument('--max-fechas', type=int, default=10, help='Número de días pendientes; 0 = todos')
    parser.add_argument('--calentamiento', type=int, default=100, help='Partidos iniciales mínimos')
    args = parser.parse_args()
    a = date.fromisoformat(args.desde)
    b = date.fromisoformat(args.hasta)
    if b < a or args.max_fechas < 0 or args.calentamiento < 24:
        raise ValueError('Intervalo o parámetros inválidos')
    OUT.mkdir(exist_ok=True)
    CACHE.mkdir(exist_ok=True)
    dates = list(days(a, b))
    fetched, failures = [], []
    print(f'Loading {len(dates)} dates', flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(download_one, d, (b-d).days <= 3): d for d in dates}
        for i, future in enumerate(concurrent.futures.as_completed(futures), 1):
            _, payload, error = future.result()
            if error:
                failures.append(error)
            if payload:
                fetched.extend(parse(payload))
            if i % 25 == 0:
                print(f'Fetched {i}/{len(dates)} dates', flush=True)
    if not fetched:
        raise RuntimeError('No ESPN data retrieved; previous outputs untouched')
    df = pd.DataFrame(fetched).drop_duplicates('id', keep='last')
    df['fecha_utc'] = pd.to_datetime(df['fecha_utc'], utc=True, errors='coerce')
    df = df.dropna(subset=['fecha_utc']).sort_values('fecha_utc')
    df['fecha_utc'] = df['fecha_utc'].dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    completed = df.loc[df['finalizado'].eq(True)].dropna(subset=['puntos_local', 'puntos_visitante']).copy()
    completed.to_csv(OUT / 'partidos_historicos.csv', index=False)
    oldpath = OUT / 'algoritmos_predicciones.csv'
    old = pd.read_csv(oldpath) if oldpath.exists() else pd.DataFrame()
    selected, timestamps, skipped, covered = select_eligible_days(completed, old, args.max_fechas, args.calentamiento)
    print(f'Calentamiento: {args.calentamiento} partidos mínimos; días iniciales sin historial: {skipped}; días cubiertos: {covered}', flush=True)
    added = 0
    if selected:
        print(f'Backfill: {len(selected)} días elegibles, desde {selected[0]} hasta {selected[-1]}; partidos candidatos: {len(timestamps)}', flush=True)
        new, note = _nba_lab_ml_validacion(completed, fechas_objetivo=timestamps)
        print(note, flush=True)
        if not new.empty:
            combined = pd.concat([old, new], ignore_index=True) if not old.empty else new
            combined['partido'] = combined['partido'].astype(str)
            combined['equipo'] = combined['equipo'].astype(str)
            combined = combined.drop_duplicates(['partido', 'equipo'], keep='first')
            combined = combined.sort_values(['fecha', 'partido', 'equipo'])
            added = len(combined) - len(old)
            combined.to_csv(oldpath, index=False)
            _nba_lab_ml_resumen(combined).to_csv(OUT / 'algoritmos_resumen.csv', index=False)
        else:
            print('No hubo predicciones en los días elegibles: revisar condiciones internas del modelo.', flush=True)
    else:
        print('No hay días pendientes con suficiente historial.', flush=True)
    print(f'Predicciones nuevas guardadas: {added}', flush=True)
    meta = {'actualizado_utc': datetime.now(timezone.utc).isoformat(), 'desde': str(a), 'hasta': str(b),
            'partidos_finalizados': len(completed),
            'predicciones_guardadas': len(pd.read_csv(oldpath)) if oldpath.exists() else 0,
            'predicciones_nuevas': added, 'dias_elegibles': len(selected),
            'dias_omitidos_por_calentamiento': skipped,
            'incidencias': failures[:50], 'incidencias_total': len(failures),
            'nota': 'Modelo de posesiones pendiente; NB comparte media con regresión lineal.'}
    (OUT / 'estado.json').write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(meta, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    main()


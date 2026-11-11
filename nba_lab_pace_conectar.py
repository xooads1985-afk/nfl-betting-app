"""Pace experimental: ESPN boxscores -> predicciones walk-forward, sin alterar motores estables."""
import argparse
import json
import time
from pathlib import Path
import pandas as pd
import requests

URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary'

def numero(v):
    try: return float(str(v).replace(',', '').strip())
    except (TypeError, ValueError): return None

def estadisticas(items):
    """Acepta el formato ESPN de equipos, incluido FG/FT como 'hechos-intentos'."""
    d = {}
    for item in items or []:
        key = str(item.get('name') or item.get('abbreviation') or '').lower().replace(' ', '')
        value = item.get('displayValue', item.get('value'))
        if isinstance(value, str) and '-' in value and key in ('fieldgoalsmade-fieldgoalsattempted','fieldgoals','fg','freethrowsmade-freethrowsattempted','freethrows','ft'):
            value = value.split('-')[-1]
        d[key] = numero(value)
    def get(*keys):
        for k in keys:
            if d.get(k) is not None: return d[k]
        return None
    return (get('fieldgoalsattempted','fieldgoalsmade-fieldgoalsattempted','fieldgoals','fg'),
            get('offensiverebounds','offreb','oreb'),
            get('turnovers','totalturnovers','to'),
            get('freethrowsattempted','freethrowsmade-freethrowsattempted','freethrows','ft'))

def extraer(data, game_id):
    box = data.get('boxscore') or {}
    teams = box.get('teams') or []
    rows = []
    for item in teams:
        team = item.get('team') or {}
        fga, orb, tov, fta = estadisticas(item.get('statistics'))
        if any(x is None for x in (fga,orb,tov,fta)) or fga <= 0:
            continue
        poss = fga - orb + tov + 0.44 * fta
        if not 60 <= poss <= 140: continue
        rows.append({'partido': str(game_id), 'equipo': team.get('displayName'), 'posesiones': poss})
    return rows if len(rows) == 2 and len({r['equipo'] for r in rows}) == 2 else []

def descargar(ids, cache):
    cache.mkdir(parents=True, exist_ok=True)
    rows, errores = [], []
    session = requests.Session()
    for i, game_id in enumerate(ids, 1):
        file = cache / f'{game_id}.json'
        try:
            if file.exists(): data = json.loads(file.read_text(encoding='utf-8'))
            else:
                for intento in range(3):
                    try:
                        r = session.get(URL, params={'event':game_id}, timeout=20, headers={'User-Agent':'NBA-Lab-Research/1.0'})
                        r.raise_for_status(); data = r.json(); break
                    except (requests.RequestException, ValueError):
                        if intento == 2: raise
                        time.sleep(1.5 * (intento+1))
                file.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
            parsed = extraer(data,game_id)
            if parsed: rows.extend(parsed)
            else: errores.append({'partido':game_id,'motivo':'boxscore incompleto o sin posesiones válidas'})
        except (OSError, ValueError, requests.RequestException) as e:
            errores.append({'partido':game_id,'motivo':str(e)[:180]})
        if i % 100 == 0: print(f'Boxscores: {i}/{len(ids)}; completos: {len(rows)//2}', flush=True)
    return pd.DataFrame(rows, columns=['partido','equipo','posesiones']), pd.DataFrame(errores,columns=['partido','motivo'])

def calcular(historial, pred, box):
    """Cada predicción usa SOLO boxscores con fecha anterior al inicio del partido."""
    h = historial.copy(); p = pred.copy(); b = box.copy()
    h['id'] = h['id'].astype(str); p['partido'] = p['partido'].astype(str); b['partido'] = b['partido'].astype(str)
    h['fecha_utc'] = pd.to_datetime(h['fecha_utc'], utc=True, errors='coerce')
    p['fecha'] = pd.to_datetime(p['fecha'], utc=True, errors='coerce')
    h['puntos_local'] = pd.to_numeric(h['puntos_local'],errors='coerce'); h['puntos_visitante'] = pd.to_numeric(h['puntos_visitante'],errors='coerce')
    sides = pd.concat([h[['id','fecha_utc','local','puntos_local','puntos_visitante']].rename(columns={'id':'partido','local':'equipo','puntos_local':'pf','puntos_visitante':'pc'}), h[['id','fecha_utc','visitante','puntos_visitante','puntos_local']].rename(columns={'id':'partido','visitante':'equipo','puntos_visitante':'pf','puntos_local':'pc'})],ignore_index=True)
    sides = sides.merge(b,on=['partido','equipo'],how='inner')
    sides = sides.dropna(subset=['fecha_utc','posesiones','pf','pc']).sort_values('fecha_utc')
    output = p.copy(); output['Posesiones + eficiencia'] = float('nan')
    for fecha, indexes in p.groupby('fecha').groups.items():
        prior = sides.loc[sides['fecha_utc'] < fecha]
        for idx in indexes:
            r = p.loc[idx]; game = h.loc[h['id'].eq(r['partido'])]
            if game.empty: continue
            g = game.iloc[0]; team = r['equipo']; opponent = g['visitante'] if team == g['local'] else g['local']
            own = prior.loc[prior['equipo'].eq(team)].tail(10)
            opp = prior.loc[prior['equipo'].eq(opponent)].tail(10)
            if min(len(own),len(opp)) < 3: continue
            pace = (own['posesiones'].mean()+opp['posesiones'].mean())/2
            off = (own['pf']/own['posesiones']*100).mean()
            defense = (opp['pc']/opp['posesiones']*100).mean()
            value = pace*(off+defense)/200
            if 60 <= pace <= 140 and 60 <= value <= 180:
                output.at[idx,'Posesiones + eficiencia'] = float(value)
    return output

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--historial',type=Path,default=Path('nba_lab_resultados_depurados/reentrenamiento/historial_regular.csv'))
    ap.add_argument('--predicciones',type=Path,default=Path('nba_lab_resultados_depurados/reentrenamiento/predicciones_reentrenadas.csv'))
    ap.add_argument('--cache',type=Path,default=Path('nba_lab_boxscores_cache'))
    ap.add_argument('--salida',type=Path,default=Path('nba_lab_resultados_depurados/pace'))
    args=ap.parse_args()
    h=pd.read_csv(args.historial,dtype={'id':str}); p=pd.read_csv(args.predicciones,dtype={'partido':str})
    ids=h['id'].dropna().astype(str).unique().tolist()
    box, errors=descargar(ids,args.cache)
    result=calcular(h,p,box)
    args.salida.mkdir(parents=True,exist_ok=True)
    result.to_csv(args.salida/'predicciones_con_pace.csv',index=False)
    errors.to_csv(args.salida/'boxscores_pendientes.csv',index=False)
    valid=result[['real','Posesiones + eficiencia']].dropna()
    report={'partidos_regulares':len(h),'boxscores_completos':len(box)//2,'boxscores_pendientes':len(errors),'predicciones_totales':len(p),'predicciones_pace':len(valid),'pace_validado':len(valid)>0,'mae_pace':round(float((valid['Posesiones + eficiencia']-valid['real']).abs().mean()),3) if len(valid) else None,'nota':'Evaluación cronológica: solo boxscores de fechas anteriores. No altera los modelos estables.'}
    (args.salida/'estado_pace.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if not len(valid): raise RuntimeError('Sin predicciones Pace válidas: revisar boxscores_pendientes.csv')

if __name__=='__main__': main()

"""Recupera boxscores de la temporada 2025-26 y compara Pace con predicciones históricas.
Solo lectura; no cambia los módulos estables ni realiza entrenamiento.
"""
import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
import pandas as pd

BASE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary'

def load_parser():
    from nba_lab_recuperacion_controlada import parse
    return parse

def build_game(row):
    return {'id':str(row.id),'date':str(row.fecha_utc),
            'scores':{'home':int(row.puntos_local),'away':int(row.puntos_visitante)},
            'teams':{'home':str(row.local),'away':str(row.visitante)},'linescores':{}}

def download(gid, timeout=25):
    url=BASE+'?'+urllib.parse.urlencode({'event':gid})
    req=urllib.request.Request(url,headers={'User-Agent':'NBA-Lab-Research/1.0'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--historico',default='nba_lab_resultados/partidos_historicos.csv')
    a.add_argument('--predicciones',default='nba_lab_resultados/algoritmos_predicciones.csv')
    a.add_argument('--salida',default='nba_comparacion_2025_resultados')
    a.add_argument('--max-partidos',type=int,default=350)
    args=a.parse_args()
    out=Path(args.salida);out.mkdir(parents=True,exist_ok=True)
    hist=pd.read_csv(args.historico,dtype={'id':str})
    preds=pd.read_csv(args.predicciones,dtype={'partido':str})
    hist['fecha_utc']=pd.to_datetime(hist.fecha_utc,utc=True,errors='coerce')
    # 2025-26 season; only finalized games strictly before the earliest prediction are context.
    hist=hist[(hist.fecha_utc>='2025-10-21')&(hist.fecha_utc<'2026-07-01')&hist.finalizado.eq(True)]
    hist=hist.dropna(subset=['fecha_utc','puntos_local','puntos_visitante']).sort_values(['fecha_utc','id']).drop_duplicates('id')
    selected=hist.head(max(1,min(args.max_partidos,1000)))
    from nba_lab_recuperacion_controlada import parse
    from nba_lab_puente_integral import construir, comparar
    from nba_lab_pace_integral import evaluar
    teams=[]; errors=[]; checked=0
    for row in selected.itertuples(index=False):
        checked+=1
        # Parse ESPN summary using its OWN team abbreviations from boxscore, not full-name from historical CSV.
        game=build_game(row)
        try:
            payload=download(game['id'])
            blocks=payload.get('boxscore',{}).get('teams') or []
            header=(payload.get('header',{}).get('competitions') or [{}])[0]
            mapping={str(c.get('team',{}).get('id') or c.get('id')):c.get('homeAway') for c in header.get('competitors',[])}
            for block in blocks:
                side=block.get('homeAway') or mapping.get(str(block.get('team',{}).get('id')))
                if side in ('home','away'):
                    game['teams'][side]=block.get('team',{}).get('abbreviation')
            t,_,_,issues=parse(payload,game)
            if issues or len(t)!=2 or {x['side'] for x in t}!={'home','away'}:
                errors.append({'id':game['id'],'reason':';'.join(issues) or 'incomplete_teams'});continue
            # Reject mismatched scoreboard or absent pace inputs.
            if any(x['points']!=game['scores'][x['side']] or x['possessions_est'] is None for x in t):
                errors.append({'id':game['id'],'reason':'score_or_pace_mismatch'});continue
            teams.extend(t)
        except Exception as e:
            errors.append({'id':game['id'],'reason':str(e)[:180]})
        if checked%50==0:print(f'Procesados {checked}/{len(selected)}; completos {len(teams)//2}',flush=True)
        time.sleep(0.1)
    columns=['id','date','side','team','points','fga','fgm','fta','orb','tov','fg3m','fg3a','possessions_est']
    pd.DataFrame(teams,columns=columns).to_csv(out/'equipos_espn_2025.csv',index=False)
    pd.DataFrame(errors,columns=['id','reason']).to_csv(out/'errores_descarga.csv',index=False)
    report={'temporada':'2025-26','partidos_solicitados':len(selected),'partidos_con_boxscore_completo':len(teams)//2,'errores':len(errors),'predicciones_originales':len(preds),'comparacion_valida':False}
    if teams:
        games=construir(out/'equipos_espn_2025.csv',out/'boxscores_para_pace.csv')
        try:
            evaluar(out/'boxscores_para_pace.csv',out,5,10)
            report.update(comparar(out/'pace_predicciones.csv',args.predicciones,out))
        except ValueError as e:report['error_comparacion']=str(e)
    (out/'reporte_comparacion_2025.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if not teams:sys.exit('No se obtuvieron boxscores completos; revisar errores_descarga.csv')

if __name__=='__main__':main()

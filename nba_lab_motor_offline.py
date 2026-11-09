"""NBA laboratory offline. Fetches ESPN scores, saves cache and results.
No betting decisions or automated wagers.
"""
from __future__ import annotations
import argparse
import concurrent.futures
from datetime import date, timedelta, datetime, timezone
import io
import json
import os
from pathlib import Path
import time
import requests
import pandas as pd
from nba_lab_motor_offline import _nba_lab_ml_validacion, _nba_lab_ml_resumen

BASE=Path(__file__).resolve().parent
OUT=BASE/'nba_lab_resultados'
CACHE=BASE/'nba_lab_cache'
URL='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard'


def days(a,b):
    d=a
    while d<=b:
        yield d
        d+=timedelta(days=1)


def download_one(d,refresh=False):
    path=CACHE/(d.isoformat()+'.json')
    if path.exists() and not refresh:
        return d, json.loads(path.read_text(encoding='utf-8')), None
    err=None
    for attempt in range(3):
        try:
            r=requests.get(URL,params={'dates':d.strftime('%Y%m%d'),'limit':100},timeout=20,
                           headers={'User-Agent':'NBA-Lab-Research/1.0'})
            r.raise_for_status()
            payload=r.json()
            if not isinstance(payload.get('events'),list):
                raise ValueError('No events list')
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
            return d,payload,None
        except (requests.RequestException,ValueError) as exc:
            err=f'{d}: {type(exc).__name__}: {exc}'
            time.sleep(1.5*(attempt+1))
    if path.exists():
        return d,json.loads(path.read_text(encoding='utf-8')),err+' (cached copy used)'
    return d,None,err


def parse(payload):
    rows=[]
    for event in payload.get('events',[]):
        comp=(event.get('competitions') or [{}])[0]
        entries=comp.get('competitors') or []
        home=next((x for x in entries if x.get('homeAway')=='home'),None)
        away=next((x for x in entries if x.get('homeAway')=='away'),None)
        if not home or not away:continue
        status=event.get('status',{}).get('type',{})
        def score(e):
            try:return float(e.get('score'))
            except (ValueError,TypeError):return None
        rows.append({'id':str(event.get('id','')),'fecha_utc':event.get('date',''),
          'local':home.get('team',{}).get('displayName',''),
          'visitante':away.get('team',{}).get('displayName',''),
          'puntos_local':score(home),'puntos_visitante':score(away),
          'finalizado':bool(status.get('completed',False)),
          'estado':status.get('description','')})
    return rows


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--desde',default='2025-10-21')
    parser.add_argument('--hasta',default=date.today().isoformat())
    parser.add_argument('--max-fechas',type=int,default=0,
                        help='0 = todas las fechas nuevas')
    args=parser.parse_args()
    a=date.fromisoformat(args.desde); b=date.fromisoformat(args.hasta)
    if b<a:raise ValueError('Invalid date interval')
    OUT.mkdir(exist_ok=True);CACHE.mkdir(exist_ok=True)
    dates=list(days(a,b)); fetched=[]; failures=[]
    print(f'Loading {len(dates)} dates',flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures={pool.submit(download_one,d,(b-d).days<=3):d for d in dates}
        for i,f in enumerate(concurrent.futures.as_completed(futures),1):
            day,payload,error=f.result()
            if error:failures.append(error)
            if payload:fetched.extend(parse(payload))
            if i%25==0:print(f'Fetched {i}/{len(dates)} dates',flush=True)
    if not fetched:raise RuntimeError('No ESPN data retrieved; previous outputs untouched')
    df=pd.DataFrame(fetched).drop_duplicates('id',keep='last')
    df['fecha_utc']=pd.to_datetime(df['fecha_utc'],utc=True,errors='coerce')
    df=df.dropna(subset=['fecha_utc']).sort_values('fecha_utc')
    df['fecha_utc']=df['fecha_utc'].dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    completed=df.loc[df['finalizado'].eq(True)].dropna(subset=['puntos_local','puntos_visitante'])
    completed.to_csv(OUT/'partidos_historicos.csv',index=False)
    oldpath=OUT/'algoritmos_predicciones.csv'
    old=pd.read_csv(oldpath) if oldpath.exists() else pd.DataFrame()
    # El motor usa marcas de tiempo exactas para walk-forward. Para seleccionar
    # bloques, agrupamos por día UTC y no por hora de inicio de cada encuentro.
    # Los primeros 100 partidos finalizados son calentamiento: no se evalúan.
    MIN_PARTIDOS_CALENTAMIENTO = 100
    old_ids=set(old['partido'].astype(str)) if not old.empty else set()
    juegos=completed[['id','fecha_utc']].copy()
    juegos['dia_utc']=pd.to_datetime(juegos['fecha_utc'],utc=True).dt.date
    fechas=sorted(juegos['dia_utc'].unique())
    elegibles=[]
    calentamiento=[]
    for dia in fechas:
        anteriores=int((juegos['dia_utc'] < dia).sum())
        if anteriores < MIN_PARTIDOS_CALENTAMIENTO:
            calentamiento.append(dia)
            continue
        ids_dia=set(juegos.loc[juegos['dia_utc'].eq(dia),'id'].astype(str))
        if not ids_dia.issubset(old_ids):
            elegibles.append(dia)
    dias_objetivo=elegibles if args.max_fechas==0 else elegibles[:args.max_fechas]
    print(f'Calentamiento: {len(calentamiento)} dias excluidos (<{MIN_PARTIDOS_CALENTAMIENTO} partidos previos).',flush=True)
    print(f'Fechas elegibles pendientes: {len(elegibles)}; bloque seleccionado: {len(dias_objetivo)}.',flush=True)
    if dias_objetivo:
        # El validador acepta fechas exactas, no fechas de calendario.
        objetivo=pd.to_datetime(juegos.loc[juegos['dia_utc'].isin(dias_objetivo),'fecha_utc'],utc=True).tolist()
        print(f'Backfill: desde {dias_objetivo[0]} hasta {dias_objetivo[-1]} (UTC)',flush=True)
        new,note=_nba_lab_ml_validacion(completed,fechas_objetivo=objetivo)
        print(note,flush=True)
        if not new.empty:
            combined=pd.concat([old,new],ignore_index=True) if not old.empty else new
            combined['partido']=combined['partido'].astype(str)
            combined=combined.drop_duplicates(['partido','equipo'],keep='first')
            combined=combined.sort_values(['fecha','partido','equipo'])
            combined.to_csv(oldpath,index=False)
            _nba_lab_ml_resumen(combined).to_csv(OUT/'algoritmos_resumen.csv',index=False)
            print(f'Nuevas filas: {len(new)}; total guardado: {len(combined)}',flush=True)
        else:
            print('ADVERTENCIA: el bloque no produjo predicciones; revisar requisitos de caracteristicas y entrenamiento.',flush=True)
    else:
        print('No hay fechas elegibles pendientes; se conservan resultados.',flush=True)
    meta={'actualizado_utc':datetime.now(timezone.utc).isoformat(),
          'desde':str(a),'hasta':str(b),'partidos_finalizados':len(completed),
          'predicciones_guardadas':len(pd.read_csv(oldpath)) if oldpath.exists() else 0,
          'incidencias':failures[:50], 'incidencias_total':len(failures),
          'nota':'Modelo de posesiones pendiente; NB comparte media con regresión lineal.'}
    (OUT/'estado.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(meta,ensure_ascii=False),flush=True)

if __name__=='__main__':main()

"""Incremental read-only ESPN NBA extraction, conservative sample audit.
No writes to repository history or training. Results go to Actions artifact.
"""
import argparse,csv,datetime as dt,json,time,urllib.parse,urllib.request
from pathlib import Path
from nba_lab_recuperacion_controlada import parse,write_csv
from nba_lab_verificar_identidad_espn import verify

SCOREBOARD='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard'
SUMMARY='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary'
HEADERS={'User-Agent':'NBA-Lab-Historical-Audit/1.0'}

def fetch(url,params):
    req=urllib.request.Request(url+'?'+urllib.parse.urlencode(params),headers=HEADERS)
    with urllib.request.urlopen(req,timeout=30) as r:return json.load(r)

def discover(day):
    payload=fetch(SCOREBOARD,{'dates':day.strftime('%Y%m%d'),'limit':100})
    games=[]
    for event in payload.get('events',[]):
        comp=(event.get('competitions') or [{}])[0]
        if not comp.get('status',{}).get('type',{}).get('completed'):continue
        sides={c.get('homeAway'):c for c in comp.get('competitors',[])}
        if set(sides)!={'home','away'}:continue
        try:scores={k:int(float(v['score'])) for k,v in sides.items()}
        except (KeyError,ValueError,TypeError):continue
        games.append({'id':str(event['id']),'date':event.get('date'), 'scores':scores,
          'teams':{k:v.get('team',{}).get('abbreviation') for k,v in sides.items()},
          'linescores':{k:v.get('linescores',[]) for k,v in sides.items()}})
    return games

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--inicio',default='2026-10-20');ap.add_argument('--dias',type=int,default=7)
    ap.add_argument('--salida',default='nba_historial_incremental_salida')
    args=ap.parse_args()
    start=dt.date.fromisoformat(args.inicio);days=max(1,min(7,args.dias))
    end=min(start+dt.timedelta(days=days-1),dt.datetime.now(dt.timezone.utc).date())
    out=Path(args.salida);out.mkdir(parents=True,exist_ok=True)
    team_rows=[];player_rows=[];period_rows=[];results=[];seen=set()
    for n in range((end-start).days+1):
        day=start+dt.timedelta(days=n)
        try:games=discover(day)
        except Exception as e:
            results.append({'date':day.isoformat(),'status':'scoreboard_error','error':str(e)[:250]});continue
        for game in games:
            gid=game['id']
            if gid in seen:continue
            seen.add(gid)
            try:
                payload=fetch(SUMMARY,{'event':gid})
                t,p,q,issues=parse(payload,game)
                if len(t)!=2 or len(q)!=2 or not p:issues.append('incomplete_rows')
                # Exclude suspicious games from all exported samples.
                if issues:
                    results.append({'date':day.isoformat(),'id':gid,'status':'rejected','issues':issues})
                else:
                    team_rows.extend(t);player_rows.extend(p);period_rows.extend(q)
                    results.append({'date':day.isoformat(),'id':gid,'status':'extracted','teams':len(t),'players':len(p),'periods':len(q)})
            except Exception as e:
                results.append({'date':day.isoformat(),'id':gid,'status':'summary_error','error':str(e)[:250]})
            time.sleep(.15)
        time.sleep(.15)
    write_csv(out/'equipos_muestra.csv',team_rows,['id','date','side','team','points','fga','fgm','fta','orb','tov','fg3m','fg3a','possessions_est'])
    write_csv(out/'jugadores_muestra.csv',player_rows,['id','date','team','player_id','player','minutes','points','rebounds','assists','threes'])
    write_csv(out/'periodos_muestra.csv',period_rows,['id','side','q1','q2','q3','q4','overtime','total'])
    summary={'start':start.isoformat(),'end':end.isoformat(),'dates_checked':(end-start).days+1,
       'games_discovered':len(seen),'games_extracted':sum(r.get('status')=='extracted' for r in results),
       'games_rejected':sum(r.get('status')=='rejected' for r in results),
       'team_rows':len(team_rows),'player_rows':len(player_rows),'period_rows':len(period_rows),
       'training_authorized':False,'results':results}
    (out/'reporte_historial.json').write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps({k:v for k,v in summary.items() if k!='results'},indent=2))
    if not team_rows:raise SystemExit('No se extrajeron partidos; revisar reporte_historial.json')
    # Recheck every player against a fresh ESPN summary.
    verify(out,out/'auditoria_identidad')

if __name__=='__main__':main()

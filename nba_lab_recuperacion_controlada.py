"""Read-only ESPN historical sample. Produces artifact files only, no repository writes."""
import argparse,csv,json,time,urllib.request,urllib.parse
from pathlib import Path

BASE='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary'

def games_from_cache(folder):
    seen=set()
    for file in sorted(Path(folder).glob('20??-??-??.json'),reverse=True):
        try: data=json.loads(file.read_text(encoding='utf8'))
        except (OSError,ValueError):continue
        for event in data.get('events',[]):
            cs=(event.get('competitions') or [{}])[0]
            if not cs.get('status',{}).get('type',{}).get('completed'):continue
            gid=str(event.get('id',''))
            if not gid or gid in seen:continue
            sides={c.get('homeAway'):c for c in cs.get('competitors',[])}
            if set(sides)!={'home','away'}:continue
            try: scores={k:int(float(v['score'])) for k,v in sides.items()}
            except (ValueError,KeyError,TypeError):continue
            seen.add(gid)
            yield {'id':gid,'date':event.get('date'),'scores':scores,'teams':{k:v.get('team',{}).get('abbreviation') for k,v in sides.items()},'linescores':{k:v.get('linescores',[]) for k,v in sides.items()}}

def parse(payload,game):
    team_rows=[];player_rows=[];period_rows=[];issues=[]
    competition=(payload.get('header',{}).get('competitions') or [{}])[0]
    mapping={str(c.get('team',{}).get('id') or c.get('id')):c.get('homeAway') for c in competition.get('competitors',[])}
    teamblocks=payload.get('boxscore',{}).get('teams') or []
    for block in teamblocks:
        side=block.get('homeAway') or block.get('team',{}).get('homeAway') or mapping.get(str(block.get('team',{}).get('id')))
        if side not in ('home','away'):issues.append('team_side_unknown');continue
        stats={s.get('name'):s.get('displayValue',s.get('value')) for s in block.get('statistics',[])}
        def number(*names,attempt=False):
            for name in names:
                if name in stats:
                    try:return float(str(stats[name]).split('-')[-1 if attempt else 0])
                    except (ValueError,TypeError):pass
            return None
        fga=number('fieldGoalsMade-fieldGoalsAttempted',attempt=True)
        fta=number('freeThrowsMade-freeThrowsAttempted',attempt=True)
        fgm=number('fieldGoalsMade-fieldGoalsAttempted')
        fg3=number('threePointFieldGoalsMade-threePointFieldGoalsAttempted')
        fg3a=number('threePointFieldGoalsMade-threePointFieldGoalsAttempted',attempt=True)
        fga=fga if fga is not None else number('fieldGoalsAttempted')
        fta=fta if fta is not None else number('freeThrowsAttempted')
        orb=number('offensiveRebounds');tov=number('turnovers','totalTurnovers')
        if any(x is None for x in (fga,fta,orb,tov)):issues.append('incomplete_pace_'+side)
        poss=fga+.44*fta-orb+tov if all(x is not None for x in (fga,fta,orb,tov)) else None
        team_rows.append({'id':game['id'],'date':game['date'],'side':side,'team':game['teams'][side], 'points':game['scores'][side], 'fga':fga,'fgm':fgm,'fta':fta,'orb':orb,'tov':tov,'fg3m':fg3,'fg3a':fg3a,'possessions_est':round(poss,3) if poss is not None else None})
    if len(team_rows)!=2 or {r['side'] for r in team_rows}!={'home','away'}:issues.append('missing_team')
    for block in payload.get('boxscore',{}).get('players') or []:
        team=block.get('team',{}).get('abbreviation')
        for group in block.get('statistics',[]):
            labels=[str(x).upper() for x in group.get('labels',[])]
            for entry in group.get('athletes',[]):
                stats=dict(zip(labels,entry.get('stats',[])))
                ath=entry.get('athlete',{})
                if not ath.get('id'):continue
                try:
                    m=str(stats['MIN']);mins=float(m.split(':')[0])+float(m.split(':')[1])/60 if ':' in m else float(m)
                    pts=float(stats['PTS']);reb=float(stats['REB']);ast=float(stats['AST'])
                    threes=float(str(stats['3PT']).split('-')[0])
                except (KeyError,ValueError,TypeError):continue
                player_rows.append({'id':game['id'],'date':game['date'],'team':team,'player_id':str(ath['id']),'player':ath.get('displayName'),'minutes':mins,'points':pts,'rebounds':reb,'assists':ast,'threes':threes})
    if not player_rows:issues.append('no_player_rows')
    for side,values in game['linescores'].items():
        try: q=[int(float(x.get('displayValue',x.get('value')))) for x in values]
        except (ValueError,TypeError):q=[]
        if len(q)<4 or sum(q)!=game['scores'][side]:issues.append('period_mismatch_'+side);continue
        period_rows.append({'id':game['id'],'side':side,'q1':q[0],'q2':q[1],'q3':q[2],'q4':q[3],'overtime':sum(q[4:]),'total':sum(q)})
    return team_rows,player_rows,period_rows,issues

def write_csv(path,rows,columns):
    with open(path,'w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(rows)

def run(cache,out,limit):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    teams=[];players=[];periods=[];report=[]
    for game in list(games_from_cache(cache))[:limit]:
        item={'id':game['id'],'date':game['date'],'teams':game['teams'],'scores':game['scores']}
        try:
            req=urllib.request.Request(BASE+'?'+urllib.parse.urlencode({'event':game['id']}),headers={'User-Agent':'NBA-Lab-Validation/1.0'})
            with urllib.request.urlopen(req,timeout=20) as response: payload=json.load(response)
            t,p,q,issues=parse(payload,game)
            teams+=t;players+=p;periods+=q
            item.update({'http_status':200,'team_rows':len(t),'player_rows':len(p),'period_rows':len(q),'issues':issues})
        except Exception as exc:
            item.update({'http_status':None,'issues':['download_failed'],'error':str(exc)[:200]})
        report.append(item);time.sleep(.2)
    write_csv(out/'equipos_muestra.csv',teams,['id','date','side','team','points','fga','fgm','fta','orb','tov','fg3m','fg3a','possessions_est'])
    write_csv(out/'jugadores_muestra.csv',players,['id','date','team','player_id','player','minutes','points','rebounds','assists','threes'])
    write_csv(out/'periodos_muestra.csv',periods,['id','side','q1','q2','q3','q4','overtime','total'])
    (out/'reporte.json').write_text(json.dumps({'sample_only':True,'games_checked':len(report),'games':report},indent=2,ensure_ascii=False),encoding='utf8')
    print('Partidos:',len(report),'equipos:',len(teams),'jugadores:',len(players),'periodos:',len(periods))
    if not report or not any(x.get('http_status')==200 for x in report):raise SystemExit('No se pudieron verificar partidos con ESPN')

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--cache',default='nba_lab_cache');a.add_argument('--salida',default='diagnostico_recuperacion');a.add_argument('--max-partidos',type=int,default=8);v=a.parse_args();run(v.cache,v.salida,max(1,min(20,v.max_partidos)))

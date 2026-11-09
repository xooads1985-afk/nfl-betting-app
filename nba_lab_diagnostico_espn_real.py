"""Read-only ESPN coverage diagnostic; never modifies existing lab history/cache."""
import argparse, json, time
from pathlib import Path
import requests

BASE='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary'

def scoreboard_games(payload):
    out=[]
    for ev in payload.get('events',[]):
        cs=(ev.get('competitions') or [{}])[0]
        status=cs.get('status',{}).get('type',{})
        if not status.get('completed',False): continue
        sides={x.get('homeAway'):x for x in cs.get('competitors',[])}
        if set(sides)!={'home','away'}:continue
        out.append({'id':str(ev['id']),'teams':{s:sides[s].get('team',{}).get('abbreviation') for s in sides},
                    'periods':{s:len(sides[s].get('linescores',[])) for s in sides},
                    'score':{s:int(sides[s]['score']) for s in sides},
                    'scoreboard_stats':{s:{v.get('name'):v.get('displayValue') for v in sides[s].get('statistics',[])} for s in sides}})
    return out

def diagnose_summary(payload):
    bs=payload.get('boxscore') or {}
    teams=bs.get('teams') or []
    players=bs.get('players') or []
    stats_by_team=[]
    for team in teams:
        stats=team.get('statistics') or []
        names=[s.get('name') or s.get('label') for s in stats]
        stats_by_team.append({'team':team.get('team',{}).get('abbreviation'),'fields':names,
                              'has_fga':any(x in names for x in ('fieldGoalsAttempted','fieldGoalsMade-fieldGoalsAttempted')),
                              'has_fta':any(x in names for x in ('freeThrowsAttempted','freeThrowsMade-freeThrowsAttempted')),
                              'has_orb':any(x in names for x in ('offensiveRebounds','offensiveReboundsPerGame')),
                              'has_tov':any(x in names for x in ('turnovers','totalTurnovers'))})
    player_groups=[]
    for group in players:
        categories=group.get('statistics') or []
        player_groups.append({'team':group.get('team',{}).get('abbreviation'),
                              'athletes':sum(len(c.get('athletes') or []) for c in categories),
                              'columns':[c.get('labels') for c in categories]})
    return {'team_stats':stats_by_team,'player_groups':player_groups,
            'complete_pace_inputs':len(stats_by_team)==2 and all(all(t[k] for k in ('has_fga','has_fta','has_orb','has_tov')) for t in stats_by_team),
            'players_available':sum(x['athletes'] for x in player_groups)>0}

def run(cache,output,max_games=2,timeout=15):
    cache=Path(cache); output=Path(output); output.parent.mkdir(parents=True,exist_ok=True)
    report={'source':'ESPN public NBA scoreboard/summary','read_only':True,'files_checked':0,'games_found':0,'games_tested':[],'errors':[]}
    files=sorted(cache.glob('20??-??-??.json'),reverse=True)
    games=[]
    for p in files:
        try:
            data=json.loads(p.read_text(encoding='utf-8')); games.extend(scoreboard_games(data));report['files_checked']+=1
        except (OSError,ValueError,KeyError,TypeError) as exc:report['errors'].append({'file':p.name,'error':str(exc)[:160]})
        if len(games)>=max_games:break
    report['games_found']=len(games)
    for game in games[:max_games]:
        entry={'id':game['id'],'teams':game['teams'],'score':game['score'],'periods':game['periods'],
               'scoreboard_fields':{s:sorted(game['scoreboard_stats'][s]) for s in game['scoreboard_stats']}}
        try:
            r=requests.get(BASE,params={'event':game['id']},timeout=timeout,headers={'User-Agent':'NBA-Lab-Diagnostics/1.0'})
            r.raise_for_status();entry.update(diagnose_summary(r.json()));entry['http_status']=r.status_code
        except (requests.RequestException,ValueError,TypeError) as exc:
            entry['error']=str(exc)[:200];report['errors'].append({'game':game['id'],'error':str(exc)[:160]})
        report['games_tested'].append(entry);time.sleep(0.2)
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('ESPN diagnosis: files',report['files_checked'],'games',report['games_found'],'tested',len(report['games_tested']),'errors',len(report['errors']))
    print('Output:',output)
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--cache',default='nba_lab_cache');p.add_argument('--salida',default='nba_lab_auditoria_resultados/diagnostico_espn_real.json');p.add_argument('--partidos',type=int,default=2)
    a=p.parse_args();run(a.cache,a.salida,max_games=max(1,min(a.partidos,5)))

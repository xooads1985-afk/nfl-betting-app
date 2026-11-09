"""Cotejo de muestra con ESPN Summary: lectura sola, entrenamiento bloqueado si hay dudas."""
import argparse,csv,json,time,urllib.request,urllib.parse
from pathlib import Path
BASE='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary'
def read(path):
    with open(path,encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def fetch(game_id):
    url=BASE+'?'+urllib.parse.urlencode({'event':game_id})
    req=urllib.request.Request(url,headers={'User-Agent':'NBA-Lab-Identity-Audit/1.0'})
    with urllib.request.urlopen(req,timeout=25) as resp:return json.load(resp)
def verify(folder,out):
    folder=Path(folder);out=Path(out);out.mkdir(parents=True,exist_ok=True)
    players=read(folder/'jugadores_muestra.csv');teams=read(folder/'equipos_muestra.csv')
    by_game={}
    for r in players:by_game.setdefault(r['id'],[]).append(r)
    problems=[];results=[];verified=0
    for gid,rows in by_game.items():
        issue_count=len(problems)
        try:
            data=fetch(gid)
            header=(data.get('header',{}).get('competitions') or [{}])[0]
            competitors=header.get('competitors',[])
            sides={c.get('homeAway'):c.get('team',{}).get('abbreviation') for c in competitors}
            expected={r['team'] for r in teams if r['id']==gid}
            if not expected or set(sides.values())!=expected:
                problems.append({'id':gid,'player_id':'','reason':'equipos_no_coinciden_con_espn','detail':str(sides)})
            source={}
            for block in data.get('boxscore',{}).get('players') or []:
                team=block.get('team',{}).get('abbreviation')
                for group in block.get('statistics',[]):
                    labels=[str(x).upper() for x in group.get('labels',[])]
                    for item in group.get('athletes',[]):
                        athlete=item.get('athlete') or {};pid=str(athlete.get('id') or '')
                        if not pid:continue
                        stats=dict(zip(labels,item.get('stats') or []))
                        source.setdefault(pid,[]).append({'team':team,'name':athlete.get('displayName'),'stats':stats})
            for r in rows:
                pid=r['player_id'];entries=source.get(pid,[])
                if len(entries)!=1:
                    problems.append({'id':gid,'player_id':pid,'reason':'atleta_ausente_o_duplicado_en_fuente','detail':str(len(entries))});continue
                e=entries[0]
                if e['team']!=r['team'] or e['name']!=r['player']:
                    problems.append({'id':gid,'player_id':pid,'reason':'identidad_equipo_o_nombre_no_coincide','detail':f"CSV={r['team']}/{r['player']} ESPN={e['team']}/{e['name']}"});continue
                def number(v):return float(v)
                try:
                    comparisons=[('points','PTS'),('rebounds','REB'),('assists','AST')]
                    for csvkey,espnkey in comparisons:
                        if number(r[csvkey])!=number(e['stats'][espnkey]):raise ValueError(csvkey+' difiere')
                    threes=float(str(e['stats']['3PT']).split('-')[0])
                    if number(r['threes'])!=threes:raise ValueError('triples difieren')
                except (ValueError,KeyError,TypeError) as exc:
                    problems.append({'id':gid,'player_id':pid,'reason':'estadisticas_no_coinciden','detail':str(exc)});continue
                verified+=1
            results.append({'id':gid,'source_accessible':True,'csv_players':len(rows),'new_issues':len(problems)-issue_count})
        except Exception as exc:
            problems.append({'id':gid,'player_id':'','reason':'fuente_no_disponible','detail':str(exc)[:250]})
            results.append({'id':gid,'source_accessible':False,'csv_players':len(rows),'new_issues':len(problems)-issue_count})
        time.sleep(.25)
    with (out/'incidencias_identidad.csv').open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['id','player_id','reason','detail']);w.writeheader();w.writerows(problems)
    summary={'sample_players':len(players),'verified_player_rows':verified,'issues':len(problems),'games_checked':len(by_game),'games':results,'training_authorized':False,'note':'Solo auditoría de muestra; no autoriza entrenamiento masivo ni confirma afiliaciones históricas fuera de la fuente ESPN.'}
    (out/'reporte_identidad.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 0 if not problems and verified==len(players) and len(players)>0 else 1
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--muestra',default='muestra');p.add_argument('--salida',default='auditoria_identidad_espn');a=p.parse_args();raise SystemExit(verify(a.muestra,a.salida))

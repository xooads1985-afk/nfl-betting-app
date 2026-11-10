"""Evaluación prospectiva NFL sin mutar el historial de pronósticos."""
import argparse
import csv
import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

FIELDS = ['game_id','fecha_partido_utc','modelo','generado_utc','puntos_local','puntos_visitante','total','margen','version']
DETAIL = ['game_id','modelo','version','fecha_partido_utc','generado_utc','local_real','visitante_real','total_real','margen_real','error_local','error_visitante','error_total','error_margen','abs_local','abs_visitante','abs_total','abs_margen']
METRICS = ['modelo','version','partidos','mae_local','mae_visitante','mae_total','mae_margen','sesgo_local','sesgo_visitante','sesgo_total','sesgo_margen']

def utc(s):
    d=datetime.fromisoformat(str(s).replace('Z','+00:00'))
    if d.tzinfo is None: raise ValueError('Fecha sin zona horaria')
    return d.astimezone(timezone.utc)

def read(path):
    with Path(path).open(encoding='utf-8',newline='') as f:
        return list(csv.DictReader(f))

def write(path,fields,rows):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

def evaluar(historial,calendario,destino,corte_utc=None,margen_horas=24):
    if margen_horas<6: raise ValueError('Margen insuficiente')
    now=utc(corte_utc) if corte_utc else datetime.now(timezone.utc)
    pred=read(historial); games=read(calendario)
    if not pred: raise ValueError('Historial vacío')
    if set(pred[0])!=set(FIELDS): raise ValueError('Esquema de historial incompatible')
    if not games or not {'game_id','home_score','away_score','gameday','gametime'}.issubset(games[0]):
        raise ValueError('Calendario incompatible')
    ids={}
    for g in games:
        gid=g['game_id']
        if gid in ids: raise ValueError('game_id duplicado en calendario')
        ids[gid]=g
    detail=[]; count={'evaluados':0,'pendientes':0,'sin_marcador':0,'recientes':0,'sin_calendario':0}
    seen=set()
    for p in pred:
        key=(p['game_id'],p['modelo'],p['version'])
        if key in seen: raise ValueError('Predicción duplicada')
        seen.add(key)
        start=utc(p['fecha_partido_utc']); generated=utc(p['generado_utc'])
        if generated>=start: raise ValueError('Predicción posterior al kickoff')
        a,b=float(p['puntos_local']),float(p['puntos_visitante'])
        if not all(math.isfinite(v) for v in [a,b,float(p['total']),float(p['margen'])]):raise ValueError('Predicción no finita')
        if abs(a+b-float(p['total']))>1e-6 or abs(a-b-float(p['margen']))>1e-6:raise ValueError('Predicción inconsistente')
        if start>now:count['pendientes']+=1;continue
        if start+timedelta(hours=margen_horas)>now:count['recientes']+=1;continue
        g=ids.get(p['game_id'])
        if g is None:count['sin_calendario']+=1;continue
        # Verificar la correspondencia del encuentro incluso si todavía no tiene marcador.
        # NFLverse: gameday/gametime son hora del Este. Comparar fecha de juego y no reinterpretar UTC.
        from zoneinfo import ZoneInfo
        local=datetime.fromisoformat(g['gameday']+'T'+g['gametime']).replace(tzinfo=ZoneInfo('America/New_York'))
        if abs((local.astimezone(timezone.utc)-start).total_seconds())>60:raise ValueError('Kickoff inconsistente con calendario')
        # Un solo marcador no representa un resultado válido.
        home_score, away_score = g['home_score'].strip(), g['away_score'].strip()
        if bool(home_score) != bool(away_score):
            raise ValueError('Marcador parcial en calendario')
        if not home_score:
            count['sin_marcador'] += 1
            continue
        real_a,real_b=float(home_score),float(away_score)
        if not all(math.isfinite(x) and x>=0 for x in (real_a,real_b)):raise ValueError('Marcador inválido')
        errs=[a-real_a,b-real_b,(a+b)-(real_a+real_b),(a-b)-(real_a-real_b)]
        row=dict(game_id=p['game_id'],modelo=p['modelo'],version=p['version'],fecha_partido_utc=p['fecha_partido_utc'],generado_utc=p['generado_utc'],local_real=real_a,visitante_real=real_b,total_real=real_a+real_b,margen_real=real_a-real_b)
        for name,value in zip(('local','visitante','total','margen'),errs):row['error_'+name]=value;row['abs_'+name]=abs(value)
        detail.append(row);count['evaluados']+=1
    grouped={}
    for d in detail:grouped.setdefault((d['modelo'],d['version']),[]).append(d)
    metrics=[]
    for (model,version),rows in sorted(grouped.items()):
        m=dict(modelo=model,version=version,partidos=len(rows))
        for n in ('local','visitante','total','margen'):
            m['mae_'+n]=sum(r['abs_'+n] for r in rows)/len(rows)
            m['sesgo_'+n]=sum(r['error_'+n] for r in rows)/len(rows)
        metrics.append(m)
    out=Path(destino);out.mkdir(parents=True,exist_ok=True)
    write(out/'detalle_validacion.csv',DETAIL,detail)
    write(out/'metricas_modelos.csv',METRICS,metrics)
    audit=dict(count,pronosticos=len(pred),corte_utc=now.isoformat(),margen_horas=margen_horas,fuente_resultados='NFLverse, estado final inferido por marcador y margen temporal; no confirmado oficialmente')
    (out/'auditoria_validacion.json').write_text(json.dumps(audit,indent=2,ensure_ascii=False),encoding='utf-8')
    return audit

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--historial',required=True);p.add_argument('--calendario',required=True);p.add_argument('--destino',required=True);p.add_argument('--corte-utc');a=p.parse_args()
    print(json.dumps(evaluar(a.historial,a.calendario,a.destino,a.corte_utc),ensure_ascii=False))

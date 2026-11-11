"""Historial pace NBA desde detalles ESPN, sin modificar motores existentes."""
import math
import re
import pandas as pd


def _int(v):
    try:
        n=float(v)
        return int(n) if math.isfinite(n) and n >= 0 and n.is_integer() else None
    except (ValueError, TypeError):
        return None


def _attempt(v):
    m=re.fullmatch(r'\s*(\d+)\s*[-/]\s*(\d+)\s*',str(v or ''))
    if not m:return None
    made,attempt=map(int,m.groups())
    return attempt if made <= attempt else None


def _stats(team):
    entries=team.get('statistics',[])
    lookup={s.get('name'):s.get('displayValue') for s in entries if isinstance(s,dict)}
    return {'fga':_attempt(lookup.get('fieldGoalsMade-fieldGoalsAttempted')),
            'fta':_attempt(lookup.get('freeThrowsMade-freeThrowsAttempted')),
            'oreb':_int(lookup.get('offensiveRebounds')),
            'tov':_int(lookup.get('turnovers'))}


def extraer_partido(detalle, partido_id=None):
    """Devuelve una fila por partido finalizado o None si faltan datos verificables.

    Puntos: marcador final ESPN. En prórroga se normalizan puntos y posesiones
    al tiempo reglamentario para estimar ratings; no se presenta como score real.
    """
    if not isinstance(detalle,dict):return None
    comp=(detalle.get('header') or {}).get('competitions') or []
    if not comp:return None
    comp=comp[0]
    if not ((comp.get('status') or {}).get('type') or {}).get('completed'):return None
    competitors=comp.get('competitors') or []
    boxteams=(detalle.get('boxscore') or {}).get('teams') or []
    if len(competitors)!=2 or len(boxteams)!=2:return None
    byid={str(t.get('team',{}).get('id')):t for t in boxteams}
    result={'partido_id':str(partido_id or comp.get('id') or ''),'fecha_utc':comp.get('date'),'finalizado':True}
    if not result['partido_id'] or pd.isna(pd.to_datetime(result['fecha_utc'],utc=True,errors='coerce')):return None
    lengths=[]
    for c in competitors:
        side=c.get('homeAway')
        if side not in ('home','away'):return None
        info=c.get('team') or {}
        t=byid.get(str(info.get('id')))
        if t is None:return None
        vals=_stats(t)
        if any(v is None for v in vals.values()):return None
        score=_int(c.get('score'))
        if score is None:return None
        lines=c.get('linescores') or []
        if len(lines)<4:return None
        periods=[_int(z.get('displayValue')) for z in lines]
        if any(p is None for p in periods):return None
        if sum(periods)!=score:return None
        lengths.append(len(periods))
        possessions=vals['fga']+0.44*vals['fta']-vals['oreb']+vals['tov']
        if not 50<=possessions<=180:return None
        tag='local' if side=='home' else 'visitante'
        result.update({tag:info.get('displayName'),'puntos_'+tag:score,
                       'posesiones_'+tag:round(possessions,3),
                       'equipo_id_'+tag:str(info.get('id'))})
    if lengths[0]!=lengths[1]:return None
    result['prorroga']=lengths[0]>4
    result['minutos_partido']=48+5*(lengths[0]-4)
    result['pace_48']=round(((result['posesiones_local']+result['posesiones_visitante'])/2)*48/result['minutos_partido'],3)
    result['eficiencia_local_100']=round(100*result['puntos_local']/result['posesiones_local'],3)
    result['eficiencia_visitante_100']=round(100*result['puntos_visitante']/result['posesiones_visitante'],3)
    return result


def construir_historial(partidos,cargar_detalle,max_partidos=20):
    """Consulta por lotes hasta 50 juegos finalizados, sin escribir en Supabase."""
    if not callable(cargar_detalle):raise TypeError('cargar_detalle no es callable')
    if not 1<=max_partidos<=50:raise ValueError('max_partidos fuera de rango')
    df=pd.DataFrame(partidos)
    if not {'id','finalizado','fecha_utc'}.issubset(df.columns):raise ValueError('Historial sin columnas necesarias')
    df=df.loc[df['finalizado'].eq(True)].drop_duplicates('id').sort_values('fecha_utc').tail(max_partidos)
    good=[];errors=[]
    for r in df.to_dict('records'):
        pid=str(r['id'])
        try:
            row=extraer_partido(cargar_detalle(pid),pid)
            if row:good.append(row)
            else:errors.append({'partido_id':pid,'motivo':'detalle incompleto o inconsistente'})
        except Exception as exc:
            errors.append({'partido_id':pid,'motivo':type(exc).__name__})
    return pd.DataFrame(good),pd.DataFrame(errors)

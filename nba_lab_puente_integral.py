"""Puente aislado ESPN -> Pace -> comparación emparejada; sin modificar módulos estables."""
import argparse, json
from pathlib import Path
import pandas as pd
import numpy as np
from nba_lab_pace_integral import evaluar

NAMES={'ATL':'Atlanta Hawks','BOS':'Boston Celtics','BKN':'Brooklyn Nets','CHA':'Charlotte Hornets','CHI':'Chicago Bulls','CLE':'Cleveland Cavaliers','DAL':'Dallas Mavericks','DEN':'Denver Nuggets','DET':'Detroit Pistons','GS':'Golden State Warriors','GSW':'Golden State Warriors','HOU':'Houston Rockets','IND':'Indiana Pacers','LAC':'LA Clippers','LAL':'Los Angeles Lakers','MEM':'Memphis Grizzlies','MIA':'Miami Heat','MIL':'Milwaukee Bucks','MIN':'Minnesota Timberwolves','NO':'New Orleans Pelicans','NOP':'New Orleans Pelicans','NY':'New York Knicks','NYK':'New York Knicks','OKC':'Oklahoma City Thunder','ORL':'Orlando Magic','PHI':'Philadelphia 76ers','PHX':'Phoenix Suns','POR':'Portland Trail Blazers','SAC':'Sacramento Kings','SA':'San Antonio Spurs','SAS':'San Antonio Spurs','TOR':'Toronto Raptors','UTAH':'Utah Jazz','UTA':'Utah Jazz','WAS':'Washington Wizards','WSH':'Washington Wizards'}

def construir(equipos, destino):
    d=pd.read_csv(equipos,dtype={'id':str})
    needed={'id','date','side','team','points','fga','fta','orb','tov'}
    if not needed.issubset(d.columns):raise ValueError('Columnas faltantes: '+str(needed-set(d.columns)))
    if d.duplicated(['id','side']).any():raise ValueError('Partido/lado duplicado')
    if not d.side.isin(['home','away']).all():raise ValueError('Lado inválido')
    if not d.team.isin(NAMES).all():raise ValueError('Abreviaturas desconocidas: '+str(set(d.team)-set(NAMES)))
    for c in ['points','fga','fta','orb','tov']:
        d[c]=pd.to_numeric(d[c],errors='coerce')
    if d[['points','fga','fta','orb','tov']].isna().any().any():raise ValueError('Datos estadísticos incompletos')
    if (d[['points','fga','fta','orb','tov']]<0).any().any():raise ValueError('Estadísticas negativas')
    if not d.groupby('id').side.agg(lambda s:set(s)=={'home','away'} and len(s)==2).all():raise ValueError('Partidos incompletos')
    d['fecha']=pd.to_datetime(d.date,utc=True,errors='coerce')
    if d.fecha.isna().any() or d.groupby('id').fecha.nunique().gt(1).any():raise ValueError('Fechas inconsistentes')
    h=d[d.side=='home'].set_index('id'); a=d[d.side=='away'].set_index('id')
    out=pd.DataFrame({'id':h.index,'fecha_utc':h.fecha,'local':h.team.map(NAMES),'visitante':a.team.map(NAMES),'puntos_local':h.points,'puntos_visitante':a.points})
    for c in ['fga','fta','orb','tov']:
        out[c+'_local']=h[c];out[c+'_visitante']=a[c]
    out=out.reset_index(drop=True).sort_values(['fecha_utc','id']).reset_index(drop=True)
    destino=Path(destino);destino.parent.mkdir(parents=True,exist_ok=True);out.to_csv(destino,index=False)
    return out

def comparar(pace_csv, original_csv, salida):
    pace=pd.read_csv(pace_csv,dtype={'partido':str})
    old=pd.read_csv(original_csv,dtype={'partido':str})
    modelos=[c for c in old.columns if c not in ('fecha','partido','equipo','real','Entrenamiento','NB desviación','Posesiones + eficiencia') and pd.api.types.is_numeric_dtype(old[c])]
    old=old[['partido','equipo','real']+modelos].copy()
    if old.duplicated(['partido','equipo']).any() or pace.duplicated(['partido','equipo']).any():raise ValueError('Duplicados en predicciones')
    matched=pace.merge(old,on=['partido','equipo'],suffixes=('_pace','_original'),how='inner',validate='one_to_one')
    if not matched.empty and not np.allclose(matched.real_pace,matched.real_original,atol=0.01):raise ValueError('Resultados reales no coinciden')
    filas=[]
    # Muestra común para todos los modelos: comparación justa.
    matched=matched.dropna(subset=['real_pace','Pace + eficiencia']+modelos)
    for modelo in ['Pace + eficiencia']+modelos:
        if matched.empty:continue
        s=matched[['real_pace',modelo]].dropna()
        if s.empty:continue
        e=s[modelo]-s.real_pace
        filas.append({'modelo':modelo,'muestra':len(s),'MAE':float(e.abs().mean()),'RMSE':float(np.sqrt((e**2).mean())),'sesgo':float(e.mean())})
    dest=Path(salida);dest.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(filas,columns=['modelo','muestra','MAE','RMSE','sesgo']).to_csv(dest/'comparacion_emparejada.csv',index=False)
    reporte={'partidos_boxscores':None,'predicciones_pace':len(pace),'registros_comparables':len(matched),'modelos_originales':modelos,'comparacion_valida':len(matched)>0,'advertencia':None if len(matched)>0 else 'Sin coincidencias entre fechas/partidos del historial Pace y las predicciones originales; no se puede comparar precisión.'}
    (dest/'reporte_integracion.json').write_text(json.dumps(reporte,indent=2,ensure_ascii=False),encoding='utf8')
    return reporte

def main():
    p=argparse.ArgumentParser();p.add_argument('--equipos',required=True);p.add_argument('--predicciones',required=True);p.add_argument('--salida',default='nba_lab_integracion_resultados');p.add_argument('--minimo',type=int,default=5);p.add_argument('--ventana',type=int,default=10);args=p.parse_args()
    out=Path(args.salida);out.mkdir(parents=True,exist_ok=True)
    games=construir(args.equipos,out/'boxscores_para_pace.csv')
    evaluar(out/'boxscores_para_pace.csv',out,args.minimo,args.ventana)
    r=comparar(out/'pace_predicciones.csv',args.predicciones,out);r['partidos_boxscores']=len(games)
    (out/'reporte_integracion.json').write_text(json.dumps(r,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps(r,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

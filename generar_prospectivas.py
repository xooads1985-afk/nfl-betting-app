"""Genera el CSV requerido por el flujo experimental de persistencia.
No ejecuta si no hay kickoff UTC y estado FINAL verificable.
"""
import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from proyeccion_prospectiva import proyectar
from puente_prospectivo import convertir_filas

CAMPOS=['game_id','kickoff_utc','generated_utc','model','version','home','away','total','margin','train_n','last_train_kickoff_utc']

def generar(calendario, salida, ahora_utc, version='nfl-lab-prospectivo-v1', minimo=150):
    now=pd.Timestamp(ahora_utc)
    if now.tzinfo is None:raise ValueError('Hora de generación sin zona horaria')
    now=now.tz_convert('UTC')
    predictions=proyectar(calendario, now, minimo_entrenamiento=minimo)
    # Un calendario sin partidos futuros es normal fuera de temporada.
    # Se escribe CSV con encabezado, sin inventar predicciones.
    # El motor exige cortes diarios. Para la auditoría usar la última fecha histórica
    # anterior al día del encuentro, no el partido más reciente sin comprobar.
    hist=calendario.copy()
    hist['kickoff_utc']=pd.to_datetime(hist.kickoff_utc,utc=True,errors='raise')
    final=hist.game_status.astype(str).str.upper().str.strip().isin({'FINAL','F','COMPLETED','COMPLETE'})
    scores=pd.to_numeric(hist.home_score,errors='coerce').notna() & pd.to_numeric(hist.away_score,errors='coerce').notna()
    rows=[]
    for p in predictions.itertuples(index=False):
        kickoff=pd.Timestamp(p.kickoff_utc)
        cutoff=kickoff.floor('D')
        eligible=hist[final & scores & (hist.kickoff_utc < cutoff) & (hist.kickoff_utc < now)]
        if len(eligible)<minimo:raise ValueError('Entrenamiento insuficiente')
        # El modelo usa train con fecha UTC < día objetivo; verificar conteo.
        if len(eligible)!=int(p.entrenamiento_n):raise ValueError('Conteo de entrenamiento no coincide')
        last=eligible.kickoff_utc.max()
        rows.append(dict(game_id=p.game_id,kickoff_utc=kickoff.isoformat(),
            generated_utc=now.isoformat(),model=p.modelo,version=version,
            home=p.puntos_local,away=p.puntos_visitante,total=p.total,margin=p.margen,
            train_n=p.entrenamiento_n,last_train_kickoff_utc=last.isoformat()))
    convertir_filas(rows)  # Validación de todo el lote antes de escribir.
    output=Path(salida);output.parent.mkdir(parents=True,exist_ok=True)
    from tempfile import NamedTemporaryFile
    import os
    with NamedTemporaryFile('w',encoding='utf-8',newline='',dir=output.parent,delete=False) as tmp:
        temp=Path(tmp.name)
        try:
            w=csv.DictWriter(tmp,fieldnames=CAMPOS);w.writeheader();w.writerows(rows)
        except BaseException:
            temp.unlink(missing_ok=True);raise
    os.replace(temp,output)
    return len(rows)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--calendario',required=True)
    parser.add_argument('--salida',default='resultados_nfl/prospectivas.csv')
    parser.add_argument('--minimo',type=int,default=150)
    a=parser.parse_args()
    n=generar(pd.read_csv(a.calendario),a.salida,datetime.now(timezone.utc),minimo=a.minimo)
    print('Predicciones prospectivas validadas:',n)

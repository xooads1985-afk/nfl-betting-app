"""Auditoría reproducible de resultados del laboratorio, sin escribir en la aplicación."""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd


def auditar(predicciones):
    df=predicciones.copy()
    requeridas={'game_id','season','week','date','target','model','actual','predicted','error','train_n','latest_train_date'}
    faltan=requeridas-set(df.columns)
    if faltan:raise ValueError(f'Columnas ausentes: {sorted(faltan)}')
    if df.empty:raise ValueError('Sin predicciones para auditar')
    if df.duplicated(['game_id','target','model']).any():raise ValueError('Predicciones duplicadas')
    if not np.isfinite(df[['actual','predicted','error']].to_numpy(float)).all():raise ValueError('Valores no finitos')
    if not np.allclose(df.predicted-df.actual,df.error,atol=1e-7):raise ValueError('Errores inconsistentes')
    if not (pd.to_datetime(df.latest_train_date)<pd.to_datetime(df.date)).all():raise ValueError('Fuga temporal detectada')
    wide=df.pivot(index=['game_id','model'],columns='target',values='predicted')
    if {'home','away','total','margin'}.issubset(wide.columns):
        if not np.allclose(wide.home+wide.away,wide.total,atol=1e-6):raise ValueError('Total no cuadra')
        if not np.allclose(wide.home-wide.away,wide.margin,atol=1e-6):raise ValueError('Margen no cuadra')
    return {'predicciones':len(df),'partidos':df.game_id.nunique(),'modelos':df.model.nunique(),
            'objetivos':df.target.nunique(),'temporadas':sorted(df.season.unique().astype(int).tolist()),
            'fuga_temporal':False,'consistencia_puntos':True}


def comparacion_pareada(predicciones,objetivo='total',referencia='hybrid'):
    df=predicciones[predicciones.target.eq(objetivo)].copy()
    wide=df.pivot(index='game_id',columns='model',values='error')
    if referencia not in wide:raise ValueError('Modelo de referencia no disponible')
    rows=[]
    for modelo in wide:
        par=wide[[referencia,modelo]].dropna() if modelo!=referencia else wide[[referencia]].dropna()
        if len(par)==0:continue
        diferencia=par[modelo].abs()-par[referencia].abs()
        rows.append({'target':objetivo,'model':modelo,'reference':referencia,'games':len(par),
                     'MAE':float(par[modelo].abs().mean()),'MAE_reference':float(par[referencia].abs().mean()),
                     'delta_MAE':float(diferencia.mean()),'pct_better':float((diferencia<0).mean()*100)})
    return pd.DataFrame(rows).sort_values('delta_MAE')


def main():
    p=argparse.ArgumentParser();p.add_argument('--csv',required=True);p.add_argument('--output',default='auditoria_nfl')
    args=p.parse_args();df=pd.read_csv(args.csv);dest=Path(args.output);dest.mkdir(parents=True,exist_ok=True)
    info=auditar(df)
    for objetivo in ['total','margin','home','away']:
        comparacion_pareada(df,objetivo).to_csv(dest/f'comparacion_{objetivo}.csv',index=False)
    (dest/'auditoria.txt').write_text('\n'.join(f'{k}: {v}' for k,v in info.items()),encoding='utf-8')
    print(info)
if __name__=='__main__':main()

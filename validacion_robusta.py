"""Auditoría adicional: comparaciones por temporada, intervalos bootstrap por partido.
No modifica el motor original. Los intervalos son descriptivos, no garantizan mejora futura.
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
from auditoria import auditar


def evaluar(predicciones, referencia='hybrid', seed=2026, bootstrap=2000):
    auditar(predicciones)
    if bootstrap < 100: raise ValueError('Se requieren >=100 réplicas')
    rng=np.random.default_rng(seed)
    rows=[]
    for (target,season),subset in predicciones.groupby(['target','season']):
        matrix=subset.pivot(index='game_id',columns='model',values='error')
        if referencia not in matrix: continue
        for model in matrix.columns:
            if model==referencia: continue
            pair=matrix[[referencia,model]].dropna()
            if len(pair)<5:continue
            diff=pair[model].abs().to_numpy()-pair[referencia].abs().to_numpy()
            sample=rng.integers(0,len(diff),size=(bootstrap,len(diff)))
            boot=diff[sample].mean(axis=1)
            rows.append(dict(target=target,season=int(season),model=model,reference=referencia,
                games=len(diff),delta_mae=float(diff.mean()),ci95_low=float(np.quantile(boot,.025)),
                ci95_high=float(np.quantile(boot,.975)),pct_games_better=float((diff<0).mean()*100),
                evidence_of_improvement=bool(np.quantile(boot,.975)<0)))
    return pd.DataFrame(rows)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--csv',required=True)
    parser.add_argument('--output',default='nfl_lab_resultados')
    args=parser.parse_args()
    df=pd.read_csv(args.csv)
    report=evaluar(df)
    path=Path(args.output);path.mkdir(parents=True,exist_ok=True)
    report.to_csv(path/'comparacion_por_temporada.csv',index=False)
    print(report.to_string(index=False) if not report.empty else 'Datos insuficientes')

if __name__=='__main__':main()

"""Pipeline manual de datos NFLverse + auditoría + backtest + comparación pareada."""
import argparse
import json
from pathlib import Path
import pandas as pd
from descargar_nflverse import descargar
from ejecutar_validacion import ejecutar
from comparacion_pareada_20 import comparar
from comparacion_motor_real import comparar_motor

def pipeline(seasons,output,first_season=2024,min_train=150,simulations=10000,
             min_games_test=50):
    output=Path(output)
    datos=output/"datos"
    calendario=descargar(seasons,datos,with_pbp=True,require_all=True)
    recibidas=set(int(x) for x in calendario.season.unique())
    faltantes=set(seasons)-recibidas
    if faltantes:
        raise ValueError("Descarga incompleta; faltan temporadas: "+str(sorted(faltantes)))
    pbp=pd.read_csv(datos/"pbp.csv")
    meta=ejecutar(calendario,pbp,output/"validacion",first_season,
                 min_train,simulations,min_games_test)
    pred,met=comparar(calendario,pbp,first_season,min_train,simulations)
    if pred.game_id.nunique()<min_games_test:
        raise ValueError("Muestra pareada insuficiente")
    (output/"comparacion").mkdir(parents=True,exist_ok=True)
    pred.to_csv(output/"comparacion"/"predicciones_pareadas.csv",index=False)
    met.to_csv(output/"comparacion"/"metricas_pareadas.csv",index=False)
    pred_original,met_original=comparar_motor(calendario,pbp,min_train,simulations)
    (output/"motor_original").mkdir(parents=True,exist_ok=True)
    pred_original.to_csv(output/"motor_original"/"predicciones.csv",index=False)
    met_original.to_csv(output/"motor_original"/"metricas.csv",index=False)
    meta["comparacion"]="Incluye réplica independiente del motor original; validar paridad en datos reales"
    (output/"estado.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    return meta

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seasons",nargs="+",type=int,default=[2022,2023,2024,2025])
    p.add_argument("--output",default="resultados_nfl")
    p.add_argument("--first-season",type=int,default=2024)
    p.add_argument("--min-train",type=int,default=150)
    p.add_argument("--min-games-test",type=int,default=50)
    p.add_argument("--simulations",type=int,default=10000)
    a=p.parse_args()
    if a.first_season not in a.seasons:
        p.error("first-season debe estar en seasons")
    if len(set(a.seasons))!=len(a.seasons):
        p.error("Temporadas duplicadas")
    print(json.dumps(pipeline(a.seasons,a.output,a.first_season,
                              a.min_train,a.simulations,a.min_games_test),
                     ensure_ascii=False,indent=2))
if __name__=="__main__":main()

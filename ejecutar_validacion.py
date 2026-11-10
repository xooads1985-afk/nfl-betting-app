"""Ejecución integral fail-closed; usa únicamente archivos CSV locales.
No descarga datos, no modifica módulos estables y no declara ganadores.
"""
import argparse
import json
from pathlib import Path
import pandas as pd
from validar_prevuelo import validar
from nfl_lab_precision import backtest, summarize


def ejecutar(calendario, pbp, salida, first_season=2024, min_train=150, simulations=10000,
             min_games_test=50, cobertura_minima=90):
    salida=Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    reporte=validar(calendario,pbp,cobertura_minima=cobertura_minima)
    (salida/'auditoria.json').write_text(json.dumps(reporte,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    if not reporte['preflight']['aprobado']:
        raise ValueError('Validación bloqueada: '+ '; '.join(reporte['preflight']['motivos']))
    resultados=backtest(calendario,first_season=first_season,min_train=min_train,simulations=simulations,pbp=pbp)
    if resultados.empty:
        raise ValueError('Sin predicciones evaluables; revisar temporadas y tamaño de entrenamiento')
    # Cada fila debe ser verdaderamente anterior al juego objetivo.
    fechas=pd.to_datetime(resultados['date'],errors='raise')
    fechas_train=pd.to_datetime(resultados['latest_train_date'],errors='raise')
    if not (fechas_train<fechas).all():
        raise ValueError('Fuga temporal detectada: entrenamiento posterior o simultáneo al partido')
    # El mínimo es por partidos únicos, no por filas (4 objetivos x 7 modelos).
    partidos=resultados.game_id.nunique()
    if partidos<min_games_test:
        raise ValueError(f'Muestra de evaluación insuficiente: {partidos} < {min_games_test}')
    resumen=summarize(resultados)
    resultados.to_csv(salida/'predicciones.csv',index=False)
    resumen.to_csv(salida/'metricas.csv',index=False)
    meta={'estado':'evaluacion_historica','partidos_evaluados':int(partidos),
          'temporadas_evaluadas':sorted(int(x) for x in resultados.season.unique()),
          'primer_temporada':first_season,'simulaciones':simulations,
          'nota':'Los resultados no prueban precisión prospectiva ni comparan aún el motor original completo.'}
    (salida/'resumen_ejecucion.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
    return meta


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--calendar',required=True);p.add_argument('--pbp',required=True)
    p.add_argument('--output',default='resultados_nfl_v10')
    p.add_argument('--first-season',type=int,default=2024)
    p.add_argument('--min-train',type=int,default=150)
    p.add_argument('--min-games-test',type=int,default=50)
    p.add_argument('--simulations',type=int,default=10000)
    a=p.parse_args()
    if not 100<=a.simulations<=100000: p.error('simulations debe estar entre 100 y 100000')
    meta=ejecutar(pd.read_csv(a.calendar),pd.read_csv(a.pbp),a.output,
                  a.first_season,a.min_train,a.simulations,a.min_games_test)
    print(json.dumps(meta,ensure_ascii=False,indent=2))

if __name__=='__main__':main()

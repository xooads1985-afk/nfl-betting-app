"""Convierte calendario NFLverse local a entrada del laboratorio, sin descargar ni escribir al repositorio."""
import argparse
from pathlib import Path
import pandas as pd
from nfl_lab_precision import REQUIRED,prepare

def convertir(df):
    data=df.copy()
    if 'game_id' not in data and 'id' in data:data=data.rename(columns={'id':'game_id'})
    if 'gameday' not in data and 'game_date' in data:data=data.rename(columns={'game_date':'gameday'})
    if 'game_id' not in data and all(x in data for x in ['season','week','home_team','away_team']):
        data['game_id']=data[['season','week','home_team','away_team']].astype(str).agg('_'.join,axis=1)
    if 'game_type' in data:data=data[data.game_type.eq('REG')]
    if 'season_type' in data:data=data[data.season_type.eq('REG')]
    if 'result' in data and 'home_score' not in data:
        raise ValueError('Se requieren marcadores de ambos equipos; result no es suficiente')
    if 'home_score' in data and 'away_score' in data:
        data=data[data.home_score.notna()&data.away_score.notna()]
    return prepare(data)[REQUIRED]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True);p.add_argument('--output',default='nflverse_calendario_limpio.csv')
    a=p.parse_args();df=convertir(pd.read_csv(a.input));Path(a.output).parent.mkdir(parents=True,exist_ok=True)
    df.to_csv(a.output,index=False);print('Partidos completos:',len(df),'Guardado:',a.output)
if __name__=='__main__':main()

"""Descarga cruda de NFLverse para auditoría, sin tocar archivos estables."""
import argparse
from pathlib import Path
import pandas as pd

def descargar(seasons, destino, loader=None):
    if loader is None:
        import nflreadpy
        loader = nflreadpy.load_schedules
    if not seasons or len(set(seasons)) != len(seasons):
        raise ValueError('Temporadas vacías o repetidas')
    partes=[]
    for season in seasons:
        raw=loader([int(season)])
        df=raw.to_pandas() if hasattr(raw,'to_pandas') else pd.DataFrame(raw)
        if df.empty: raise ValueError(f'Temporada {season} vacía')
        if 'season' not in df or not df.season.eq(int(season)).all():
            raise ValueError(f'Temporada {season} inconsistente')
        partes.append(df)
    all_games=pd.concat(partes,ignore_index=True)
    if 'game_id' not in all_games or all_games.game_id.isna().any() or all_games.game_id.duplicated().any():
        raise ValueError('game_id ausente o duplicado')
    path=Path(destino)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(path.suffix+'.tmp')
    all_games.to_csv(temp,index=False)
    temp.replace(path)
    return all_games

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--seasons',nargs='+',type=int,required=True)
    p.add_argument('--output',required=True)
    a=p.parse_args()
    print('Filas descargadas:',len(descargar(a.seasons,a.output)))

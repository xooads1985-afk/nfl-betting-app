"""Carga temporadas NFLverse para el laboratorio, sin tocar módulos estables.

Ejemplo: python descargar_nflverse.py --seasons 2022 2023 2024 2025 --with-pbp
Requiere nflreadpy y acceso a internet. No imprime ni guarda credenciales.
"""
import argparse
from pathlib import Path
import pandas as pd
from convertir_nflverse import convertir

PBP_COLS=['game_id','posteam','defteam','epa','success','play_type']

def _pandas(data):
    if isinstance(data,pd.DataFrame):return data
    if hasattr(data,'to_pandas'):return data.to_pandas()
    return pd.DataFrame(data)

def validar_pbp(pbp,valid_ids):
    missing=set(PBP_COLS)-set(pbp.columns)
    if missing:raise ValueError('PBP incompleto: '+', '.join(sorted(missing)))
    x=pbp[PBP_COLS].copy()
    x=x[x.game_id.astype(str).isin(set(map(str,valid_ids))) & x.play_type.isin(['pass','run'])]
    x=x.dropna(subset=['game_id','posteam','defteam','epa','success'])
    return x

def cobertura(schedule,pbp):
    ids=set(schedule.game_id.astype(str))
    covered=set(pbp.game_id.astype(str))
    return {'juegos_calendario':len(ids),'juegos_pbp':len(ids&covered),
            'cobertura_pct':round(100*len(ids&covered)/len(ids),2) if ids else 0,
            'jugadas_validas':len(pbp)}

def descargar(seasons,output,with_pbp=False,require_all=False):
    import nflreadpy as nfl
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    schedules=[];plays=[];issues=[]
    for year in seasons:
        try:
            raw=_pandas(nfl.load_schedules([year]))
            clean=convertir(raw)
            # Transacción por temporada: calendario y PBP deben completarse juntos.
            # Evita incluir temporadas sin estadísticas avanzadas en el CSV final.
            if with_pbp:
                p = _pandas(nfl.load_pbp(year))
                valid = validar_pbp(p, clean.game_id)
                if valid.empty:
                    raise ValueError('Sin jugadas PBP válidas para la temporada')
                plays.append(valid)
            schedules.append(clean)
        except Exception as exc:
            issues.append(f'{year}: {type(exc).__name__}: {exc}')
    if not schedules:raise RuntimeError('No se pudo cargar ninguna temporada completa. '+'; '.join(issues))
    if require_all and issues:
        raise RuntimeError('Descarga incompleta; no se escribirán CSV parciales. '+'; '.join(issues))
    calendar=pd.concat(schedules,ignore_index=True).drop_duplicates('game_id')
    calendar.to_csv(output/'calendario.csv',index=False)
    if with_pbp:
        pbp=pd.concat(plays,ignore_index=True) if plays else pd.DataFrame(columns=PBP_COLS)
        pbp.to_csv(output/'pbp.csv',index=False)
        print('Cobertura:',cobertura(calendar,pbp))
    (output/'incidencias.txt').write_text('\n'.join(issues) if issues else 'Sin incidencias',encoding='utf-8')
    print('Temporadas:',sorted(calendar.season.unique().tolist()),'Partidos:',len(calendar))
    if issues:print('ADVERTENCIA: revisar incidencias.txt; temporadas fallidas EXCLUIDAS')
    return calendar

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--seasons',nargs='+',type=int,default=[2022,2023,2024,2025,2026])
    p.add_argument('--output',default='datos_nflverse')
    p.add_argument('--with-pbp',action='store_true')
    a=p.parse_args()
    descargar(a.seasons,a.output,a.with_pbp)
if __name__=='__main__':main()

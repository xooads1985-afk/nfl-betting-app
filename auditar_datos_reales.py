"""Auditoría previa a modelar NFLverse; nunca modifica datos de entrada."""
import argparse
import json
from pathlib import Path
import pandas as pd

REQUIRED = {'game_id','season','gameday','home_team','away_team','home_score','away_score'}

def auditar(calendario, pbp=None):
    missing=sorted(REQUIRED-set(calendario.columns))
    if missing: raise ValueError('Calendario sin columnas: '+', '.join(missing))
    df=calendario.copy()
    fechas=pd.to_datetime(df.gameday,errors='coerce',utc=True)
    hs=pd.to_numeric(df.home_score,errors='coerce')
    aw=pd.to_numeric(df.away_score,errors='coerce')
    completos=hs.notna() & aw.notna()
    problems={
      'ids_duplicados':int(df.game_id.duplicated().sum()),
      'fechas_invalidas':int(fechas.isna().sum()),
      'equipos_iguales':int((df.home_team==df.away_team).sum()),
      'marcadores_incompletos':int((~completos).sum()),
      'marcadores_negativos':int(((hs<0)|(aw<0)).sum()),
      'equipos_faltantes':int((df.home_team.isna()|df.away_team.isna()).sum()),
    }
    report={'partidos':int(len(df)),'temporadas':sorted(str(v) for v in df.season.dropna().unique()),
            'partidos_finalizados_con_marcador':int(completos.sum()),'incidencias':problems,
            'apto_para_validacion':not any(problems[k] for k in ('ids_duplicados','fechas_invalidas','equipos_iguales','marcadores_negativos','equipos_faltantes'))}
    if pbp is not None:
        need={'game_id','posteam','defteam','epa','success','play_type'}
        if not need.issubset(pbp.columns): raise ValueError('PBP sin columnas: '+', '.join(sorted(need-set(pbp.columns))))
        played=pbp[pbp.play_type.isin(['pass','run'])]
        ids=set(df.loc[completos,'game_id'].astype(str))
        valid=played[played.game_id.astype(str).isin(ids)]
        covered=set(valid.game_id.astype(str))
        report['pbp']={'jugadas_pase_carrera':int(len(played)), 'partidos_finalizados_con_pbp':len(ids&covered),
                       'cobertura_pct':round(100*len(ids&covered)/len(ids),2) if ids else 0,
                       'epa_faltante':int(pd.to_numeric(valid.epa,errors='coerce').isna().sum()),
                       'success_faltante':int(pd.to_numeric(valid.success,errors='coerce').isna().sum())}
    return report

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--calendar',required=True);ap.add_argument('--pbp');ap.add_argument('--output',default='auditoria_nflverse.json');args=ap.parse_args()
    cal=pd.read_csv(args.calendar);pbp=pd.read_csv(args.pbp) if args.pbp else None
    report=auditar(cal,pbp)
    Path(args.output).write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=False))
    if not report['apto_para_validacion']:raise SystemExit(2)
if __name__=='__main__':main()

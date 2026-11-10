"""Clasifica calendario nflverse sin inventar estados finales ni usar resultados futuros."""
import argparse
import json
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

REQUIRED={'game_id','season','week','gameday','gametime','home_team','away_team','home_score','away_score'}
FINAL={'final','finished','completed','complete'}

def preparar(df, fecha_corte_utc):
    faltan=sorted(REQUIRED-set(df.columns))
    if faltan: raise ValueError(f'Faltan columnas: {faltan}')
    if df.game_id.isna().any() or df.game_id.astype(str).str.strip().eq('').any() or df.game_id.duplicated().any():
        raise ValueError('Identificadores vacíos o duplicados')
    corte=pd.Timestamp(fecha_corte_utc)
    if corte.tzinfo is None: raise ValueError('La fecha de corte debe incluir zona horaria')
    corte=corte.tz_convert('UTC')
    base=df.copy()
    naive=pd.to_datetime(base.gameday.astype(str)+' '+base.gametime.astype(str),errors='coerce')
    if naive.isna().any(): raise ValueError('Fecha u hora de inicio incompleta')
    try: inicio=naive.dt.tz_localize(ZoneInfo('America/New_York'),ambiguous='NaT',nonexistent='NaT').dt.tz_convert('UTC')
    except Exception as exc: raise ValueError('Hora del Este inválida') from exc
    if inicio.isna().any(): raise ValueError('Hora del Este ambigua o inexistente')
    base['kickoff_utc']=inicio
    home=pd.to_numeric(base.home_score,errors='coerce')
    away=pd.to_numeric(base.away_score,errors='coerce')
    if (home.notna() ^ away.notna()).any(): raise ValueError('Marcador parcial')
    if ((home<0)|(away<0)).any(): raise ValueError('Marcador negativo')
    scored=home.notna() & away.notna()
    status_col=next((c for c in ('game_status','status','game_status_detail') if c in base.columns),None)
    confirmed=base[status_col].astype('string').str.lower().str.strip().isin(FINAL) if status_col else pd.Series(False,index=base.index)
    if (confirmed & ~scored).any(): raise ValueError('Estado final sin marcador')
    if ((inicio>corte) & scored).any(): raise ValueError('Marcador de partido posterior a fecha de corte: fuga de información')
    base['resultado_confirmado']=confirmed & scored & (inicio<=corte)
    base['resultado_no_confirmado']=scored & ~confirmed & (inicio<=corte)
    base['pendiente']=~scored & (inicio>corte)
    base['sin_resultado_vencido']=~scored & (inicio<=corte)
    reporte={'total':len(base),'confirmados':int(base.resultado_confirmado.sum()),'historicos_sin_confirmacion':int(base.resultado_no_confirmado.sum()),'futuros_pendientes':int(base.pendiente.sum()),'vencidos_sin_resultado':int(base.sin_resultado_vencido.sum()),'corte_utc':corte.isoformat()}
    return base,reporte

def ejecutar(origen,destino,corte):
    origen=Path(origen);destino=Path(destino)
    df=pd.read_parquet(origen) if origen.suffix.lower()=='.parquet' else pd.read_csv(origen)
    result,report=preparar(df,corte)
    destino.mkdir(parents=True,exist_ok=True)
    # No se publican marcadores no confirmados como resultados verificados.
    result.loc[result.resultado_confirmado].to_csv(destino/'finales_confirmados.csv',index=False)
    result.loc[result.pendiente].to_csv(destino/'partidos_futuros.csv',index=False)
    result.loc[result.resultado_no_confirmado].to_csv(destino/'marcadores_sin_confirmar.csv',index=False)
    (destino/'auditoria.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--origen',required=True);p.add_argument('--destino',required=True);p.add_argument('--corte-utc',required=True)
    a=p.parse_args();print(json.dumps(ejecutar(a.origen,a.destino,a.corte_utc),ensure_ascii=False))

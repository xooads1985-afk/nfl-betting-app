"""Adaptador experimental NFLverse -> motor prospectivo.

FINAL inferido es una etiqueta operativa, NO confirmación oficial. Se admite
únicamente si kickoff + margen <= corte y existen ambos marcadores. La fecha
real de publicación de marcadores no es verificable en un CSV retrospectivo.
"""
import pandas as pd
from preparar_calendario import preparar

COLS=['game_id','season','week','gameday','gametime','home_team','away_team','home_score','away_score']

def adaptar(raw, corte_utc, margen_horas=24):
    if margen_horas < 6:
        raise ValueError('Margen de seguridad menor de 6 horas')
    data=raw.copy()
    if not set(COLS).issubset(data):
        raise ValueError('Faltan campos del calendario NFLverse')
    corte=pd.Timestamp(corte_utc)
    if corte.tzinfo is None:
        raise ValueError('Corte sin zona horaria')
    corte=corte.tz_convert('UTC')
    # No aceptar marcadores posteriores al corte; un archivo retrospectivo
    # con resultados futuros no permite reconstruir snapshots pasados.
    base,reporte=preparar(data,corte)
    completos=base.home_score.notna() & base.away_score.notna()
    seguros=completos & (base.kickoff_utc + pd.Timedelta(hours=margen_horas) <= corte)
    sin_confirmar=completos & ~seguros
    if sin_confirmar.any():
        raise ValueError('Marcadores demasiado recientes para margen de seguridad')
    # Partidos vencidos sin marcador no se clasifican como futuros.
    futuros=(base.kickoff_utc>corte) & ~completos
    output=base.loc[seguros | futuros].copy()
    output['game_status']=''
    output.loc[seguros.loc[output.index],'game_status']='FINAL'
    output.loc[futuros.loc[output.index],'game_status']='SCHEDULED'
    output['clasificacion_origen']=''
    output.loc[seguros.loc[output.index],'clasificacion_origen']='inferido_por_marcador_y_margen'
    output.loc[futuros.loc[output.index],'clasificacion_origen']='futuro_sin_marcador'
    reporte.update(entrenables_inferidos=int(seguros.sum()),futuros=int(futuros.sum()),margen_horas=margen_horas,
                   limitacion='FINAL inferido no es estado oficial ni prueba de disponibilidad del marcador en backtests')
    return output.reset_index(drop=True),reporte

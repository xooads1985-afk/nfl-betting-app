"""Generación experimental por lotes: no modifica módulos estables."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
from nba_lab_prueba_real import calendario_real
from nba_lab_reentrenar_depurado import preparar, clasificaciones_cache
from nba_lab_puente_seguro import preparar_tarjeta_segura
from nba_lab_lector_tarjetas import leer_tarjeta


def generar(max_partidos=10, salida='nba_lab_resultados_futuro/lotes'):
    if not 1 <= max_partidos <= 30:
        raise ValueError('max_partidos debe estar entre 1 y 30')
    destino = Path(salida)
    destino.mkdir(parents=True, exist_ok=True)
    bruto = pd.read_csv('nba_lab_resultados/partidos_historicos.csv', dtype={'id':str})
    audit, regular = preparar(bruto, clasificaciones_cache(Path('nba_lab_cache')))
    if regular.empty:
        raise RuntimeError('No hay historial regular verificado')
    calendario = calendario_real()
    calendario['fecha_utc'] = pd.to_datetime(calendario['fecha_utc'], utc=True, errors='coerce')
    ahora = datetime.now(timezone.utc).isoformat()
    pendientes = calendario.loc[(calendario['fecha_utc'] > pd.Timestamp(ahora)) & (~calendario['finalizado'])].sort_values('fecha_utc')
    if pendientes.empty:
        raise RuntimeError('No hay partidos futuros')
    informe = {'generado_utc':ahora,'historial_regular':len(regular), 'partidos_pendientes':len(pendientes), 'limite':max_partidos, 'tarjetas':[], 'errores':[]}
    for _, juego in pendientes.head(max_partidos).iterrows():
        pid = str(juego['id'])
        try:
            tarjeta = preparar_tarjeta_segura(calendario, audit, pid, ahora_utc=ahora)
            ruta = destino / f'tarjeta_{pid}.json'
            ruta.write_text(json.dumps(tarjeta,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
            vista = leer_tarjeta(destino, pid, ahora_utc=tarjeta['generado_utc'])
            informe['tarjetas'].append({'id':pid,'archivo':ruta.name,'fecha_utc':vista['fecha_utc'],'generado_utc':vista['generado_utc'],'local':vista['local'],'visitante':vista['visitante']})
        except Exception as exc:
            (destino / f'tarjeta_{pid}.json').unlink(missing_ok=True)
            informe['errores'].append({'id':pid,'error':f'{type(exc).__name__}: {exc}'})
    (destino/'indice_tarjetas.json').write_text(json.dumps(informe,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(informe,ensure_ascii=False,indent=2))
    if not informe['tarjetas'] or informe['errores']:
        raise RuntimeError('Lote incompleto o sin tarjetas válidas; revisar índice')
    return informe

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--max-partidos',type=int,default=10)
    p.add_argument('--salida',default='nba_lab_resultados_futuro/lotes')
    a=p.parse_args()
    generar(a.max_partidos,a.salida)

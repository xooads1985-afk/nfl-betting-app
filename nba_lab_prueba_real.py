"""Prueba aislada de calendario ESPN -> guardia -> motor real -> tarjetas JSON."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
import requests
from nba_lab_reentrenar_depurado import preparar, clasificaciones_cache
from nba_lab_puente_seguro import preparar_tarjeta_segura

SALIDA = Path('nba_lab_resultados_futuro/prueba_real')
URL = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard'

def calendario_real():
    hoy = datetime.now(timezone.utc)
    fechas = f'{hoy:%Y%m%d}-{(hoy + timedelta(days=7)):%Y%m%d}'
    resp = requests.get(URL, params={'dates': fechas, 'limit': 200}, timeout=30)
    resp.raise_for_status()
    filas = []
    for ev in resp.json().get('events', []):
        comp = (ev.get('competitions') or [{}])[0]
        teams = comp.get('competitors') or []
        local = next((x for x in teams if x.get('homeAway') == 'home'), None)
        visita = next((x for x in teams if x.get('homeAway') == 'away'), None)
        if not local or not visita:
            continue
        estado = ev.get('status', {}).get('type', {})
        filas.append({'id': str(ev['id']), 'fecha_utc': ev.get('date'),
                      'local': local.get('team', {}).get('displayName'),
                      'visitante': visita.get('team', {}).get('displayName'),
                      'finalizado': bool(estado.get('completed')),
                      'estado': estado.get('name', '')})
    return pd.DataFrame(filas, columns=['id','fecha_utc','local','visitante','finalizado','estado'])

def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv('nba_lab_resultados/partidos_historicos.csv', dtype={'id':str})
    audit, regular = preparar(raw, clasificaciones_cache(Path('nba_lab_cache')))
    if regular.empty:
        raise RuntimeError('No hay historial regular clasificado')
    cal = calendario_real()
    ahora = datetime.now(timezone.utc).isoformat()
    cal['fecha_utc'] = pd.to_datetime(cal['fecha_utc'], utc=True, errors='coerce')
    futuros = cal.loc[(cal['fecha_utc'] > pd.Timestamp(ahora)) & (~cal['finalizado'])].sort_values('fecha_utc')
    informe = {'fecha_consulta_utc': ahora, 'origen_calendario':'ESPN scoreboard',
               'partidos_calendario':len(cal), 'partidos_pendientes':len(futuros),
               'historial_recibido':len(raw), 'historial_regular_verificado':len(regular),
               'predicciones_reales':[], 'errores':[], 'motor_simulado':False}
    if futuros.empty:
        raise RuntimeError('No se encontraron partidos futuros')
    # Máximo dos partidos: permite revisar el motor real sin duplicar reentrenamientos extensos.
    for _, partido in futuros.head(2).iterrows():
        ident = str(partido['id'])
        try:
            tarjeta = preparar_tarjeta_segura(cal, audit, ident, ahora_utc=ahora)
            if tarjeta.get('esquema') != 'nba_tarjeta_futura_v1' or tarjeta.get('detalle_motor',{}).get('origen') != 'prepartido_experimental':
                raise RuntimeError('Salida no corresponde al motor real')
            if tarjeta.get('partido_id') != ident:
                raise RuntimeError('ID inconsistente')
            (SALIDA/f'tarjeta_{ident}.json').write_text(json.dumps(tarjeta, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
            informe['predicciones_reales'].append({'id':ident, 'local':tarjeta['local'], 'visitante':tarjeta['visitante'],
                'fecha_utc':tarjeta['fecha_utc'], 'total_ensemble':tarjeta['total_ensemble'],
                'total_modelo_c':tarjeta['total_modelo_c'], 'pace_prepartido':tarjeta['pace_prepartido'],
                'historial_regular_anterior':tarjeta['auditoria_guardia']['historial_regular_anterior']})
        except Exception as exc:
            informe['errores'].append({'id':ident, 'error':str(exc)})
    (SALIDA/'informe_prueba_real.json').write_text(json.dumps(informe, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(informe, ensure_ascii=False, indent=2))
    if not informe['predicciones_reales']:
        raise RuntimeError('No se produjo ninguna tarjeta real; revisar informe_prueba_real.json')

if __name__ == '__main__':
    main()

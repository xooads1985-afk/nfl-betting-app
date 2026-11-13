"""Actualiza el CSV Pace de forma incremental, validando cada boxscore ESPN."""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
from nba_cargador_historial import cargar_historial_bloques
from nba_pace_historial import construir_historial

CSV = Path(__file__).with_name('nba_historial_pace.csv')

def actualizar(dias=7, max_partidos=100):
    if not CSV.is_file():
        raise FileNotFoundError(f'No se encontró el historial Pace: {CSV}')
    previo = pd.read_csv(CSV, encoding='utf-8-sig', dtype={'partido_id': str})
    if previo.empty or 'partido_id' not in previo or previo['partido_id'].duplicated().any():
        raise ValueError('Historial Pace previo vacío, inválido o con IDs duplicados')
    columnas = list(previo.columns)
    hoy = datetime.now(timezone.utc).date()
    inicio = hoy - timedelta(days=dias)
    juegos, incidencias = cargar_historial_bloques(inicio, hoy)
    if incidencias:
        raise ValueError('Cobertura del calendario incompleta: ' + '; '.join(map(str, incidencias)))
    necesarias = {'id', 'fecha_utc', 'finalizado'}
    if juegos.empty or not necesarias.issubset(juegos.columns):
        raise ValueError('Calendario vacío o sin campos obligatorios')
    fechas = pd.to_datetime(juegos['fecha_utc'], utc=True, errors='coerce')
    if fechas.isna().any():
        raise ValueError('Fechas de calendario inválidas')
    pendientes = juegos.loc[
        juegos['finalizado'].eq(True) & fechas.lt(pd.Timestamp.now(tz='UTC'))
        & ~juegos['id'].astype(str).isin(set(previo['partido_id']))
    ].copy().sort_values('fecha_utc')
    if len(pendientes) > max_partidos:
        raise ValueError(f'{len(pendientes)} juegos pendientes superan el límite de {max_partidos}; revisar cobertura')
    if pendientes.empty:
        print('Historial Pace actualizado: no hay partidos nuevos')
        return
    from modulo_nba import cargar_detalle
    bloques = []
    fallos = []
    for inicio_bloque in range(0, len(pendientes), 50):
        bloque = pendientes.iloc[inicio_bloque:inicio_bloque + 50]
        filas, errores_bloque = construir_historial(bloque, cargar_detalle, max_partidos=50)
        bloques.append(filas)
        if not errores_bloque.empty:
            fallos.append(errores_bloque)
    nuevos = pd.concat(bloques, ignore_index=True)
    errores = pd.concat(fallos, ignore_index=True) if fallos else pd.DataFrame()
    if not errores.empty or len(nuevos) != len(pendientes):
        raise ValueError(f'No se publica historial parcial: {len(nuevos)} válidos de {len(pendientes)}; errores: {errores.to_dict("records")[:8]}')
    if not set(columnas).issubset(nuevos.columns):
        raise ValueError('El extractor no produjo las columnas del historial Pace existente')
    combinado = pd.concat([previo, nuevos[columnas]], ignore_index=True)
    if combinado['partido_id'].duplicated().any():
        raise ValueError('IDs duplicados tras combinar')
    combinado['fecha_utc'] = pd.to_datetime(combinado['fecha_utc'], utc=True, errors='raise')
    combinado = combinado.sort_values(['fecha_utc', 'partido_id'])
    temporal = CSV.with_suffix('.csv.tmp')
    combinado.to_csv(temporal, index=False, encoding='utf-8-sig', date_format='%Y-%m-%dT%H:%M:%SZ')
    temporal.replace(CSV)
    print(f'Pace actualizado: {len(nuevos)} nuevos; {len(combinado)} totales')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dias', type=int, default=7)
    parser.add_argument('--max-partidos', type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.dias <= 30 or not 1 <= args.max_partidos <= 100:
        parser.error('Rango de días o máximo de partidos inválido')
    actualizar(args.dias, args.max_partidos)

"""Registro prospectivo NBA: ventana corta y ejecución manual segura.
No altera los modelos ni los módulos principales.
"""
import argparse
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def log(mensaje):
    print(f'[{datetime.now(timezone.utc).isoformat(timespec="seconds")}] {mensaje}', flush=True)


def configurar_secretos():
    url = os.environ.get('SUPABASE_URL', '')
    key = os.environ.get('SUPABASE_SECRET_KEY', '')
    if not url.startswith('https://') or not key:
        raise RuntimeError('Faltan secretos SUPABASE_URL o SUPABASE_SECRET_KEY')
    path = Path('.streamlit/secrets.toml')
    path.parent.mkdir(exist_ok=True)
    path.write_text('SUPABASE_URL = ' + json.dumps(url) + '\nSUPABASE_SECRET_KEY = ' + json.dumps(key) + '\n')
    path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('dry_run', 'save'), default='dry_run')
    args = parser.parse_args()
    configurar_secretos()
    import pandas as pd
    from resumen_inteligente_nba import _cargar_historial_temporada_nba, _calendario_proximos_nba
    from nba_laboratorio_prospectivo import calcular, guardar, registros

    ahora = pd.Timestamp.now(tz='UTC')
    hoy = ahora.date()
    log(f'INICIO modo={args.mode}; ventana=60min a 24h; máximo=8 partidos')
    log('Cargando calendario NBA...')
    futuros, errores = _calendario_proximos_nba(hoy.isoformat(), (hoy + timedelta(days=2)).isoformat())
    if errores:
        log(f'AVISO calendario: {len(errores)} incidencias')
    if futuros is None or futuros.empty:
        log('Sin partidos en calendario. No se escribe nada.')
        return
    futuros = futuros.copy()
    futuros['_inicio'] = pd.to_datetime(futuros['fecha_utc'], utc=True, errors='coerce')
    elegibles = futuros.loc[
        futuros['_inicio'].gt(ahora + pd.Timedelta(minutes=60))
        & futuros['_inicio'].le(ahora + pd.Timedelta(hours=24))
        & futuros['finalizado'].eq(False)
    ].drop_duplicates('id').sort_values('_inicio')
    log(f'Partidos dentro de ventana: {len(elegibles)}')
    if elegibles.empty:
        log('RESUMEN modo=' + args.mode + ' calculados=0 omitidos=0 fallos=0 insertados=0')
        return

    log('Consultando predicciones existentes...')
    existentes = {(str(r['partido_id']), str(r['equipo']), str(r['modelo'])) for r in registros()}
    pendientes = []
    omitidos = 0
    for juego in elegibles.to_dict('records'):
        ident = str(juego['id'])
        claves = {(ident, str(equipo), modelo) for equipo in (juego['local'], juego['visitante']) for modelo in ('Base', 'Modelo C', 'Ensemble')}
        if claves.issubset(existentes):
            omitidos += 1
            log(f'OMITIDO {ident}: seis registros existentes')
        else:
            pendientes.append(juego)
    if not pendientes:
        log(f'RESUMEN modo={args.mode} calculados=0 omitidos={omitidos} fallos=0 insertados=0')
        return
    if len(pendientes) > 8:
        log(f'AVISO: {len(pendientes)} pendientes; se procesan los primeros 8 por hora de inicio')
        pendientes = pendientes[:8]

    log('Cargando historial de entrenamiento (2025-10-21 hasta hoy)...')
    inicio_carga = time.monotonic()
    historico, incidencias = _cargar_historial_temporada_nba(date(2025, 10, 21), hoy)
    if incidencias:
        log(f'AVISO: {len(incidencias)} incidencias de cobertura histórica')
    if historico is None or historico.empty:
        raise RuntimeError('Historial vacío: ejecución cancelada')
    log(f'Historial listo: {len(historico)} partidos en {time.monotonic()-inicio_carga:.1f}s')

    calculados = fallos = insertados = 0
    for indice, juego in enumerate(pendientes, 1):
        ident = str(juego['id'])
        log(f'CALCULANDO {indice}/{len(pendientes)} partido={ident} inicio={juego["fecha_utc"]}')
        inicio_modelo = time.monotonic()
        try:
            # Se comprueba de nuevo que el encuentro no haya comenzado.
            if pd.to_datetime(juego['fecha_utc'], utc=True) <= pd.Timestamp.now(tz='UTC') + pd.Timedelta(minutes=60):
                log(f'OMITIDO {ident}: inicio demasiado cercano')
                omitidos += 1
                continue
            pred = calcular(historico, juego)
            calculados += 1
            log(f'CALCULADO {ident} en {time.monotonic()-inicio_modelo:.1f}s: {pred}')
            if args.mode == 'save':
                # La función guardar del laboratorio impide sobrescribir filas existentes.
                cantidad = guardar(juego, pred)
                insertados += cantidad
                log(f'GUARDADO {ident}: {cantidad} registros nuevos')
            else:
                log(f'SIMULACION {ident}: sin escrituras')
        except Exception as exc:
            fallos += 1
            log(f'ERROR {ident}: {type(exc).__name__}: {exc}')
    log(f'RESUMEN modo={args.mode} calculados={calculados} omitidos={omitidos} fallos={fallos} insertados={insertados}')
    if fallos:
        raise RuntimeError('Uno o más encuentros fallaron; revisar registro')


if __name__ == '__main__':
    main()

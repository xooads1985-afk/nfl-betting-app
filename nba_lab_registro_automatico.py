"""Prueba manual del registro prospectivo NBA. No cambia módulos estables."""
import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


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
    p = argparse.ArgumentParser()
    p.add_argument('--mode', choices=('dry_run', 'save'), default='dry_run')
    args = p.parse_args()
    configurar_secretos()
    import pandas as pd
    from resumen_inteligente_nba import _cargar_historial_temporada_nba, _calendario_proximos_nba
    from nba_laboratorio_prospectivo import calcular, guardar, registros

    hoy = datetime.now(timezone.utc).date()
    historico, incidencias = _cargar_historial_temporada_nba(date(2025, 10, 21), hoy)
    if incidencias:
        print(f'AVISO: {len(incidencias)} incidencias de cobertura histórica')
    if historico.empty:
        raise RuntimeError('Historial vacío: ejecución cancelada')
    futuros, errores = _calendario_proximos_nba(hoy.isoformat(), (hoy + timedelta(days=3)).isoformat())
    if errores:
        print(f'AVISO: {len(errores)} incidencias de calendario')
    if futuros.empty:
        print('Sin partidos futuros; no se guarda nada')
        return
    existentes = {(str(r['partido_id']), r['equipo'], r['modelo']) for r in registros()}
    futuros = futuros.copy()
    futuros['_inicio'] = pd.to_datetime(futuros['fecha_utc'], utc=True, errors='coerce')
    futuros = futuros.loc[(futuros['_inicio'] > pd.Timestamp.now(tz='UTC') + pd.Timedelta(minutes=60)) & futuros['finalizado'].eq(False)]
    futuros = futuros.drop_duplicates('id').sort_values('_inicio')
    calculados = omitidos = fallos = insertados = 0
    for juego in futuros.to_dict('records'):
        ident = str(juego['id'])
        claves = {(ident, str(equipo), modelo) for equipo in (juego['local'], juego['visitante']) for modelo in ('Base', 'Modelo C', 'Ensemble')}
        if claves.issubset(existentes):
            omitidos += 1
            print(f'OMITIDO {ident}: seis registros existentes')
            continue
        try:
            pred = calcular(historico, juego)
            calculados += 1
            print(f'CALCULADO {ident}: {pred}')
            if args.mode == 'save':
                cantidad = guardar(juego, pred)
                insertados += cantidad
                print(f'GUARDADO {ident}: {cantidad} registros nuevos')
            else:
                print(f'SIMULACION {ident}: sin escrituras')
        except Exception as exc:
            fallos += 1
            print(f'ERROR {ident}: {type(exc).__name__}: {exc}')
    print(f'RESUMEN modo={args.mode} calculados={calculados} omitidos={omitidos} fallos={fallos} insertados={insertados}')
    if fallos:
        raise RuntimeError('Uno o más encuentros fallaron; revisar registro')


if __name__ == '__main__':
    main()

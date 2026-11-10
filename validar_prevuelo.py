"""Puerta de calidad antes de entrenar con NFLverse; sin tocar los módulos estables."""
import argparse
import json
from pathlib import Path
import pandas as pd
from auditar_datos_reales import auditar


def validar(calendario, pbp, cobertura_minima=90.0, minimo_partidos=100):
    reporte = auditar(calendario, pbp)
    incidencias = reporte['incidencias']
    problemas = []
    if not reporte['apto_para_validacion']:
        problemas.append('Inconsistencias estructurales del calendario')
    completos = pd.to_numeric(calendario.home_score, errors='coerce').notna() & pd.to_numeric(calendario.away_score, errors='coerce').notna()
    if int(completos.sum()) < minimo_partidos:
        problemas.append('Partidos finalizados insuficientes')
    # Los partidos futuros sin marcador son válidos, pero no pueden entrar al entrenamiento.
    if 'pbp' not in reporte or reporte['pbp']['cobertura_pct'] < cobertura_minima:
        problemas.append('Cobertura PBP inferior al mínimo')
    if 'pbp' in reporte and (reporte['pbp']['epa_faltante'] or reporte['pbp']['success_faltante']):
        problemas.append('Jugadas con EPA o Success Rate faltante: revisar antes de entrenar')
    if incidencias['marcadores_incompletos']:
        reporte['aviso'] = 'Separar encuentros sin marcador antes de entrenar'
    reporte['preflight'] = {'aprobado': not problemas, 'motivos': problemas,
                           'cobertura_minima_pct': cobertura_minima,
                           'minimo_partidos': minimo_partidos}
    return reporte


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--calendar', required=True)
    p.add_argument('--pbp', required=True)
    p.add_argument('--output', default='preflight_nfl.json')
    p.add_argument('--cobertura-minima', type=float, default=90.)
    p.add_argument('--minimo-partidos', type=int, default=100)
    args = p.parse_args()
    reporte = validar(pd.read_csv(args.calendar), pd.read_csv(args.pbp), args.cobertura_minima, args.minimo_partidos)
    Path(args.output).write_text(json.dumps(reporte, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(reporte['preflight'], ensure_ascii=False))
    if not reporte['preflight']['aprobado']:
        raise SystemExit(2)

if __name__ == '__main__':
    main()

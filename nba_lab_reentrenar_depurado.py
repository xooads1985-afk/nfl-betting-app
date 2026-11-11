"""Reentrenamiento aislado, reproducible y sin acceso a información posterior.
Uso: python nba_lab_reentrenar_depurado.py --historial nba_lab_resultados/partidos_historicos.csv --cache nba_lab_cache
No modifica datos originales ni módulos Streamlit.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import pandas as pd
from nba_lab_clasificacion import clasificar_evento, es_exhibicion
from nba_lab_motor_offline import _nba_lab_ml_validacion, _nba_lab_ml_resumen


def clasificaciones_cache(cache: Path):
    tipos = {}
    conflictos = set()
    for archivo in sorted(cache.glob('*.json')):
        try:
            datos = json.loads(archivo.read_text(encoding='utf-8'))
        except (ValueError, OSError) as exc:
            raise ValueError(f'Cache inválida: {archivo.name}: {exc}') from exc
        for evento in datos.get('events', []):
            ident = str(evento.get('id', ''))
            if not ident:
                continue
            tipo = clasificar_evento(evento)
            if ident in tipos and tipos[ident] != tipo:
                conflictos.add(ident)
            tipos[ident] = tipo
    for ident in conflictos:
        tipos[ident] = 'sin_verificar'
    return tipos


def preparar(historial: pd.DataFrame, tipos: dict):
    df = historial.copy()
    requeridas = {'id', 'fecha_utc', 'local', 'visitante', 'puntos_local', 'puntos_visitante', 'finalizado'}
    faltan = requeridas - set(df.columns)
    if faltan:
        raise ValueError(f'Columnas faltantes: {sorted(faltan)}')
    if df['id'].astype(str).duplicated().any():
        raise ValueError('IDs duplicados en historial; corregir origen antes de evaluar')
    df['id'] = df['id'].astype(str)
    df['tipo_competicion'] = df['id'].map(tipos).fillna('sin_verificar')
    exhibicion = df.apply(lambda x: es_exhibicion(x['id'], x['local'], x['visitante']), axis=1)
    df.loc[exhibicion, 'tipo_competicion'] = 'especial'
    df['fecha_utc'] = pd.to_datetime(df['fecha_utc'], utc=True, errors='coerce')
    df['puntos_local'] = pd.to_numeric(df['puntos_local'], errors='coerce')
    df['puntos_visitante'] = pd.to_numeric(df['puntos_visitante'], errors='coerce')
    df['finalizado'] = df['finalizado'].astype(str).str.lower().eq('true')
    df['apto'] = (df['tipo_competicion'].eq('regular') & df['finalizado'] &
                  df['fecha_utc'].notna() & df['puntos_local'].notna() & df['puntos_visitante'].notna())
    df = df.sort_values(['fecha_utc', 'id'])
    return df, df.loc[df['apto']].copy()


def ejecutar(historial: Path, cache: Path, salida: Path):
    if not cache.is_dir() or not list(cache.glob('*.json')):
        raise ValueError('No hay metadatos ESPN en caché: clasificación bloqueada')
    raw = pd.read_csv(historial, dtype={'id': str})
    audit, regular = preparar(raw, clasificaciones_cache(cache))
    if regular.empty:
        raise ValueError('Ningún partido regular verificado: reentrenamiento bloqueado')
    pred, nota = _nba_lab_ml_validacion(regular)
    if pred.empty:
        raise ValueError(f'No hay predicciones para evaluar: {nota}')
    # Todos los cálculos concluyeron: publicar resultados en directorio exclusivo.
    salida.mkdir(parents=True, exist_ok=True)
    audit.to_csv(salida / 'historial_clasificado.csv', index=False)
    regular.to_csv(salida / 'historial_regular.csv', index=False)
    pred.to_csv(salida / 'predicciones_reentrenadas.csv', index=False)
    resumen = _nba_lab_ml_resumen(pred)
    resumen.to_csv(salida / 'resumen_reentrenado.csv', index=False)
    meta = {'partidos_originales': len(raw), 'partidos_regulares': len(regular),
            'predicciones': len(pred), 'clasificacion': audit['tipo_competicion'].value_counts().to_dict(),
            'nota': nota, 'pace_validado': False}
    (salida / 'estado_reentrenamiento.json').write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
    return meta


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--historial', type=Path, default=Path('nba_lab_resultados/partidos_historicos.csv'))
    p.add_argument('--cache', type=Path, default=Path('nba_lab_cache'))
    p.add_argument('--salida', type=Path, default=Path('nba_lab_resultados_depurados/reentrenamiento'))
    args = p.parse_args()
    print(json.dumps(ejecutar(args.historial, args.cache, args.salida), ensure_ascii=False, indent=2))

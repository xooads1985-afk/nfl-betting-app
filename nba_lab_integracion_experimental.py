"""Integración experimental de lectura: no modifica NBA, NFL ni main.py.
Uso: python nba_lab_integracion_experimental.py --predicciones predicciones_con_pace.csv --salida nba_lab_integracion_resultados
"""
from pathlib import Path
import argparse, json
import numpy as np
import pandas as pd

KEY = ['partido', 'equipo']
REQUIRED = KEY + ['fecha', 'real', 'Ensemble', 'Modelo C', 'Posesiones + eficiencia', 'pace_prepartido', 'partidos_previos_equipo', 'partidos_previos_rival']

def integrar(df: pd.DataFrame):
    missing = set(REQUIRED) - set(df.columns)
    if missing: raise ValueError(f'Columnas faltantes: {sorted(missing)}')
    d = df.copy()
    d['partido'] = d['partido'].astype(str)
    if d.duplicated(KEY).any(): raise ValueError('Partido/equipo duplicado')
    d['fecha'] = pd.to_datetime(d['fecha'], utc=True, errors='coerce')
    if d['fecha'].isna().any(): raise ValueError('Fechas inválidas')
    nums = ['real', 'Ensemble', 'Modelo C', 'Posesiones + eficiencia', 'pace_prepartido', 'partidos_previos_equipo', 'partidos_previos_rival']
    for col in nums: d[col] = pd.to_numeric(d[col], errors='coerce')
    if d[nums].isna().any().any(): raise ValueError('Valores numéricos faltantes')
    if (d[['partidos_previos_equipo','partidos_previos_rival']] < 3).any().any(): raise ValueError('Pace sin 3 antecedentes previos')
    sizes = d.groupby('partido').size()
    if not sizes.eq(2).all(): raise ValueError('Cada partido debe contener exactamente dos equipos')
    if not d.groupby('partido')['fecha'].nunique().eq(1).all(): raise ValueError('Fechas diferentes dentro de un partido')
    d['proyeccion_equipo'] = d['Ensemble']
    d['proyeccion_total_modelo_c'] = d.groupby('partido')['Modelo C'].transform('sum')
    d['proyeccion_total_ensemble'] = d.groupby('partido')['Ensemble'].transform('sum')
    d['referencia_modelo_base'] = d['Base'] if 'Base' in d else np.nan
    d['diferencia_frente_base'] = d['proyeccion_equipo'] - d['referencia_modelo_base']
    d['error_abs_equipo'] = (d['proyeccion_equipo'] - d['real']).abs()
    # No utiliza el marcador real en ninguna proyección; únicamente para evaluación posterior.
    g = d.sort_values(['partido','equipo']).groupby('partido',sort=False)
    p = g.agg(fecha=('fecha','first'),equipo_1=('equipo','first'),proyeccion_total=('Modelo C','sum'),proyeccion_total_ensemble=('Ensemble','sum'),total_real=('real','sum'),pace_promedio_prepartido=('pace_prepartido','mean'),min_antecedentes=('partidos_previos_equipo','min')).reset_index()
    p['error_abs_total_modelo_c'] = (p.proyeccion_total-p.total_real).abs()
    p['error_abs_total_ensemble'] = (p.proyeccion_total_ensemble-p.total_real).abs()
    metrics = {'filas':int(len(d)), 'partidos':int(len(p)), 'mae_equipo_ensemble':float(d.error_abs_equipo.mean()),'mae_equipo_modelo_c':float((d['Modelo C']-d.real).abs().mean()),'mae_equipo_pace':float((d['Posesiones + eficiencia']-d.real).abs().mean()),'mae_total_modelo_c':float(p.error_abs_total_modelo_c.mean()),'mae_total_ensemble':float(p.error_abs_total_ensemble.mean()),'minimo_antecedentes':int(d[['partidos_previos_equipo','partidos_previos_rival']].min().min()),'pace_usado_como_ajuste':False,'nota':'Los valores reales se usan exclusivamente para validación retrospectiva. La referencia Base no representa cuotas de apuestas.'}
    return d,p,metrics

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--predicciones',type=Path,default=Path('nba_lab_resultados_depurados/pace/predicciones_con_pace.csv'))
    parser.add_argument('--salida',type=Path,default=Path('nba_lab_integracion_resultados'))
    args=parser.parse_args()
    d,p,m=integrar(pd.read_csv(args.predicciones,dtype={'partido':str}))
    args.salida.mkdir(parents=True,exist_ok=True)
    d.to_csv(args.salida/'proyecciones_equipos.csv',index=False)
    p.to_csv(args.salida/'proyecciones_partidos.csv',index=False)
    (args.salida/'informe_integracion.json').write_text(json.dumps(m,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(m,indent=2,ensure_ascii=False))

if __name__=='__main__':main()

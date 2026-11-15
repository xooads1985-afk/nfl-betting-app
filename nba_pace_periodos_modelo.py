"""Proyección experimental Q1/1H basada en períodos reales y ritmo Pace.

No altera las predicciones de partido completo. No escribe datos. Los
pronósticos requieren historial previo; validación cronológica separada.
"""
import math
import pandas as pd

PERIODOS = {
    'q1': ('puntos_q1_local', 'puntos_q1_visitante'),
    'mitad': ('puntos_mitad_local', 'puntos_mitad_visitante'),
}
BASE = {'fecha_utc', 'local', 'visitante', 'finalizado', 'partido_id',
        'posesiones_local', 'posesiones_visitante'}


def _preparar(historial, fecha, excluir=None):
    if not isinstance(historial, pd.DataFrame):
        raise ValueError('Historial Pace inválido')
    requeridas = BASE | {c for columnas in PERIODOS.values() for c in columnas}
    if not requeridas.issubset(historial.columns):
        raise ValueError('Faltan puntos históricos por período: ' +
                         ', '.join(sorted(requeridas - set(historial.columns))))
    limite = pd.to_datetime(fecha, utc=True, errors='coerce')
    if pd.isna(limite):
        raise ValueError('Fecha objetivo inválida')
    h = historial.copy()
    h['_fecha'] = pd.to_datetime(h['fecha_utc'], utc=True, errors='coerce')
    terminados = h['finalizado'].astype(str).str.lower().eq('true')
    h = h.loc[h['_fecha'].notna() & h['_fecha'].lt(limite) & terminados].copy()
    if excluir is not None:
        h = h.loc[h['partido_id'].astype(str).ne(str(excluir))]
    if h['partido_id'].astype(str).duplicated().any():
        raise ValueError('IDs duplicados en historial de períodos')
    for c in (set().union(*PERIODOS.values()) | {'posesiones_local', 'posesiones_visitante'}):
        h[c] = pd.to_numeric(h[c], errors='coerce')
    h = h.dropna(subset=list(set().union(*PERIODOS.values()) |
                             {'posesiones_local', 'posesiones_visitante'}))
    h = h.loc[h['posesiones_local'].between(50, 180) &
              h['posesiones_visitante'].between(50, 180)].copy()
    for c in set().union(*PERIODOS.values()):
        h = h.loc[h[c].ge(0) & h[c].le(180)]
    if not h.empty:
        h = h.loc[h['puntos_q1_local'].le(h['puntos_mitad_local']) &
                  h['puntos_q1_visitante'].le(h['puntos_mitad_visitante'])]
    return h.sort_values('_fecha')


def proyectar_periodos(historial, partido, *, ventana=10, minimo=5, corte_utc=None):
    """Pronostica Q1 y 1H con tasas históricas reales por posesión.

    Se emplea el promedio de ataque propio y defensa rival, multiplicado por
    el ritmo medio Pace del emparejamiento. Las posesiones son del partido
    completo: su uso aquí es un proxy empírico, NO posesiones observadas Q1/1H.
    """
    if ventana < minimo or minimo < 3:
        raise ValueError('Ventana/muestra insuficiente')
    local, visitante = str(partido['local']), str(partido['visitante'])
    if local == visitante or not local or not visitante:
        raise ValueError('Equipos inválidos')
    # El corte de generación evita usar partidos posteriores al pronóstico.
    limite = partido['fecha_utc']
    if corte_utc is not None:
        fecha_objetivo = pd.to_datetime(partido['fecha_utc'], utc=True, errors='raise')
        fecha_corte = pd.to_datetime(corte_utc, utc=True, errors='raise')
        limite = min(fecha_objetivo, fecha_corte)
    h = _preparar(historial, limite, partido.get('id'))
    datos = {}
    for equipo in (local, visitante):
        filas = h.loc[h['local'].eq(equipo) | h['visitante'].eq(equipo)].tail(ventana)
        if len(filas) < minimo:
            return None
        en_casa = filas['local'].eq(equipo)
        pos = (filas['posesiones_local'] + filas['posesiones_visitante']) / 2
        tasas = {}
        for periodo, (col_local, col_visita) in PERIODOS.items():
            propios = filas[col_local].where(en_casa, filas[col_visita])
            rivales = filas[col_visita].where(en_casa, filas[col_local])
            tasas[periodo] = (float((propios / pos).mean()),
                              float((rivales / pos).mean()))
        datos[equipo] = {'pace': float(pos.mean()), 'muestra': len(filas), 'tasas': tasas}
    ritmo = (datos[local]['pace'] + datos[visitante]['pace']) / 2
    salida = {}
    for periodo in PERIODOS:
        valores = {}
        for equipo, rival in ((local, visitante), (visitante, local)):
            ataque = datos[equipo]['tasas'][periodo][0]
            defensa = datos[rival]['tasas'][periodo][1]
            puntos = ritmo * (ataque + defensa) / 2
            if not math.isfinite(puntos) or puntos < 0:
                return None
            valores[equipo] = round(puntos, 3)
        salida[periodo] = {'local': valores[local], 'visitante': valores[visitante],
                           'total': round(sum(valores.values()), 3)}
    if any(salida['q1'][k] > salida['mitad'][k] for k in ('local', 'visitante', 'total')):
        return None
    return {'periodos': salida, 'muestras': {e: datos[e]['muestra'] for e in datos},
            'ritmo_pace_proxy': round(ritmo, 3), 'metodo': 'tasas históricas Q1/1H por posesión de partido'}


def validar_cronologicamente(historial, *, ventana=10, minimo=5, min_evaluaciones=5):
    """Backtest prospectivo: cada partido usa solo encuentros anteriores.

    No declara aprobación automática: entrega MAE y tamaño de muestra para
    que el proyecto determine un criterio de aceptación antes de publicar.
    """
    if not isinstance(historial, pd.DataFrame) or 'fecha_utc' not in historial:
        raise ValueError('Historial inválido')
    df = historial.copy()
    df['_fecha'] = pd.to_datetime(df['fecha_utc'], utc=True, errors='coerce')
    df = df.loc[df['_fecha'].notna()].sort_values('_fecha')
    errores = {p: {'local': [], 'visitante': [], 'total': []} for p in PERIODOS}
    for _, juego in df.iterrows():
        if str(juego.get('finalizado')).lower() != 'true':
            continue
        partido = {'id': juego['partido_id'], 'fecha_utc': juego['fecha_utc'],
                   'local': juego['local'], 'visitante': juego['visitante']}
        pred = proyectar_periodos(historial, partido, ventana=ventana, minimo=minimo)
        if pred is None:
            continue
        for p, (cl, cv) in PERIODOS.items():
            reales = {'local': float(juego[cl]), 'visitante': float(juego[cv])}
            reales['total'] = reales['local'] + reales['visitante']
            for campo in ('local', 'visitante', 'total'):
                errores[p][campo].append(pred['periodos'][p][campo] - reales[campo])
    salida = {}
    for p in PERIODOS:
        n = len(errores[p]['total'])
        salida[p] = {'n': n, 'validacion_suficiente': n >= min_evaluaciones,
                     'mae': {campo: round(sum(map(abs, errores[p][campo])) / n, 3)
                             if n else None for campo in ('local', 'visitante', 'total')},
                     'sesgo': {campo: round(sum(errores[p][campo]) / n, 3)
                               if n else None for campo in ('local', 'visitante', 'total')}}
    return salida

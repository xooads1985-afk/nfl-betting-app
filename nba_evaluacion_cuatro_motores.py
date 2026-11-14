"""Evaluación independiente de los cuatro motores NBA; solo lectura.

Complementa nba_evaluacion_consolidada.py sin cambiar su contrato.
Usa instantáneas verificadas y resultados finales reglamentarios.
"""
import hashlib
import json
import math
from collections import defaultdict
from nba_evaluacion_consolidada import _fecha

MODELOS = ('Base', 'Modelo C', 'Ensemble', 'Pace + Eficiencia')
OBJETIVOS = ('local', 'visitante', 'total', 'puntos_por_equipo')


def _numero(valor):
    if isinstance(valor, bool):
        raise ValueError('Número inválido')
    n = float(valor)
    if not math.isfinite(n) or n < 0:
        raise ValueError('Número inválido')
    return n


def evaluar_cuatro_motores(guardados, resultados):
    """Devuelve detalle, métricas por motor/objetivo y motivos de descarte.

    No interpreta los cuatro motores como predicciones seleccionadas: cada uno
    se evalúa con sus propios puntos por equipo y total.
    """
    partidos = {str(p['id']): p for p in resultados if p.get('id') is not None}
    vistos = set()
    detalle, descartes = [], defaultdict(int)
    for item in guardados:
        try:
            reg = item['registro']
            pid = str(reg['partido_id'])
            if pid in vistos:
                descartes['duplicado'] += 1
                continue
            vistos.add(pid)
            if (item['clave_unica'] != 'nba-consolidado-v1:' + pid or
                    str(item['partido_id']) != pid):
                descartes['identidad'] += 1
                continue
            canon = json.dumps(reg, sort_keys=True, ensure_ascii=False,
                               separators=(',', ':'), allow_nan=False)
            if hashlib.sha256(canon.encode()).hexdigest() != item['huella_sha256']:
                descartes['huella'] += 1
                continue
            inicio = _fecha(reg['inicio_utc'])
            if (_fecha(item['inicio_utc']) != inicio or
                    _fecha(item['creado_utc']) >= inicio):
                descartes['registro_tardio'] += 1
                continue
            real = partidos.get(pid)
            if real is None or real.get('finalizado') is not True:
                descartes['sin_resultado_final'] += 1
                continue
            if _fecha(real['fecha_utc']) != inicio:
                descartes['fecha_inconsistente'] += 1
                continue
            if (str(real['local']) != str(reg['equipos']['local']) or
                    str(real['visitante']) != str(reg['equipos']['visitante'])):
                descartes['equipos_inconsistentes'] += 1
                continue
            local = _numero(real['puntos_local'])
            visitante = _numero(real['puntos_visitante'])
            # La fuente de resultados debe garantizar que estos son puntos
            # reglamentarios; no se infiere si hubo prórroga.
            modelos = reg['cuatro_motores']
            if not isinstance(modelos, list) or len(modelos) != 4:
                descartes['cuatro_motores_incompletos'] += 1
                continue
            mapa = {}
            for m in modelos:
                nombre = m['modelo']
                if nombre not in MODELOS or nombre in mapa:
                    raise ValueError('Modelo desconocido o repetido')
                pl = _numero(m['local'])
                pv = _numero(m['visitante'])
                pt = _numero(m['total'])
                # El total del mismo motor debe coincidir con la suma de equipos.
                if abs((pl + pv) - pt) > 0.015:
                    raise ValueError('Total inconsistente')
                mapa[nombre] = (pl, pv, pt)
            if set(mapa) != set(MODELOS):
                descartes['cuatro_motores_incompletos'] += 1
                continue
            for nombre in MODELOS:
                pl, pv, pt = mapa[nombre]
                for objetivo, pred, observado in (
                    ('local', pl, local),
                    ('visitante', pv, visitante),
                    ('total', pt, local + visitante),
                ):
                    detalle.append({'partido_id': pid, 'motor': nombre,
                                    'objetivo': objetivo, 'proyeccion': pred,
                                    'real': observado, 'error': pred - observado})
        except (ValueError, TypeError, KeyError, OverflowError, AttributeError):
            descartes['datos_incompletos'] += 1

    grupos = defaultdict(list)
    for fila in detalle:
        grupos[(fila['motor'], fila['objetivo'])].append(fila['error'])
        if fila['objetivo'] in ('local', 'visitante'):
            grupos[(fila['motor'], 'puntos_por_equipo')].append(fila['error'])
    resumen = []
    for motor in MODELOS:
        for objetivo in OBJETIVOS:
            errores = grupos[(motor, objetivo)]
            if errores:
                resumen.append({'motor': motor, 'objetivo': objetivo,
                                'n': len(errores),
                                'MAE': round(sum(abs(e) for e in errores) / len(errores), 3),
                                'sesgo': round(sum(errores) / len(errores), 3)})
    return {'detalle': detalle, 'resumen': resumen, 'descartes': dict(descartes),
            'partidos_evaluados': len({r['partido_id'] for r in detalle})}

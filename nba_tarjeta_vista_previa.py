"""Vista previa de solo lectura: combina registros válidos y cálculos no persistidos."""
from datetime import datetime, timezone
from nba_tarjeta_controlador import diagnosticar, fecha_utc
from tarjeta_motor_cuatro import preparar


def preparar_vista_previa(partido, resultado, *, ahora=None):
    if resultado.get('estado') != 'simulacion':
        raise ValueError('La vista previa requiere modo de prueba')
    instante = fecha_utc(ahora or datetime.now(timezone.utc))
    inicio = fecha_utc(partido.get('fecha_utc'))
    if instante is None or inicio is None or instante >= inicio:
        raise ValueError('No se generan predicciones nuevas tras el inicio')
    existentes = list(resultado.get('registros') or [])
    faltantes = diagnosticar(partido, existentes)
    calculados = resultado.get('calculados') or {}
    tres, pace = calculados.get('tres'), calculados.get('pace')
    nuevos = []
    for equipo, modelo in sorted(faltantes):
        if modelo == 'Pace + Eficiencia':
            if not isinstance(pace, dict) or not isinstance(pace.get('equipos'), dict):
                continue
            valor = pace['equipos'].get(equipo)
        else:
            valor = (tres.get(equipo) or {}).get(modelo) if isinstance(tres, dict) else None
        if valor is None:
            continue
        nuevos.append({'partido_id': str(partido['id']), 'equipo': equipo,
                       'modelo': modelo, 'proyeccion': valor,
                       'inicio_utc': inicio.isoformat(), 'registrado_utc': instante.isoformat()})
    registros = existentes + nuevos
    restantes = diagnosticar(partido, registros)
    if restantes:
        descripcion = ', '.join(f'{e}: {m}' for e, m in sorted(restantes))
        raise ValueError('Faltan predicciones verificables: ' + descripcion)
    datos = preparar(partido, registros)
    datos['provisionales'] = len(nuevos)
    return datos

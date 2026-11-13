"""Construye una tarjeta verificable con resultados calculados sin persistirlos."""
from datetime import datetime, timezone
from tarjeta_motor_cuatro import preparar


def preparar_vista_previa(partido, resultado, *, ahora=None):
    """Valida 8 predicciones originales usando el mismo adaptador de la tarjeta final."""
    if resultado.get('estado') != 'simulacion':
        raise ValueError('La vista previa requiere resultados del modo de prueba')
    calculados = resultado.get('calculados') or {}
    tres = calculados.get('tres')
    pace = calculados.get('pace')
    if not isinstance(tres, dict) or not isinstance(pace, dict):
        raise ValueError('No se calcularon los cuatro motores')
    if not isinstance(pace.get('equipos'), dict):
        raise ValueError('Pace no tiene el esquema original')
    ahora = ahora or datetime.now(timezone.utc)
    if ahora.tzinfo is None:
        raise ValueError('La hora de registro debe incluir zona horaria')
    fecha = str(partido['fecha_utc'])
    registros = []
    for equipo in (str(partido['local']), str(partido['visitante'])):
        for modelo in ('Base', 'Modelo C', 'Ensemble', 'Pace + Eficiencia'):
            valor = (pace['equipos'][equipo] if modelo == 'Pace + Eficiencia'
                     else tres[equipo][modelo])
            registros.append({'partido_id': str(partido['id']), 'equipo': equipo,
                              'modelo': modelo, 'proyeccion': valor,
                              'inicio_utc': fecha, 'registrado_utc': ahora.isoformat()})
    return preparar(partido, registros)

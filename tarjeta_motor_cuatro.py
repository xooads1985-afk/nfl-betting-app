"""Adaptador puro de datos para tarjeta NBA, sin Streamlit ni conexiones externas."""
from datetime import datetime, timezone
from math import isfinite

MODELOS = ('Base', 'Modelo C', 'Pace + Eficiencia', 'Ensemble')


def fecha_utc(v):
    try:
        dt = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (TypeError, ValueError):
        return None


def preparar(partido, registros):
    """Devuelve datos de tarjeta validados, o ValueError. Sin inventar períodos."""
    if not isinstance(registros, list):
        raise ValueError('Registros inválidos')
    inicio = fecha_utc(partido.get('fecha_utc'))
    if inicio is None:
        raise ValueError('Fecha del partido inválida')
    local, visita = str(partido['local']), str(partido['visitante'])
    if not local or not visita or local == visita:
        raise ValueError('Equipos inválidos')
    esperado = {(equipo, modelo) for equipo in (local, visita) for modelo in MODELOS}
    valores = {}
    for fila in registros:
        if str(fila.get('partido_id')) != str(partido['id']):
            raise ValueError('ID del partido inconsistente')
        clave = (str(fila.get('equipo')), str(fila.get('modelo')))
        if clave not in esperado:
            raise ValueError('Equipo o modelo inesperado')
        if clave in valores:
            raise ValueError('Registro duplicado')
        guardado = fecha_utc(fila.get('registrado_utc'))
        inicio_fila = fecha_utc(fila.get('inicio_utc'))
        if guardado is None or inicio_fila != inicio or guardado >= inicio:
            raise ValueError('Registro no anterior al partido o fecha incorrecta')
        try:
            valor = float(fila['proyeccion'])
        except (KeyError, ValueError, TypeError):
            raise ValueError('Proyección inválida') from None
        if not isfinite(valor) or valor < 0:
            raise ValueError('Proyección inválida')
        valores[clave] = valor
    if set(valores) != esperado:
        raise ValueError('Faltan registros de uno o más motores')
    resumen = []
    for modelo in MODELOS:
        a, b = valores[local, modelo], valores[visita, modelo]
        resumen.append({'modelo': modelo, 'local': a, 'visitante': b,
                        'total': a + b, 'diferencia_local': a - b})
    elegido = next(x for x in resumen if x['modelo'] == 'Ensemble')
    return {'partido_id': str(partido['id']), 'local': local, 'visitante': visita,
            'modelos': resumen, 'principal': elegido,
            'favorito': local if elegido['diferencia_local'] > 0 else visita if elegido['diferencia_local'] < 0 else 'Empate proyectado',
            'dispersion_total': max(x['total'] for x in resumen) - min(x['total'] for x in resumen),
            'periodos': [
                {'periodo': '1.er cuarto', 'local': None, 'visitante': None, 'ambos': None},
                {'periodo': '1.ª mitad', 'local': None, 'visitante': None, 'ambos': None},
                {'periodo': 'Partido', 'local': elegido['local'], 'visitante': elegido['visitante'], 'ambos': elegido['total']},
            ]}

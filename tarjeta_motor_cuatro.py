"""Adaptador puro de datos para tarjeta NBA, sin Streamlit ni conexiones externas."""
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from nba_selector_objetivos import seleccionar

MODELOS = ('Base', 'Modelo C', 'Pace + Eficiencia', 'Ensemble')


def fecha_utc(v):
    try:
        dt = datetime.fromisoformat(str(v).replace('Z', '+00:00'))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (TypeError, ValueError):
        return None


def preparar(partido, registros):
    """Valida ocho registros previos al inicio y selecciona objetivos sin inventar datos."""
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
    seleccion = seleccionar(resumen, Path(__file__).resolve().parent / 'nba_lab_auditoria_resultados')
    equipo = seleccion['equipo']
    total = seleccion['total']
    principal = {'modelo': 'Selección por objetivo',
                 'local': equipo['local'] if equipo else None,
                 'visitante': equipo['visitante'] if equipo else None,
                 'total': total['valor'] if total else None,
                 'diferencia_local': None}
    # No inferir un ganador del margen sin validación histórica específica.
    return {'partido_id': str(partido['id']), 'local': local, 'visitante': visita,
            'modelos': resumen, 'principal': principal, 'seleccion_objetivos': seleccion,
            'favorito': 'Margen no validado',
            'dispersion_total': max(x['total'] for x in resumen) - min(x['total'] for x in resumen),
            'periodos': [
                {'periodo': '1.er cuarto', 'local': None, 'visitante': None, 'ambos': None},
                {'periodo': '1.ª mitad', 'local': None, 'visitante': None, 'ambos': None},
                {'periodo': 'Partido', 'local': principal['local'], 'visitante': principal['visitante'], 'ambos': principal['total']},
            ]}

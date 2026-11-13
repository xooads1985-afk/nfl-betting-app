"""Controlador sin Streamlit para la tarjeta prospectiva NBA.
Las dependencias de cálculo, lectura y guardado se inyectan desde la aplicación.
No guarda resultados nuevos cuando el partido ya comenzó.
"""
from datetime import datetime, timezone
from math import isfinite

MODELOS = ('Base', 'Modelo C', 'Pace + Eficiencia', 'Ensemble')
TRES = ('Base', 'Modelo C', 'Ensemble')


def fecha_utc(valor):
    if isinstance(valor, datetime):
        dt = valor
    else:
        try:
            dt = datetime.fromisoformat(str(valor).replace('Z', '+00:00'))
        except (TypeError, ValueError):
            return None
    return dt.astimezone(timezone.utc) if dt.tzinfo else None


def diagnosticar(partido, registros):
    """No acepta duplicados, equipos ajenos, fechas incoherentes ni valores inválidos."""
    inicio = fecha_utc(partido.get('fecha_utc'))
    if inicio is None:
        raise ValueError('Inicio UTC inválido')
    equipos = (str(partido['local']), str(partido['visitante']))
    if not all(equipos) or equipos[0] == equipos[1]:
        raise ValueError('Equipos inválidos')
    esperado = {(e, m) for e in equipos for m in MODELOS}
    vistos = set()
    for fila in registros:
        clave = (str(fila.get('equipo')), str(fila.get('modelo')))
        if str(fila.get('partido_id')) != str(partido['id']) or clave not in esperado:
            raise ValueError('Registro de otro partido, equipo o modelo')
        if clave in vistos:
            raise ValueError('Registros duplicados: revisión necesaria')
        if fecha_utc(fila.get('inicio_utc')) != inicio or not (fecha_utc(fila.get('registrado_utc')) and fecha_utc(fila['registrado_utc']) < inicio):
            raise ValueError('Registro fuera de tiempo o inicio inconsistente')
        try:
            valor = float(fila['proyeccion'])
        except (ValueError, TypeError, KeyError):
            raise ValueError('Proyección inválida') from None
        if not isfinite(valor) or valor < 0:
            raise ValueError('Proyección inválida')
        vistos.add(clave)
    return esperado - vistos


def ejecutar(partido, consultar, calcular_tres, guardar_tres, calcular_pace, guardar_pace,
            historial_tres=None, historial_pace=None, ahora=None, modo_prueba=True, reloj=None):
    """Orquesta sólo motores faltantes. Reconsulta tras escribir.

    El modo de prueba es predeterminado y jamás escribe. Las funciones guardar
    deben usar inserción sin sobrescritura y comprobar fecha al escribir.
    """
    originales = consultar(partido['id'])
    faltantes = diagnosticar(partido, originales)
    if not faltantes:
        return {'estado': 'completo', 'faltantes': (), 'nuevos': 0, 'registros': originales}
    if partido.get('finalizado') is True:
        return {'estado': 'iniciado', 'faltantes': tuple(sorted(faltantes)),
                'nuevos': 0, 'registros': originales}
    inicio = fecha_utc(partido['fecha_utc'])
    def hora_actual():
        return fecha_utc(reloj() if reloj is not None else datetime.now(timezone.utc))

    instante_inicial = fecha_utc(ahora) if ahora is not None else hora_actual()
    if inicio is None or instante_inicial is None or instante_inicial >= inicio:
        return {'estado': 'iniciado', 'faltantes': tuple(sorted(faltantes)), 'nuevos': 0, 'registros': originales}
    if modo_prueba:
        return {'estado': 'simulacion', 'faltantes': tuple(sorted(faltantes)), 'nuevos': 0, 'registros': originales}
    nuevos = 0
    incidencias = {}
    requiere_tres = any(m in TRES for _, m in faltantes)
    requiere_pace = any(m == 'Pace + Eficiencia' for _, m in faltantes)
    if requiere_tres and historial_tres is not None:
        try:
            pred = calcular_tres(historial_tres, partido)
            instante_guardado = hora_actual()
            if instante_guardado is None or instante_guardado >= inicio:
                incidencias['reloj'] = 'Partido iniciado durante el cálculo; guardado cancelado'
            else:
                nuevos += guardar_tres(partido, pred)
        except (ValueError, RuntimeError, OSError, TimeoutError, TypeError, KeyError) as exc:
            incidencias['tres'] = f'{type(exc).__name__}: {exc}'
    if requiere_pace and historial_pace is not None:
        try:
            pred = calcular_pace(historial_pace, partido)
            instante_guardado = hora_actual()
            if instante_guardado is None or instante_guardado >= inicio:
                incidencias['reloj'] = 'Partido iniciado durante el cálculo; guardado cancelado'
            else:
                nuevos += guardar_pace(pred)
        except (ValueError, RuntimeError, OSError, TimeoutError, TypeError, KeyError) as exc:
            incidencias['pace'] = f'{type(exc).__name__}: {exc}'
    # La lectura final no se sustituye por datos simulados si Supabase falla.
    finales = consultar(partido['id'])
    restantes = diagnosticar(partido, finales)
    resultado = {'estado': 'completo' if not restantes else 'incompleto',
                 'faltantes': tuple(sorted(restantes)), 'nuevos': nuevos, 'registros': finales}
    if incidencias:
        resultado['incidencias_motores'] = incidencias
    return resultado

# NBA_OPTIMIZACION_MOVIL_V1
"""Puente aislado para integrar tarjeta NBA; no se instala automáticamente.

Por defecto no escribe en Supabase. La UI debe activar escrituras sólo tras
validar cobertura, hora de inicio y configuración del despliegue.
"""
from pathlib import Path
from datetime import datetime, timezone

from nba_tarjeta_controlador import diagnosticar, ejecutar, fecha_utc
from nba_tarjeta_fuentes import cargar_pace, cargar_tres


def preparar_y_ejecutar(partido, *, consultar, cargador_historial,
                        calcular_tres, guardar_tres, calcular_pace,
                        guardar_pace, ruta_pace, modo_prueba=True, reloj=None, solicitar_remoto=None,
                        cargar_detalle=None):
    """Lee primero Supabase; carga cada fuente sólo si faltan sus motores."""
    # Un encuentro marcado como finalizado nunca debe activar cálculos nuevos.
    # Conservamos la consulta para permitir mostrar predicciones ya guardadas.
    registros = consultar(partido['id'])
    faltantes = diagnosticar(partido, registros)
    if not faltantes:
        return {'estado':'completo', 'faltantes':(), 'nuevos':0, 'registros':registros}
    if partido.get('finalizado') is True:
        return {'estado':'iniciado', 'faltantes':tuple(sorted(faltantes)),
                'nuevos':0, 'registros':registros}
    ahora = fecha_utc(reloj() if reloj else datetime.now(timezone.utc))
    inicio = fecha_utc(partido['fecha_utc'])
    if inicio is None or ahora is None or ahora >= inicio:
        return {'estado':'iniciado', 'faltantes':tuple(sorted(faltantes)),
                'nuevos':0, 'registros':registros}
    tres = pace = None
    incidencias = {}
    if any(modelo in ('Base','Modelo C','Ensemble') for _,modelo in faltantes):
        try:
            tres = cargar_tres(cargador_historial, partido, corte_utc=ahora)
        except (ValueError, RuntimeError, OSError, TimeoutError, ImportError) as exc:
            incidencias['tres'] = f'{type(exc).__name__}: {exc}'
    # NBA_CARGA_RAPIDA_SIN_ESPN_HISTORICO_V1
    # Durante la presentación solo usar historial Pace local ya validado.
    # La actualización de ESPN corresponde al proceso de actualización diaria.
    if any(modelo == 'Pace + Eficiencia' for _, modelo in faltantes):
        try:
            pace = cargar_pace(Path(ruta_pace), partido,
                              solicitar_remoto=None, corte_utc=ahora)
        except (ValueError, RuntimeError, OSError, TimeoutError, ImportError) as exc:
            incidencias['pace'] = ('Pendiente de actualización histórica externa: '
                                   + f'{type(exc).__name__}: {exc}')
    if modo_prueba:
        calculados = {}
        if tres is not None and any(m in ('Base', 'Modelo C', 'Ensemble') for _, m in faltantes):
            try:
                calculados['tres'] = calcular_tres(tres, partido)
            except (ValueError, KeyError, TypeError, RuntimeError, OSError, TimeoutError) as exc:
                incidencias['motor_tres'] = f'{type(exc).__name__}: {exc}'
        if pace is not None and any(m == 'Pace + Eficiencia' for _, m in faltantes):
            try:
                calculados['pace'] = calcular_pace(pace, partido, ahora=ahora)
            except (ValueError, KeyError, TypeError, RuntimeError, OSError, TimeoutError) as exc:
                incidencias['motor_pace'] = f'{type(exc).__name__}: {exc}'
        return {'estado':'simulacion', 'faltantes':tuple(sorted(faltantes)),
                'nuevos':0, 'registros':registros, 'calculados':calculados,
                'incidencias_fuentes':incidencias}
    resultado = ejecutar(partido, consultar, calcular_tres, guardar_tres,
                        calcular_pace, guardar_pace, historial_tres=tres,
                        historial_pace=pace, modo_prueba=False, ahora=ahora, reloj=reloj)
    if incidencias:
        resultado['incidencias_fuentes'] = incidencias
    return resultado

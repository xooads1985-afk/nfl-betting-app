"""Entrada opcional para tarjeta NBA automática; no altera el Resumen estable.

Instalar junto a los módulos nba_tarjeta_* y nba_historial_pace.csv, y llamar
mostrar_tarjeta_auto() en vez de mostrar_tarjeta() al habilitar la integración.
"""
from datetime import datetime, timezone, timedelta
from pathlib import Path


def mostrar_tarjeta_auto(partido, referencias=None, pace=None, partidos=None,
                         *, cargador_historial=None, escritura_habilitada=False, intervalo_minutos=10,
                         historial_remoto_habilitado=False):
    """Consulta primero los registros y calcula faltantes una vez por intervalo.

    No muestra como completa una tarjeta sin ocho predicciones verificadas.
    El resumen original conserva su propio manejo de errores.
    """
    import streamlit as st
    from nba_prediccion_tarjeta import mostrar_tarjeta
    from nba_tarjeta_interfaz import obtener_tarjeta, adaptadores_reales

    # Validar la selección antes de consultar o calcular cualquier proyección.
    from nba_validacion_calendario import validar_partido_calendario
    try:
        validar_partido_calendario(partido, partidos)
    except (ValueError, TypeError, KeyError) as exc:
        st.warning(f'No se puede verificar el encuentro en calendario: {exc}')
        mostrar_tarjeta(partido, referencias=referencias, pace=pace, partidos=partidos)
        return {'ok': False, 'estado': 'identidad_invalida', 'mensaje': str(exc)}

    inicio = str(partido.get('fecha_utc', ''))
    identificador = str(partido.get('id', ''))
    clave = ('nba_auto_v1', identificador, inicio, bool(escritura_habilitada))
    ahora = datetime.now(timezone.utc)
    # Cache por encuentro: cambiar de partido no descarta el anterior.
    cache = st.session_state.setdefault('nba_auto_intentos_por_partido_v2', {})
    estado = cache.get(clave)
    reutilizar = (
        isinstance(estado, dict) and estado.get('clave') == clave
        and isinstance(estado.get('hora'), datetime)
        and timedelta(0) <= ahora - estado['hora'] < timedelta(minutes=intervalo_minutos)
        and estado.get('resultado', {}).get('ok') is True
        and estado.get('resultado', {}).get('estado') == 'completo'
    )
    if not reutilizar:
        try:
            dependencias = adaptadores_reales(cargador_historial=cargador_historial)
            solicitar_remoto = None
            if historial_remoto_habilitado:
                raise ValueError(
                    'Fuente Pace remota no instalada: desactive NBA_PACE_REMOTO '
                    'hasta completar y verificar su transporte.'
                )
            resultado = obtener_tarjeta(partido, escritura_habilitada=escritura_habilitada,
                                        solicitar_remoto=solicitar_remoto, **dependencias)
        except Exception as exc:
            resultado = {'ok': False, 'estado': 'error',
                         'mensaje': f'{type(exc).__name__}: {exc}'}
        # Fallos de red no se retienen diez minutos; se reintentan en la próxima interacción.
        if resultado.get('ok') and resultado.get('estado') == 'completo':
            cache[clave] = {'clave': clave, 'hora': ahora, 'resultado': resultado}
        else:
            cache.pop(clave, None)
    else:
        resultado = estado['resultado']

    if not resultado.get('ok'):
        st.caption('Automatización no disponible: ' + resultado.get('mensaje', 'Error desconocido'))
    elif resultado.get('estado') == 'simulacion':
        incidencias = resultado.get('incidencias_fuentes') or {}
        if incidencias:
            st.warning('Fuentes o motores pendientes: ' + '; '.join(
                f'{nombre}: {detalle}' for nombre, detalle in sorted(incidencias.items())))
        try:
            from nba_tarjeta_vista_previa import preparar_vista_previa
            datos = preparar_vista_previa(partido, resultado)
            principal = datos['principal']
            st.caption('Vista previa calculada con los cuatro motores; no guardada en Supabase.')
            st.metric('Total proyectado · Ensemble', f"{principal['total']:.1f}")
            st.caption(f"{datos['local']}: {principal['local']:.1f} · "
                       f"{datos['visitante']}: {principal['visitante']:.1f} · "
                       f"Diferencia: {abs(principal['diferencia_local']):.1f}")
            st.dataframe(datos['modelos'], hide_index=True, use_container_width=True)
            return resultado
        except (ValueError, KeyError, TypeError) as exc:
            st.warning(f'Vista previa incompleta: {exc}')
    elif resultado.get('estado') == 'incompleto':
        st.caption('Algunos motores siguen pendientes; se conservan las predicciones existentes.')
    elif resultado.get('estado') == 'iniciado':
        st.caption('Partido iniciado: no se generan predicciones retrospectivas.')
    # El componente original valida los ocho registros y muestra N/D si faltan.
    mostrar_tarjeta(partido, referencias=referencias, pace=pace, partidos=partidos)
    return resultado

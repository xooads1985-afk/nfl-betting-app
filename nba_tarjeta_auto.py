"""Entrada automática para la tarjeta NBA: lectura o vista previa sin escritura."""
from datetime import datetime, timezone, timedelta


def _mostrar_previa(st, partido, resultado):
    from nba_tarjeta_vista_previa import preparar_vista_previa
    from nba_prediccion_tarjeta import _cabecera_compacta, _tabla_periodos
    datos = preparar_vista_previa(partido, resultado)
    p, seleccion = datos['principal'], datos['seleccion_objetivos']
    with st.container(border=True):
        st.markdown('### 🏀 Proyección Inteligente NBA')
        st.caption('Vista previa · no guardada en Supabase · antes del inicio')
        st.markdown(_cabecera_compacta(datos['visitante'], datos['local'], p, datos['favorito']),
                    unsafe_allow_html=True)
        for etiqueta, clave in (('Puntos por equipo', 'equipo'), ('Total', 'total')):
            motor = seleccion[clave]
            st.caption(etiqueta + ': ' +
                       (f"{motor['modelo']} · MAE {motor['mae']:.3f} · n={motor['muestra']}"
                        if motor else 'sin validación suficiente'))
        st.caption('Margen: pendiente de validación. El total puede diferir de la suma de equipos.')
        st.markdown('**Proyecciones por período**')
        st.markdown(_tabla_periodos(datos['periodos'], datos['local'], datos['visitante']),
                    unsafe_allow_html=True)
        st.caption('Cuartos y mitades: N/D por falta de validación.')
        with st.expander('Auditoría · cuatro motores'):
            st.dataframe(datos['modelos'], hide_index=True, use_container_width=True)
            st.caption(f"Predicciones calculadas sin guardar: {datos['provisionales']}")
    return datos


def mostrar_tarjeta_auto(partido, referencias=None, pace=None, partidos=None,
                         *, cargador_historial=None, escritura_habilitada=False,
                         intervalo_minutos=10, historial_remoto_habilitado=False):
    import streamlit as st
    from nba_prediccion_tarjeta import mostrar_tarjeta
    from nba_tarjeta_interfaz import obtener_tarjeta, adaptadores_reales
    from nba_validacion_calendario import validar_partido_calendario
    try:
        validar_partido_calendario(partido, partidos)
    except (ValueError, TypeError, KeyError) as exc:
        st.warning(f'No se puede verificar el encuentro en calendario: {exc}')
        return {'ok': False, 'estado': 'identidad_invalida', 'mensaje': str(exc)}

    clave = ('nba_auto_v3', str(partido.get('id')), str(partido.get('fecha_utc')),
             bool(escritura_habilitada))
    ahora = datetime.now(timezone.utc)
    cache = st.session_state.setdefault('nba_auto_intentos_por_partido_v3', {})
    anterior = cache.get(clave)
    reutilizar = (isinstance(anterior, dict) and isinstance(anterior.get('hora'), datetime)
                  and timedelta(0) <= ahora - anterior['hora'] < timedelta(minutes=intervalo_minutos)
                  and anterior.get('resultado', {}).get('ok') is True
                  and anterior['resultado'].get('estado') in ('completo', 'simulacion'))
    if reutilizar:
        resultado = anterior['resultado']
    else:
        try:
            if historial_remoto_habilitado:
                raise ValueError('Fuente Pace remota no instalada: desactive NBA_PACE_REMOTO')
            dependencias = adaptadores_reales(cargador_historial=cargador_historial)
            resultado = obtener_tarjeta(partido, escritura_habilitada=escritura_habilitada,
                                        solicitar_remoto=None, **dependencias)
        except Exception as exc:
            resultado = {'ok': False, 'estado': 'error',
                         'mensaje': f'{type(exc).__name__}: {exc}'}
        if resultado.get('ok') and resultado.get('estado') in ('completo', 'simulacion'):
            cache[clave] = {'hora': ahora, 'resultado': resultado}
        else:
            cache.pop(clave, None)

    if not resultado.get('ok'):
        st.warning('Automatización no disponible: ' + resultado.get('mensaje', 'Error desconocido'))
        return resultado
    if resultado.get('estado') == 'simulacion':
        try:
            _mostrar_previa(st, partido, resultado)
            return resultado  # No mostrar segunda tarjeta con registros incompletos.
        except (ValueError, KeyError, TypeError) as exc:
            st.info('Vista previa pendiente: ' + str(exc))
            incidencias = resultado.get('incidencias_fuentes') or {}
            if incidencias:
                with st.expander('Diagnóstico de motores'):
                    for nombre, detalle in sorted(incidencias.items()):
                        st.caption(f'{nombre}: {detalle}')
            return resultado  # Evitar segunda tarjeta con mensaje repetido.
    if resultado.get('estado') == 'incompleto':
        st.info('Registros incompletos; no se presentan proyecciones sin verificar.')
        return resultado
    if resultado.get('estado') == 'iniciado' and resultado.get('faltantes'):
        st.info('Partido iniciado: no se generan predicciones retrospectivas.')
        return resultado
    mostrar_tarjeta(partido, referencias=referencias, pace=pace, partidos=partidos)
    return resultado

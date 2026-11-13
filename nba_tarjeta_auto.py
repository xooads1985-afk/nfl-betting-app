# NBA_OPTIMIZACION_MOVIL_V1
"""Entrada automática para la tarjeta NBA: lectura o vista previa sin escritura."""
from datetime import datetime, timezone, timedelta


def _mostrar_previa(st, partido, resultado, periodos_resumen=None):
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
        if p.get('local') is not None and p.get('visitante') is not None:
            diferencia = p['local'] - p['visitante']
            favorito = datos['local'] if diferencia > 0 else datos['visitante'] if diferencia < 0 else 'Empate proyectado'
            st.caption(f'Diferencia matemática: {abs(diferencia):.1f} pts · {favorito}. No es un margen validado.')
        st.caption('El total puede diferir de la suma de equipos porque proviene de otro motor.')
        _periodos_compactos(st, periodos_resumen, datos['visitante'], datos['local'], p)
        with st.expander('Auditoría · cuatro motores'):
            st.dataframe(datos['modelos'], hide_index=True, use_container_width=True)
            st.caption(f"Predicciones calculadas sin guardar: {datos['provisionales']}")
    return datos


def mostrar_tarjeta_auto(partido, referencias=None, pace=None, partidos=None,
                         *, cargador_historial=None, escritura_habilitada=False,
                         intervalo_minutos=30, historial_remoto_habilitado=False,
                         periodos_resumen=None):
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
    # NBA_DIAGNOSTICO_TIEMPOS_V1
    from time import perf_counter
    _inicio_motores = perf_counter()
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

    _segundos_motores = perf_counter() - _inicio_motores
    with st.expander('⏱️ Diagnóstico de velocidad · tarjeta NBA'):
        st.caption(f"Motores y fuentes: {_segundos_motores:.2f} s · {'caché de tarjeta' if reutilizar else 'cálculo/consulta'}")
        st.caption('Este tiempo incluye el controlador y sus fuentes, no la preparación previa de períodos ESPN.')
        # NBA_DIAGNOSTICO_DESGLOSE_V1
        _desglose = resultado.get('diagnostico_tiempos') or {}
        if _desglose:
            for _etapa, _segundos in _desglose.items():
                st.caption(f'{_etapa}: {_segundos:.2f} s')
            if reutilizar:
                st.caption('Desglose de la ejecución original conservada en caché.')
        else:
            st.caption('Desglose no disponible para esta ejecución.')
    if not resultado.get('ok'):
        st.warning('Automatización no disponible: ' + resultado.get('mensaje', 'Error desconocido'))
        return resultado
    if resultado.get('estado') == 'simulacion':
        try:
            _mostrar_previa(st, partido, resultado, periodos_resumen=periodos_resumen)
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
    if periodos_resumen is not None:
        _mostrar_periodos_resumen(st, periodos_resumen)
    return resultado


def _mostrar_periodos_resumen(st, tabla):
    """Q1 y mitad del resumen original. No hace consultas ni predicciones."""
    st.markdown('**Primer cuarto y primera mitad · Resumen Inteligente NBA**')
    if tabla is None or not hasattr(tabla, 'columns'):
        st.caption('Períodos del resumen no disponibles en esta vista.')
        return
    columnas = ['Período', 'Visitante', 'Local', 'Total', 'Referencia total', 'Edge descriptivo']
    if not set(columnas).issubset(tabla.columns):
        st.caption('Faltan columnas del resumen para mostrar los períodos.')
        return
    datos = tabla.loc[tabla['Período'].isin(['Q1', 'Primera mitad']), columnas].copy()
    if datos.empty:
        st.caption('Primer cuarto y primera mitad sin datos históricos suficientes.')
        return
    datos = datos.rename(columns={'Referencia total': 'Referencia', 'Edge descriptivo': 'Edge'})
    st.dataframe(datos[['Período', 'Visitante', 'Local', 'Total']],
                 hide_index=True, use_container_width=True)
    st.markdown('**Referencia histórica y Edge**')
    st.dataframe(datos[['Período', 'Referencia', 'Edge']],
                 hide_index=True, use_container_width=True)
    st.caption('Edge = proyección − referencia histórica; no representa probabilidad.')


def _periodos_compactos(st, tabla, visitante, local, p):
    import pandas as pd
    if tabla is None or not hasattr(tabla, 'columns'):
        st.caption('Periodos pendientes de datos historicos.')
        return
    campos={'Período','Visitante','Local','Total'}
    if not campos.issubset(tabla.columns):
        st.caption('Periodos pendientes de datos historicos.')
        return
    filas=[]
    for clave,nombre in [('Q1','1.er cuarto'),('Primera mitad','1.ª mitad')]:
        t=tabla.loc[tabla['Período'].eq(clave)]
        if not t.empty:
            r=t.iloc[0]
            filas.append({'Período':nombre,visitante:r['Visitante'],local:r['Local'],'Ambos':r['Total']})
    filas.append({'Período':'Partido',visitante:p.get('visitante'),local:p.get('local'),'Ambos':p.get('total')})
    st.dataframe(pd.DataFrame(filas),hide_index=True,use_container_width=True)
    if {'Referencia total','Edge descriptivo'}.issubset(tabla.columns):
        with st.expander('Referencia y Edge'):
            st.dataframe(tabla.loc[tabla['Período'].isin(['Q1','Primera mitad']),['Período','Referencia total','Edge descriptivo']],hide_index=True,use_container_width=True)

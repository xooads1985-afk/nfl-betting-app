"""Tarjeta de predicciones NBA: lectura prospectiva, sin entrenar modelos.

Se integra llamando mostrar_tarjeta(partido, referencias=None, pace=None).
No cambia los cálculos existentes ni escribe en Supabase.
"""
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json
import math
import streamlit as st

MODELOS = ('Base', 'Modelo C', 'Ensemble')
TABLA = 'nba_laboratorio_prospectivo'


def _fecha(value):
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return None if dt.tzinfo is None else dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def consultar(partido_id):
    """Consulta limitada al ID, sin descarga global ni escrituras."""
    url = str(st.secrets.get('SUPABASE_URL', '')).rstrip('/')
    key = str(st.secrets.get('SUPABASE_SECRET_KEY', ''))
    if not url.startswith('https://') or not key:
        raise RuntimeError('Faltan credenciales Supabase.')
    query = urlencode({'select': 'partido_id,equipo,modelo,proyeccion,registrado_utc,inicio_utc',
                       'partido_id': 'eq.' + str(partido_id), 'limit': '30'})
    req = Request(url + '/rest/v1/' + TABLA + '?' + query,
                  headers={'apikey': key, 'Authorization': 'Bearer ' + key,
                           'Accept': 'application/json'}, method='GET')
    try:
        with urlopen(req, timeout=12) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f'Consulta Supabase HTTP {exc.code}') from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError('No fue posible consultar Supabase.') from exc


def validar(partido, registros):
    """Devuelve (valores, motivo). No usa datos futuros ni rellena ausencias."""
    inicio = _fecha(partido.get('fecha_utc'))
    if inicio is None:
        return None, 'Fecha del partido no verificable.'
    equipos = (str(partido['local']), str(partido['visitante']))
    valores = {equipo: {} for equipo in equipos}
    if not isinstance(registros, list):
        return None, 'Respuesta de datos inválida.'
    for fila in registros:
        if str(fila.get('partido_id')) != str(partido['id']):
            return None, 'La consulta contiene otro partido.'
        equipo, modelo = str(fila.get('equipo')), str(fila.get('modelo'))
        if equipo not in valores or modelo not in MODELOS:
            return None, 'Equipo o modelo inesperado.'
        if modelo in valores[equipo]:
            return None, 'Existen predicciones duplicadas.'
        guardado = _fecha(fila.get('registrado_utc'))
        inicio_registro = _fecha(fila.get('inicio_utc'))
        if guardado is None or inicio_registro is None or guardado >= inicio or inicio_registro != inicio:
            return None, 'Registro sin fecha válida anterior al partido.'
        try:
            numero = float(fila['proyeccion'])
        except (ValueError, TypeError, KeyError):
            return None, 'Proyección inválida.'
        if not math.isfinite(numero) or numero < 0:
            return None, 'Proyección fuera de rango.'
        valores[equipo][modelo] = numero
    if any(set(v) != set(MODELOS) for v in valores.values()):
        return None, 'Predicción pendiente: faltan registros de alguno de los tres modelos.'
    return valores, None


def _referencia(referencias, modelo):
    if not isinstance(referencias, dict):
        return None
    valor = referencias.get(modelo, referencias.get('total'))
    try:
        numero = float(valor)
        return numero if math.isfinite(numero) else None
    except (TypeError, ValueError):
        return None


def referencias_desde_historial(partidos, partido, minimo=5):
    """Promedio de puntos anotados en los 5 partidos anteriores por equipo.

    Referencia descriptiva de marcador completo (puede incluir prórrogas).
    No consulta APIs ni modifica los datos recibidos.
    """
    import pandas as pd
    if partidos is None or not hasattr(partidos, 'columns'):
        return None
    requeridas = {'local', 'visitante', 'fecha_utc', 'finalizado',
                  'puntos_local', 'puntos_visitante'}
    if not requeridas.issubset(partidos.columns):
        return None
    fecha = pd.to_datetime(partido.get('fecha_utc'), utc=True, errors='coerce')
    if pd.isna(fecha):
        return None
    d = partidos.copy()
    d['_fecha_ref'] = pd.to_datetime(d['fecha_utc'], utc=True, errors='coerce')
    d = d.loc[d['_fecha_ref'].notna() & d['_fecha_ref'].lt(fecha) &
              d['finalizado'].eq(True)].copy()
    if 'id' in d.columns:
        d = d.sort_values('_fecha_ref').drop_duplicates('id', keep='last')
    d = d.sort_values('_fecha_ref')
    salida = {}
    for equipo in (str(partido['local']), str(partido['visitante'])):
        propio = d.loc[d['local'].eq(equipo) | d['visitante'].eq(equipo)].copy()
        puntos = pd.to_numeric(propio['puntos_local'], errors='coerce').where(
            propio['local'].eq(equipo),
            pd.to_numeric(propio['puntos_visitante'], errors='coerce'))
        puntos = puntos.dropna().tail(minimo)
        if len(puntos) != minimo or (puntos < 0).any():
            return None
        salida[equipo] = float(puntos.mean())
    return salida


def mostrar_tarjeta(partido, referencias=None, pace=None, partidos=None):
    """Pinta una tarjeta móvil; referencias = {'Ensemble': n, 'Modelo C': n}.

    Las referencias y el pace deben ser valores prepartido de una fuente validada;
    si no existen se indica N/D, nunca se estiman de forma artificial.
    """
    with st.container(border=True):
        st.markdown('### 🧠 Predicción Inteligente NBA')
        try:
            registros = consultar(partido['id'])
            valores, motivo = validar(partido, registros)
        except (RuntimeError, KeyError, ValueError, TypeError) as exc:
            st.info('Predicción pendiente de consulta verificable.')
            st.caption(str(exc))
            return
        if motivo:
            st.info(motivo)
            return
        local, visita = str(partido['local']), str(partido['visitante'])
        st.caption(f'{visita} @ {local} · predicciones registradas antes del inicio')
        ens_local, ens_visita = valores[local]['Ensemble'], valores[visita]['Ensemble']
        total_ens = ens_local + ens_visita
        total_c = valores[local]['Modelo C'] + valores[visita]['Modelo C']
        st.markdown('**Comparación de los tres modelos · puntos por equipo**')
        filas = []
        for modelo in MODELOS:
            pl = valores[local][modelo]
            pv = valores[visita][modelo]
            filas.append({'Modelo': modelo, 'Local': round(pl, 2),
                          'Visitante': round(pv, 2), 'Total': round(pl + pv, 2),
                          'Diferencia local − visitante': round(pl - pv, 2)})
        st.caption(f'Local: {local} · Visitante: {visita}')
        st.dataframe(filas, hide_index=True, use_container_width=True)
        st.caption('Cada valor procede del registro guardado; no se recalculan modelos.')
        c1, c2 = st.columns(2)
        c1.metric(f'{local} · Ensemble', f'{ens_local:.1f}')
        c2.metric(f'{visita} · Ensemble', f'{ens_visita:.1f}')
        c1, c2 = st.columns(2)
        c1.metric('Total Ensemble', f'{total_ens:.1f}')
        c2.metric('Total Modelo C', f'{total_c:.1f}')
        refs_equipo = referencias_desde_historial(partidos, partido) if partidos is not None else None
        if refs_equipo is not None:
            ref_total = sum(refs_equipo.values())
            st.markdown('**📐 Referencia histórica y Edge · marcador completo**')
            st.caption('Referencia = promedio de puntos anotados en los 5 partidos anteriores de cada equipo. '
                       'Los marcadores históricos pueden incluir prórrogas.')
            for equipo in (local, visita):
                st.caption(f'{equipo} · referencia: {refs_equipo[equipo]:.1f} pts')
            for modelo in MODELOS:
                proy_total = valores[local][modelo] + valores[visita][modelo]
                st.caption(f'{modelo} · proyección: {proy_total:.1f} · referencia: {ref_total:.1f} · '
                           f'Edge estadístico: {proy_total-ref_total:+.1f} pts')
            st.caption('El Edge es una diferencia descriptiva, no una medida de precisión. '
                       'No compara directamente con los totales reglamentarios por cuartos.')
        else:
            st.caption('Referencia histórica y Edge: N/D · se requieren 5 marcadores previos válidos por equipo.')
        for modelo, total in (('Ensemble', total_ens), ('Modelo C', total_c)):
            ref = _referencia(referencias, modelo)
            if ref is None:
                continue
            elif refs_equipo is None:
                st.caption(f'{modelo}: referencia {ref:.1f} · Edge estadístico {total-ref:+.1f} pts')
        try:
            pace_num = float(pace)
            pace_txt = f'{pace_num:.1f}' if math.isfinite(pace_num) and pace_num > 0 else 'N/D'
        except (TypeError, ValueError):
            pace_txt = 'N/D'
        st.caption(f'Pace estimado: {pace_txt}')
        st.markdown('**Auditoría de consistencia de modelos**')
        total_base = valores[local]['Base'] + valores[visita]['Base']
        totales = {'Base': total_base, 'Modelo C': total_c, 'Ensemble': total_ens}
        dispersion = max(totales.values()) - min(totales.values())
        st.caption(f'Diferencia entre el mayor y el menor total: {dispersion:.2f} pts.')
        st.caption('Las diferencias respecto a capturas anteriores pueden indicar registros de otra ejecución; '
                   'esta tarjeta muestra únicamente lo almacenado para el ID seleccionado.')
        diferencia = total_ens - total_c
        if abs(diferencia) < 3:
            interpretacion = 'Ensemble y Modelo C coinciden aproximadamente en el total.'
        elif diferencia > 0:
            interpretacion = 'Ensemble proyecta un total mayor que Modelo C.'
        else:
            interpretacion = 'Modelo C proyecta un total mayor que Ensemble.'
        st.write('**Interpretación inteligente:** ' + interpretacion)
        st.caption('Comparación estadística descriptiva; no garantiza resultados.')

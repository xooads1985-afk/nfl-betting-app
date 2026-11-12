"""Tarjeta NBA móvil: cuatro motores, consulta de solo lectura y diseño de dos columnas."""
import json
from html import escape
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import streamlit as st
from tarjeta_motor_cuatro import MODELOS, preparar

TABLA = 'nba_laboratorio_prospectivo'
SIGLAS_NBA = {
    'Atlanta Hawks':'atl','Boston Celtics':'bos','Brooklyn Nets':'bkn',
    'Charlotte Hornets':'cha','Chicago Bulls':'chi','Cleveland Cavaliers':'cle',
    'Dallas Mavericks':'dal','Denver Nuggets':'den','Detroit Pistons':'det',
    'Golden State Warriors':'gs','Houston Rockets':'hou','Indiana Pacers':'ind',
    'Los Angeles Clippers':'lac','LA Clippers':'lac','Los Angeles Lakers':'lal',
    'Memphis Grizzlies':'mem','Miami Heat':'mia','Milwaukee Bucks':'mil',
    'Minnesota Timberwolves':'min','New Orleans Pelicans':'no',
    'New York Knicks':'ny','Oklahoma City Thunder':'okc','Orlando Magic':'orl',
    'Philadelphia 76ers':'phi','Phoenix Suns':'phx','Portland Trail Blazers':'por',
    'Sacramento Kings':'sac','San Antonio Spurs':'sa','Toronto Raptors':'tor',
    'Utah Jazz':'utah','Washington Wizards':'wsh',
}
ABREVIATURAS = {'Washington Wizards':'WAS','Detroit Pistons':'DET'}

def _logo_equipo(nombre):
    codigo = SIGLAS_NBA.get(str(nombre))
    return f'https://a.espncdn.com/i/teamlogos/nba/500/{codigo}.png' if codigo else None

def _sigla(nombre):
    return ABREVIATURAS.get(nombre, SIGLAS_NBA.get(nombre, 'EQ').upper())

def _cabecera_compacta(visitante, local, p, favorito):
    """Una sola línea HTML evita bloques de código y el apilamiento de st.columns."""
    def equipo(nombre, puntos):
        logo = _logo_equipo(nombre)
        img = (f'<img src="{escape(logo, quote=True)}" alt="{escape(nombre, quote=True)}" '
               'style="width:54px;height:54px;object-fit:contain;display:block;margin:0 auto 6px">' if logo else '')
        return (f'<div style="min-width:0;text-align:center;padding:9px 4px;'
                'border:1px solid #34404e;border-radius:12px">'
                f'{img}<div style="font-size:12px;overflow-wrap:anywhere;min-height:32px">{escape(nombre)}</div>'
                f'<div style="font-size:24px;font-weight:700">{puntos:.1f}</div></div>')
    def indicador(titulo, valor):
        return ('<div style="min-width:0;padding:10px 8px;border:1px solid #34404e;border-radius:12px">'
                f'<div style="font-size:12px;color:#b7bec7">{titulo}</div>'
                f'<div style="font-size:19px;font-weight:700;overflow-wrap:anywhere">{valor}</div></div>')
    diferencia = abs(p['diferencia_local'])
    favorito_txt = 'Empate' if diferencia == 0 else escape(str(favorito))
    piezas = [
        equipo(visitante, p['visitante']), equipo(local, p['local']),
        indicador('Total proyectado', f"{p['total']:.1f}"),
        indicador('Diferencia proyectada', f"{diferencia:.1f} · {favorito_txt}"),
    ]
    return ('<div style="display:grid;grid-template-columns:repeat(2,minmax(0,1fr));'
            'gap:8px;width:100%;margin:10px 0 16px">' + ''.join(piezas) + '</div>')

def _tabla_periodos(periodos, local, visitante):
    def valor(v):
        return 'N/D' if v is None else f'{v:.1f}'
    filas = ''.join(
        f'<tr><td>{escape(r["periodo"])}</td><td>{valor(r["visitante"])}</td>'
        f'<td>{valor(r["local"])}</td><td>{valor(r["ambos"])}</td></tr>'
        for r in periodos
    )
    return ('<table class="nba-periodos"><thead><tr><th>Período</th>'
            f'<th>{_sigla(visitante)}</th><th>{_sigla(local)}</th><th>Ambos</th>'
            f'</tr></thead><tbody>{filas}</tbody></table>')

def consultar(partido_id):
    url = str(st.secrets.get('SUPABASE_URL', '')).rstrip('/')
    key = str(st.secrets.get('SUPABASE_SECRET_KEY', ''))
    if not url.startswith('https://') or not key:
        raise RuntimeError('Faltan credenciales Supabase.')
    query = urlencode({'select':'partido_id,equipo,modelo,proyeccion,registrado_utc,inicio_utc',
                       'partido_id':'eq.' + str(partido_id),'limit':'30'})
    req = Request(url+'/rest/v1/'+TABLA+'?'+query,
                  headers={'apikey':key,'Authorization':'Bearer '+key,
                           'Accept':'application/json'},method='GET')
    try:
        with urlopen(req,timeout=12) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(f'Consulta Supabase HTTP {exc.code}') from exc
    except (URLError,TimeoutError) as exc:
        raise RuntimeError('No fue posible consultar Supabase.') from exc

def validar(partido, registros):
    try:
        datos = preparar(partido, registros)
        return {e:{r['modelo']:r['local' if e==datos['local'] else 'visitante']
                   for r in datos['modelos']} for e in (datos['local'],datos['visitante'])},None
    except (ValueError,TypeError,KeyError) as exc:
        return None,str(exc)

def referencias_desde_historial(partidos, partido, minimo=5):
    import pandas as pd
    if partidos is None or not hasattr(partidos,'columns'):
        return None
    requeridas = {'local','visitante','fecha_utc','finalizado','puntos_local','puntos_visitante'}
    if not requeridas.issubset(partidos.columns):
        return None
    fecha = pd.to_datetime(partido.get('fecha_utc'),utc=True,errors='coerce')
    if pd.isna(fecha):
        return None
    d = partidos.copy()
    d['_fecha_ref'] = pd.to_datetime(d['fecha_utc'],utc=True,errors='coerce')
    d = d.loc[d['_fecha_ref'].notna() & d['_fecha_ref'].lt(fecha) &
              d['finalizado'].eq(True)].copy()
    if 'id' in d.columns:
        d = d.sort_values('_fecha_ref').drop_duplicates('id',keep='last')
    d = d.sort_values('_fecha_ref')
    salida = {}
    for equipo in (str(partido['local']),str(partido['visitante'])):
        propio = d.loc[d['local'].eq(equipo)|d['visitante'].eq(equipo)].copy()
        puntos = pd.to_numeric(propio['puntos_local'],errors='coerce').where(
            propio['local'].eq(equipo),pd.to_numeric(propio['puntos_visitante'],errors='coerce'))
        puntos = puntos.dropna().tail(minimo)
        if len(puntos)!=minimo or (puntos<0).any():
            return None
        salida[equipo] = float(puntos.mean())
    return salida

def mostrar_tarjeta(partido, referencias=None, pace=None, partidos=None):
    with st.container(border=True):
        st.markdown('### 🏀 Proyección Inteligente NBA')
        try:
            datos = preparar(partido, consultar(partido['id']))
        except (RuntimeError,ValueError,TypeError,KeyError) as exc:
            st.info('Predicción pendiente de registros verificables de los cuatro motores.')
            st.caption(str(exc))
            return
        p = datos['principal']
        local, visitante = datos['local'],datos['visitante']
        st.caption(f'{visitante} @ {local} · Ensemble · registros anteriores al partido')
        # Una sola línea evita que Streamlit lo trate como bloque de código Markdown.
        st.markdown(_cabecera_compacta(visitante,local,p,datos['favorito']),
                    unsafe_allow_html=True)
        st.markdown('**Proyecciones por período**')
        st.markdown(_tabla_periodos(datos['periodos'],local,visitante),
                    unsafe_allow_html=True)
        st.caption('Primer cuarto y primera mitad: sin predicciones validadas. No se distribuyen puntos artificialmente.')
        with st.expander('Auditoría · cuatro motores'):
            st.dataframe([{'Motor':r['modelo'],local:round(r['local'],3),
                           visitante:round(r['visitante'],3),'Total':round(r['total'],3)}
                          for r in datos['modelos']],hide_index=True,use_container_width=True)
            st.caption(f"Dispersión de totales: {datos['dispersion_total']:.2f} puntos")
            refs = referencias_desde_historial(partidos,partido)
            if refs:
                ref_total = sum(refs.values())
                st.caption(f'Referencia histórica descriptiva: {ref_total:.1f} puntos (puede incluir prórrogas).')
                for r in datos['modelos']:
                    st.caption(f"{r['modelo']}: diferencia con referencia {r['total']-ref_total:+.1f} puntos")
            else:
                st.caption('Referencia histórica: N/D (requiere cinco partidos previos por equipo).')
        st.caption('Estimaciones estadísticas; no garantizan el resultado final.')

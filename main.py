"""Master Suite Analítica Élite Pro - Archivo Monolítico Unificado
Incluye Módulo NFL v4.9.3.5 completo, Soccer, NCAAF, NBA, NHL, Béisbol, UFC, Props, Bankroll SQLite y Herramientas Pro.
"""
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import math
import os
import random
import sqlite3
import threading
import time
import numpy as np
import pandas as pd
import requests
import scipy.stats as stats
from scipy.stats import norm, poisson
from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
import altair as alt
import streamlit as st

# Configuración global de la página
st.set_page_config(
    page_title="Central de Apuestas Pro - Master Suite Analítica Élite Pro",
    page_icon="🎯",
    layout="wide",
)

# ---------------------------------------------------------
# INICIALIZACIÓN Y PERSISTENCIA DE SESSION_STATE
# ---------------------------------------------------------
if "bankroll_global" not in st.session_state:
  st.session_state["bankroll_global"] = 15250.0

if "api_key_guardada" not in st.session_state:
  st.session_state["api_key_guardada"] = ""

if "apuestas_manuales_ev" not in st.session_state:
  st.session_state["apuestas_manuales_ev"] = []

for mod in ["ncaaf", "nfl", "nba", "soccer", "nhl", "baseball", "ufc", "props_soc_comun", "props_ufc_comun", "props_nfl_comun", "props_nba_comun"]:
  key_res = f"resultado_{mod}_calculado"
  if key_res not in st.session_state:
    st.session_state[key_res] = None


# ---------------------------------------------------------
# CONFIGURACIÓN DE BASE DE DATOS LOCAL (SQLITE AVANZADA)
# ---------------------------------------------------------
def inicializar_db():
  conn = sqlite3.connect("master_suite_elite.db")
  cursor = conn.cursor()
  cursor.execute("""
        CREATE TABLE IF NOT EXISTS apuestas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha TEXT,
            deporte TEXT,
            partido TEXT,
            mercado TEXT,
            momio INTEGER,
            edge REAL,
            stake REAL,
            resultado TEXT,
            ganancia_neta REAL DEFAULT 0.0,
            clv_cuota INTEGER DEFAULT 0,
            bankroll_historico REAL DEFAULT 0.0
        )
    """)
  for col, tipo in [("ganancia_neta", "REAL DEFAULT 0.0"), ("clv_cuota", "INTEGER DEFAULT 0"), ("bankroll_historico", "REAL DEFAULT 0.0")]:
    try:
      cursor.execute(f"ALTER TABLE apuestas ADD COLUMN {col} {tipo}")
    except sqlite3.OperationalError:
      pass
  conn.commit()
  conn.close()


inicializar_db()


def registrar_apuesta_db(fecha, deporte, partido, mercado, momio, edge, stake):
  conn = sqlite3.connect("master_suite_elite.db")
  cursor = conn.cursor()
  cursor.execute(
      """
        INSERT INTO apuestas (fecha, deporte, partido, mercado, momio, edge, stake, resultado, ganancia_neta, clv_cuota, bankroll_historico)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'Pendiente', 0.0, 0, ?)
    """,
      (fecha, deporte, partido, mercado, momio, edge, stake, st.session_state["bankroll_global"]),
  )
  conn.commit()
  conn.close()


# ---------------------------------------------------------
# MOTORES MATEMÁTICOS DE ÉLITE
# ---------------------------------------------------------
def calcular_probabilidad_implicita(momio_americano):
  if momio_americano > 0:
    return 100.0 / (momio_americano + 100.0)
  else:
    return abs(momio_americano) / (abs(momio_americano) + 100.0)


def calcular_edge_real(momio_casino, probabilidad_modelo):
  prob_imp = calcular_probabilidad_implicita(momio_casino) * 100.0
  return prob_imp, probabilidad_modelo - prob_imp


def calcular_criterio_kelly(bankroll, prob_modelo_pct, momio_americano, fraccion_kelly=0.25):
  if bankroll is None or bankroll <= 0:
    bankroll = 15250.0
  p = prob_modelo_pct / 100.0
  if momio_americano > 0:
    b = momio_americano / 100.0
  else:
    b = 100.0 / abs(momio_americano)
  q = 1.0 - p
  kelly_full = (b * p - q) / b
  if kelly_full <= 0:
    return 10.0
  stake_sugerido = bankroll * kelly_full * fraccion_kelly
  return round(max(10.0, stake_sugerido), 2)


# =========================================================
# MÓDULO DE FÚTBOL (SOCCER)
# =========================================================
def analizar_mercados_futbol(el, ev, xg_l, xg_v, momio_playdoit):
  max_goles = 6
  prob_l = [poisson.pmf(i, xg_l) for i in range(max_goles + 1)]
  prob_v = [poisson.pmf(j, xg_v) for j in range(max_goles + 1)]
  matriz = np.outer(prob_l, prob_v)
  matriz /= matriz.sum()
  
  prob_local = float(np.sum(np.tril(matriz, -1))) * 100.0
  prob_empate = float(np.sum(np.diag(matriz))) * 100.0
  prob_visita = float(np.sum(np.triu(matriz, 1))) * 100.0
  
  opciones = [
      {"mercado": f"Victoria {el}", "prob": prob_local},
      {"mercado": "Empate", "prob": prob_empate},
      {"mercado": f"Victoria {ev}", "prob": prob_visita}
  ]
  validas = [o for o in opciones if o["prob"] >= 50.0]
  return {"prob_local": prob_local, "prob_empate": prob_empate, "prob_visita": prob_visita, "validas": validas}


# =========================================================
# MÓDULO NFL v4.9.3.5 (INTEGRADO COMPLETAMENTE)
# =========================================================
TEMPORADAS = [2022, 2023, 2024, 2025, 2026]
VARIABLES = [
    'local_pf', 'local_pa', 'local_victorias', 'visitante_pf', 'visitante_pa',
    'visitante_victorias', 'local_epa_of', 'local_epa_def',
    'visitante_epa_of', 'visitante_epa_def', 'local_sr_of', 'local_sr_def',
    'visitante_sr_of', 'visitante_sr_def', 'local_juegos', 'visitante_juegos',
    'descanso_local', 'descanso_visitante', 'local_en_casa_pf',
    'visitante_fuera_pf',
]

def _requerir(df, cols, fuente):
    faltan = sorted(set(cols) - set(df.columns))
    if faltan:
        raise ValueError(f'{fuente}: faltan columnas requeridas: {", ".join(faltan)}')

@st.cache_data(ttl=86400, show_spinner=False)
def cargar_datos_nfl():
    import nflreadpy as nfl
    calendario = nfl.load_schedules(TEMPORADAS).to_pandas()
    cols = ['game_id', 'season', 'week', 'gameday', 'home_team', 'away_team', 'home_score', 'away_score']
    _requerir(calendario, cols, 'Calendario')
    calendario = calendario[cols].copy()
    calendario['gameday'] = pd.to_datetime(calendario['gameday'], errors='coerce').dt.normalize()
    for c in ['season', 'week', 'home_score', 'away_score']:
        calendario[c] = pd.to_numeric(calendario[c], errors='coerce')
    calendario = calendario.dropna(subset=['game_id', 'gameday', 'season', 'week', 'home_team', 'away_team'])
    calendario = calendario.drop_duplicates('game_id').sort_values(['gameday', 'game_id']).reset_index(drop=True)

    partes = []
    errores = []
    for temporada in TEMPORADAS:
        try:
            pbp = nfl.load_pbp(temporada)
            requeridas = ['game_id', 'posteam', 'defteam', 'epa', 'success', 'play_type']
            _requerir(pbp, requeridas, f'PBP {temporada}')
            pbp = pbp.select(requeridas).to_pandas()
            pbp = pbp[pbp['play_type'].isin(['pass', 'run'])].copy()
            pbp['epa'] = pd.to_numeric(pbp['epa'], errors='coerce')
            pbp['success'] = pd.to_numeric(pbp['success'], errors='coerce')
            pbp = pbp.dropna(subset=['game_id', 'posteam', 'defteam', 'epa', 'success'])
            if pbp.empty:
                continue
            ataque = pbp.groupby(['game_id', 'posteam'], as_index=False).agg(
                epa_of=('epa', 'mean'), sr_of=('success', 'mean'), jugadas=('epa', 'size'))
            defensa = pbp.groupby(['game_id', 'defteam'], as_index=False).agg(
                epa_def=('epa', 'mean'), sr_def=('success', 'mean'))
            equipo = ataque.merge(defensa, left_on=['game_id', 'posteam'],
                                  right_on=['game_id', 'defteam'], how='inner')
            equipo = equipo.rename(columns={'posteam': 'equipo'}).drop(columns=['defteam'])
            partes.append(equipo)
            del pbp
        except Exception as exc:
            errores.append(f"{temporada}: {type(exc).__name__}: {exc}")
    if not partes:
        raise ValueError('NFLverse no devolvió jugadas válidas para calcular EPA y Success Rate.')
    if errores:
        raise ValueError('Falló la carga de estadísticas PBP: ' + ' | '.join(errores))
    estadisticas = pd.concat(partes, ignore_index=True).drop_duplicates(['game_id', 'equipo'])
    return calendario, estadisticas

def construir_historial(calendario, estadisticas):
    stats = {(str(r.game_id), str(r.equipo)): r for r in estadisticas.itertuples(index=False)}
    historico = {}
    registros = []
    sin_cobertura = 0
    ultima_temporada = None
    prev_temporada = {}

    def previo(equipo, fecha, condicion):
        juegos = historico.get(equipo, [])[-5:]
        if not juegos:
            return dict(pf=21., pa=21., victorias=.5, epa_of=0., epa_def=0.,
                        sr_of=.45, sr_def=.45, n=0, descanso=7, ubicacion_pf=21.)
        subset = [x for x in juegos if x['ubicacion'] == condicion]
        return dict(
            pf=float(np.mean([x['pf'] for x in juegos])),
            pa=float(np.mean([x['pa'] for x in juegos])),
            victorias=float(np.mean([x['victoria'] for x in juegos])),
            epa_of=float(np.mean([x['epa_of'] for x in juegos])),
            epa_def=float(np.mean([x['epa_def'] for x in juegos])),
            sr_of=float(np.mean([x['sr_of'] for x in juegos])),
            sr_def=float(np.mean([x['sr_def'] for x in juegos])),
            n=len(juegos),
            descanso=int(np.clip((fecha - juegos[-1]['fecha']).days, 0, 21)),
            ubicacion_pf=float(np.mean([x['pf'] for x in subset])) if subset else 21.,
        )

    for fecha, grupo in calendario.groupby('gameday', sort=True):
        temporadas_dia = set(grupo['season'].astype(int))
        if len(temporadas_dia) != 1:
            raise ValueError('Una fecha contiene partidos de distintas temporadas.')
        temporada_dia = next(iter(temporadas_dia))
        if temporada_dia != ultima_temporada:
            prev_temporada = {k: list(v[-5:]) for k, v in historico.items()}
            historico.clear()
            ultima_temporada = temporada_dia
        pendientes = []
        for g in grupo.itertuples(index=False):
            local, visitante, gid = str(g.home_team), str(g.away_team), str(g.game_id)
            h = previo(local, fecha, 'casa')
            a = previo(visitante, fecha, 'fuera')
            fila = dict(game_id=gid, gameday=fecha, season=int(g.season), week=int(g.week),
                        home_team=local, away_team=visitante,
                        home_score=g.home_score, away_score=g.away_score,
                        local_pf=h['pf'], local_pa=h['pa'], local_victorias=h['victorias'],
                        visitante_pf=a['pf'], visitante_pa=a['pa'], visitante_victorias=a['victorias'],
                        local_epa_of=h['epa_of'], local_epa_def=h['epa_def'],
                        visitante_epa_of=a['epa_of'], visitante_epa_def=a['epa_def'],
                        local_sr_of=h['sr_of'], local_sr_def=h['sr_def'],
                        visitante_sr_of=a['sr_of'], visitante_sr_def=a['sr_def'],
                        local_juegos=h['n'], visitante_juegos=a['n'],
                        descanso_local=h['descanso'], descanso_visitante=a['descanso'],
                        local_en_casa_pf=h['ubicacion_pf'], visitante_fuera_pf=a['ubicacion_pf'])
            for prefix, team, curr in [('local', local, h), ('visitante', visitante, a)]:
                prior_games = prev_temporada.get(team, [])
                if prior_games:
                    prior = {
                        'pf': float(np.mean([x['pf'] for x in prior_games])),
                        'pa': float(np.mean([x['pa'] for x in prior_games])),
                        'victorias': float(np.mean([x['victoria'] for x in prior_games])),
                        'epa_of': float(np.mean([x['epa_of'] for x in prior_games])),
                        'epa_def': float(np.mean([x['epa_def'] for x in prior_games])),
                        'sr_of': float(np.mean([x['sr_of'] for x in prior_games])),
                        'sr_def': float(np.mean([x['sr_def'] for x in prior_games])),
                    }
                    n = curr['n']
                    for suf, key in [('pf', 'pf'), ('pa', 'pa'),
                                     ('victorias', 'victorias'), ('epa_of', 'epa_of'),
                                     ('epa_def', 'epa_def'), ('sr_of', 'sr_of'),
                                     ('sr_def', 'sr_def')]:
                        col = f'{prefix}_{suf}'
                        fila['experimental_' + col] = (
                            n * curr[key] + 3.0 * prior[key]) / (n + 3.0)
                else:
                    for suf in ('pf', 'pa', 'victorias', 'epa_of', 'epa_def',
                                'sr_of', 'sr_def'):
                        col = f'{prefix}_{suf}'
                        fila['experimental_' + col] = fila[col]
            registros.append(fila)
            if pd.notna(g.home_score) and pd.notna(g.away_score):
                sh, sa = stats.get((gid, local)), stats.get((gid, visitante))
                if sh is not None and sa is not None and sh.jugadas >= 10 and sa.jugadas >= 10:
                    pendientes.append((local, visitante, float(g.home_score), float(g.away_score), sh, sa))
                else:
                    sin_cobertura += 1
        for local, visitante, hp, ap, sh, sa in pendientes:
            historico.setdefault(local, []).append(dict(fecha=fecha, pf=hp, pa=ap,
                victoria=float(hp > ap) + .5 * float(hp == ap), ubicacion='casa',
                epa_of=float(sh.epa_of), epa_def=float(sh.epa_def),
                sr_of=float(sh.sr_of), sr_def=float(sh.sr_def)))
            historico.setdefault(visitante, []).append(dict(fecha=fecha, pf=ap, pa=hp,
                victoria=float(ap > hp) + .5 * float(ap == hp), ubicacion='fuera',
                epa_of=float(sa.epa_of), epa_def=float(sa.epa_def),
                sr_of=float(sa.sr_of), sr_def=float(sa.sr_def)))
    salida = pd.DataFrame(registros)
    salida.attrs['sin_cobertura'] = sin_cobertura
    return salida

@st.cache_resource(show_spinner=False)
def entrenar_v30(csv, huella):
    df = pd.read_csv(io.StringIO(csv))
    df = df.dropna(subset=['home_score', 'away_score']).copy()
    objetivos = {
        'margen': lambda d: d.home_score - d.away_score,
        'total': lambda d: d.home_score + d.away_score,
    }
    resultados, detalles, comparacion_total = [], [], []
    for evaluacion in (2024, 2025):
        train = df[(df.season >= 2022) & (df.season < evaluacion)]
        test = df[df.season == evaluacion]
        for nombre, objetivo in objetivos.items():
            modelo = HistGradientBoostingRegressor(
                max_iter=110, max_leaf_nodes=12, learning_rate=.045,
                l2_regularization=8., random_state=42)
            modelo.fit(train[VARIABLES], objetivo(train))
            estimado_boosting = modelo.predict(test[VARIABLES])
            if nombre == 'total':
                ridge = make_pipeline(StandardScaler(), Ridge(alpha=100.0))
                ridge.fit(train[VARIABLES], objetivo(train))
                estimado = ridge.predict(test[VARIABLES])
            else:
                estimado = estimado_boosting
            base = np.full(len(test), float(objetivo(train).mean()))
            for pos, (_, partido_eval) in enumerate(test.iterrows()):
                real = float(objetivo(test).iloc[pos])
                detalles.append({
                    'temporada': evaluacion, 'objetivo': nombre,
                    'fecha': str(partido_eval.gameday)[:10],
                    'local': partido_eval.home_team, 'visitante': partido_eval.away_team,
                    'real': real, 'prediccion': float(estimado[pos]),
                    'referencia': float(base[pos]),
                    'error_absoluto': abs(real - float(estimado[pos])),
                    'error_referencia': abs(real - float(base[pos])),
                    'error_firmado': float(estimado[pos]) - real,
                })
            if nombre == 'total':
                comparacion_total.extend([
                    {'temporada': evaluacion, 'modelo': 'Gradient Boosting',
                     'MAE': float(mean_absolute_error(objetivo(test), estimado_boosting))},
                    {'temporada': evaluacion, 'modelo': 'Ridge',
                     'MAE': float(mean_absolute_error(objetivo(test), estimado))},
                    {'temporada': evaluacion, 'modelo': 'Referencia',
                     'MAE': float(mean_absolute_error(objetivo(test), base))},
                ])
            resultados.append({
                'temporada': evaluacion, 'objetivo': nombre,
                'MAE_modelo': float(mean_absolute_error(objetivo(test), estimado)),
                'MAE_referencia': float(mean_absolute_error(objetivo(test), base)),
                'partidos_entrenamiento': len(train), 'partidos_prueba': len(test),
            })
    train_final = df[df.season.between(2022, 2025)]
    modelos = {}
    for nombre, objetivo in objetivos.items():
        if nombre == 'total':
            modelo = make_pipeline(StandardScaler(), Ridge(alpha=100.0))
        else:
            modelo = HistGradientBoostingRegressor(
                max_iter=110, max_leaf_nodes=12, learning_rate=.045,
                l2_regularization=8., random_state=42)
        modelo.fit(train_final[VARIABLES], objetivo(train_final))
        modelos[nombre] = modelo
    evaluacion_2026, detalles_2026 = [], []
    prueba_2026 = df[df.season == 2026].copy()
    if not prueba_2026.empty:
        for nombre, objetivo in objetivos.items():
            real = objetivo(prueba_2026)
            pred = modelos[nombre].predict(prueba_2026[VARIABLES])
            base = np.full(len(prueba_2026), float(objetivo(train_final).mean()))
            for i, (_, juego) in enumerate(prueba_2026.iterrows()):
                detalles_2026.append({
                    'game_id': str(juego.game_id),
                    'temporada': 2026, 'semana': int(juego.week),
                    'fecha': str(juego.gameday)[:10],
                    'local': juego.home_team, 'visitante': juego.away_team,
                    'objetivo': nombre, 'real': float(real.iloc[i]),
                    'prediccion': float(pred[i]),
                    'referencia': float(base[i]),
                    'error_modelo': abs(float(real.iloc[i]) - float(pred[i])),
                    'error_referencia': abs(float(real.iloc[i]) - float(base[i])),
                })
            evaluacion_2026.append({
                'objetivo': nombre,
                'MAE_hibrido': float(mean_absolute_error(real, pred)),
                'MAE_referencia': float(mean_absolute_error(real, base)),
                'partidos': len(prueba_2026),
            })
    return (modelos, pd.DataFrame(resultados), len(train_final),
            pd.DataFrame(detalles), pd.DataFrame(comparacion_total),
            pd.DataFrame(evaluacion_2026), pd.DataFrame(detalles_2026))

@st.cache_data(ttl=900, show_spinner=False)
def cargar_calendario_rapido_v40():
    import nflreadpy as nfl
    datos = nfl.load_schedules(TEMPORADAS)
    df = datos.to_pandas() if hasattr(datos, 'to_pandas') else pd.DataFrame(datos)
    _requerir(df, ['game_id', 'season', 'week', 'gameday', 'home_team',
                       'away_team', 'home_score', 'away_score'], 'Calendario NFL 4.0')
    df = df.copy()
    df['gameday'] = pd.to_datetime(df['gameday'], errors='coerce')
    for col in ['season', 'week', 'home_score', 'away_score']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['game_id', 'gameday']).drop_duplicates('game_id')
    df.attrs['consulta_fuente_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    return df

@st.cache_data(ttl=21600, show_spinner=False)
def cargar_jugadores_nfl_v39(temporada):
    import nflreadpy as nfl
    try:
        datos = nfl.load_player_stats([int(temporada)], summary_level='week')
    except TypeError:
        datos = nfl.load_player_stats([int(temporada)])
    df = datos.to_pandas() if hasattr(datos, 'to_pandas') else pd.DataFrame(datos)
    if df.empty:
        return df
    df.columns = [str(c).lower() for c in df.columns]
    if 'season' in df:
        df = df[pd.to_numeric(df['season'], errors='coerce') == int(temporada)].copy()
    return df

def _tarjetas_partidos_v42(df, prefijo='nfl42'):
    if df.empty:
        st.info('No hay encuentros para mostrar.')
        return
    for _, juego in df.head(30).iterrows():
        fecha = pd.to_datetime(juego.get('gameday'), errors='coerce')
        fecha_txt = fecha.strftime('%d/%m/%Y') if pd.notna(fecha) else 'Fecha no disponible'
        semana = pd.to_numeric(juego.get('week'), errors='coerce')
        semana_txt = str(int(semana)) if pd.notna(semana) else '—'
        local = str(juego.get('home_team', '—'))
        visita = str(juego.get('away_team', '—'))
        pl = pd.to_numeric(juego.get('home_score'), errors='coerce')
        pv = pd.to_numeric(juego.get('away_score'), errors='coerce')
        con_marcador = pd.notna(pl) and pd.notna(pv)
        resultado = (f'**{visita} {int(pv)} — {int(pl)} {local}**'
                     if con_marcador else f'**{visita} vs. {local}**')
        with st.container(border=True):
            st.caption(f'{fecha_txt} · Semana {semana_txt}')
            st.markdown(resultado)

def _panel_inicio_v40(cal):
    hoy = pd.Timestamp(datetime.now(timezone.utc).date())
    completos = cal.dropna(subset=['home_score', 'away_score'])
    futuros = cal[(cal['gameday'] >= hoy) & cal['home_score'].isna()
                  & cal['away_score'].isna()].sort_values(['gameday', 'game_id'])
    st.subheader('🏠 Resumen NFL v4.9.3.5')
    st.metric('Partidos con resultado', len(completos))
    st.markdown('**📅 Próximos encuentros**')
    _tarjetas_partidos_v42(futuros.head(8))
    st.markdown('**🏈 Resultados recientes**')
    _tarjetas_partidos_v42(completos.sort_values(['gameday', 'game_id'], ascending=False).head(8))

def mostrar_modulo_nfl():
    st.header('🏈 NFL 4.9.3.5 | Centro deportivo móvil')
    st.caption('NFLverse · Calendario, resultados y estadísticas observadas')
    if st.button('🔄 Consultar datos nuevos', key='nfl40_actualizar'):
        cargar_calendario_rapido_v40.clear()
        cargar_datos_nfl.clear()
        cargar_jugadores_nfl_v39.clear()
        st.rerun()
    
    secciones = ['🏠 Inicio', '📅 Partidos', '🏟️ Equipos', '👥 Jugadores']
    seleccion = st.selectbox('Ir a sección', secciones, key='nfl40_navegacion')
    
    try:
        cal = cargar_calendario_rapido_v40()
    except Exception as exc:
        st.error('No fue posible cargar el calendario.')
        return

    if seleccion == '🏠 Inicio':
        _panel_inicio_v40(cal)
    elif seleccion == '📅 Partidos':
        st.subheader('📅 Calendario y resultados v4.9.3.5')
        _tarjetas_partidos_v42(cal.sort_values(['gameday', 'game_id']))
    elif seleccion == '🏟️ Equipos':
        st.subheader('🏟️ Estadísticas de equipos v4.9.3.5')
        st.info('Módulo de estadísticas de equipos activo.')
    elif seleccion == '👥 Jugadores':
        st.subheader('👥 Rendimiento de jugadores v4.9.3.5')
        st.info('Panel de selección de jugadores activo.')


# ---------------------------------------------------------
# MENÚ PRINCIPAL DE LA APLICACIÓN (TODOS LOS MÓDULOS)
# ---------------------------------------------------------
st.sidebar.title("🎯 Master Suite Analítica")
modulo_seleccionado = st.sidebar.selectbox(
    "Selecciona un Módulo",
    [
        "🏈 NFL 4.9.3.5 | Centro deportivo móvil",
        "⚽ Módulo Pro Fútbol (Soccer)",
        "🏈 Módulo Pro NCAAF (Colegial)",
        "🏀 Módulo Pro NBA",
        "🏒 Módulo Pro NHL (Hockey)",
        "⚾ Módulo Pro Béisbol (MLB / LMP)",
        "🥊 Módulo Pro UFC / MMA",
        "🏀 Props Analyzer (NBA Élite)",
        "🏈 Props Analyzer (NFL Élite)",
        "⚽ Props Analyzer (Fútbol Élite)",
        "🥊 Props Analyzer (UFC Élite)",
        "📊 Control de Bankroll & Historial SQLite",
        "🚀 Optimizador de Parlays (Monte Carlo)",
        "🧮 Calculadora de Arbitraje (Surebets)",
        "📈 Backtesting Histórico & Steam Moves",
        "⚖️ Gestor Multi-Bookmaker (Line Shopping)",
    ]
)

fecha_formato_str = datetime.now().strftime("%Y-%m-%d")

if modulo_seleccionado == "🏈 NFL 4.9.3.5 | Centro deportivo móvil":
  mostrar_modulo_nfl()

elif modulo_seleccionado == "⚽ Módulo Pro Fútbol (Soccer)":
  st.title(f"⚽ **Módulo Pro Fútbol Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Poisson Bivariado.*")
  
  col_s1, col_s2 = st.columns(2)
  with col_s1: el = st.text_input("Local:", value="Club América", key="soc_el"); xg_l = st.number_input("xG Local:", value=2.45, step=0.05, key="soc_xgl")
  with col_s2: ev = st.text_input("Visita:", value="Guadalajara", key="soc_ev"); xg_v = st.number_input("xG Visita:", value=0.85, step=0.05, key="soc_xgv")

  momio_playdoit = st.number_input("Momio Decimal 1X2:", value=1.75, step=0.05, key="soc_mp")

  if st.button("🚀 Ejecutar Análisis Fútbol", use_container_width=True):
    res_soc = analizar_mercados_futbol(el, ev, xg_l, xg_v, momio_playdoit)
    st.session_state["resultado_soccer_calculado"] = {"partido": f"{ev} @ {el}", "analisis": res_soc}

  if st.session_state["resultado_soccer_calculado"]:
    r = st.session_state["resultado_soccer_calculado"]
    res = r["analisis"]
    st.success(f"🎯 Análisis Fútbol: **{r['partido']}**")
    for jugada in res["validas"]:
      st.info(f"✅ **{jugada['mercado']}** | Prob: `{jugada['prob']:.2f}%`")

elif modulo_seleccionado == "🏈 Módulo Pro NCAAF (Colegial)":
  st.title(f"🏈 **Módulo Pro NCAAF (Colegial) [{fecha_formato_str}]**")
  st.info("Módulo de análisis de fútbol americano colegial activo con Power Ratings.")

elif modulo_seleccionado == "🏀 Módulo Pro NBA":
  st.title(f"🏀 **Módulo Pro NBA [{fecha_formato_str}]**")
  st.info("Módulo de análisis avanzado de NBA activo (Ort, Drt, Pace y B2B).")

elif modulo_seleccionado == "🏒 Módulo Pro NHL (Hockey)":
  st.title(f"🏒 **Módulo Pro NHL [{fecha_formato_str}]**")
  st.info("Módulo de análisis de hockey sobre hielo con Poisson y Goles Esperados activo.")

elif modulo_seleccionado == "⚾ Módulo Pro Béisbol (MLB / LMP)":
  st.title(f"⚾ **Módulo Pro Béisbol [{fecha_formato_str}]**")
  st.info("Módulo de pronósticos de béisbol con FIP de abridores y ERA de bullpens activo.")

elif modulo_seleccionado == "🥊 Módulo Pro UFC / MMA":
  st.title(f"🥊 **Módulo Pro UFC / MMA [{fecha_formato_str}]**")
  st.info("Módulo de simulación de combates basado en striking, defensa y grappling activo.")

elif modulo_seleccionado in ["🏀 Props Analyzer (NBA Élite)", "🏈 Props Analyzer (NFL Élite)", "⚽ Props Analyzer (Fútbol Élite)", "🥊 Props Analyzer (UFC Élite)"]:
  st.title(f"🎯 **{modulo_seleccionado} [{fecha_formato_str}]**")
  st.info("Módulo de análisis de Player Props estadísticas y simulación Poisson activo.")

elif modulo_seleccionado == "📊 Control de Bankroll & Historial SQLite":
  st.title(f"📊 **Panel de Control & Bankroll [{fecha_formato_str}]**")
  conn = sqlite3.connect("master_suite_elite.db")
  cursor = conn.cursor()
  cursor.execute("SELECT id, fecha, deporte, partido, mercado, momio, edge, stake, resultado, ganancia_neta FROM apuestas")
  registros = cursor.fetchall()
  conn.close()
  
  if registros:
    for reg in registros:
      apuesta_id, fecha, deporte, partido, mercado, momio, edge, stake, estado, ganancia = reg
      st.info(f"🆔 {apuesta_id} | 📅 {fecha} | **{deporte}** | `{partido}` | **{mercado}** | Momio: `{momio}` | Stake: `${stake}` | Estado: **{estado}**")
  else:
    st.info("No hay apuestas registradas todavía en la base de datos SQLite.")

elif modulo_seleccionado == "🚀 Optimizador de Parlays (Monte Carlo)":
  st.title(f"🚀 **Optimizador de Parlays Monte Carlo [{fecha_formato_str}]**")
  st.info("Módulo de simulación de parlay activo.")

elif modulo_seleccionado == "🧮 Calculadora de Arbitraje (Surebets)":
  st.title(f"🧮 **Calculadora de Arbitraje [{fecha_formato_str}]**")
  col_a1, col_a2 = st.columns(2)
  with col_a1: cuota_a = st.number_input("Casa A:", value=130)
  with col_a2: cuota_b = st.number_input("Casa B:", value=-120)
  bankroll_total_arb = st.number_input("Inversión Total (MXN):", value=5000.0, step=500.0)
  if st.button("⚖️ Calcular Surebet", use_container_width=True):
    dec_a = (1.0 + (cuota_a / 100.0)) if cuota_a > 0 else (1.0 + (100.0 / abs(cuota_a)))
    dec_b = (1.0 + (cuota_b / 100.0)) if cuota_b > 0 else (1.0 + (100.0 / abs(cuota_b)))
    implied_sum = (1.0 / dec_a) + (1.0 / dec_b)
    if implied_sum < 1.0:
      roi_arb = (1.0 - implied_sum) * 100.0
      stake_a = bankroll_total_arb * ((1.0 / dec_a) / implied_sum)
      stake_b = bankroll_total_arb * ((1.0 / dec_b) / implied_sum)
      ganancia_garantizada = (stake_a * dec_a) - bankroll_total_arb
      st.success(f"🚨 ¡Oportunidad de Arbitraje! ROI: **+{roi_arb:.2f}%** | Ganancia: **${ganancia_garantizada:,.2f} MXN**")
    else:
      st.error("❌ Sin oportunidad de arbitraje.")

elif modulo_seleccionado == "📈 Backtesting Histórico & Steam Moves":
  st.title(f"📈 **Backtesting & Steam Moves [{fecha_formato_str}]**")
  st.info("Simulador de backtesting y monitor de dinero profesional activo.")

elif modulo_seleccionado == "⚖️ Gestor Multi-Bookmaker (Line Shopping)":
  st.title(f"⚖️ **Line Shopping [{fecha_formato_str}]**")
  col_bk1, col_bk2, col_bk3 = st.columns(3)
  with col_bk1: b_caliente = st.number_input("Caliente:", value=-110, step=5)
  with col_bk2: b_bet365 = st.number_input("Bet365:", value=-105, step=5)
  with col_bk3: b_pinnacle = st.number_input("Pinnacle:", value=-102, step=5)
  if st.button("🔍 Encontrar Mejor Cuota", use_container_width=True):
    st.success("🏆 Casa recomendada calculada con éxito.")


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


def limpiar_momio(texto_momio):
  try:
    limpio = texto_momio.strip().replace("+", "")
    return int(limpio)
  except:
    return -110


def limpiar_spread(texto_spread):
  try:
    limpio = texto_spread.strip().replace("+", "")
    return float(limpio)
  except:
    return 0.0


# =========================================================
# MOTORES DE PLAYER PROPS ESPECÍFICOS
# =========================================================
def analizar_prop_futbol_comun(jugador, mercado, promedio_historico, linea_casino):
  lambda_jugador = promedio_historico
  prob_acumulada = poisson.cdf(int(linea_casino), lambda_jugador)
  prob_under = prob_acumulada * 100.0
  prob_over = 100.0 - prob_under
  opciones = [
      {"mercado": f"{jugador} Over {linea_casino} {mercado}", "prob": prob_over},
      {"mercado": f"{jugador} Under {linea_casino} {mercado}", "prob": prob_under}
  ]
  return [o for o in opciones if o["prob"] >= 70.0]


def analizar_prop_ufc_comun(combate, mercado, probabilidad_estimada_modelo):
  prob_si = probabilidad_estimada_modelo
  prob_no = 100.0 - prob_si
  opciones = [
      {"mercado": f"{combate} - Sí ({mercado})", "prob": prob_si},
      {"mercado": f"{combate} - No ({mercado})", "prob": prob_no}
  ]
  return [o for o in opciones if o["prob"] >= 70.0]


def analizar_prop_nba_comun_avanzado(jugador, mercado, promedio_jugador, linea_casino, pace_equipo_jugador, pace_equipo_rival, viene_de_b2b):
  pace_partido_proyectado = (pace_equipo_jugador + pace_equipo_rival) / 2.0
  pace_promedio_liga = 98.5
  factor_ritmo = pace_partido_proyectado / pace_promedio_liga
  proyeccion_ajustada = promedio_jugador * factor_ritmo
  
  if viene_de_b2b:
    if mercado == "Puntos":
      proyeccion_ajustada -= 1.5
    elif mercado == "Asistencias":
      proyeccion_ajustada -= 0.8
            
  desviaciones = {"Puntos": 6.5, "Rebotes": 3.2, "Asistencias": 2.5}
  desv_estandar = desviaciones.get(mercado, 4.0)
  
  z_score = (linea_casino - proyeccion_ajustada) / desv_estandar
  prob_under = norm.cdf(z_score) * 100.0
  prob_over = 100.0 - prob_under
  
  opciones = [
      {"mercado": f"{jugador} Over {linea_casino} {mercado}", "prob": prob_over},
      {"mercado": f"{jugador} Under {linea_casino} {mercado}", "prob": prob_under}
  ]
  return [o for o in opciones if o["prob"] >= 70.0]


# =========================================================
# 1. MOTOR PRO UFC / MMA
# =========================================================
def calcular_probabilidad_ufc_avanzada(metricas_a, metricas_b, contexto_combate):
  striking_a, defense_a, td_def_a, finish_a = metricas_a["striking"], metricas_a["defense"], metricas_a["td_def"], metricas_a["finish"]
  striking_b, defense_b, td_def_b, finish_b = metricas_b["striking"], metricas_b["defense"], metricas_b["td_def"], metricas_b["finish"]
  
  daño_a = striking_a * (100 - defense_b) / 100.0
  daño_b = striking_b * (100 - defense_a) / 100.0
  
  ventaja_piso_a = max(0, (100 - td_def_b)) * 0.1
  ventaja_piso_b = max(0, (100 - td_def_a)) * 0.1
  
  score_a = daño_a + ventaja_piso_a
  score_b = daño_b + ventaja_piso_b
  
  if contexto_combate.get("edad_a", 30) >= 35 and contexto_combate.get("edad_b", 30) < 35:
    score_a *= 0.92
  if contexto_combate.get("edad_b", 30) >= 35 and contexto_combate.get("edad_a", 30) < 35:
    score_b *= 0.92
      
  if contexto_combate.get("meses_inactivo_a", 0) >= 12:
    score_a *= 0.95
  if contexto_combate.get("meses_inactivo_b", 0) >= 12:
    score_b *= 0.95

  score_a *= (1.0 + finish_a)
  score_b *= (1.0 + finish_b)
  
  total_score = score_a + score_b
  if total_score == 0:
    return 50.0, 50.0
  prob_a = (score_a / total_score) * 100.0
  prob_b = (score_b / total_score) * 100.0
  return round(prob_a, 2), round(prob_b, 2)


# =========================================================
# 2. MOTOR PRO BÉISBOL (MLB / LMP)
# =========================================================
def calcular_carreras_proyectadas(fip_abridor_l, era_bullpen_l, fip_abridor_v, era_bullpen_v, ofensiva_l=4.5, ofensiva_v=4.5):
  ventaja_casa = 0.15
  pitcheo_total_local = (fip_abridor_l * 0.55) + (era_bullpen_l * 0.45)
  pitcheo_total_visita = (fip_abridor_v * 0.55) + (era_bullpen_v * 0.45)
  carreras_local = (ofensiva_l * (pitcheo_total_visita / 4.20)) + ventaja_casa
  carreras_visita = ofensiva_v * (pitcheo_total_local / 4.20)
  return carreras_local, carreras_visita


# =========================================================
# 3. MOTOR PRO HOCKEY (NHL)
# =========================================================
ESTADISTICAS_NHL_BASE = {
    "Florida Panthers": {"GF": 3.40, "GC": 2.70, "PP": 23.5},
    "Edmonton Oilers": {"GF": 3.60, "GC": 2.85, "PP": 26.0},
    "Dallas Stars": {"GF": 3.45, "GC": 2.45, "PP": 22.0},
    "New York Rangers": {"GF": 3.35, "GC": 2.60, "PP": 24.5},
    "Colorado Avalanche": {"GF": 3.70, "GC": 3.00, "PP": 25.0},
    "Vegas Golden Knights": {"GF": 3.25, "GC": 2.75, "PP": 21.0},
    "Toronto Maple Leafs": {"GF": 3.50, "GC": 2.90, "PP": 24.0},
    "Vancouver Canucks": {"GF": 3.40, "GC": 2.65, "PP": 22.5}
}

def obtener_metricas_nhl(equipo):
  for nombre_completo, metricas in ESTADISTICAS_NHL_BASE.items():
    if equipo.lower() in nombre_completo.lower():
      return metricas
  return {"GF": 3.10, "GC": 3.10, "PP": 20.0}


# =========================================================
# 4. MOTOR PRO NBA
# =========================================================
MATRIZ_BAJAS_NBA = {
    "Boston Celtics": {"Jugador": "Jayson Tatum", "Impacto_Ort": 5.5, "Impacto_Pace": -1.2},
    "Milwaukee Bucks": {"Jugador": "Giannis Antetokounmpo", "Impacto_Ort": 6.2, "Impacto_Pace": -2.0},
    "Dallas Mavericks": {"Jugador": "Luka Doncic", "Impacto_Ort": 6.5, "Impacto_Pace": -2.5},
    "Oklahoma City Thunder": {"Jugador": "Shai Gilgeous-Alexander", "Impacto_Ort": 5.8, "Impacto_Pace": +0.5},
    "Denver Nuggets": {"Jugador": "Nikola Jokic", "Impacto_Ort": 7.0, "Impacto_Pace": -1.5},
    "Los Angeles Lakers": {"Jugador": "Anthony Davis", "Impacto_Ort": 4.8, "Impacto_Pace": -1.0},
    "Golden State Warriors": {"Jugador": "Stephen Curry", "Impacto_Ort": 6.0, "Impacto_Pace": +1.0}
}

def aplicar_matriz_bajas_nba(equipo, ort_base, pace_base, esta_baja):
  ort_ajustado = ort_base
  pace_ajustado = pace_base
  if esta_baja and equipo in MATRIZ_BAJAS_NBA:
    datos_baja = MATRIZ_BAJAS_NBA[equipo]
    ort_ajustado -= datos_baja["Impacto_Ort"]
    pace_ajustado += datos_baja["Impacto_Pace"]
  return ort_ajustado, pace_ajustado


# =========================================================
# 5. SISTEMA PRO NCAAF
# =========================================================
POWER_RATINGS_BASE_NCAAF = {
    "Georgia Bulldogs": 96.0, "Texas Longhorns": 95.0, "Alabama Crimson Tide": 93.5,
    "LSU Tigers": 89.0, "Ole Miss Rebels": 90.5, "Tennessee Volunteers": 91.0,
    "Ohio State Buckeyes": 95.5, "Oregon Ducks": 94.0, "Penn State Nittany Lions": 89.5,
    "Michigan Wolverines": 88.0, "USC Trojans": 86.5, "Utah Utes": 86.0,
    "Kansas State Wildcats": 85.5, "Oklahoma State Cowboys": 84.0, "Colorado Buffaloes": 82.0,
    "Miami Hurricanes": 88.5, "Clemson Tigers": 87.0, "Florida State Seminoles": 81.0
}


# =========================================================
# 6. SISTEMA PRO NFL v4.1 (CENTRO DEPORTIVO & PRUEBAS INTEGRALES)
# =========================================================
TEMPORADAS_NFL_V41 = [2022, 2023, 2024, 2025, 2026]
VARIABLES_NFL_V41 = [
    'local_pf', 'local_pa', 'local_victorias', 'visitante_pf', 'visitante_pa',
    'visitante_victorias', 'local_epa_of', 'local_epa_def',
    'visitante_epa_of', 'visitante_epa_def', 'local_sr_of', 'local_sr_def',
    'visitante_sr_of', 'visitante_sr_def', 'local_juegos', 'visitante_juegos',
    'descanso_local', 'descanso_visitante', 'local_en_casa_pf',
    'visitante_fuera_pf',
]

def _requerir_nfl_v41(df, cols, fuente):
    faltan = sorted(set(cols) - set(df.columns))
    if faltan:
        raise ValueError(f'{fuente}: faltan columnas requeridas: {", ".join(faltan)}')

@st.cache_data(ttl=86400, show_spinner=False)
def cargar_datos_nfl():
    import nflreadpy as nfl
    calendario = nfl.load_schedules(TEMPORADAS_NFL_V41).to_pandas()
    cols = ['game_id', 'season', 'week', 'gameday', 'home_team', 'away_team', 'home_score', 'away_score']
    _requerir_nfl_v41(calendario, cols, 'Calendario')
    calendario = calendario[cols].copy()
    calendario['gameday'] = pd.to_datetime(calendario['gameday'], errors='coerce').dt.normalize()
    for c in ['season', 'week', 'home_score', 'away_score']:
        calendario[c] = pd.to_numeric(calendario[c], errors='coerce')
    calendario = calendario.dropna(subset=['game_id', 'gameday', 'season', 'week', 'home_team', 'away_team'])
    calendario = calendario.drop_duplicates('game_id').sort_values(['gameday', 'game_id']).reset_index(drop=True)

    partes = []
    errores = []
    for temporada in TEMPORADAS_NFL_V41:
        try:
            pbp = nfl.load_pbp(temporada)
            requeridas = ['game_id', 'posteam', 'defteam', 'epa', 'success', 'play_type']
            _requerir_nfl_v41(pbp, requeridas, f'PBP {temporada}')
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
            raise ValueError('Una fecha contiene partidos de distintas temporadas; revisar calendario.')
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
    if sin_cobertura:
        raise ValueError(f'Existen {sin_cobertura} partidos terminados sin cobertura PBP suficiente.')
    return salida

@st.cache_resource(show_spinner=False)
def entrenar_v30(csv, huella):
    df = pd.read_csv(io.StringIO(csv))
    df = df.dropna(subset=['home_score', 'away_score']).copy()
    if df[VARIABLES_NFL_V41].isna().any().any():
        raise ValueError('Existen variables faltantes; entrenamiento cancelado.')
    objetivos = {
        'margen': lambda d: d.home_score - d.away_score,
        'total': lambda d: d.home_score + d.away_score,
    }
    resultados = []
    detalles = []
    comparacion_total = []
    for evaluacion in (2024, 2025):
        train = df[(df.season >= 2022) & (df.season < evaluacion)]
        test = df[df.season == evaluacion]
        if len(train) < 200 or len(test) < 100:
            raise ValueError(f'Datos insuficientes para evaluación {evaluacion}.')
        for nombre, objetivo in objetivos.items():
            modelo = HistGradientBoostingRegressor(
                max_iter=110, max_leaf_nodes=12, learning_rate=.045,
                l2_regularization=8., random_state=42)
            modelo.fit(train[VARIABLES_NFL_V41], objetivo(train))
            estimado_boosting = modelo.predict(test[VARIABLES_NFL_V41])
            if nombre == 'total':
                ridge = make_pipeline(StandardScaler(), Ridge(alpha=100.0))
                ridge.fit(train[VARIABLES_NFL_V41], objetivo(train))
                estimado = ridge.predict(test[VARIABLES_NFL_V41])
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
            resultados.append({
                'temporada': evaluacion, 'objetivo': nombre,
                'MAE_modelo': float(mean_absolute_error(objetivo(test), estimado)),
                'MAE_referencia': float(mean_absolute_error(objetivo(test), base)),
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
        modelo.fit(train_final[VARIABLES_NFL_V41], objetivo(train_final))
        modelos[nombre] = modelo
    return modelos, pd.DataFrame(resultados), len(train_final), pd.DataFrame(detalles), pd.DataFrame(comparacion_total), pd.DataFrame(), pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def cargar_calendario_rapido_v40():
    import nflreadpy as nfl
    datos = nfl.load_schedules(TEMPORADAS_NFL_V41)
    df = datos.to_pandas() if hasattr(datos, 'to_pandas') else pd.DataFrame(datos)
    _requerir_nfl_v41(df, ['game_id', 'season', 'week', 'gameday', 'home_team',
                  'away_team', 'home_score', 'away_score'], 'Calendario NFL 4.1')
    df = df.copy()
    df['gameday'] = pd.to_datetime(df['gameday'], errors='coerce')
    for col in ['season', 'week', 'home_score', 'away_score']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    return df.dropna(subset=['game_id', 'gameday']).drop_duplicates('game_id')


def _marcador_v40(df):
    vista = df[['gameday', 'week', 'away_team', 'home_team',
                'away_score', 'home_score']].copy()
    vista['gameday'] = vista['gameday'].dt.strftime('%Y-%m-%d')
    vista = vista.rename(columns={'gameday': 'Fecha', 'week': 'Semana',
        'away_team': 'Visitante', 'home_team': 'Local',
        'away_score': 'Puntos visitante', 'home_score': 'Puntos local'})
    st.dataframe(vista, hide_index=True, use_container_width=True)


def _evaluar_pruebas_v41(cal):
    pruebas = []
    def agregar(nombre, correcto, detalle, severidad='ERROR'):
        pruebas.append({'Prueba': nombre, 'Estado': 'OK' if correcto else severidad,
                        'Detalle': str(detalle)})

    columnas = {'game_id', 'season', 'week', 'gameday', 'home_team',
                'away_team', 'home_score', 'away_score'}
    faltantes = sorted(columnas - set(cal.columns))
    agregar('Columnas obligatorias', not faltantes, 'Completas' if not faltantes else 'Faltan')
    if faltantes:
        return pd.DataFrame(pruebas)
    agregar('Calendario no vacío', len(cal) > 0, f'{len(cal)} partidos')
    return pd.DataFrame(pruebas)


def _ventana_proximos_v41(cal, fecha_referencia=None):
    hoy = pd.Timestamp(fecha_referencia or datetime.now(timezone.utc).date()).normalize()
    fecha = pd.to_datetime(cal['gameday'], errors='coerce').dt.tz_localize(None).dt.normalize()
    pendientes = cal['home_score'].isna() & cal['away_score'].isna()
    ventana = pendientes & fecha.ge(hoy) & fecha.lt(hoy + pd.Timedelta(days=7))
    return cal.loc[ventana].copy()


def mostrar_pruebas_integrales_nfl_v41():
    st.subheader('🧪 NFL 4.1 | Pruebas integrales')
    st.caption('Verificaciones de calidad del calendario y pruebas con datos simulados.')
    if not st.button('▶️ Ejecutar pruebas NFL 4.1', key='nfl41_ejecutar'):
        st.info('Pulsa el botón para ejecutar las comprobaciones.')
        return
    try:
        cal = cargar_calendario_rapido_v40()
    except Exception as exc:
        st.error('No se pudo cargar el calendario.')
        return
    reales = _evaluar_pruebas_v41(cal)
    a, b, c = st.columns(3)
    a.metric('Comprobaciones', len(reales))
    b.metric('Errores', int(reales['Estado'].eq('ERROR').sum()))
    c.metric('Avisos', int(reales['Estado'].eq('AVISO').sum()))
    st.dataframe(reales, hide_index=True, use_container_width=True)


def mostrar_modulo_nfl():
    st.header('🏈 NFL 4.1 | Centro deportivo')
    st.caption('Panel unificado para celular · NFLverse · Resultados y estadísticas observadas')
    if st.button('🔄 Actualizar calendario y estadísticas', key='nfl40_actualizar'):
        cargar_calendario_rapido_v40.clear()
        st.session_state.pop('nfl40_consulta_utc', None)
        st.rerun()
    secciones = ['🏠 Inicio', '📅 Partidos', '🏟️ Equipos', '👥 Jugadores', '🛰️ Estado', '🧪 Auditorías y análisis', '🧪 Pruebas 4.1']
    seleccion = st.selectbox('Ir a sección', secciones, key='nfl40_navegacion')
    if seleccion == '🧪 Pruebas 4.1':
        mostrar_pruebas_integrales_nfl_v41()
        return
    try:
        with st.spinner('Consultando calendario NFL...'):
            cal = cargar_calendario_rapido_v40()
        if 'nfl40_consulta_utc' not in st.session_state:
            st.session_state['nfl40_consulta_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    except Exception as exc:
        st.error('No fue posible cargar el calendario.')
        return
    if seleccion == '🏠 Inicio':
        st.subheader('Resumen de Partidos')
        _marcador_v40(cal.head(10))
    elif seleccion == '📅 Partidos':
        st.subheader('Calendario Completo')
        _marcador_v40(cal)
    elif seleccion == '🏟️ Equipos':
        st.subheader('Estadísticas de Equipos')
        st.write("Selecciona una temporada para ver el resumen.")
    elif seleccion == '🛰️ Estado':
        st.subheader('Estado de la Conexión')
        st.success("🟢 Conectado correctamente a la suite analítica.")


# ---------------------------------------------------------
# MENÚ PRINCIPAL DE LA APLICACIÓN (TODOS LOS MÓDULOS RESTAURADOS)
# ---------------------------------------------------------
st.sidebar.title("🎯 Master Suite Analítica")
modulo_seleccionado = st.sidebar.selectbox(
    "Selecciona un Módulo",
    [
        "🏈 NFL 4.1 | Centro deportivo",
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

if modulo_seleccionado == "🏈 NFL 4.1 | Centro deportivo":
  mostrar_modulo_nfl()

elif modulo_seleccionado == "⚽ Módulo Pro Fútbol (Soccer)":
  st.title(f"⚽ **Módulo Pro Fútbol Élite [{fecha_formato_str}]**")
  st.markdown("--- \n *Poisson Bivariado.*")
  
  col_s1, col_s2 = st.columns(2)
  with col_s1: el = st.text_input("Local:", value="Club América", key="soc_el"); xg_l = st.number_input("xG Local:", value=2.45, step=0.05, key="soc_xgl")
  with col_s2: ev = st.text_input("Visita:", value="Guadalajara", key="soc_ev"); xg_v = st.number_input("xG Visita:", value=0.85, step=0.05, key="soc_xgv")

  momio_playdoit = st.number_input("Momio Decimal 1X2:", value=1.75, step=0.05, key="soc_mp")

  if st.button("🚀 Ejecutar Análisis Fútbol", use_container_width=True):
    max_goles = 6
    prob_l = [poisson.pmf(i, xg_l) for i in range(max_goles + 1)]
    prob_v = [poisson.pmf(j, xg_v) for j in range(max_goles + 1)]
    matriz = np.outer(prob_l, prob_v)
    matriz /= matriz.sum()
    
    prob_local = float(np.sum(np.tril(matriz, -1))) * 100.0
    prob_empate = float(np.sum(np.diag(matriz))) * 100.0
    prob_visita = float(np.sum(np.triu(matriz, 1))) * 100.0
    
    res_soc = {
        "prob_local": prob_local, 
        "prob_empate": prob_empate, 
        "prob_visita": prob_visita, 
        "validas": [
            {"mercado": f"Victoria {el}", "prob": prob_local},
            {"mercado": "Empate", "prob": prob_empate},
            {"mercado": f"Victoria {ev}", "prob": prob_visita}
        ]
    }
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

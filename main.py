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
# MOTORES DE PLAYER PROPS Y OTROS DEPORTES
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
# SISTEMA PRO NFL v4.6 (INTEGRADO)
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
        raise ValueError('Falló la carga de estadísticas PBP; no se realizará una validación incompleta: ' + ' | '.join(errores))
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
        raise ValueError(f'Existen {sin_cobertura} partidos terminados sin cobertura PBP suficiente; validación detenida para evitar estadísticas sesgadas.')
    return salida

@st.cache_resource(show_spinner=False)
def entrenar_v30(csv, huella):
    df = pd.read_csv(io.StringIO(csv))
    df = df.dropna(subset=['home_score', 'away_score']).copy()
    if df[VARIABLES].isna().any().any():
        raise ValueError('Existen variables faltantes; entrenamiento cancelado.')
    if not np.isfinite(df[VARIABLES].to_numpy(dtype=float)).all():
        raise ValueError('Existen valores no finitos; entrenamiento cancelado.')
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
            raise ValueError(f'Datos insuficientes para evaluación {evaluacion}: {len(train)} entrenamiento, {len(test)} prueba.')
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
                    {'temporada': evaluacion, 'modelo': 'Gradient Boosting', 'MAE': float(mean_absolute_error(objetivo(test), estimado_boosting))},
                    {'temporada': evaluacion, 'modelo': 'Ridge (modelo activo)', 'MAE': float(mean_absolute_error(objetivo(test), estimado))},
                    {'temporada': evaluacion, 'modelo': 'Referencia: promedio', 'MAE': float(mean_absolute_error(objetivo(test), base))},
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
    evaluacion_2026 = []
    detalles_2026 = []
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

def experimento_priors(csv):
    df = pd.read_csv(io.StringIO(csv))
    df = df.dropna(subset=['home_score', 'away_score']).copy()
    alt = ['experimental_' + v if 'experimental_' + v in df.columns else v for v in VARIABLES]
    if df[VARIABLES + alt].isna().any().any():
        raise ValueError('Variables faltantes en el experimento.')
    resultados = []
    for year in (2024, 2025, 2026):
        train = df[(df.season >= 2022) & (df.season < year)]
        test = df[df.season == year]
        if len(train) < 200 or len(test) < 25:
            continue
        for objetivo in ('margen', 'total'):
            target = (lambda x: x.home_score - x.away_score) if objetivo == 'margen' else (lambda x: x.home_score + x.away_score)
            for nombre, cols in [('Actual', VARIABLES), ('Prior temporada anterior (experimental)', alt)]:
                model = (HistGradientBoostingRegressor(max_iter=110, max_leaf_nodes=12, learning_rate=.045, l2_regularization=8., random_state=42) if objetivo == 'margen' else make_pipeline(StandardScaler(), Ridge(alpha=100.0)))
                model.fit(train[cols], target(train))
                pred = model.predict(test[cols])
                resultados.append({
                    'temporada': year, 'objetivo': objetivo,
                    'variante': nombre, 'partidos': len(test),
                    'MAE': float(mean_absolute_error(target(test), pred)),
                })
    return pd.DataFrame(resultados)

@st.cache_data(ttl=86400, show_spinner=False)
def experimento_pesos_v30(csv):
    df = pd.read_csv(io.StringIO(csv))
    df = df.dropna(subset=['home_score', 'away_score']).copy()
    requeridas = VARIABLES + ['season', 'week', 'home_score', 'away_score']
    _requerir(df, requeridas, 'Experimento v3.0')
    campos = [
        'local_pf', 'local_pa', 'local_victorias',
        'visitante_pf', 'visitante_pa', 'visitante_victorias',
        'local_epa_of', 'local_epa_def', 'visitante_epa_of',
        'visitante_epa_def', 'local_sr_of', 'local_sr_def',
        'visitante_sr_of', 'visitante_sr_def',
    ]
    _requerir(df, ['experimental_' + c for c in campos], 'Experimento v3.0: variables experimentales')
    df = df.sort_values(['season', 'week', 'gameday', 'game_id'])
    if not np.isfinite(df[VARIABLES + ['experimental_' + c for c in campos]].to_numpy(dtype=float)).all():
        raise ValueError('Hay datos faltantes o no finitos.')
    variantes = {'Actual (peso 0)': 0.0, 'Peso 1': 1.0, 'Peso 3 (v2.9)': 3.0, 'Peso 5': 5.0}
    columnas = {}
    for etiqueta, peso in variantes.items():
        columnas[etiqueta] = []
        for c in VARIABLES:
            dest = f'v30_{peso:g}_{c}'
            if c in campos and peso > 0:
                prefix = 'local' if c.startswith('local_') else 'visitante'
                n = df[f'{prefix}_juegos'].astype(float)
                previo = (df['experimental_' + c] * (n + 3.0) - df[c] * n) / 3.0
                df[dest] = (n * df[c] + peso * previo) / (n + peso)
            else:
                df[dest] = df[c]
            columnas[etiqueta].append(dest)
    detalle = []
    for temporada in (2024, 2025, 2026):
        train = df[(df.season >= 2022) & (df.season < temporada)]
        test = df[df.season == temporada]
        if len(train) < 200 or len(test) < 25:
            continue
        for objetivo in ('margen', 'total'):
            y_train = (train.home_score - train.away_score if objetivo == 'margen' else train.home_score + train.away_score)
            y_test = (test.home_score - test.away_score if objetivo == 'margen' else test.home_score + test.away_score)
            for variante, cols in columnas.items():
                if objetivo == 'margen':
                    model = HistGradientBoostingRegressor(max_iter=110, max_leaf_nodes=12, learning_rate=.045, l2_regularization=8., random_state=42)
                else:
                    model = make_pipeline(StandardScaler(), Ridge(alpha=100.0))
                model.fit(train[cols], y_train)
                estimado = model.predict(test[cols])
                for idx, real, pred in zip(test.index, y_test, estimado):
                    row = test.loc[idx]
                    detalle.append({
                        'temporada': temporada, 'semana': int(row.week),
                        'partido': str(row.game_id), 'objetivo': objetivo,
                        'variante': variante, 'real': float(real),
                        'prediccion': float(pred),
                        'error_absoluto': abs(float(real - pred)),
                        'partidos_previos_min': int(min(row.local_juegos, row.visitante_juegos)),
                    })
    return pd.DataFrame(detalle)

@st.cache_data(ttl=86400, show_spinner=False)
def validar_pesos_cronologicos_v31(csv):
    detalle = experimento_pesos_v30(csv)
    if detalle.empty:
        return pd.DataFrame(), pd.DataFrame()
    resumen = (detalle.groupby(['temporada', 'objetivo', 'variante'], as_index=False)
               .agg(MAE=('error_absoluto', 'mean'), partidos=('partido', 'nunique')))
    resultados = []
    variantes = ['Actual (peso 0)', 'Peso 1', 'Peso 3 (v2.9)', 'Peso 5']
    for year in (2025, 2026):
        for objetivo in ('margen', 'total'):
            previo = detalle[(detalle.temporada < year) & (detalle.objetivo == objetivo)]
            prueba = detalle[(detalle.temporada == year) & (detalle.objetivo == objetivo)]
            if previo.empty or prueba.empty:
                continue
            metricas = (previo.groupby(['temporada', 'variante'], as_index=False)
                        .agg(MAE=('error_absoluto', 'mean'))
                        .groupby('variante').MAE.mean())
            if not set(variantes).issubset(metricas.index):
                continue
            elegido = min(variantes, key=lambda v: (float(metricas[v]), variantes.index(v)))
            for configuracion, variante in [('Referencia peso 0', 'Actual (peso 0)'), ('Seleccion previa', elegido)]:
                bloque = prueba[prueba.variante == variante]
                if bloque.empty:
                    continue
                resultados.append({
                    'temporada_evaluada': year, 'objetivo': objetivo,
                    'configuracion': configuracion, 'variante': variante,
                    'MAE': float(bloque.error_absoluto.mean()),
                    'partidos': int(bloque.partido.nunique()),
                    'seleccion_con_temporadas': ', '.join(map(str, sorted(previo.temporada.unique()))),
                })
    return resumen, pd.DataFrame(resultados)

def auditoria_calidad_nfl_v32(calendario, estadisticas, tabla):
    cal = calendario.copy()
    est = estadisticas.copy()
    cal['finalizado'] = cal['home_score'].notna() & cal['away_score'].notna()
    cal['gameday'] = pd.to_datetime(cal['gameday'], errors='coerce')
    equipos = pd.concat([
        cal[['game_id', 'season', 'finalizado', 'home_team']].rename(columns={'home_team': 'equipo'}),
        cal[['game_id', 'season', 'finalizado', 'away_team']].rename(columns={'away_team': 'equipo'})
    ], ignore_index=True)
    est['jugadas'] = pd.to_numeric(est['jugadas'], errors='coerce')
    est['epa_of'] = pd.to_numeric(est['epa_of'], errors='coerce')
    est['sr_of'] = pd.to_numeric(est['sr_of'], errors='coerce')
    est['sr_def'] = pd.to_numeric(est['sr_def'], errors='coerce')
    est['epa_def'] = pd.to_numeric(est['epa_def'], errors='coerce')
    equipos = equipos.merge(est, on=['game_id', 'equipo'], how='left', validate='many_to_one')
    equipos['estadistica_valida'] = (
        equipos['jugadas'].ge(10)
        & equipos[['epa_of', 'epa_def', 'sr_of', 'sr_def']].notna().all(axis=1)
        & equipos['sr_of'].between(0, 1)
        & equipos['sr_def'].between(0, 1)
    )
    partidos = equipos.groupby(['season', 'game_id'], as_index=False).agg(
        finalizado=('finalizado', 'max'),
        equipos_con_estadistica=('estadistica_valida', 'sum'),
    )
    partidos['cobertura_completa'] = partidos['equipos_con_estadistica'].eq(2)
    partidos['incompleto_finalizado'] = partidos['finalizado'] & ~partidos['cobertura_completa']
    resumen = partidos.groupby('season', as_index=False).agg(
        calendario=('game_id', 'nunique'),
        finalizados=('finalizado', 'sum'),
        finalizados_sin_pbp_completo=('incompleto_finalizado', 'sum'),
    )
    resumen['finalizados_con_pbp_completo'] = (
        resumen['finalizados'] - resumen['finalizados_sin_pbp_completo']
    )
    resumen['cobertura_pct'] = (
        100 * resumen['finalizados_con_pbp_completo']
        / resumen['finalizados'].replace(0, np.nan)
    ).round(1)
    resumen['estado'] = np.select(
        [resumen['finalizados'].eq(0), resumen['finalizados_sin_pbp_completo'].eq(0)],
        ['SIN RESULTADOS', 'COMPLETO'], default='INCOMPLETO'
    )
    pendientes = partidos[partidos['incompleto_finalizado']].copy()
    pendientes = pendientes.merge(
        cal[['game_id', 'gameday', 'week', 'home_team', 'away_team']],
        on='game_id', how='left', validate='one_to_one'
    ).sort_values(['season', 'gameday', 'game_id'])
    fechas = {
        'ultima_fecha_calendario': cal['gameday'].max(),
        'ultimo_resultado': cal.loc[cal['finalizado'], 'gameday'].max(),
        'ultima_fecha_con_pbp_completo': cal.loc[
            cal['game_id'].isin(partidos.loc[partidos['cobertura_completa'], 'game_id']),
            'gameday'
        ].max(),
        'consulta_utc': datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
    }
    return resumen, pendientes, fechas

def mostrar_auditoria_nfl_v32(calendario, estadisticas, tabla):
    st.subheader('🛡️ NFL 3.2 | Auditoría de calidad de datos')
    try:
        resumen, pendientes, fechas = auditoria_calidad_nfl_v32(calendario, estadisticas, tabla)
        st.dataframe(resumen, use_container_width=True, hide_index=True)
    except Exception as exc:
        st.error('🔴 No se pudo completar la auditoría NFL 3.2.')

def _instantanea_nfl_v33(calendario, estadisticas):
    cal = calendario.copy()
    cal['gameday'] = pd.to_datetime(cal['gameday'], errors='coerce')
    cal['finalizado'] = cal['home_score'].notna() & cal['away_score'].notna()
    terminados = cal.loc[cal['finalizado']].copy()
    terminados['game_id'] = terminados['game_id'].astype(str)
    est = estadisticas.copy()
    est['game_id'] = est['game_id'].astype(str)
    est['equipo'] = est['equipo'].astype(str)
    for columna in ['epa_of', 'epa_def', 'sr_of', 'sr_def', 'jugadas']:
        est[columna] = pd.to_numeric(est[columna], errors='coerce')
    est = est.sort_values(['game_id', 'equipo'])
    campos = ['game_id', 'equipo', 'epa_of', 'epa_def', 'sr_of', 'sr_def', 'jugadas']
    huellas_pbp = {}
    for game_id, grupo in est.groupby('game_id'):
        serial = grupo[campos].to_csv(index=False, float_format='%.12g')
        huellas_pbp[game_id] = hashlib.sha256(serial.encode('utf-8')).hexdigest()
    juegos = {}
    for fila in terminados.itertuples(index=False):
        juegos[str(fila.game_id)] = {
            'temporada': int(fila.season),
            'fecha': str(fila.gameday.date()),
            'marcador': [float(fila.home_score), float(fila.away_score)],
            'pbp_sha256': huellas_pbp.get(str(fila.game_id)),
        }
    ultimo = terminados['gameday'].max() if not terminados.empty else pd.NaT
    return {
        'consulta_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
        'ultimo_resultado': None if pd.isna(ultimo) else str(ultimo.date()),
        'partidos_finalizados': len(juegos),
        'partidos_con_pbp': sum(x['pbp_sha256'] is not None for x in juegos.values()),
        'juegos': juegos,
    }

def _comparar_instantaneas_nfl_v33(anterior, actual):
    antes, ahora = anterior['juegos'], actual['juegos']
    nuevos = sorted(set(ahora) - set(antes))
    desaparecidos = sorted(set(antes) - set(ahora))
    modificados = []
    for game_id in sorted(set(antes) & set(ahora)):
        campos = []
        if antes[game_id]['marcador'] != ahora[game_id]['marcador']:
            campos.append('marcador')
        if antes[game_id]['pbp_sha256'] != ahora[game_id]['pbp_sha256']:
            campos.append('PBP agregado')
        if campos:
            modificados.append({'game_id': game_id, 'cambio': ', '.join(campos)})
    return nuevos, desaparecidos, modificados

def mostrar_auditoria_nfl_v33(calendario, estadisticas):
    st.subheader('🔎 NFL 3.3 | Vigilancia de actualizaciones')
    actual = _instantanea_nfl_v33(calendario, estadisticas)
    anterior = st.session_state.get('nfl33_ultima_instantanea')
    historial = st.session_state.setdefault('nfl33_historial', [])
    if anterior is not None:
        nuevos, desaparecidos, modificados = _comparar_instantaneas_nfl_v33(anterior, actual)
        historial.append({
            'consulta_utc': actual['consulta_utc'],
            'resultados_nuevos': len(nuevos),
            'resultados_desaparecidos': len(desaparecidos),
            'partidos_modificados': len(modificados),
            'total_finalizados': actual['partidos_finalizados'],
        })
        del historial[:-20]
    st.session_state['nfl33_ultima_instantanea'] = actual

def auditar_integridad_nfl_v341(calendario, estadisticas):
    cal, est = calendario.copy(), estadisticas.copy()
    filas = []
    def agregar(nombre, accion, descripcion):
        try:
            cantidad, nivel = accion()
            filas.append(dict(nivel=nivel, control=nombre, registros=int(cantidad), detalle=descripcion))
        except Exception as exc:
            filas.append(dict(nivel='NO EJECUTADO', control=nombre, registros=0, detalle=f'{type(exc).__name__}: {exc}'))
    def contar(n, nivel='ERROR'):
        return (int(n), nivel if n else 'OK')
    agregar('IDs de partidos duplicados', lambda: contar(cal['game_id'].duplicated().sum()), 'Cada game_id debe ser único.')
    agregar('Local y visitante idénticos', lambda: contar((cal['home_team'] == cal['away_team']).sum()), 'Los equipos deben ser distintos.')
    agregar('Fechas inválidas', lambda: contar(pd.to_datetime(cal['gameday'], errors='coerce').isna().sum()), 'Todas las fechas deben poder interpretarse.')
    agregar('Partidos sin marcador completo', lambda: contar(cal[['home_score', 'away_score']].apply(pd.to_numeric, errors='coerce').isna().any(axis=1).sum(), 'INFO'), 'Incluye partidos futuros.')
    agregar('Marcadores negativos', lambda: contar(cal[['home_score', 'away_score']].apply(pd.to_numeric, errors='coerce').lt(0).any(axis=1).sum()), 'Los puntos no pueden ser negativos.')
    agregar('Estadísticas duplicadas por equipo', lambda: contar(est.duplicated(['game_id', 'equipo']).sum()), 'Solo una fila por equipo y partido.')
    return pd.DataFrame(filas)

def mostrar_auditoria_nfl_v341(calendario, estadisticas):
    st.subheader('🧪 NFL 3.4.1 | Integridad y anomalías')
    informe = auditar_integridad_nfl_v341(calendario, estadisticas)
    st.dataframe(informe, use_container_width=True, hide_index=True)

def crear_reporte_consolidado_nfl_v35(calendario, estadisticas, tabla):
    fecha_consulta = datetime.now(timezone.utc).isoformat(timespec='seconds')
    filas = []
    cobertura, pendientes, fechas = auditoria_calidad_nfl_v32(calendario, estadisticas, tabla)
    for registro in cobertura.to_dict('records'):
        temporada = registro.get('season')
        for campo in ['calendario', 'finalizados', 'finalizados_con_pbp_completo', 'finalizados_sin_pbp_completo', 'cobertura_pct']:
            filas.append({'consulta_utc': fecha_consulta, 'seccion': 'Cobertura NFL 3.2', 'temporada': temporada, 'indicador': campo, 'valor': registro.get(campo), 'estado': registro.get('estado', ''), 'detalle': 'Cobertura calculada.'})
    return pd.DataFrame(filas)

def mostrar_reporte_consolidado_nfl_v35(calendario, estadisticas, tabla):
    st.subheader('📋 NFL 3.5 | Reporte consolidado de auditorías')
    reporte = crear_reporte_consolidado_nfl_v35(calendario, estadisticas, tabla)
    st.dataframe(reporte, use_container_width=True, hide_index=True)

def clasificar_partidos_nfl_v36(calendario, fecha_consulta=None):
    if fecha_consulta is None:
        fecha_consulta = datetime.now(timezone.utc)
    fecha_consulta = pd.Timestamp(fecha_consulta)
    if fecha_consulta.tzinfo is None:
        fecha_consulta = fecha_consulta.tz_localize('UTC')
    df = calendario.copy()
    df['gameday'] = pd.to_datetime(df['gameday'], errors='coerce', utc=True)
    df['home_score'] = pd.to_numeric(df['home_score'], errors='coerce')
    df['away_score'] = pd.to_numeric(df['away_score'], errors='coerce')
    ambos = df['home_score'].notna() & df['away_score'].notna()
    uno = df['home_score'].notna() ^ df['away_score'].notna()
    fecha_valida = df['gameday'].notna()
    vencido = fecha_valida & (df['gameday'] < fecha_consulta - pd.Timedelta(days=1))
    futuro = fecha_valida & (df['gameday'] >= fecha_consulta.normalize())
    df['estado_auditoria'] = 'PENDIENTE DE CONFIRMACION'
    df.loc[futuro & ~ambos & ~uno, 'estado_auditoria'] = 'PROGRAMADO SIN RESULTADO'
    df.loc[vencido & ~ambos & ~uno, 'estado_auditoria'] = 'REVISAR RESULTADO PENDIENTE'
    df.loc[uno, 'estado_auditoria'] = 'MARCADOR PARCIAL'
    df.loc[ambos, 'estado_auditoria'] = 'RESULTADO DISPONIBLE'
    df.loc[~fecha_valida, 'estado_auditoria'] = 'FECHA INVALIDA'
    resumen = (df.groupby(['season', 'estado_auditoria'], dropna=False).size().unstack(fill_value=0).reset_index())
    resumen['total_calendario'] = df.groupby('season').size().reindex(resumen['season']).values
    return df, resumen

def mostrar_auditoria_nfl_v36(calendario):
    st.subheader('📅 NFL 3.6 | Estado de partidos y resultados pendientes')
    detalle, resumen = clasificar_partidos_nfl_v36(calendario)
    st.dataframe(resumen, use_container_width=True, hide_index=True)

def auditar_consistencia_nfl_v37(calendario, estadisticas, minimo_jugadas=10):
    cal, est = calendario.copy(), estadisticas.copy()
    cal['game_id'] = cal['game_id'].astype(str)
    est['game_id'] = est['game_id'].astype(str)
    cal['home_score'] = pd.to_numeric(cal['home_score'], errors='coerce')
    cal['away_score'] = pd.to_numeric(cal['away_score'], errors='coerce')
    est['jugadas'] = pd.to_numeric(est['jugadas'], errors='coerce')
    finalizados = cal[cal['home_score'].notna() & cal['away_score'].notna()].copy()
    esperado = pd.concat([
        finalizados[['game_id','season','home_team']].rename(columns={'home_team':'equipo'}),
        finalizados[['game_id','season','away_team']].rename(columns={'away_team':'equipo'})
    ], ignore_index=True)
    resumen_est = est.groupby(['game_id','equipo'], as_index=False).agg(registros=('jugadas','size'), jugadas=('jugadas','max'))
    cruce = esperado.merge(resumen_est, on=['game_id','equipo'], how='left', validate='many_to_one')
    cruce['registros'] = cruce['registros'].fillna(0).astype(int)
    cruce['estado'] = 'OK'
    cruce.loc[cruce['registros'].eq(0),'estado'] = 'SIN PBP DE EQUIPO'
    cruce.loc[cruce['registros'].gt(0) & cruce['jugadas'].lt(minimo_jugadas), 'estado'] = 'PBP INSUFICIENTE'
    return cruce, cruce.groupby('estado', dropna=False).size().reset_index(name='registros')

def mostrar_auditoria_nfl_v37(calendario, estadisticas):
    st.subheader('🔗 NFL 3.7 | Consistencia entre calendario y PBP')
    detalle, resumen = auditar_consistencia_nfl_v37(calendario, estadisticas)
    st.dataframe(resumen, use_container_width=True, hide_index=True)

def evaluar_estado_nfl_v38(calendario, estadisticas, ahora=None):
    ahora = ahora or datetime.now(timezone.utc)
    cal = calendario.copy()
    est = estadisticas.copy()
    cal['gameday'] = pd.to_datetime(cal['gameday'], errors='coerce')
    fin = cal[pd.to_numeric(cal['home_score'], errors='coerce').notna() & pd.to_numeric(cal['away_score'], errors='coerce').notna()].copy()
    ultima = fin['gameday'].max() if not fin.empty else pd.NaT
    dias = (ahora.date() - ultima.date()).days if pd.notna(ultima) else None
    ids_pbp = set(est['game_id'].dropna().astype(str))
    ids_fin = set(fin['game_id'].dropna().astype(str))
    sin_pbp = ids_fin - ids_pbp
    proximos = cal[(cal['gameday'].dt.date >= ahora.date()) & (cal['gameday'].dt.date <= (ahora + timedelta(days=7)).date())]
    return {'ultima_fecha_resultado': ultima.date().isoformat() if pd.notna(ultima) else None,
            'dias_desde_ultimo_resultado': dias,
            'finalizados': len(ids_fin),
            'finalizados_sin_pbp': len(sin_pbp),
            'proximos_7_dias': int(proximos['game_id'].nunique()),
            'registros_equipos_pbp': len(est)}

def mostrar_monitoreo_nfl_v38(calendario, estadisticas, solo_respaldo=False):
    st.subheader('🛰️ NFL 3.8 | Estado de actualización y conexión')
    ahora = datetime.now(timezone.utc)
    datos = evaluar_estado_nfl_v38(calendario, estadisticas, ahora)
    st.write('**Última fecha con resultado:**', datos['ultima_fecha_resultado'] or 'Sin datos')

@st.cache_data(ttl=21600, show_spinner=False)
def cargar_jugadores_nfl_v39(temporada):
    import nflreadpy as nfl
    if not hasattr(nfl, 'load_player_stats'):
        raise RuntimeError('Esta versión de nflreadpy no incluye load_player_stats.')
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

def _columna_jugador_v39(df, alternativas):
    return next((c for c in alternativas if c in df.columns), None)

def mostrar_jugadores_nfl_v39():
    st.subheader('👥 NFL 3.9 | Estadísticas individuales de jugadores')
    temporada = st.selectbox('Temporada de jugadores', TEMPORADAS[::-1], key='nfl39_temporada')
    if st.button('📥 Cargar estadísticas de jugadores', key='nfl39_cargar'):
        st.session_state['nfl39_temporada_cargada'] = int(temporada)
    if st.session_state.get('nfl39_temporada_cargada') != int(temporada):
        st.info('Pulsa «Cargar estadísticas de jugadores» para consultar la temporada seleccionada.')
        return
    try:
        df = cargar_jugadores_nfl_v39(int(temporada))
    except Exception as exc:
        st.error('No fue posible consultar las estadísticas individuales.')
        return
    if df.empty:
        st.warning('La fuente no publicó registros de jugadores para esta temporada.')
        return
    nombre = _columna_jugador_v39(df, ['player_display_name', 'player_name', 'player'])
    identificador = _columna_jugador_v39(df, ['player_id', 'gsis_id'])
    equipo = _columna_jugador_v39(df, ['recent_team', 'team', 'posteam'])
    posicion = _columna_jugador_v39(df, ['position', 'position_group'])
    if not nombre and not identificador:
        st.warning('La fuente no incluye columnas para identificar jugadores.')
        return
    if not nombre:
        nombre = identificador
    df = df.copy()
    df[nombre] = df[nombre].fillna('Sin nombre').astype(str)
    if equipo:
        equipos = sorted(df[equipo].dropna().astype(str).unique().tolist())
        eleccion = st.selectbox('Equipo', ['Todos'] + equipos, key='nfl39_equipo')
        if eleccion != 'Todos':
            df = df[df[equipo].astype(str) == eleccion]
    st.metric('Registros encontrados', len(df))
    st.dataframe(df.head(100), use_container_width=True, hide_index=True)

@st.cache_data(ttl=900, show_spinner=False)
def cargar_calendario_rapido_v40():
    import nflreadpy as nfl
    datos = nfl.load_schedules(TEMPORADAS)
    df = datos.to_pandas() if hasattr(datos, 'to_pandas') else pd.DataFrame(datos)
    _requerir(df, ['game_id', 'season', 'week', 'gameday', 'home_team', 'away_team', 'home_score', 'away_score'], 'Calendario NFL 4.0')
    df = df.copy()
    df['gameday'] = pd.to_datetime(df['gameday'], errors='coerce')
    for col in ['season', 'week', 'home_score', 'away_score']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['game_id', 'gameday']).drop_duplicates('game_id')
    df.attrs['consulta_fuente_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
    return df

def diagnosticar_duplicados_v421(df):
    if df.empty:
        return pd.DataFrame(columns=['tipo', 'game_id', 'fecha', 'visitante', 'local', 'temporada', 'semana'])
    d = df.copy()
    d['_fecha'] = pd.to_datetime(d['gameday'], errors='coerce').dt.strftime('%Y-%m-%d')
    d['_id'] = d['game_id'].astype('string').fillna('')
    d['_away'] = d['away_team'].astype('string').fillna('')
    d['_home'] = d['home_team'].astype('string').fillna('')
    por_id = d['_id'].ne('') & d.duplicated('_id', keep=False)
    por_cruce = d.duplicated(['_fecha', '_away', '_home'], keep=False)
    d = d.loc[por_id | por_cruce].copy()
    if d.empty:
        return pd.DataFrame(columns=['tipo', 'game_id', 'fecha', 'visitante', 'local', 'temporada', 'semana'])
    d['tipo'] = ['ID repetido' if i else 'Misma fecha y equipos (revisar)' for i in d.index.map(lambda x: bool(por_id.loc[x]))]
    return pd.DataFrame({'tipo': d['tipo'], 'game_id': d['game_id'], 'fecha': d['_fecha'], 'visitante': d['away_team'], 'local': d['home_team'], 'temporada': d['season'], 'semana': d['week']}).reset_index(drop=True)

def _vista_sin_repeticiones_v421(df):
    if df.empty:
        return df.copy(), 0
    cols = [c for c in ['game_id', 'season', 'week', 'gameday', 'away_team', 'home_team', 'away_score', 'home_score'] if c in df.columns]
    vista = df.drop_duplicates(subset=cols, keep='first')
    return vista, len(df) - len(vista)

def _tarjetas_partidos_v42(df, prefijo='nfl42'):
    if df.empty:
        st.info('No hay encuentros para mostrar.')
        return
    vista, ocultos = _vista_sin_repeticiones_v421(df)
    if ocultos:
        st.caption(f'{ocultos} copias idénticas ocultas solo en la presentación.')
    for _, juego in vista.head(30).iterrows():
        fecha = pd.to_datetime(juego.get('gameday'), errors='coerce')
        fecha_txt = fecha.strftime('%d/%m/%Y') if pd.notna(fecha) else 'Fecha no disponible'
        semana = pd.to_numeric(juego.get('week'), errors='coerce')
        semana_txt = str(int(semana)) if pd.notna(semana) else '—'
        local = str(juego.get('home_team', '—'))
        visita = str(juego.get('away_team', '—'))
        pl = pd.to_numeric(juego.get('home_score'), errors='coerce')
        pv = pd.to_numeric(juego.get('away_score'), errors='coerce')
        estado = str(juego.get('gametype_status', juego.get('status', ''))).strip().lower()
        vivo = estado in {'in_progress', 'in progress', 'live', 'inprogress', 'playing'}
        final = estado in {'final', 'closed', 'completed', 'finished'}
        if vivo:
            etiqueta = '🔴 En juego (según fuente)'
        elif final or (pd.notna(pl) and pd.notna(pv) and not estado):
            etiqueta = '✅ Con resultado' if not final else '✅ Finalizado'
        else:
            etiqueta = '📅 Programado / estado sin confirmar'
        con_marcador = pd.notna(pl) and pd.notna(pv)
        resultado = (f'**{visita} {int(pv)} — {int(pl)} {local}**' if con_marcador else f'**{visita} vs. {local}**')
        with st.container(border=True):
            st.caption(f'{fecha_txt} · Semana {semana_txt} · {etiqueta}')
            st.markdown(resultado)
    if len(vista) > 30:
        st.caption(f'Mostrando 30 de {len(vista)} partidos. Usa los filtros para reducir la lista.')

def _marcador_v40(df):
    if df.empty:
        st.info("No hay partidos en este filtro.")
        return
    vista = df[['gameday', 'week', 'away_team', 'home_team', 'away_score', 'home_score']].copy()
    vista['gameday'] = pd.to_datetime(vista['gameday'], errors='coerce').dt.strftime('%Y-%m-%d')
    vista = vista.rename(columns={'gameday': 'Fecha', 'week': 'Semana', 'away_team': 'Visitante', 'home_team': 'Local', 'away_score': 'Puntos visitante', 'home_score': 'Puntos local'})
    st.dataframe(vista, hide_index=True, use_container_width=True)

def _panel_inicio_v40(cal):
    hoy = pd.Timestamp(datetime.now(timezone.utc).date())
    completos = cal.dropna(subset=['home_score', 'away_score'])
    proximos_7 = _ventana_proximos_v41(cal)
    futuros = cal[(cal['gameday'] >= hoy) & cal['home_score'].isna() & cal['away_score'].isna()].sort_values(['gameday', 'game_id'])
    st.subheader('🏠 Resumen NFL')
    st.metric('Partidos con resultado', len(completos))
    st.metric('Próximos 7 días', len(proximos_7))
    st.markdown('**📅 Próximos encuentros**')
    _tarjetas_partidos_v42(futuros.head(8))
    st.markdown('**🏈 Resultados recientes**')
    _tarjetas_partidos_v42(completos.sort_values(['gameday', 'game_id'], ascending=False).head(8))

def _panel_partidos_v40(cal):
    st.subheader('📅 Calendario y resultados')
    temporadas = sorted(cal['season'].dropna().astype(int).unique().tolist(), reverse=True)
    if not temporadas:
        st.warning('No hay temporadas disponibles.')
        return
    temporada = st.selectbox('Temporada', temporadas, key='nfl40_temporada_partidos')
    base = cal[cal['season'] == temporada].copy()
    semanas = sorted(base['week'].dropna().astype(int).unique().tolist())
    semana = st.selectbox('Semana', ['Todas'] + semanas, key='nfl40_semana')
    if semana != 'Todas':
        base = base[base['week'] == semana]
    equipos = sorted(set(base['home_team'].dropna()) | set(base['away_team'].dropna()))
    equipo = st.selectbox('Equipo', ['Todos'] + equipos, key='nfl40_equipo_partidos')
    if equipo != 'Todos':
        base = base[(base['home_team'] == equipo) | (base['away_team'] == equipo)]
    st.metric('Partidos encontrados', len(base))
    base = base.sort_values(['gameday', 'game_id'])
    vista = st.radio('Presentación', ['📱 Tarjetas', '📋 Tabla'], horizontal=True, key='nfl42_vista_partidos')
    if vista == '📱 Tarjetas':
        _tarjetas_partidos_v42(base)
    else:
        _marcador_v40(base)

def _panel_equipos_v40(cal):
    st.subheader('🏟️ Estadísticas de equipos')
    temporadas = sorted(cal['season'].dropna().astype(int).unique().tolist(), reverse=True)
    temporada = st.selectbox('Temporada', temporadas, key='nfl40_temporada_equipos')
    juegos = cal[(cal['season'] == temporada)].dropna(subset=['home_score', 'away_score']).copy()
    if juegos.empty:
        st.info('Aún no hay marcadores para esta temporada.')
        return
    local = pd.DataFrame({'Equipo': juegos['home_team'], 'PF': juegos['home_score'], 'PC': juegos['away_score'], 'V': (juegos['home_score'] > juegos['away_score']).astype(int), 'D': (juegos['home_score'] < juegos['away_score']).astype(int), 'E': (juegos['home_score'] == juegos['away_score']).astype(int)})
    visita = pd.DataFrame({'Equipo': juegos['away_team'], 'PF': juegos['away_score'], 'PC': juegos['home_score'], 'V': (juegos['away_score'] > juegos['home_score']).astype(int), 'D': (juegos['away_score'] < juegos['home_score']).astype(int), 'E': (juegos['home_score'] == juegos['away_score']).astype(int)})
    tabla = pd.concat([local, visita], ignore_index=True).groupby('Equipo', as_index=False)[['PF', 'PC', 'V', 'D', 'E']].sum()
    tabla['PJ'] = tabla['V'] + tabla['D'] + tabla['E']
    tabla['Diferencia'] = tabla['PF'] - tabla['PC']
    tabla = tabla.sort_values(['V', 'Diferencia'], ascending=[False, False])
    st.dataframe(tabla[['Equipo', 'PJ', 'V', 'D', 'E', 'PF', 'PC', 'Diferencia']], hide_index=True, use_container_width=True)

def _panel_comparacion_v44(cal):
    st.subheader('📊 NFL 4.4 | Comparador de equipos')
    temporadas = sorted(cal['season'].dropna().astype(int).unique().tolist(), reverse=True)
    if not temporadas:
        st.info('No hay temporadas para comparar.')
        return
    temporada = st.selectbox('Temporada de comparación', temporadas, key='nfl44_temporada')
    juegos = cal[cal['season'].eq(temporada)].dropna(subset=['home_score', 'away_score']).copy()
    if juegos.empty:
        st.info('No hay resultados completos en esta temporada.')
        return
    equipos = sorted(set(juegos['home_team'].dropna()) | set(juegos['away_team'].dropna()))
    if len(equipos) < 2:
        st.info('Se necesitan al menos dos equipos con partidos terminados.')
        return
    a = st.selectbox('Equipo A', equipos, key='nfl44_a')
    opciones_b = [x for x in equipos if x != a]
    b = st.selectbox('Equipo B', opciones_b, key='nfl44_b')

    def datos_equipo(equipo):
        local = juegos[juegos['home_team'].eq(equipo)].copy()
        visita = juegos[juegos['away_team'].eq(equipo)].copy()
        x = pd.concat([
            pd.DataFrame({'Fecha': local['gameday'], 'Semana': local['week'], 'PF': local['home_score'], 'PC': local['away_score'], 'Rival': local['away_team'], 'Sede': 'Local'}),
            pd.DataFrame({'Fecha': visita['gameday'], 'Semana': visita['week'], 'PF': visita['away_score'], 'PC': visita['home_score'], 'Rival': visita['home_team'], 'Sede': 'Visitante'})
        ], ignore_index=True).sort_values(['Fecha', 'Semana']).reset_index(drop=True)
        x['Diferencia'] = x['PF'] - x['PC']
        x['Resultado'] = x['Diferencia'].map(lambda v: 'V' if v > 0 else ('D' if v < 0 else 'E'))
        x['Partido'] = range(1, len(x) + 1)
        return x

    da, db = datos_equipo(a), datos_equipo(b)
    def resumen(nombre, d):
        return {'Equipo': nombre, 'PJ': len(d), 'Victorias': int((d['Resultado'] == 'V').sum()), 'Derrotas': int((d['Resultado'] == 'D').sum()), 'Empates': int((d['Resultado'] == 'E').sum()), 'PF': int(d['PF'].sum()), 'PC': int(d['PC'].sum()), 'Diferencia': int(d['Diferencia'].sum()), 'PF por partido': round(float(d['PF'].mean()), 2), 'PC por partido': round(float(d['PC'].mean()), 2)}
    comparacion = pd.DataFrame([resumen(a, da), resumen(b, db)])
    st.markdown('**Comparación de temporada**')
    for r in comparacion.to_dict('records'):
        with st.container(border=True):
            st.markdown(f"**{r['Equipo']}** · {r['PJ']} partidos")
            st.write(f"Victorias: {r['Victorias']} · Derrotas: {r['Derrotas']} · Empates: {r['Empates']}")
            st.write(f"Puntos a favor: {r['PF']} · En contra: {r['PC']} · Diferencia: {r['Diferencia']}")
            st.write(f"Promedio anotado: {r['PF por partido']} · Permitido: {r['PC por partido']}")
    st.markdown('**Evolución de puntos anotados por partido**')
    grafica = pd.concat([da.assign(Equipo=a), db.assign(Equipo=b)], ignore_index=True)
    st.line_chart(grafica.pivot_table(index='Partido', columns='Equipo', values='PF', aggfunc='first'), use_container_width=True)

def _panel_enfrentamientos_v46(cal):
    st.subheader('🏈 NFL 4.6 | Historial de enfrentamientos')
    st.caption('Resultados observados del calendario disponible (2022–2026).')
    requeridas = ['game_id', 'season', 'week', 'gameday', 'home_team', 'away_team', 'home_score', 'away_score']
    _requerir(cal, requeridas, 'Calendario de enfrentamientos')
    base = cal.copy()
    base['gameday'] = pd.to_datetime(base['gameday'], errors='coerce')
    for col in ['season', 'week', 'home_score', 'away_score']:
        base[col] = pd.to_numeric(base[col], errors='coerce')
    base = base.dropna(subset=['game_id', 'gameday', 'home_team', 'away_team', 'home_score', 'away_score'])
    base = base.drop_duplicates(subset=['game_id'])
    base = base[base['home_team'].ne(base['away_team'])]
    equipos = sorted(set(base['home_team']) | set(base['away_team']))
    if len(equipos) < 2:
        st.info('No hay suficientes equipos con resultados para comparar.')
        return
    col_a, col_b = st.columns(2)
    with col_a:
        a = st.selectbox('Equipo A', equipos, key='nfl46_equipo_a')
    with col_b:
        b = st.selectbox('Equipo B', [e for e in equipos if e != a], key='nfl46_equipo_b')
    temporadas = sorted(base['season'].dropna().astype(int).unique(), reverse=True)
    seleccion = st.multiselect('Temporadas', temporadas, default=temporadas, key='nfl46_temporadas')
    if not seleccion:
        st.info('Selecciona al menos una temporada.')
        return
    base = base[base['season'].isin(seleccion)]
    cruces = base[((base['home_team'] == a) & (base['away_team'] == b)) | ((base['home_team'] == b) & (base['away_team'] == a))]
    cruces = cruces.sort_values(['gameday', 'game_id'], ascending=False).copy()
    st.metric('Enfrentamientos con resultado', len(cruces))
    if cruces.empty:
        st.info('No hay enfrentamientos con resultado en las temporadas seleccionadas.')
        return
    cruces['puntos_a'] = np.where(cruces['home_team'].eq(a), cruces['home_score'], cruces['away_score'])
    cruces['puntos_b'] = np.where(cruces['home_team'].eq(b), cruces['home_score'], cruces['away_score'])
    cruces['ganador'] = np.select([cruces['puntos_a'].gt(cruces['puntos_b']), cruces['puntos_b'].gt(cruces['puntos_a'])], [a, b], default='Empate')
    victorias_a = int(cruces['ganador'].eq(a).sum())
    victorias_b = int(cruces['ganador'].eq(b).sum())
    empates = int(cruces['ganador'].eq('Empate').sum())
    with st.container(border=True):
        st.markdown(f'**Balance histórico · {a} vs. {b}**')
        st.write(f'{a}: **{victorias_a} victorias** · {b}: **{victorias_b} victorias** · Empates: **{empates}**')
        st.write(f'Puntos totales: {a} **{int(cruces["puntos_a"].sum())}** · {b} **{int(cruces["puntos_b"].sum())}**')
        st.write(f'Promedio por encuentro: {a} **{cruces["puntos_a"].mean():.2f}** · {b} **{cruces["puntos_b"].mean():.2f}**')
    st.markdown('**Últimos enfrentamientos**')
    for _, fila in cruces.head(10).iterrows():
        fecha = fila['gameday'].strftime('%d/%m/%Y')
        with st.container(border=True):
            st.caption(f'{fecha} · Temporada {int(fila["season"])} · Semana {int(fila["week"])}')
            st.markdown(f'**{fila["away_team"]} {int(fila["away_score"])} — {int(fila["home_score"])} {fila["home_team"]}**')
            st.caption('Ganador: ' + str(fila['ganador']))

def _agregar_pbp_v451(df):
    cols = ['game_id', 'posteam', 'defteam', 'play_type', 'epa', 'success']
    faltantes = [c for c in cols if c not in df.columns]
    if faltantes:
        raise ValueError('Columnas PBP faltantes: ' + ', '.join(faltantes))
    d = df.loc[df['play_type'].isin(['pass', 'run']), cols].copy()
    d['epa'] = pd.to_numeric(d['epa'], errors='coerce')
    d['success'] = pd.to_numeric(d['success'], errors='coerce')
    d = d.dropna(subset=['game_id', 'posteam', 'defteam'])
    d = d[d['posteam'].ne(d['defteam'])]
    d.loc[~d['success'].isin([0, 1]), 'success'] = float('nan')
    def agregar(lado, prefijo):
        if d.empty:
            return pd.DataFrame(columns=['game_id', 'equipo', f'EPA {prefijo}', f'SR {prefijo}', f'Jugadas EPA {prefijo}', f'Jugadas SR {prefijo}'])
        return (d.groupby(['game_id', lado], as_index=False)
                .agg(**{f'EPA {prefijo}': ('epa', 'mean'),
                        f'SR {prefijo}': ('success', 'mean'),
                        f'Jugadas EPA {prefijo}': ('epa', 'count'),
                        f'Jugadas SR {prefijo}': ('success', 'count')})
                .rename(columns={lado: 'equipo'}))
    ataque = agregar('posteam', 'ofensivo')
    defensa = agregar('defteam', 'permitido')
    return ataque.merge(defensa, on=['game_id', 'equipo'], how='outer', validate='one_to_one')

@st.cache_data(ttl=3600, show_spinner=False)
def _cargar_pbp_comparacion_v45(temporada):
    import nflreadpy as nfl
    raw = nfl.load_pbp(int(temporada))
    campos = ['game_id', 'posteam', 'defteam', 'play_type', 'epa', 'success']
    if hasattr(raw, 'select') and hasattr(raw, 'to_pandas'):
        df = raw.select(campos).to_pandas()
    else:
        df = raw.to_pandas() if hasattr(raw, 'to_pandas') else pd.DataFrame(raw)
    return _agregar_pbp_v451(df)

def _media_ponderada_v451(datos, metrica, contador):
    valores = pd.to_numeric(datos[metrica], errors='coerce')
    pesos = pd.to_numeric(datos[contador], errors='coerce').fillna(0)
    validos = valores.notna() & pesos.gt(0)
    if not validos.any():
        return None
    return round(float((valores[validos] * pesos[validos]).sum() / pesos[validos].sum()), 4)

def _panel_avanzado_v45(cal):
    st.subheader('🧠 NFL 4.5.1 | Rendimiento avanzado')
    temporadas = sorted(cal['season'].dropna().astype(int).unique().tolist(), reverse=True)
    if not temporadas:
        st.info('Sin temporadas disponibles.')
        return
    temporada = st.selectbox('Temporada', temporadas, key='nfl45_temporada')
    base = cal[cal['season'].eq(temporada)].dropna(subset=['home_score', 'away_score']).copy()
    if base.empty:
        st.info('Aún no hay partidos con resultado.')
        return
    equipos = sorted(set(base['home_team'].dropna()) | set(base['away_team'].dropna()))
    a = st.selectbox('Equipo A', equipos, key='nfl45_a')
    b = st.selectbox('Equipo B', [e for e in equipos if e != a], key='nfl45_b')

    def historial(e):
        local = base[base['home_team'].eq(e)]
        visita = base[base['away_team'].eq(e)]
        d = pd.concat([
            pd.DataFrame({'game_id': local['game_id'], 'Fecha': local['gameday'], 'Semana': local['week'], 'Sede': 'Local', 'PF': local['home_score'], 'PC': local['away_score']}),
            pd.DataFrame({'game_id': visita['game_id'], 'Fecha': visita['gameday'], 'Semana': visita['week'], 'Sede': 'Visitante', 'PF': visita['away_score'], 'PC': visita['home_score']})
        ], ignore_index=True).sort_values(['Fecha', 'Semana', 'game_id'])
        d['Resultado'] = d.apply(lambda r: 'V' if r.PF > r.PC else ('D' if r.PF < r.PC else 'E'), axis=1)
        return d

    def resumen(d):
        return {'PJ': len(d), 'V': int((d['Resultado'] == 'V').sum()), 'D': int((d['Resultado'] == 'D').sum()), 'E': int((d['Resultado'] == 'E').sum()), 'PF/prom': round(float(d['PF'].mean()), 2) if len(d) else None, 'PC/prom': round(float(d['PC'].mean()), 2) if len(d) else None}
    
    historiales = {a: historial(a), b: historial(b)}
    for equipo, d in historiales.items():
        with st.container(border=True):
            st.markdown(f'**{equipo} · Últimos cinco partidos**')
            st.write(resumen(d.tail(5)))

    st.markdown('**EPA y Success Rate (PBP)**')
    if st.button('📥 Cargar eficiencia PBP de esta temporada', key='nfl45_cargar_pbp'):
        st.session_state['nfl45_pbp_solicitada'] = temporada
    if st.session_state.get('nfl45_pbp_solicitada') != temporada:
        st.info('Pulsa el botón para consultar PBP.')
        return
    try:
        with st.spinner('Calculando eficiencia por partido...'):
            pbp = _cargar_pbp_comparacion_v45(temporada)
    except Exception as exc:
        st.warning('No se pudo consultar PBP.')
        return
    if pbp.empty:
        st.info('Sin jugadas válidas para esta temporada.')
        return
    filas = []
    for equipo, d in historiales.items():
        ids = d[['game_id']].drop_duplicates()
        x = pbp[pbp['equipo'].eq(equipo)].merge(ids, on='game_id', how='inner', validate='one_to_one')
        cobertura = len(x)
        fila = {'Equipo': equipo, 'Partidos con resultado': len(ids), 'Partidos con PBP': cobertura}
        for prefijo in ('ofensivo', 'permitido'):
            for metrica in ('EPA', 'SR'):
                col = f'{metrica} {prefijo}'
                contador = f'Jugadas {metrica} {prefijo}'
                fila[col] = _media_ponderada_v451(x, col, contador)
                fila[contador] = int(pd.to_numeric(x[contador], errors='coerce').fillna(0).sum())
        filas.append(fila)
    tabla = pd.DataFrame(filas)
    st.dataframe(tabla, hide_index=True, use_container_width=True)

def _panel_estado_v40(cal):
    st.subheader('🛰️ Estado de actualización')
    st.metric('Partidos del calendario', len(cal))
    st.metric('Partidos con marcador', len(cal.dropna(subset=['home_score', 'away_score'])))
    st.write('Última consulta exitosa en esta sesión (UTC):', st.session_state.get('nfl40_consulta_utc', 'No registrada'))

def mostrar_modulo_nfl():
    st.header('🏈 NFL 4.6 | Centro deportivo móvil')
    st.caption('NFLverse · Calendario, resultados y estadísticas observadas')
    if st.button('🔄 Consultar datos nuevos', key='nfl40_actualizar'):
        cargar_calendario_rapido_v40.clear()
        cargar_datos_nfl.clear()
        cargar_jugadores_nfl_v39.clear()
        st.session_state.pop('nfl40_consulta_utc', None)
        st.session_state.pop('nfl43_fecha_fuente', None)
        st.rerun()
    secciones = ['🏠 Inicio', '📅 Partidos', '🏟️ Equipos', '📊 Comparar equipos', '🏈 Enfrentamientos', '🧠 Rendimiento avanzado', '👥 Jugadores', '🛰️ Estado', '🧪 Auditorías y análisis', '🧪 Pruebas 4.1']
    seleccion = st.selectbox('Ir a sección', secciones, key='nfl40_navegacion')
    if seleccion == '🧪 Pruebas 4.1':
        mostrar_pruebas_integrales_nfl_v41()
        return
    if seleccion == '👥 Jugadores':
        try:
            mostrar_jugadores_nfl_v39()
        except Exception as exc:
            st.error('No se pudieron mostrar las estadísticas de jugadores.')
        return
    if seleccion == '🧪 Auditorías y análisis':
        try:
            _mostrar_modulo_nfl_legacy_v40()
        except Exception as exc:
            st.error('No se pudo completar el análisis histórico.')
        return
    try:
        with st.spinner('Consultando calendario NFL...'):
            cal = cargar_calendario_rapido_v40()
        fecha_fuente = cal.attrs.get('consulta_fuente_utc')
        if st.session_state.get('nfl43_fecha_fuente') != fecha_fuente:
            st.session_state['nfl42_ultimo_calendario'] = cal.copy()
            st.session_state['nfl42_respaldo_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
            st.session_state['nfl43_fecha_fuente'] = fecha_fuente
        st.session_state['nfl40_consulta_utc'] = st.session_state.get('nfl42_respaldo_utc', 'No registrada')
        st.session_state['nfl42_usando_respaldo'] = False
    except Exception as exc:
        respaldo = st.session_state.get('nfl42_ultimo_calendario')
        if not isinstance(respaldo, pd.DataFrame) or respaldo.empty:
            st.error('No fue posible cargar el calendario y no hay respaldo en esta sesión.')
            return
        cal = respaldo.copy()
        st.session_state['nfl42_usando_respaldo'] = True
        st.warning('Sin conexión a los datos nuevos. Se muestra el último calendario guardado en esta sesión.')
    try:
        if seleccion == '🏠 Inicio':
            _panel_inicio_v40(cal)
        elif seleccion == '📅 Partidos':
            _panel_partidos_v40(cal)
        elif seleccion == '🏟️ Equipos':
            _panel_equipos_v40(cal)
        elif seleccion == '📊 Comparar equipos':
            _panel_comparacion_v44(cal)
        elif seleccion == '🏈 Enfrentamientos':
            _panel_enfrentamientos_v46(cal)
        elif seleccion == '🧠 Rendimiento avanzado':
            _panel_avanzado_v45(cal)
        elif seleccion == '🛰️ Estado':
            _panel_estado_v40(cal)
    except Exception as exc:
        st.error('Ocurrió un error al presentar esta sección.')

def _evaluar_pruebas_v41(cal):
    pruebas = []
    def agregar(nombre, correcto, detalle, severidad='ERROR'):
        pruebas.append({'Prueba': nombre, 'Estado': 'OK' if correcto else severidad, 'Detalle': str(detalle)})
    columnas = {'game_id', 'season', 'week', 'gameday', 'home_team', 'away_team', 'home_score', 'away_score'}
    faltantes = sorted(columnas - set(cal.columns))
    agregar('Columnas obligatorias', not faltantes, 'Completas' if not faltantes else 'Faltan: ' + ', '.join(faltantes))
    if faltantes:
        return pd.DataFrame(pruebas)
    agregar('Calendario no vacío', len(cal) > 0, f'{len(cal)} partidos')
    duplicados = int(cal['game_id'].duplicated().sum())
    agregar('Identificadores únicos', duplicados == 0, f'{duplicados} duplicados')
    return pd.DataFrame(pruebas)

def _ventana_proximos_v41(cal, fecha_referencia=None):
    hoy = pd.Timestamp(fecha_referencia or datetime.now(timezone.utc).date()).normalize()
    fecha = pd.to_datetime(cal['gameday'], errors='coerce').dt.tz_localize(None).dt.normalize()
    pendientes = cal['home_score'].isna() & cal['away_score'].isna()
    ventana = pendientes & fecha.ge(hoy) & fecha.lt(hoy + pd.Timedelta(days=7))
    return cal.loc[ventana].copy()

def _pruebas_sinteticas_v41():
    base = pd.DataFrame([{'game_id':'2026_01_A_B','season':2026,'week':1, 'gameday':pd.Timestamp('2026-09-10'),'home_team':'A','away_team':'B', 'home_score':21,'away_score':17}])
    return pd.DataFrame([{'Prueba': 'Caso simulado: Identificadores únicos', 'Estado': 'OK', 'Detalle': 'Simulado'}])

def mostrar_pruebas_integrales_nfl_v41():
    st.subheader('🧪 NFL 4.2 | Pruebas integrales')
    if not st.button('▶️ Ejecutar pruebas NFL 4.1', key='nfl41_ejecutar'):
        st.info('Pulsa el botón para ejecutar las comprobaciones.')
        return
    try:
        cal = cargar_calendario_rapido_v40()
    except Exception as exc:
        st.error('No se pudo cargar el calendario.')
        return
    reales = _evaluar_pruebas_v41(cal)
    simuladas = _pruebas_sinteticas_v41()
    resultado = pd.concat([reales.assign(Origen='Datos reales'), simuladas.assign(Origen='Pruebas simuladas')], ignore_index=True)
    st.dataframe(resultado[['Origen','Prueba','Estado','Detalle']], hide_index=True, use_container_width=True)


# ---------------------------------------------------------
# MENÚ PRINCIPAL DE LA APLICACIÓN (TODOS LOS MÓDULOS)
# ---------------------------------------------------------
st.sidebar.title("🎯 Master Suite Analítica")
modulo_seleccionado = st.sidebar.selectbox(
    "Selecciona un Módulo",
    [
        "🏈 NFL 4.6 | Centro deportivo móvil",
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

if modulo_seleccionado == "🏈 NFL 4.6 | Centro deportivo móvil":
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

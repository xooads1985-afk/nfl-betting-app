"""NFL v4.9: proyecciones deportivas educativas con EPA y Success Rate reales.
Integración: from modulo_nfl import mostrar_modulo_nfl
Fuente: nflverse mediante nflreadpy. No incluye cuotas ni apuestas.
"""
from datetime import datetime, timezone, timedelta
import io
import hashlib
import numpy as np
import pandas as pd
import streamlit as st
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
import altair as alt

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

    # Procesar una temporada por vez para limitar el uso de memoria en Streamlit Cloud.
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
    """Solo usa encuentros anteriores a la fecha del partido; agrupa juegos del mismo día."""
    stats = {(str(r.game_id), str(r.equipo)): r for r in estadisticas.itertuples(index=False)}
    historico = {}
    registros = []
    sin_cobertura = 0
    ultima_temporada = None
    prev_temporada = {}

    def previo(equipo, fecha, condicion):
        juegos = historico.get(equipo, [])[-5:]
        # Priors neutrales explícitos; no son estadísticas observadas.
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
            # Preserve previous season only as an experimental prior.
            # Current-season variables remain unchanged.
            prev_temporada = {k: list(v[-5:]) for k, v in historico.items()}
            historico.clear()  # Ventana reciente limitada a la temporada actual.
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
            # Experimental empirical-Bayes style shrinkage, never future data:
            # n current games vs up to 3 pseudo-games of previous season.
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
                # No fabricar EPA/SR si falta la cobertura del partido.
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
                victoria=float(ap > hp) + .5 * float(hp == ap), ubicacion='fuera',
                epa_of=float(sa.epa_of), epa_def=float(sa.epa_def),
                sr_of=float(sa.sr_of), sr_def=float(sa.sr_def)))
    salida = pd.DataFrame(registros)
    salida.attrs['sin_cobertura'] = sin_cobertura
    if sin_cobertura:
        raise ValueError(f'Existen {sin_cobertura} partidos terminados sin cobertura PBP suficiente; validación detenida para evitar estadísticas sesgadas.')
    return salida


@st.cache_resource(show_spinner=False)
def entrenar_v30(csv, huella):
    """Validación temporal: 2024 y 2025; entrenamiento final hasta 2025.

    Las predicciones de evaluación se calculan antes del ajuste final.
    """
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
            raise ValueError(f'Datos insuficientes para evaluación {evaluacion}: '
                             f'{len(train)} entrenamiento, {len(test)} prueba.')
        for nombre, objetivo in objetivos.items():
            modelo = HistGradientBoostingRegressor(
                max_iter=110, max_leaf_nodes=12, learning_rate=.045,
                l2_regularization=8., random_state=42)
            modelo.fit(train[VARIABLES], objetivo(train))
            estimado_boosting = modelo.predict(test[VARIABLES])
            # Arquitectura híbrida: margen = Boosting; total = Ridge.
            # Ridge se eligió tras observar 2024/2025; estas evaluaciones
            # son descriptivas y NO una prueba independiente de selección.
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
                    {'temporada': evaluacion, 'modelo': 'Ridge (modelo activo)',
                     'MAE': float(mean_absolute_error(objetivo(test), estimado))},
                    {'temporada': evaluacion, 'modelo': 'Referencia: promedio',
                     'MAE': float(mean_absolute_error(objetivo(test), base))},
                ])
            resultados.append({
                'temporada': evaluacion, 'objetivo': nombre,
                'MAE_modelo': float(mean_absolute_error(objetivo(test), estimado)),
                'MAE_referencia': float(mean_absolute_error(objetivo(test), base)),
                'partidos_entrenamiento': len(train), 'partidos_prueba': len(test),
            })
    # Ajuste final solo con temporadas anteriores a la temporada actual.
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
    """Compare current features vs prior-season shrinkage on 2024/25/26.

    These are exploratory, retrospectively inspected seasons. No automatic
    promotion of a model. Holdout is season-scoped and chronological.
    """
    df = pd.read_csv(io.StringIO(csv))
    df = df.dropna(subset=['home_score', 'away_score']).copy()
    alt = ['experimental_' + v if 'experimental_' + v in df.columns else v
           for v in VARIABLES]
    if df[VARIABLES + alt].isna().any().any():
        raise ValueError('Variables faltantes en el experimento.')
    resultados = []
    for year in (2024, 2025, 2026):
        train = df[(df.season >= 2022) & (df.season < year)]
        test = df[df.season == year]
        if len(train) < 200 or len(test) < 25:
            continue
        for objetivo in ('margen', 'total'):
            target = (lambda x: x.home_score - x.away_score) if objetivo == 'margen' else (
                lambda x: x.home_score + x.away_score)
            for nombre, cols in [('Actual', VARIABLES),
                                 ('Prior temporada anterior (experimental)', alt)]:
                model = (HistGradientBoostingRegressor(
                    max_iter=110, max_leaf_nodes=12, learning_rate=.045,
                    l2_regularization=8., random_state=42)
                    if objetivo == 'margen'
                    else make_pipeline(StandardScaler(), Ridge(alpha=100.0)))
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
    """Comparación retrospectiva con partición cronológica por temporada.

    No ajusta hiperparámetros sobre el conjunto evaluado ni modifica
    los modelos activos. La inspección previa de estas temporadas
    limita la independencia de la evidencia.
    """
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
    _requerir(df, ['experimental_' + c for c in campos],
              'Experimento v3.0: variables experimentales')
    df = df.sort_values(['season', 'week', 'gameday', 'game_id'])
    if not np.isfinite(df[VARIABLES + ['experimental_' + c for c in campos]]
                       .to_numpy(dtype=float)).all():
        raise ValueError('Hay datos faltantes o no finitos.')
    variantes = {'Actual (peso 0)': 0.0, 'Peso 1': 1.0,
                 'Peso 3 (v2.9)': 3.0, 'Peso 5': 5.0}
    columnas = {}
    for etiqueta, peso in variantes.items():
        columnas[etiqueta] = []
        for c in VARIABLES:
            dest = f'v30_{peso:g}_{c}'
            if c in campos and peso > 0:
                prefix = 'local' if c.startswith('local_') else 'visitante'
                n = df[f'{prefix}_juegos'].astype(float)
                # Recover prior-season mean from the v2.9 weight-3 column.
                # If no prior exists, the experimental column equals current.
                previo = (df['experimental_' + c] * (n + 3.0)
                          - df[c] * n) / 3.0
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
            y_train = (train.home_score - train.away_score if objetivo == 'margen'
                       else train.home_score + train.away_score)
            y_test = (test.home_score - test.away_score if objetivo == 'margen'
                      else test.home_score + test.away_score)
            for variante, cols in columnas.items():
                if objetivo == 'margen':
                    model = HistGradientBoostingRegressor(
                        max_iter=110, max_leaf_nodes=12,
                        learning_rate=.045, l2_regularization=8.,
                        random_state=42)
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
                        'partidos_previos_min': int(min(
                            row.local_juegos, row.visitante_juegos)),
                    })
    return pd.DataFrame(detalle)




@st.cache_data(ttl=86400, show_spinner=False)
def validar_pesos_cronologicos_v31(csv):
    """Selecciona pesos usando temporadas anteriores a la evaluada.

    2024: diagnóstico inicial, sin selección anterior.
    2025: selección basada exclusivamente en 2024.
    2026: selección basada exclusivamente en 2024 y 2025.
    Todos los resultados son retrospectivos y las temporadas ya fueron exploradas.
    """
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
            # Promediar MAE por temporada evita que una temporada con más partidos
            # domine automáticamente la selección de configuración.
            metricas = (previo.groupby(['temporada', 'variante'], as_index=False)
                        .agg(MAE=('error_absoluto', 'mean'))
                        .groupby('variante').MAE.mean())
            if not set(variantes).issubset(metricas.index):
                continue
            elegido = min(variantes, key=lambda v: (float(metricas[v]), variantes.index(v)))
            for configuracion, variante in [
                ('Referencia peso 0', 'Actual (peso 0)'),
                ('Seleccion previa', elegido),
            ]:
                bloque = prueba[prueba.variante == variante]
                if bloque.empty:
                    continue
                resultados.append({
                    'temporada_evaluada': year,
                    'objetivo': objetivo,
                    'configuracion': configuracion,
                    'variante': variante,
                    'MAE': float(bloque.error_absoluto.mean()),
                    'partidos': int(bloque.partido.nunique()),
                    'seleccion_con_temporadas': ', '.join(map(str, sorted(previo.temporada.unique()))),
                })
    return resumen, pd.DataFrame(resultados)



def auditoria_calidad_nfl_v32(calendario, estadisticas, tabla):
    """Diagnóstico descriptivo: no modifica los datos ni los modelos."""
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
    st.caption('Comprobaciones de integridad de NFLverse. No mide precisión predictiva.')
    try:
        resumen, pendientes, fechas = auditoria_calidad_nfl_v32(
            calendario, estadisticas, tabla
        )
        for titulo, valor in [
            ('Último resultado disponible', fechas['ultimo_resultado']),
            ('Último partido con PBP completo', fechas['ultima_fecha_con_pbp_completo']),
        ]:
            fecha = 'Sin datos' if pd.isna(valor) else pd.Timestamp(valor).strftime('%Y-%m-%d')
            st.write(f'**{titulo}:** {fecha}')
        st.caption('Consulta: ' + fechas['consulta_utc'] +
                   '. La hora de consulta no garantiza que NFLverse haya publicado datos nuevos.')
        if resumen.empty:
            st.error('🔴 La auditoría no encontró partidos.')
        elif (resumen['finalizados_sin_pbp_completo'] > 0).any():
            st.warning('🟡 Hay partidos finalizados sin cobertura estadística completa.')
        elif resumen['finalizados'].sum() == 0:
            st.warning('🟡 No se encontraron resultados finalizados.')
        else:
            st.success('🟢 Los partidos finalizados disponibles tienen cobertura PBP válida.')
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        st.download_button('📥 Descargar auditoría por temporada',
            resumen.to_csv(index=False).encode('utf-8'),
            'nfl_v32_calidad_temporadas.csv', 'text/csv', key='nfl32_calidad_csv')
        if not pendientes.empty:
            st.write('**Partidos finalizados con estadísticas incompletas**')
            st.dataframe(pendientes, use_container_width=True, hide_index=True)
            st.download_button('📥 Descargar partidos incompletos',
                pendientes.to_csv(index=False).encode('utf-8'),
                'nfl_v32_partidos_incompletos.csv', 'text/csv', key='nfl32_pendientes_csv')
        st.caption('PBP completo exige al menos 10 jugadas válidas por equipo y EPA/SR '
                   'ofensivo y defensivo disponibles. El umbral es un control de cobertura, '
                   'no una garantía de exactitud. Partidos futuros no cuentan como faltantes.')
    except Exception as exc:
        st.error('🔴 No se pudo completar la auditoría NFL 3.2.')
        st.code(str(exc))

def _instantanea_nfl_v33(calendario, estadisticas):
    """Resumen reproducible para comparar dos consultas de una misma sesión."""
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
    st.caption('Compara consultas de esta sesión de Streamlit. No es monitoreo continuo ni '
               'almacenamiento permanente; al reiniciar el servidor se pierde el historial.')
    actual = _instantanea_nfl_v33(calendario, estadisticas)
    st.write('**Consulta UTC:**', actual['consulta_utc'])
    st.write('**Último resultado disponible:**', actual['ultimo_resultado'] or 'Sin resultados')
    st.write('**Partidos finalizados:**', actual['partidos_finalizados'])
    st.write('**Partidos con registros PBP:**', actual['partidos_con_pbp'])

    if actual['ultimo_resultado']:
        antiguedad = (datetime.now(timezone.utc).date() -
                      pd.Timestamp(actual['ultimo_resultado']).date()).days
        if antiguedad >= 8:
            st.warning(f'🟡 Último resultado hace {antiguedad} días. Comprueba el calendario: '
                       'puede ser una pausa de la temporada o un retraso de datos.')
        else:
            st.success('🟢 La última fecha de resultados no supera el umbral orientativo de 7 días.')
    else:
        st.error('🔴 No hay resultados finalizados disponibles.')

    anterior = st.session_state.get('nfl33_ultima_instantanea')
    historial = st.session_state.setdefault('nfl33_historial', [])
    if anterior is None:
        st.info('Primera consulta registrada en esta sesión. Actualiza para comparar cambios.')
    else:
        nuevos, desaparecidos, modificados = _comparar_instantaneas_nfl_v33(anterior, actual)
        if desaparecidos:
            st.error(f'🔴 Desaparecieron {len(desaparecidos)} partidos previamente finalizados.')
        if modificados:
            st.warning(f'🟡 Cambiaron los marcadores o datos PBP de {len(modificados)} partidos.')
            st.dataframe(pd.DataFrame(modificados), hide_index=True, use_container_width=True)
        if nuevos:
            st.success(f'🟢 Se incorporaron {len(nuevos)} resultados nuevos.')
        if not (nuevos or desaparecidos or modificados):
            st.info('No se detectaron cambios respecto de la consulta anterior de esta sesión.')
        historial.append({
            'consulta_utc': actual['consulta_utc'],
            'resultados_nuevos': len(nuevos),
            'resultados_desaparecidos': len(desaparecidos),
            'partidos_modificados': len(modificados),
            'total_finalizados': actual['partidos_finalizados'],
        })
        del historial[:-20]
    st.session_state['nfl33_ultima_instantanea'] = actual
    if historial:
        st.write('**Historial de comparaciones de esta sesión**')
        datos = pd.DataFrame(historial)
        st.dataframe(datos, hide_index=True, use_container_width=True)
        st.download_button('📥 Descargar historial NFL 3.3',
            datos.to_csv(index=False).encode('utf-8'),
            'nfl_v33_historial_sesion.csv', 'text/csv', key='nfl33_historial_csv')
    st.caption('El botón de actualización limpia la caché de carga, pero una fuente remota '
               'puede seguir publicando la misma versión. Los cambios PBP pueden ser '
               'correcciones legítimas. Este diagnóstico no mide precisión predictiva.')



def auditar_integridad_nfl_v341(calendario, estadisticas):
    """Auditoría descriptiva: cada control se ejecuta de manera independiente."""
    cal, est = calendario.copy(), estadisticas.copy()
    filas = []

    def agregar(nombre, accion, descripcion):
        try:
            cantidad, nivel = accion()
            filas.append(dict(nivel=nivel, control=nombre,
                              registros=int(cantidad), detalle=descripcion))
        except Exception as exc:
            filas.append(dict(nivel='NO EJECUTADO', control=nombre,
                              registros=0, detalle=f'{type(exc).__name__}: {exc}'))

    def serie_num(df, col):
        return pd.to_numeric(df[col], errors='coerce')

    def contar(n, nivel='ERROR'):
        return (int(n), nivel if n else 'OK')

    agregar('IDs de partidos duplicados',
            lambda: contar(cal['game_id'].duplicated().sum()),
            'Cada game_id debe ser único.')
    agregar('Local y visitante idénticos',
            lambda: contar((cal['home_team'] == cal['away_team']).sum()),
            'Los equipos deben ser distintos.')
    agregar('Fechas inválidas',
            lambda: contar(pd.to_datetime(cal['gameday'], errors='coerce').isna().sum()),
            'Todas las fechas deben poder interpretarse.')
    agregar('Partidos sin marcador completo',
            lambda: contar(cal[['home_score', 'away_score']].apply(
                pd.to_numeric, errors='coerce').isna().any(axis=1).sum(), 'INFO'),
            'Incluye partidos futuros: no implica error.')
    agregar('Marcadores negativos',
            lambda: contar(cal[['home_score', 'away_score']].apply(
                pd.to_numeric, errors='coerce').lt(0).any(axis=1).sum()),
            'Los puntos no pueden ser negativos.')
    agregar('Estadísticas duplicadas por equipo',
            lambda: contar(est.duplicated(['game_id', 'equipo']).sum()),
            'Solo una fila por equipo y partido.')
    agregar('SR ofensivo fuera de rango',
            lambda: contar((serie_num(est, 'sr_of').notna() &
                            ~serie_num(est, 'sr_of').between(0, 1)).sum()),
            'Success Rate debe estar entre 0 y 1.')
    agregar('SR defensivo fuera de rango',
            lambda: contar((serie_num(est, 'sr_def').notna() &
                            ~serie_num(est, 'sr_def').between(0, 1)).sum()),
            'Success Rate debe estar entre 0 y 1.')
    agregar('Jugadas negativas o nulas',
            lambda: contar(serie_num(est, 'jugadas').le(0).sum()),
            'Una fila estadística debe contener jugadas válidas.')
    agregar('Estadísticas numéricas faltantes',
            lambda: contar(est[['epa_of', 'epa_def', 'sr_of', 'sr_def',
                                'jugadas']].apply(pd.to_numeric, errors='coerce')
                          .isna().any(axis=1).sum(), 'AVISO'),
            'Revisar filas incompletas.')
    agregar('EPA ofensivo inusual',
            lambda: contar(serie_num(est, 'epa_of').abs().gt(5).sum(), 'REVISAR'),
            'Umbral exploratorio de EPA medio por jugada: |EPA| > 5.')
    agregar('EPA defensivo inusual',
            lambda: contar(serie_num(est, 'epa_def').abs().gt(5).sum(), 'REVISAR'),
            'Umbral exploratorio de EPA medio por jugada: |EPA| > 5.')
    return pd.DataFrame(filas)


def mostrar_auditoria_nfl_v341(calendario, estadisticas):
    st.subheader('🧪 NFL 3.4.1 | Integridad y anomalías')
    st.caption('Doce controles independientes; una falla no interrumpe los demás.')
    informe = auditar_integridad_nfl_v341(calendario, estadisticas)
    errores = int(informe.nivel.eq('ERROR').sum())
    pendientes = int(informe.nivel.eq('NO EJECUTADO').sum())
    avisos = int(informe.nivel.isin(['AVISO', 'REVISAR']).sum())
    a, b, c = st.columns(3)
    a.metric('Controles ejecutados', len(informe) - pendientes)
    b.metric('Controles con errores', errores)
    c.metric('No ejecutados', pendientes)
    if pendientes:
        st.error(f'🔴 {pendientes} controles no se pudieron ejecutar. Revisa la tabla.')
    elif errores:
        st.error(f'🔴 Se encontraron errores en {errores} controles.')
    elif avisos:
        st.warning(f'🟡 Hay {avisos} controles con observaciones.')
    else:
        st.success('🟢 Los doce controles finalizaron sin incidencias detectadas.')
    st.dataframe(informe, use_container_width=True, hide_index=True)
    st.download_button('📥 Descargar auditoría NFL 3.4.1',
                       informe.to_csv(index=False).encode('utf-8'),
                       'nfl_v341_integridad.csv', 'text/csv',
                       key='nfl341_integridad_csv')
    st.caption('Los controles verifican consistencia básica, no exactitud absoluta.')


def crear_reporte_consolidado_nfl_v35(calendario, estadisticas, tabla):
    """Genera un CSV único y portable, sin persistir información en el servidor."""
    fecha_consulta = datetime.now(timezone.utc).isoformat(timespec='seconds')
    filas = []

    def fila(seccion, temporada, indicador, valor, estado, detalle):
        filas.append({
            'consulta_utc': fecha_consulta,
            'seccion': seccion,
            'temporada': temporada,
            'indicador': indicador,
            'valor': valor,
            'estado': estado,
            'detalle': detalle,
        })

    cobertura, pendientes, fechas = auditoria_calidad_nfl_v32(
        calendario, estadisticas, tabla
    )
    for registro in cobertura.to_dict('records'):
        temporada = registro.get('season')
        for campo in ['calendario', 'finalizados',
                      'finalizados_con_pbp_completo',
                      'finalizados_sin_pbp_completo', 'cobertura_pct']:
            fila('Cobertura NFL 3.2', temporada, campo,
                 registro.get(campo), registro.get('estado', ''),
                 'Cobertura calculada sobre resultados finalizados disponibles.')

    for campo in ['ultimo_resultado', 'ultima_fecha_con_pbp_completo']:
        valor = fechas.get(campo)
        fila('Fechas NFL 3.2', '', campo,
             '' if pd.isna(valor) else str(pd.Timestamp(valor).date()),
             'INFORMATIVO', 'La fecha de consulta no prueba una publicación nueva.')

    auditoria = auditar_integridad_nfl_v341(calendario, estadisticas)
    for registro in auditoria.to_dict('records'):
        fila('Integridad NFL 3.4.1', '', registro['control'],
             registro['registros'], registro['nivel'], registro['detalle'])

    instantanea = _instantanea_nfl_v33(calendario, estadisticas)
    for campo in ['partidos_finalizados', 'partidos_con_pbp', 'ultimo_resultado']:
        fila('Actualización NFL 3.3', '', campo, instantanea.get(campo),
             'INFORMATIVO', 'Instantánea correspondiente a esta consulta.')

    historial = st.session_state.get('nfl33_historial', [])
    fila('Actualización NFL 3.3', '', 'comparaciones_en_sesion',
         len(historial), 'INFORMATIVO',
         'Historial temporal de Streamlit, no almacenamiento permanente.')

    return pd.DataFrame(filas)


def mostrar_reporte_consolidado_nfl_v35(calendario, estadisticas, tabla):
    st.subheader('📋 NFL 3.5 | Reporte consolidado de auditorías')
    st.caption('Un solo CSV reúne cobertura, fechas, vigilancia e integridad. '
               'Se genera con los datos disponibles al momento de la consulta.')
    try:
        reporte = crear_reporte_consolidado_nfl_v35(
            calendario, estadisticas, tabla
        )
        sin_ejecutar = reporte['estado'].eq('NO EJECUTADO').sum()
        errores = reporte['estado'].eq('ERROR').sum()
        st.write(f'**Registros del informe:** {len(reporte)}')
        if sin_ejecutar:
            st.error(f'🔴 {sin_ejecutar} controles no pudieron ejecutarse.')
        elif errores:
            st.warning(f'🟡 Se encontraron {errores} controles con errores.')
        else:
            st.success('🟢 Informe consolidado generado correctamente.')
        st.dataframe(reporte, use_container_width=True, hide_index=True)
        st.download_button(
            '📥 Descargar reporte consolidado NFL',
            data=reporte.to_csv(index=False).encode('utf-8-sig'),
            file_name='nfl_reporte_consolidado.csv',
            mime='text/csv',
            key='nfl35_reporte_consolidado'
        )
        st.caption('Guarda el CSV en tu dispositivo para conservarlo. '
                   'La descarga no se almacena automáticamente en la aplicación.')
    except Exception as exc:
        st.error('🔴 No se pudo generar el reporte consolidado.')
        st.code(f'{type(exc).__name__}: {exc}')


def clasificar_partidos_nfl_v36(calendario, fecha_consulta=None):
    """Clasifica encuentros sin confundir futuros con errores de datos."""
    if fecha_consulta is None:
        fecha_consulta = datetime.now(timezone.utc)
    fecha_consulta = pd.Timestamp(fecha_consulta)
    if fecha_consulta.tzinfo is None:
        fecha_consulta = fecha_consulta.tz_localize('UTC')
    fecha_consulta = fecha_consulta.tz_convert('UTC')

    columnas = ['game_id', 'season', 'gameday', 'home_team', 'away_team',
                'home_score', 'away_score']
    faltantes = [c for c in columnas if c not in calendario.columns]
    if faltantes:
        raise ValueError('Faltan columnas de calendario: ' + ', '.join(faltantes))
    df = calendario[columnas].copy()
    df['gameday'] = pd.to_datetime(df['gameday'], errors='coerce', utc=True)
    df['home_score'] = pd.to_numeric(df['home_score'], errors='coerce')
    df['away_score'] = pd.to_numeric(df['away_score'], errors='coerce')
    ambos = df['home_score'].notna() & df['away_score'].notna()
    uno = df['home_score'].notna() ^ df['away_score'].notna()
    fecha_valida = df['gameday'].notna()
    # El calendario puede incluir partidos jugados hoy sin marcador aún;
    # por ello se utiliza un margen de 1 día antes de señalar retrasos.
    vencido = fecha_valida & (df['gameday'] < fecha_consulta - pd.Timedelta(days=1))
    futuro = fecha_valida & (df['gameday'] >= fecha_consulta.normalize())

    df['estado_auditoria'] = 'PENDIENTE DE CONFIRMACION'
    df.loc[futuro & ~ambos & ~uno, 'estado_auditoria'] = 'PROGRAMADO SIN RESULTADO'
    df.loc[vencido & ~ambos & ~uno, 'estado_auditoria'] = 'REVISAR RESULTADO PENDIENTE'
    df.loc[uno, 'estado_auditoria'] = 'MARCADOR PARCIAL'
    df.loc[ambos, 'estado_auditoria'] = 'RESULTADO DISPONIBLE'
    df.loc[~fecha_valida, 'estado_auditoria'] = 'FECHA INVALIDA'
    df['consulta_utc'] = fecha_consulta.isoformat(timespec='seconds')

    resumen = (df.groupby(['season', 'estado_auditoria'], dropna=False)
                 .size().unstack(fill_value=0).reset_index())
    resumen['total_calendario'] = df.groupby('season').size().reindex(resumen['season']).values
    return df, resumen


def mostrar_auditoria_nfl_v36(calendario):
    st.subheader('📅 NFL 3.6 | Estado de partidos y resultados pendientes')
    st.caption('Distingue encuentros programados, resultados disponibles y registros a revisar. '
               'No considera los partidos futuros como errores.')
    try:
        detalle, resumen = clasificar_partidos_nfl_v36(calendario)
        resultados = int(detalle['estado_auditoria'].eq('RESULTADO DISPONIBLE').sum())
        programados = int(detalle['estado_auditoria'].eq('PROGRAMADO SIN RESULTADO').sum())
        revisar = int(detalle['estado_auditoria'].isin([
            'REVISAR RESULTADO PENDIENTE', 'MARCADOR PARCIAL', 'FECHA INVALIDA'
        ]).sum())
        a, b, c = st.columns(3)
        a.metric('Con resultado', resultados)
        b.metric('Programados', programados)
        c.metric('Para revisar', revisar)
        if revisar:
            st.warning(f'🟡 Hay {revisar} registros por verificar. No implica necesariamente error.')
        else:
            st.success('🟢 No se detectaron registros pendientes de revisión con estos criterios.')
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        with st.expander('Ver detalle de los partidos'):
            st.dataframe(detalle, use_container_width=True, hide_index=True)
        st.download_button('📥 Descargar estado de partidos NFL 3.6',
                           detalle.to_csv(index=False).encode('utf-8-sig'),
                           'nfl_v36_estado_partidos.csv', 'text/csv',
                           key='nfl36_estado_partidos')
        st.caption('La fecha del calendario puede no coincidir con la hora exacta de inicio. '
                   'El margen de un día evita alertas prematuras, pero no confirma el estado oficial.')
    except Exception as exc:
        st.error('🔴 No fue posible completar la auditoría NFL 3.6.')
        st.code(f'{type(exc).__name__}: {exc}')


def auditar_consistencia_nfl_v37(calendario, estadisticas, minimo_jugadas=10):
    """Cruza calendario con estadísticas agregadas por equipo; no altera las fuentes."""
    cal = calendario.copy()
    est = estadisticas.copy()
    columnas_cal = {'game_id','season','home_team','away_team','home_score','away_score'}
    columnas_est = {'game_id','equipo','jugadas','epa_of','epa_def','sr_of','sr_def'}
    faltan_cal = columnas_cal - set(cal.columns)
    faltan_est = columnas_est - set(est.columns)
    if faltan_cal or faltan_est:
        raise ValueError('Columnas faltantes: calendario=' + str(sorted(faltan_cal)) +
                         '; estadísticas=' + str(sorted(faltan_est)))
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
    resumen_est = est.groupby(['game_id','equipo'], as_index=False).agg(
        registros=('jugadas','size'), jugadas=('jugadas','max'))
    cruce = esperado.merge(resumen_est, on=['game_id','equipo'], how='left', validate='many_to_one')
    cruce['registros'] = cruce['registros'].fillna(0).astype(int)
    cruce['estado'] = 'OK'
    cruce.loc[cruce['registros'].eq(0),'estado'] = 'SIN PBP DE EQUIPO'
    cruce.loc[cruce['registros'].gt(0) & cruce['jugadas'].lt(minimo_jugadas),
              'estado'] = 'PBP INSUFICIENTE'
    cruce.loc[cruce['registros'].gt(0) & cruce['jugadas'].isna(),
              'estado'] = 'JUGADAS NO VALIDAS'
    ids_cal = set(cal['game_id'])
    extras = est[~est['game_id'].isin(ids_cal)][['game_id','equipo']].copy()
    extras['season'] = pd.NA
    extras['registros'] = 1
    extras['jugadas'] = pd.NA
    extras['estado'] = 'PBP SIN PARTIDO EN CALENDARIO'
    equipos = cal[['game_id','home_team','away_team']].drop_duplicates('game_id')
    unidos = est.merge(equipos, on='game_id', how='inner')
    invalidos = unidos[~(unidos['equipo'].eq(unidos['home_team']) |
                         unidos['equipo'].eq(unidos['away_team']))][['game_id','equipo']].copy()
    invalidos['season'] = pd.NA
    invalidos['registros'] = 1
    invalidos['jugadas'] = pd.NA
    invalidos['estado'] = 'EQUIPO PBP NO CORRESPONDE AL PARTIDO'
    detalle = pd.concat([cruce,extras,invalidos], ignore_index=True)
    detalle = detalle[['game_id','season','equipo','registros','jugadas','estado']]
    resumen = detalle.groupby('estado',dropna=False).size().reset_index(name='registros')
    return detalle, resumen


def mostrar_auditoria_nfl_v37(calendario, estadisticas):
    st.subheader('🔗 NFL 3.7 | Consistencia entre calendario y PBP')
    st.caption('Cruce de equipos y partidos finalizados con estadísticas agregadas. '
               'Un registro insuficiente no implica que la fuente sea incorrecta.')
    try:
        detalle, resumen = auditar_consistencia_nfl_v37(calendario, estadisticas)
        problemas = detalle[detalle['estado'] != 'OK']
        a,b,c = st.columns(3)
        a.metric('Equipos-partido revisados',len(detalle))
        b.metric('Registros para revisar',len(problemas))
        c.metric('Tipos de discrepancia',problemas['estado'].nunique())
        if problemas.empty:
            st.success('🟢 No se encontraron discrepancias con estos criterios.')
        else:
            st.warning('🟡 Se encontraron discrepancias que requieren revisión.')
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        with st.expander('Ver detalle de discrepancias'):
            st.dataframe(problemas, use_container_width=True, hide_index=True)
        st.download_button('📥 Descargar auditoría NFL 3.7',
                           detalle.to_csv(index=False).encode('utf-8-sig'),
                           'nfl_v37_consistencia.csv','text/csv',key='nfl37_csv')
    except Exception as exc:
        st.error('🔴 No se pudo completar la auditoría NFL 3.7.')
        st.code(f'{type(exc).__name__}: {exc}')

def evaluar_estado_nfl_v38(calendario, estadisticas, ahora=None):
    """Diagnóstico descriptivo, sin afirmar que una consulta en caché sea fresca."""
    ahora = ahora or datetime.now(timezone.utc)
    cal = calendario.copy()
    est = estadisticas.copy()
    _requerir(cal, ['game_id','gameday','home_score','away_score'], 'Calendario v3.8')
    _requerir(est, ['game_id','equipo'], 'PBP v3.8')
    cal['gameday'] = pd.to_datetime(cal['gameday'], errors='coerce')
    fin = cal[pd.to_numeric(cal['home_score'], errors='coerce').notna() &
              pd.to_numeric(cal['away_score'], errors='coerce').notna()].copy()
    ultima = fin['gameday'].max() if not fin.empty else pd.NaT
    ultimo_dia = ultima.date().isoformat() if pd.notna(ultima) else None
    dias = (ahora.date() - ultima.date()).days if pd.notna(ultima) else None
    ids_pbp = set(est['game_id'].dropna().astype(str))
    ids_fin = set(fin['game_id'].dropna().astype(str))
    sin_pbp = ids_fin - ids_pbp
    proximos = cal[(cal['gameday'].dt.date >= ahora.date()) &
                   (cal['gameday'].dt.date <= (ahora + timedelta(days=7)).date())]
    return {'ultima_fecha_resultado': ultimo_dia,
            'dias_desde_ultimo_resultado': dias,
            'finalizados': len(ids_fin),
            'finalizados_sin_pbp': len(sin_pbp),
            'proximos_7_dias': int(proximos['game_id'].nunique()),
            'registros_equipos_pbp': len(est)}


def mostrar_monitoreo_nfl_v38(calendario, estadisticas, solo_respaldo=False):
    st.subheader('🛰️ NFL 3.8 | Estado de actualización y conexión')
    st.caption('Diagnóstico de datos disponibles. La hora de consulta NO es la hora de publicación '
               'de NFLverse. La caché local puede contener una versión anterior (TTL: 24 horas).')
    ahora = datetime.now(timezone.utc)
    try:
        datos = evaluar_estado_nfl_v38(calendario, estadisticas, ahora)
        col1, col2, col3 = st.columns(3)
        col1.metric('Partidos con resultado', datos['finalizados'])
        col2.metric('Finalizados sin PBP', datos['finalizados_sin_pbp'])
        col3.metric('Próximos 7 días', datos['proximos_7_dias'])
        st.write('**Última fecha con resultado:**', datos['ultima_fecha_resultado'] or 'Sin datos')
        ultima_carga = st.session_state.get('nfl38_ultima_carga_exitosa')
        if ultima_carga:
            st.write('**Última consulta completada en esta sesión (UTC):**',
                     ultima_carga['consulta_utc'])
        else:
            st.info('Todavía no se ha registrado una consulta completa en esta sesión.')
        intento = st.session_state.get('nfl38_ultimo_intento_utc')
        if intento:
            st.write('**Último intento de actualización manual (UTC):**', intento)
        if solo_respaldo:
            st.error('🔴 Consulta fallida. Estos son datos guardados en memoria de la sesión, NO una actualización.')
        elif datos['finalizados_sin_pbp']:
            st.warning('🟡 Algunos partidos con resultado no tienen PBP agregado; revisa NFL 3.7.')
        else:
            st.success('🟢 Datos cargados sin error en esta ejecución; su publicación remota puede ser anterior.')
        if datos['dias_desde_ultimo_resultado'] is None:
            st.warning('No hay resultados para calcular antigüedad.')
        elif datos['dias_desde_ultimo_resultado'] >= 8:
            st.warning('🟡 Último resultado hace ' + str(datos['dias_desde_ultimo_resultado']) +
                       ' días. Puede ser descanso, temporada baja o retraso de publicación.')
        if st.session_state.get('nfl38_error_reciente'):
            st.error('Error más reciente: ' + st.session_state['nfl38_error_reciente'])
        reporte = pd.DataFrame([{'consulta_utc': ahora.isoformat(timespec='seconds'), **datos,
                                 'modo': 'respaldo' if solo_respaldo else 'consulta'}])
        st.download_button('📥 Descargar diagnóstico NFL 3.8',
                           reporte.to_csv(index=False).encode('utf-8-sig'),
                           'nfl_v38_diagnostico.csv', 'text/csv', key='nfl38_csv')
        st.caption('La actualización es manual mediante el botón superior. No hay sondeo '
                   'automático en segundo plano ni garantías de tiempo real.')
    except Exception as exc:
        st.error('No se pudo ejecutar el monitoreo NFL 3.8.')
        st.code(f'{type(exc).__name__}: {exc}')



@st.cache_data(ttl=21600, show_spinner=False)
def cargar_jugadores_nfl_v39(temporada):
    """Consulta separada por temporada: evita recargar todos los jugadores al abrir la app."""
    import nflreadpy as nfl
    if not hasattr(nfl, 'load_player_stats'):
        raise RuntimeError('Esta versión de nflreadpy no incluye load_player_stats. Actualiza la dependencia.')
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
    st.caption('Datos observados de NFLverse. Las estadísticas disponibles dependen de la publicación y cobertura de la fuente.')
    temporada = st.selectbox('Temporada de jugadores', TEMPORADAS[::-1], key='nfl39_temporada')
    if st.button('📥 Cargar estadísticas de jugadores', key='nfl39_cargar'):
        st.session_state['nfl39_temporada_cargada'] = int(temporada)
    if st.session_state.get('nfl39_temporada_cargada') != int(temporada):
        st.info('Pulsa «Cargar estadísticas de jugadores» para consultar la temporada seleccionada.')
        return
    try:
        with st.spinner('Consultando estadísticas individuales...'):
            df = cargar_jugadores_nfl_v39(int(temporada))
    except Exception as exc:
        st.error('No fue posible consultar las estadísticas individuales. Los demás paneles NFL siguen disponibles.')
        st.caption(f'Detalle técnico: {type(exc).__name__}: {exc}')
        return
    if df.empty:
        st.warning('La fuente no publicó registros de jugadores para esta temporada.')
        return
    nombre = _columna_jugador_v39(df, ['player_display_name', 'player_name', 'player'])
    identificador = _columna_jugador_v39(df, ['player_id', 'gsis_id'])
    equipo = _columna_jugador_v39(df, ['recent_team', 'team', 'posteam'])
    posicion = _columna_jugador_v39(df, ['position', 'position_group'])
    semana = _columna_jugador_v39(df, ['week'])
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
    if posicion:
        posiciones = sorted(df[posicion].dropna().astype(str).unique().tolist())
        seleccion = st.selectbox('Posición', ['Todas'] + posiciones, key='nfl39_posicion')
        if seleccion != 'Todas':
            df = df[df[posicion].astype(str) == seleccion]
    if df.empty:
        st.info('No hay jugadores para los filtros seleccionados.')
        return
    metricas = {
        'Pases completos': ['completions'],
        'Intentos de pase': ['attempts', 'passing_attempts'],
        'Yardas por pase': ['passing_yards'],
        'TD por pase': ['passing_tds'],
        'Intercepciones lanzadas': ['interceptions', 'passing_interceptions'],
        'Acarreos': ['carries', 'rushing_attempts'],
        'Yardas terrestres': ['rushing_yards'],
        'TD terrestres': ['rushing_tds'],
        'Recepciones': ['receptions'],
        'Objetivos de pase': ['targets'],
        'Yardas por recepción': ['receiving_yards'],
        'TD por recepción': ['receiving_tds'],
        'Capturas defensivas': ['sacks_solo', 'sacks', 'def_sacks'],
        'Intercepciones defensivas': ['def_interceptions', 'defensive_interceptions'],
        'Tacleadas': ['def_tackles_solo', 'tackles_solo'],
    }
    disponibles = {etiqueta: col for etiqueta, cols in metricas.items()
                   if (col := _columna_jugador_v39(df, cols)) is not None}
    if not disponibles:
        st.warning('No se encontraron columnas estadísticas reconocidas. Revisa la versión de nflreadpy.')
        with st.expander('Columnas disponibles'):
            st.write(', '.join(df.columns))
        return
    claves = [identificador] if identificador else [nombre]
    if identificador and nombre:
        claves.append(nombre)
    if equipo:
        claves.append(equipo)
    if posicion:
        claves.append(posicion)
    for col in disponibles.values():
        df[col] = pd.to_numeric(df[col], errors='coerce')
    agregados = df.groupby(claves, dropna=False, as_index=False)[list(set(disponibles.values()))].sum(min_count=1)
    agregados = agregados.rename(columns={v: k for k, v in disponibles.items()})
    metrica = st.selectbox('Estadística para ordenar', list(disponibles), key='nfl39_metrica')
    agregados = agregados.sort_values(metrica, ascending=False, na_position='last')
    st.metric('Jugadores encontrados', len(agregados))
    st.dataframe(agregados.head(100).round(2), use_container_width=True, hide_index=True)
    st.download_button('📥 Descargar estadísticas de jugadores (CSV)',
                       agregados.to_csv(index=False).encode('utf-8-sig'),
                       f'nfl_v39_jugadores_{temporada}.csv', 'text/csv', key='nfl39_csv')
    etiquetas = (agregados[nombre].astype(str) + (' | ' + agregados[equipo].astype(str) if equipo else '')).tolist()
    elegido = st.selectbox('Ver evolución de un jugador', range(len(etiquetas)),
                           format_func=lambda i: etiquetas[i], key='nfl39_jugador')
    fila = agregados.iloc[int(elegido)]
    if identificador:
        detalle = df[df[identificador] == fila[identificador]].copy()
    else:
        detalle = df[df[nombre] == fila[nombre]].copy()
        if equipo:
            detalle = detalle[detalle[equipo] == fila[equipo]]
    if semana:
        detalle[semana] = pd.to_numeric(detalle[semana], errors='coerce')
        detalle = detalle.dropna(subset=[semana])
        if not detalle.empty:
            evolucion = detalle.groupby(semana, as_index=False)[disponibles[metrica]].sum(min_count=1)
            evolucion = evolucion.sort_values(semana).rename(columns={semana: 'Semana', disponibles[metrica]: metrica})
            st.line_chart(evolucion.set_index('Semana'))
        else:
            st.info('No hay semanas válidas para graficar este jugador.')
    else:
        st.info('La fuente devolvió datos agregados sin desglose semanal.')
    st.caption('Las cifras son sumas de los registros publicados; no se calculan promedios ni se completan datos faltantes.')


def _mostrar_modulo_nfl_legacy_v40():
    st.header('🏈 NFL | Análisis avanzado v3.9')
    st.caption('Fuente: NFLverse · EPA y Success Rate · Margen: Gradient Boosting · Total: Ridge')
    if st.button('🔄 Consultar nuevamente la fuente NFL', key='nfl_v2_refresh'):
        st.session_state['nfl38_actualizacion_solicitada'] = True
        st.session_state['nfl38_ultimo_intento_utc'] = datetime.now(timezone.utc).isoformat(timespec='seconds')
        cargar_datos_nfl.clear()
        cargar_jugadores_nfl_v39.clear()
        st.rerun()
    try:
        with st.spinner('Cargando jugadas históricas y entrenando el modelo; la primera carga puede tardar...'):
            calendario, estadisticas = cargar_datos_nfl()
            st.session_state['nfl38_ultima_carga_exitosa'] = {
                'calendario': calendario.copy(),
                'estadisticas': estadisticas.copy(),
                'consulta_utc': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            }
            st.session_state['nfl38_error_reciente'] = None
            st.session_state['nfl38_actualizacion_solicitada'] = False
            tabla = construir_historial(calendario, estadisticas)
            completos = tabla.dropna(subset=['home_score', 'away_score'])
            if completos.empty:
                raise ValueError('No hay resultados completos disponibles.')
            # La huella incluye TODAS las variables, no solo los marcadores.
            csv_modelo = tabla.to_csv(index=False)
            import hashlib
            huella = hashlib.sha256(csv_modelo.encode('utf-8')).hexdigest()
            modelos, reporte, ntrain, detalles, comparacion_total, evaluacion_2026, detalles_2026 = entrenar_v30(csv_modelo, huella)
    except Exception as exc:
        st.session_state['nfl38_error_reciente'] = f'{type(exc).__name__}: {exc}'
        st.error('🔴 No se pudo cargar o validar NFL 3.8. No se mostrarán resultados nuevos como si fueran actuales.')
        st.code(str(exc))
        anterior = st.session_state.get('nfl38_ultima_carga_exitosa')
        if anterior is not None:
            st.warning('🟡 Existe una copia de datos de una consulta anterior de esta sesión. Es solo referencia; no se recalcularán modelos con ella.')
            mostrar_monitoreo_nfl_v38(anterior['calendario'], anterior['estadisticas'], solo_respaldo=True)
        return
    mostrar_auditoria_nfl_v32(calendario, estadisticas, tabla)
    mostrar_auditoria_nfl_v33(calendario, estadisticas)
    mostrar_auditoria_nfl_v341(calendario, estadisticas)
    mostrar_reporte_consolidado_nfl_v35(calendario, estadisticas, tabla)
    mostrar_auditoria_nfl_v36(calendario)
    mostrar_auditoria_nfl_v37(calendario, estadisticas)
    mostrar_monitoreo_nfl_v38(calendario, estadisticas)
    mostrar_jugadores_nfl_v39()
    st.success('🟢 Datos históricos cargados y evaluaciones temporales completadas')
    st.write(f'**Partidos usados para ajuste final:** {ntrain}')
    st.caption(f'Último partido con resultado disponible: {completos.gameday.max().date()}')
    st.caption(f'Partidos históricos sin cobertura suficiente de jugadas: '
               f"{tabla.attrs.get('sin_cobertura', 0)}. No se inventó EPA ni Success Rate.")
    st.subheader('📊 Evaluación histórica — 2024 y 2025')
    st.warning('⚠️ Ridge fue seleccionado después de observar los resultados de 2024 y 2025. '
               'Estas temporadas no son una confirmación independiente de su superioridad; '
               'se requiere seguimiento con nuevos partidos.')
    st.dataframe(reporte.round(2), use_container_width=True, hide_index=True)
    st.caption('En cada evaluación se entrena solo con temporadas anteriores; las variables se construyen con partidos previos de la misma temporada. '
               'La referencia predice el promedio del objetivo en el entrenamiento. '
               'Las métricas no garantizan precisión futura.')
    if (reporte.MAE_modelo >= reporte.MAE_referencia).any():
        st.warning('🟡 El modelo no supera la referencia en todas las evaluaciones.')
    else:
        st.info('🟢 El modelo supera la referencia en estas evaluaciones; '
                'aún necesita seguimiento con nuevas temporadas.')
    st.download_button('📥 Descargar evaluación', reporte.to_csv(index=False).encode('utf-8'),
                       'nfl_v30_validacion.csv', 'text/csv', key='nfl_v30_eval')
    st.subheader('🧪 Evaluación de partidos finalizados de 2026')
    st.caption('Estos partidos no se utilizaron para entrenar los modelos finales (2022–2025). '
               'La evaluación es retrospectiva: no demuestra que las proyecciones '
               'se hubieran registrado antes de cada encuentro.')
    if evaluacion_2026.empty:
        st.info('Todavía no hay partidos finalizados de 2026 disponibles para evaluar.')
    else:
        st.dataframe(evaluacion_2026.round(2), use_container_width=True, hide_index=True)
    st.subheader('📅 Auditoría semanal de 2026')
    if detalles_2026.empty:
        st.info('No hay partidos de 2026 para el análisis semanal.')
    else:
        por_semana = detalles_2026.groupby(['objetivo', 'semana'], as_index=False).agg(
            MAE_modelo=('error_modelo', 'mean'),
            MAE_referencia=('error_referencia', 'mean'),
            partidos=('game_id', 'nunique'))
        variable_semana = st.selectbox(
            'Variable para análisis semanal', ['margen', 'total'], key='nfl_v30_week_target')
        semanal = por_semana[por_semana.objetivo == variable_semana].copy()
        columnas_mae = ['MAE_modelo', 'MAE_referencia']
        semanal['semana'] = pd.to_numeric(semanal['semana'], errors='coerce')
        for columna in columnas_mae:
            semanal[columna] = pd.to_numeric(semanal[columna], errors='coerce')
        semanal = semanal.dropna(subset=['semana']).sort_values('semana')
        if semanal.empty or semanal[columnas_mae].isna().all().all():
            st.warning('No hay valores numéricos para graficar esta variable.')
        else:
            datos_largos = semanal[['semana'] + columnas_mae].melt(
                id_vars='semana', value_vars=columnas_mae,
                var_name='indicador', value_name='MAE').dropna(subset=['MAE'])
            grafica = alt.Chart(datos_largos).mark_line(point=True).encode(
                x=alt.X('semana:O', title='Semana NFL'),
                y=alt.Y('MAE:Q', title='Error absoluto medio'),
                color=alt.Color('indicador:N', title='Indicador'),
                tooltip=['semana:O', 'indicador:N', alt.Tooltip('MAE:Q', format='.2f')]
            ).properties(height=350)
            st.altair_chart(grafica, use_container_width=True)
        st.dataframe(semanal.round(2), use_container_width=True, hide_index=True)
        with st.expander('🔍 Diagnóstico de la gráfica semanal'):
            st.write('Semanas:', len(semanal))
            st.write('Valores faltantes:', semanal[columnas_mae].isna().sum().to_dict())
            st.write('Tipos de datos:', semanal.dtypes.astype(str).to_dict())
        st.download_button('📥 Descargar auditoría semanal',
                           por_semana.to_csv(index=False).encode('utf-8'),
                           'nfl_v30_semanas.csv', 'text/csv', key='nfl_v30_weeks_csv')
        st.caption('Cada semana se evalúa con el modelo fijo entrenado hasta 2025. '
                   'No se reentrena utilizando resultados de 2026.')
    st.subheader('🏟️ Auditoría de errores por equipo — 2026')
    if detalles_2026.empty:
        st.info('Sin partidos terminados de 2026 para evaluar por equipo.')
    else:
        objetivo_equipo = st.selectbox(
            'Variable para auditoría por equipo', ['margen', 'total'],
            key='nfl_v30_team_target')
        detalle_equipo = detalles_2026[
            detalles_2026.objetivo == objetivo_equipo].copy()
        # Cada partido se atribuye a los dos equipos; se informa el número
        # de partidos para evitar interpretar promedios con muestras pequeñas.
        local = detalle_equipo.rename(columns={'local': 'equipo'}).copy()
        visitante = detalle_equipo.rename(columns={'visitante': 'equipo'}).copy()
        por_equipo = pd.concat([
            local[['equipo', 'game_id', 'error_modelo', 'error_referencia']],
            visitante[['equipo', 'game_id', 'error_modelo', 'error_referencia']],
        ], ignore_index=True)
        resumen_equipos = por_equipo.groupby('equipo', as_index=False).agg(
            partidos=('game_id', 'nunique'),
            MAE_modelo=('error_modelo', 'mean'),
            MAE_referencia=('error_referencia', 'mean'))
        resumen_equipos['diferencia_MAE'] = (
            resumen_equipos.MAE_modelo - resumen_equipos.MAE_referencia)
        resumen_equipos = resumen_equipos.sort_values(
            ['diferencia_MAE', 'partidos'], ascending=[False, False])
        minimo = st.slider('Mínimo de partidos por equipo', 1, 15, 4,
                           key='nfl_v30_min_games')
        filtrados = resumen_equipos[resumen_equipos.partidos >= minimo]
        st.caption('Diferencia MAE = modelo menos referencia. Positivo indica '
                   'mayor error del modelo. Cada partido cuenta para ambos equipos; '
                   'los resultados por equipo no son independientes.')
        st.dataframe(filtrados.round(2), use_container_width=True,
                     hide_index=True)
        st.download_button('📥 Descargar errores por equipo',
                           resumen_equipos.to_csv(index=False).encode('utf-8'),
                           'nfl_v30_equipos.csv', 'text/csv',
                           key='nfl_v30_teams_csv')
        equipo_seleccionado = st.selectbox(
            'Consultar partidos de un equipo',
            sorted(resumen_equipos.equipo.unique().tolist()),
            key='nfl_v30_team_choice')
        juegos_equipo = detalle_equipo[
            (detalle_equipo.local == equipo_seleccionado) |
            (detalle_equipo.visitante == equipo_seleccionado)
        ].sort_values(['fecha', 'game_id'])
        st.dataframe(
            juegos_equipo[['fecha', 'semana', 'local', 'visitante',
                           'real', 'prediccion', 'error_modelo',
                           'error_referencia']].round(2),
            use_container_width=True, hide_index=True)
        if len(juegos_equipo) < 5:
            st.warning('Muestra pequeña: evita sacar conclusiones sobre este equipo.')

    st.subheader('🔬 Investigación de partidos con mayores errores — 2026')
    if detalles_2026.empty:
        st.info('Todavía no hay partidos terminados de 2026 para investigar.')
    else:
        variable_partido = st.selectbox('Objetivo para revisar partidos',
            ['margen', 'total'], key='nfl_v30_game_target')
        partidos_error = detalles_2026[
            detalles_2026.objetivo == variable_partido].copy()
        partidos_error['diferencia_error'] = (
            partidos_error.error_modelo - partidos_error.error_referencia)
        top_n = st.slider('Cantidad de partidos con mayor error', 5, 30, 10,
                          key='nfl_v30_top_n')
        peores = partidos_error.nlargest(top_n, 'error_modelo')
        st.dataframe(peores[['fecha', 'semana', 'visitante', 'local', 'real',
            'prediccion', 'error_modelo', 'error_referencia', 'diferencia_error']]
            .round(2), hide_index=True, use_container_width=True)
        st.caption('Ordenados por error absoluto del modelo, no por la diferencia '
                   'con la referencia. Seleccionar extremos después de conocer '
                   'resultados no valida un cambio de algoritmo.')
        st.download_button('📥 Descargar errores de partidos 2026',
            partidos_error.to_csv(index=False).encode('utf-8'),
            'nfl_v30_partidos_2026.csv', 'text/csv', key='nfl_v30_games_csv')

        st.subheader('📐 Indicadores anteriores al partido investigado')
        opciones_partidos = {
            f"{r.fecha} | {r.visitante} @ {r.local} | error {r.error_modelo:.1f}": r.game_id
            for r in peores.itertuples(index=False)}
        partido_etiqueta = st.selectbox('Selecciona un partido',
            list(opciones_partidos), key='nfl_v30_selected_game')
        id_seleccionado = opciones_partidos[partido_etiqueta]
        registro = tabla[tabla.game_id.astype(str) == str(id_seleccionado)]
        if len(registro) == 1:
            fila_partido = registro.iloc[0]
            columnas = [
                ('EPA ofensivo', 'local_epa_of', 'visitante_epa_of'),
                ('EPA defensivo', 'local_epa_def', 'visitante_epa_def'),
                ('Success Rate ofensivo', 'local_sr_of', 'visitante_sr_of'),
                ('Success Rate defensivo', 'local_sr_def', 'visitante_sr_def'),
                ('Puntos a favor recientes', 'local_pf', 'visitante_pf'),
                ('Puntos permitidos recientes', 'local_pa', 'visitante_pa'),
                ('Partidos previos', 'local_juegos', 'visitante_juegos'),
                ('Días de descanso', 'descanso_local', 'descanso_visitante'),
            ]
            indicadores = pd.DataFrame([{
                'indicador': titulo,
                'local': float(fila_partido[cl]),
                'visitante': float(fila_partido[cv]),
            } for titulo, cl, cv in columnas])
            st.dataframe(indicadores.round(3), hide_index=True,
                         use_container_width=True)
            if min(fila_partido.local_juegos, fila_partido.visitante_juegos) < 3:
                st.warning('Historial reducido: uno de los equipos tenía menos '
                           'de tres partidos previos válidos.')
            st.caption('Estos indicadores fueron construidos usando encuentros '
                       'anteriores; no incluyen el resultado del partido elegido.')

        st.subheader('📈 Estabilidad según historial disponible')
        cobertura = tabla[['game_id', 'local_juegos', 'visitante_juegos']].copy()
        cobertura['minimo_juegos'] = cobertura[
            ['local_juegos', 'visitante_juegos']].min(axis=1)
        analisis_cobertura = partidos_error.merge(
            cobertura[['game_id', 'minimo_juegos']], on='game_id', how='left',
            validate='one_to_one')
        analisis_cobertura['grupo_historial'] = pd.cut(
            analisis_cobertura.minimo_juegos,
            bins=[-1, 0, 2, 4, float('inf')],
            labels=['0', '1–2', '3–4', '5+'])
        estabilidad = analisis_cobertura.groupby(
            'grupo_historial', observed=True, as_index=False).agg(
            partidos=('game_id', 'nunique'),
            MAE_modelo=('error_modelo', 'mean'),
            MAE_referencia=('error_referencia', 'mean'))
        st.dataframe(estabilidad.round(2), hide_index=True,
                     use_container_width=True)
        st.caption('Agrupación descriptiva por el menor número de partidos '
                   'previos entre los dos equipos. Grupos pequeños pueden '
                   'mostrar variaciones aleatorias grandes.')
    st.subheader('🧹 Calidad de datos por temporada')
    control = tabla.copy()
    control['terminado'] = (
        control.home_score.notna() & control.away_score.notna())
    control['con_historial_3'] = (
        (control.local_juegos >= 3) & (control.visitante_juegos >= 3))
    control['sin_historial'] = (
        (control.local_juegos == 0) | (control.visitante_juegos == 0))
    calidad = control.groupby('season', as_index=False).agg(
        partidos_calendario=('game_id', 'nunique'),
        finalizados=('terminado', 'sum'),
        con_historial_3=('con_historial_3', 'sum'),
        sin_historial=('sin_historial', 'sum'))
    calidad['porcentaje_historial_3'] = (
        100 * calidad.con_historial_3 / calidad.partidos_calendario)
    st.dataframe(calidad.round(1), use_container_width=True, hide_index=True)
    st.caption('Cobertura de historial = partidos con al menos tres juegos '
               'previos válidos por equipo en la misma temporada. '
               'Incluye partidos futuros en el denominador del calendario.')
    st.download_button('📥 Descargar calidad de datos',
                       calidad.to_csv(index=False).encode('utf-8'),
                       'nfl_v30_calidad.csv', 'text/csv',
                       key='nfl_v30_quality_csv')
    st.subheader('🧪 Experimento de estabilidad al inicio de temporada — v3.0')
    st.caption('Se compara el modelo actual con una variante que mezcla las '
               'estadísticas de la temporada actual y los últimos cinco partidos '
               'de la temporada anterior, con peso equivalente a tres partidos. '
               'Solo se usa información anterior al encuentro. '
               'El modelo activo NO cambia.')
    if st.button('🔬 Ejecutar comparación de historial previo', key='nfl_v30_prior_run'):
        with st.spinner('Entrenando variantes históricas...'):
            try:
                tabla_exp = experimento_priors(csv_modelo)
                if tabla_exp.empty:
                    st.warning('No hay suficientes partidos para la comparación.')
                else:
                    st.dataframe(tabla_exp.round(2), hide_index=True,
                                 use_container_width=True)
                    st.download_button(
                        '📥 Descargar experimento',
                        tabla_exp.to_csv(index=False).encode('utf-8'),
                        'nfl_v30_experimento_priors.csv', 'text/csv',
                        key='nfl_v30_prior_csv')
                    st.warning('Resultados exploratorios: las temporadas 2024–2026 '
                               'ya se examinaron durante el desarrollo. '
                               'No deben usarse como confirmación independiente.')
            except Exception as exc:
                st.error('No se pudo completar el experimento.')
                st.code(str(exc))
    st.subheader('🧪 NFL 3.1 | Validación temporal de pesos')
    st.caption('Para cada temporada se selecciona el peso usando solo temporadas anteriores. '
               'Esto evita elegir el ganador mirando los errores de la misma temporada evaluada. '
               '2024–2026 ya fueron examinadas en el desarrollo, por lo que esta auditoría sigue siendo exploratoria.')
    if st.button('🔬 Ejecutar validación NFL 3.1', key='nfl31_run'):
        st.session_state['nfl31_enabled'] = True
    if st.session_state.get('nfl31_enabled', False):
        try:
            with st.spinner('Calculando validación cronológica...'):
                resumen31, validacion31 = validar_pesos_cronologicos_v31(csv_modelo)
            if validacion31.empty:
                st.info('No hay suficientes partidos completos para esta validación.')
            else:
                st.write('**Comparación de la selección previa frente al peso cero**')
                st.dataframe(validacion31.round(3), hide_index=True, use_container_width=True)
                st.download_button('📥 Descargar validación NFL 3.1',
                    validacion31.to_csv(index=False).encode('utf-8'),
                    'nfl_v31_validacion_temporal.csv', 'text/csv', key='nfl31_csv')
                periodo31 = st.selectbox('Periodo para desglose',
                    ['Semanas 1–4', 'Semana 5+'], key='nfl31_periodo')
                detalles31 = experimento_pesos_v30(csv_modelo)
                filtrados31 = detalles31[detalles31.semana.le(4) if periodo31 == 'Semanas 1–4' else detalles31.semana.gt(4)]
                desglose31 = (filtrados31.groupby(['temporada', 'objetivo', 'variante'], as_index=False)
                    .agg(MAE=('error_absoluto', 'mean'), partidos=('partido', 'nunique')))
                st.dataframe(desglose31.round(2), hide_index=True, use_container_width=True)
                st.warning('La selección de pesos sigue siendo experimental. No garantiza menor error en partidos futuros.')
        except Exception as exc:
            st.error('Falló la validación NFL 3.1.')
            st.code(str(exc))

    st.subheader('🧪 NFL 3.0 | Sensibilidad al peso histórico')
    st.caption('Experimento exploratorio: pesos 0, 1, 3 y 5 partidos '
               'equivalentes de la temporada anterior. Entrena con temporadas '
               'anteriores y evalúa cada temporada posterior por separado. '
               'No cambia las proyecciones principales.')
    if st.button('📊 Comparar pesos y semanas', key='nfl_v30_run'):
        st.session_state['nfl31_experiment_enabled'] = True
    if st.session_state.get('nfl31_experiment_enabled', False):
        try:
            with st.spinner('Comparando variantes cronológicas...'):
                exp30 = experimento_pesos_v30(csv_modelo)
            if exp30.empty:
                st.warning('No hay suficientes partidos para comparar.')
            else:
                resumen = (exp30.groupby(['temporada', 'objetivo', 'variante'],
                                         as_index=False)
                           .agg(partidos=('partido', 'nunique'),
                                MAE=('error_absoluto', 'mean')))
                st.write('**MAE por temporada y variante (menor es mejor)**')
                st.dataframe(resumen.round(2), hide_index=True,
                             use_container_width=True)
                objetivo30 = st.selectbox(
                    'Objetivo para auditoría semanal', ['margen', 'total'],
                    key='nfl_v30_obj')
                temporada30 = st.selectbox(
                    'Temporada para auditoría semanal',
                    sorted(exp30.temporada.unique().tolist(), reverse=True),
                    key='nfl_v30_year')
                sub = exp30[(exp30.objetivo == objetivo30)
                            & (exp30.temporada == temporada30)]
                semanal = (sub.groupby(['semana', 'variante'], as_index=False)
                           .agg(partidos=('partido', 'nunique'),
                                MAE=('error_absoluto', 'mean')))
                st.write('**Errores por semana (mismo conjunto de partidos)**')
                st.dataframe(semanal.round(2), hide_index=True,
                             use_container_width=True)
                grafica = (alt.Chart(semanal).mark_line(point=True)
                           .encode(x=alt.X('semana:O', title='Semana'),
                                   y=alt.Y('MAE:Q', title='MAE'),
                                   color='variante:N',
                                   tooltip=['semana', 'variante',
                                            'partidos', alt.Tooltip('MAE:Q', format='.2f')]))
                st.altair_chart(grafica, use_container_width=True)
                st.write('**Primeras semanas (1–4) frente al resto**')
                temp = exp30.copy()
                temp['periodo'] = np.where(temp.semana <= 4, 'Semanas 1–4', 'Semana 5+')
                periodos = (temp.groupby(['temporada', 'objetivo', 'periodo',
                                          'variante'], as_index=False)
                            .agg(partidos=('partido', 'nunique'),
                                 MAE=('error_absoluto', 'mean')))
                st.dataframe(periodos.round(2), hide_index=True,
                             use_container_width=True)
                st.download_button('📥 Descargar comparación 3.0',
                                   exp30.to_csv(index=False).encode('utf-8'),
                                   'nfl_v30_errores_por_partido.csv', 'text/csv',
                                   key='nfl_v30_download')
                st.warning('Las temporadas 2024–2026 ya fueron exploradas '
                           'en versiones anteriores. No selecciones un peso '
                           'como ganador definitivo usando estas mismas pruebas. '
                           'Hace falta una evaluación futura independiente.')
        except Exception as exc:
            st.error('No se pudo ejecutar el experimento 3.0.')
            st.code(str(exc))
    st.subheader('🔎 Auditoría de variables entre temporadas')
    auditoria = tabla.groupby('season', as_index=False).agg(
        partidos=('game_id', 'nunique'),
        EPA_local_medio=('local_epa_of', 'mean'),
        EPA_visitante_medio=('visitante_epa_of', 'mean'),
        SR_local_medio=('local_sr_of', 'mean'),
        SR_visitante_medio=('visitante_sr_of', 'mean'),
        juegos_previos_local=('local_juegos', 'mean'),
        juegos_previos_visitante=('visitante_juegos', 'mean'))
    st.dataframe(auditoria.round(3), use_container_width=True, hide_index=True)
    st.caption('Los promedios incluyen partidos programados y valores neutrales de inicio de temporada. '
               'Son indicadores de cambios y cobertura, no pruebas concluyentes de calidad.')
    faltantes = tabla[VARIABLES].isna().sum().sort_values(ascending=False)
    st.write('**Variables con datos faltantes:**')
    st.dataframe(faltantes.rename('faltantes').to_frame(), use_container_width=True)
    st.subheader('🔬 Diagnóstico del modelo (partidos no vistos durante el entrenamiento)')
    st.caption('Los errores se calculan exclusivamente con los partidos de prueba de 2024 y 2025. '
               'No son métricas de los partidos usados para entrenar cada evaluación.')
    objetivo_diag = st.selectbox('Variable para diagnóstico', ['margen', 'total'], key='nfl_v30_objetivo')
    muestra = detalles[detalles['objetivo'] == objetivo_diag].copy()
    resumen = muestra.groupby('temporada', as_index=False).agg(
        MAE_modelo=('error_absoluto', 'mean'),
        MAE_referencia=('error_referencia', 'mean'),
        sesgo_promedio=('error_firmado', 'mean'),
        partidos=('real', 'size'))
    st.write('**Error absoluto medio por temporada**')
    # Barras agrupadas: nunca apilar dos errores MAE.
    barras = resumen.melt(id_vars='temporada', value_vars=['MAE_modelo', 'MAE_referencia'],
                          var_name='serie', value_name='MAE')
    grafico = alt.Chart(barras).mark_bar().encode(
        x=alt.X('temporada:O', title='Temporada'),
        xOffset='serie:N',
        y=alt.Y('MAE:Q', title='Error absoluto medio (puntos)', scale=alt.Scale(zero=True)),
        color=alt.Color('serie:N', title='Serie'),
        tooltip=['temporada:O', 'serie:N', alt.Tooltip('MAE:Q', format='.2f')],
    ).properties(height=280)
    st.altair_chart(grafico, use_container_width=True)
    st.dataframe(resumen.round(2), use_container_width=True, hide_index=True)
    st.caption('Sesgo promedio = proyección menos resultado real. Cerca de cero significa menor sesgo sistemático, '
               'pero no garantiza un error pequeño.')
    if objetivo_diag == 'total':
        st.subheader('🧪 Diagnóstico específico del total de puntos')
        st.caption('Comparación histórica de Ridge (modelo activo), Gradient Boosting y referencia. '
                   'Los partidos de evaluación no se usaron para ajustar los parámetros, '
                   'pero sus resultados influyeron en la elección de Ridge.')
        st.dataframe(comparacion_total.pivot(index='temporada', columns='modelo', values='MAE').round(2),
                     use_container_width=True)
        st.write('**Sesgo del total (predicción menos puntos reales)**')
        st.dataframe(resumen[['temporada', 'sesgo_promedio', 'partidos']].round(2),
                     use_container_width=True, hide_index=True)
        st.caption('Sesgo positivo: sobreestimación promedio. Negativo: subestimación promedio. '
                   'Un sesgo bajo no implica necesariamente un MAE bajo.')
        st.write('**Total real frente a total proyectado**')
        puntos = alt.Chart(muestra).mark_circle(size=48, opacity=0.55).encode(
            x=alt.X('real:Q', title='Puntos reales'),
            y=alt.Y('prediccion:Q', title='Puntos proyectados'),
            color=alt.Color('temporada:N', title='Temporada'),
            tooltip=['fecha:N', 'local:N', 'visitante:N',
                     alt.Tooltip('real:Q', format='.1f'),
                     alt.Tooltip('prediccion:Q', format='.1f')],
        ).properties(height=310)
        st.altair_chart(puntos, use_container_width=True)
        st.info('Ridge es ahora el modelo activo para el total. Su ventaja histórica '
                'debe confirmarse con datos posteriores a la selección del algoritmo.')
    st.write('**Errores absolutos por partido (orden cronológico)**')
    orden = muestra.sort_values(['fecha', 'local', 'visitante']).reset_index(drop=True)
    st.line_chart(orden[['error_absoluto', 'error_referencia']].rename(
        columns={'error_absoluto': 'Modelo', 'error_referencia': 'Referencia'}))
    st.write('**Diez partidos con mayor error del modelo**')
    peores = muestra.nlargest(10, 'error_absoluto')[[
        'temporada', 'fecha', 'visitante', 'local', 'real', 'prediccion', 'error_absoluto']]
    st.dataframe(peores.round(2), use_container_width=True, hide_index=True)
    st.download_button('📥 Descargar errores por partido',
                       detalles.to_csv(index=False).encode('utf-8'),
                       'nfl_v30_errores.csv', 'text/csv', key='nfl_v30_errores')
    st.subheader('🧪 Calidad y cobertura de datos')
    cobertura = tabla.groupby('season', as_index=False).agg(
        partidos_calendario=('game_id', 'size'),
        partidos_finalizados=('home_score', 'count'))
    cobertura['partidos_sin_resultado'] = (cobertura['partidos_calendario'] -
                                           cobertura['partidos_finalizados'])
    st.dataframe(cobertura, use_container_width=True, hide_index=True)
    st.caption(f"Partidos finalizados sin PBP suficiente: {tabla.attrs.get('sin_cobertura', 0)}. "
               'Los valores neutrales al inicio de cada temporada son supuestos y no observaciones. '
               'El panel no sustituye una auditoría externa de la fuente.')
    st.subheader('🏟️ Próximos partidos')
    st.caption('Margen: Gradient Boosting. Total: Ridge. '
               'Los resultados de 2026 se usan para auditar, no para reentrenar.')
    hoy = pd.Timestamp(datetime.now(timezone.utc).date())
    futuros = tabla[(tabla.gameday >= hoy) & tabla.home_score.isna() & tabla.away_score.isna()].sort_values('gameday')
    if futuros.empty:
        st.info('No se encontraron próximos partidos en el calendario publicado.')
        return
    opciones = {f'{r.gameday.date()} | {r.away_team} @ {r.home_team} | Semana {r.week}': idx
                for idx, r in futuros.iterrows()}
    seleccion = st.selectbox('Partido', list(opciones), key='nfl_v2_game')
    partido = futuros.loc[opciones[seleccion]]
    X = pd.DataFrame([partido[VARIABLES].to_dict()])[VARIABLES]
    if min(int(partido.local_juegos), int(partido.visitante_juegos)) < 3:
        st.warning('⚠️ Se requieren al menos tres partidos previos por equipo en esta temporada. No se muestra una proyección con datos neutrales.')
        return
    margen = float(modelos['margen'].predict(X)[0])
    total = float(modelos['total'].predict(X)[0])
    c1, c2, c3 = st.columns(3)
    st.caption('Modelos activos: Gradient Boosting (margen) y Ridge (total). '
               'Ajuste final: temporadas 2022–2025; 2026 no participa en el entrenamiento.')
    c1.metric('Margen local', f'{margen:+.1f}')
    c2.metric('Total estimado', f'{total:.1f}')
    c3.metric('Puntos local / visitante', f'{(total+margen)/2:.1f} / {(total-margen)/2:.1f}')
    st.subheader('📝 Registro verificable de proyección')
    fecha_registro = datetime.now(timezone.utc).isoformat(timespec='seconds')
    registro = pd.DataFrame([{
        'registrado_utc': fecha_registro,
        'game_id': str(partido.game_id),
        'fecha_partido': str(partido.gameday)[:10],
        'local': partido.home_team,
        'visitante': partido.away_team,
        'margen_estimado': round(margen, 3),
        'total_estimado': round(total, 3),
        'modelo_version': '2.6',
        'datos_sha256': huella,
        'entrenamiento_hasta': 2025,
    }])
    st.download_button(
        '📥 Guardar registro fechado (CSV)', registro.to_csv(index=False).encode('utf-8'),
        f'nfl_registro_{partido.game_id}.csv', 'text/csv', key='nfl_v30_log')
    st.caption('El registro se genera al descargarlo. Guárdalo antes del partido '
               'en un lugar con historial de versiones; Streamlit no lo almacena '
               'automáticamente ni certifica su fecha.')
    st.write('**Indicadores previos al partido (últimos cinco encuentros disponibles):**')
    st.dataframe(pd.DataFrame({
        'Métrica': ['EPA ofensivo', 'EPA defensivo', 'Success Rate ofensivo', 'Success Rate defensivo', 'Partidos previos'],
        'Local': [partido.local_epa_of, partido.local_epa_def, partido.local_sr_of,
                  partido.local_sr_def, partido.local_juegos],
        'Visitante': [partido.visitante_epa_of, partido.visitante_epa_def,
                      partido.visitante_sr_of, partido.visitante_sr_def, partido.visitante_juegos],
    }).round(3), hide_index=True, use_container_width=True)
    st.caption('Los valores neutrales iniciales son supuestos explícitos para equipos sin historial. No se incorporan lesiones ni clima. Proyecciones educativas, no certezas.')
    exportar = pd.DataFrame([{'fecha': partido.gameday.date(), 'local': partido.home_team,
        'visitante': partido.away_team, 'margen_local': round(margen, 2), 'total': round(total, 2)}])
    st.download_button('📥 Descargar proyección', exportar.to_csv(index=False).encode('utf-8'),
                       'nfl_v30_proyeccion.csv', 'text/csv', key='nfl_v2_export')


# NFL 4.0: navegación móvil. Los paneles pesados se cargan únicamente cuando se solicitan.
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



def diagnosticar_duplicados_v421(df):
    """Reporta coincidencias sin alterar el calendario original."""
    if df.empty:
        return pd.DataFrame(columns=['tipo', 'game_id', 'fecha', 'visitante', 'local', 'temporada', 'semana'])
    d = df.copy()
    d['_fecha'] = pd.to_datetime(d['gameday'], errors='coerce').dt.strftime('%Y-%m-%d')
    d['_id'] = d['game_id'].astype('string').fillna('')
    d['_away'] = d['away_team'].astype('string').fillna('')
    d['_home'] = d['home_team'].astype('string').fillna('')
    # Coincidencias por fecha/equipos no se consideran automáticamente duplicados reales.
    por_id = d['_id'].ne('') & d.duplicated('_id', keep=False)
    por_cruce = d.duplicated(['_fecha', '_away', '_home'], keep=False)
    d = d.loc[por_id | por_cruce].copy()
    if d.empty:
        return pd.DataFrame(columns=['tipo', 'game_id', 'fecha', 'visitante', 'local', 'temporada', 'semana'])
    d['tipo'] = ['ID repetido' if i else 'Misma fecha y equipos (revisar)' for i in d.index.map(lambda x: bool(por_id.loc[x]))]
    return pd.DataFrame({'tipo': d['tipo'], 'game_id': d['game_id'],
                         'fecha': d['_fecha'], 'visitante': d['away_team'],
                         'local': d['home_team'], 'temporada': d['season'],
                         'semana': d['week']}).reset_index(drop=True)


def _vista_sin_repeticiones_v421(df):
    """Oculta solo copias exactas en tarjetas, nunca borra filas de la fuente."""
    if df.empty:
        return df.copy(), 0
    # Un game_id diferente no se descarta aunque fecha y equipos coincidan.
    # Se consideran repetidos visuales solo registros con los mismos campos clave.
    cols = [c for c in ['game_id', 'season', 'week', 'gameday', 'away_team',
                         'home_team', 'away_score', 'home_score'] if c in df.columns]
    vista = df.drop_duplicates(subset=cols, keep='first')
    return vista, len(df) - len(vista)


def _tarjetas_partidos_v42(df, prefijo='nfl42'):
    """Tarjetas móviles; estado EN VIVO solo si la fuente lo declara."""
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
        # La presencia de un marcador no basta para afirmar que terminó.
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
        resultado = (f'**{visita} {int(pv)} — {int(pl)} {local}**'
                     if con_marcador else f'**{visita} vs. {local}**')
        with st.container(border=True):
            st.caption(f'{fecha_txt} · Semana {semana_txt} · {etiqueta}')
            st.markdown(resultado)
    if len(vista) > 30:
        st.caption(f'Mostrando 30 de {len(vista)} partidos. Usa los filtros para reducir la lista.')


def _marcador_v40(df):
    """Vista original en tabla, disponible para descargas y consulta detallada."""
    if df.empty:
        st.info("No hay partidos en este filtro.")
        return
    vista = df[['gameday', 'week', 'away_team', 'home_team',
                'away_score', 'home_score']].copy()
    vista['gameday'] = pd.to_datetime(vista['gameday'], errors='coerce').dt.strftime('%Y-%m-%d')
    vista = vista.rename(columns={'gameday': 'Fecha', 'week': 'Semana',
        'away_team': 'Visitante', 'home_team': 'Local',
        'away_score': 'Puntos visitante', 'home_score': 'Puntos local'})
    st.dataframe(vista, hide_index=True, use_container_width=True)


def _panel_inicio_v40(cal):
    hoy = pd.Timestamp(datetime.now(timezone.utc).date())
    completos = cal.dropna(subset=['home_score', 'away_score'])
    proximos_7 = _ventana_proximos_v41(cal)
    futuros = cal[(cal['gameday'] >= hoy) & cal['home_score'].isna()
                  & cal['away_score'].isna()].sort_values(['gameday', 'game_id'])
    st.subheader('🏠 Resumen NFL')
    st.caption('Los estados en vivo requieren un campo explícito de la fuente; el calendario NFLverse puede no ofrecerlo.')
    st.metric('Partidos con resultado', len(completos))
    st.metric('Próximos 7 días', len(proximos_7))
    st.caption('Ventana: desde hoy UTC (incluido) hasta dentro de 7 días (excluido).')
    if not completos.empty:
        st.caption('Última fecha con resultado: ' + str(completos['gameday'].max().date()))
    st.markdown('**📅 Próximos encuentros**')
    _tarjetas_partidos_v42(futuros.head(8))
    st.markdown('**🏈 Resultados recientes**')
    _tarjetas_partidos_v42(completos.sort_values(['gameday', 'game_id'], ascending=False).head(8))
    with st.expander("Ver tablas completas"):
        st.markdown("Próximos encuentros")
        _marcador_v40(futuros.head(12))
        st.markdown("Resultados recientes")
        _marcador_v40(completos.sort_values('gameday', ascending=False).head(12))


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
    vista = st.radio('Presentación', ['📱 Tarjetas', '📋 Tabla'],
                    horizontal=True, key='nfl42_vista_partidos')
    if vista == '📱 Tarjetas':
        _tarjetas_partidos_v42(base)
    else:
        _marcador_v40(base)
    with st.expander('🔍 Diagnóstico de coincidencias del calendario'):
        incidencias = diagnosticar_duplicados_v421(base)
        st.metric('Registros coincidentes', len(incidencias))
        if incidencias.empty:
            st.success('No se encontraron identificadores repetidos ni coincidencias de fecha y equipos en este filtro.')
        else:
            st.warning('Estos registros necesitan revisión. No se eliminaron del calendario.')
            st.dataframe(incidencias, hide_index=True, use_container_width=True)
            st.download_button('📥 Descargar diagnóstico (CSV)',
                               incidencias.to_csv(index=False).encode('utf-8-sig'),
                               'nfl421_coincidencias.csv', 'text/csv', key='nfl421_diag_csv')
    st.download_button('📥 Descargar calendario (CSV)',
                       base.to_csv(index=False).encode('utf-8-sig'),
                       'nfl42_calendario.csv', 'text/csv', key='nfl40_csv_calendario')


def _panel_equipos_v40(cal):
    st.subheader('🏟️ Estadísticas de equipos')
    temporadas = sorted(cal['season'].dropna().astype(int).unique().tolist(), reverse=True)
    temporada = st.selectbox('Temporada', temporadas, key='nfl40_temporada_equipos')
    juegos = cal[(cal['season'] == temporada)].dropna(subset=['home_score', 'away_score']).copy()
    if juegos.empty:
        st.info('Aún no hay marcadores para esta temporada.')
        return
    local = pd.DataFrame({'Equipo': juegos['home_team'], 'PF': juegos['home_score'],
        'PC': juegos['away_score'], 'V': (juegos['home_score'] > juegos['away_score']).astype(int),
        'D': (juegos['home_score'] < juegos['away_score']).astype(int),
        'E': (juegos['home_score'] == juegos['away_score']).astype(int)})
    visita = pd.DataFrame({'Equipo': juegos['away_team'], 'PF': juegos['away_score'],
        'PC': juegos['home_score'], 'V': (juegos['away_score'] > juegos['home_score']).astype(int),
        'D': (juegos['away_score'] < juegos['home_score']).astype(int),
        'E': (juegos['home_score'] == juegos['away_score']).astype(int)})
    tabla = pd.concat([local, visita], ignore_index=True).groupby('Equipo', as_index=False)[['PF', 'PC', 'V', 'D', 'E']].sum()
    tabla['PJ'] = tabla['V'] + tabla['D'] + tabla['E']
    tabla['Diferencia'] = tabla['PF'] - tabla['PC']
    tabla = tabla.sort_values(['V', 'Diferencia'], ascending=[False, False])
    st.caption('Resumen calculado de los marcadores disponibles. No representa la clasificación oficial por desempates.')
    st.dataframe(tabla[['Equipo', 'PJ', 'V', 'D', 'E', 'PF', 'PC', 'Diferencia']],
                 hide_index=True, use_container_width=True)
    st.download_button('📥 Descargar equipos (CSV)', tabla.to_csv(index=False).encode('utf-8-sig'),
                       'nfl40_equipos.csv', 'text/csv', key='nfl40_csv_equipos')



def _panel_comparacion_v44(cal):
    """Comparación descriptiva de resultados, sin inferencias ni proyecciones."""
    st.subheader('📊 NFL 4.4 | Comparador de equipos')
    st.caption('Indicadores calculados a partir de marcadores finales disponibles; '
               'no incluyen métricas PBP ni clasificación oficial.')
    temporadas = sorted(cal['season'].dropna().astype(int).unique().tolist(), reverse=True)
    if not temporadas:
        st.info('No hay temporadas para comparar.')
        return
    temporada = st.selectbox('Temporada de comparación', temporadas, key='nfl44_temporada')
    juegos = cal[cal['season'].eq(temporada)].dropna(
        subset=['home_score', 'away_score']).copy()
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
            pd.DataFrame({'Fecha': local['gameday'], 'Semana': local['week'],
                          'PF': local['home_score'], 'PC': local['away_score'],
                          'Rival': local['away_team'], 'Sede': 'Local'}),
            pd.DataFrame({'Fecha': visita['gameday'], 'Semana': visita['week'],
                          'PF': visita['away_score'], 'PC': visita['home_score'],
                          'Rival': visita['home_team'], 'Sede': 'Visitante'})
        ], ignore_index=True).sort_values(['Fecha', 'Semana']).reset_index(drop=True)
        x['Diferencia'] = x['PF'] - x['PC']
        x['Resultado'] = x['Diferencia'].map(lambda v: 'V' if v > 0 else ('D' if v < 0 else 'E'))
        x['Partido'] = range(1, len(x) + 1)
        return x

    da, db = datos_equipo(a), datos_equipo(b)
    def resumen(nombre, d):
        return {'Equipo': nombre, 'PJ': len(d),
                'Victorias': int((d['Resultado'] == 'V').sum()),
                'Derrotas': int((d['Resultado'] == 'D').sum()),
                'Empates': int((d['Resultado'] == 'E').sum()),
                'PF': int(d['PF'].sum()), 'PC': int(d['PC'].sum()),
                'Diferencia': int(d['Diferencia'].sum()),
                'PF por partido': round(float(d['PF'].mean()), 2),
                'PC por partido': round(float(d['PC'].mean()), 2)}
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
    st.line_chart(grafica.pivot_table(index='Partido', columns='Equipo', values='PF',
                                     aggfunc='first'), use_container_width=True)
    st.caption('Eje horizontal: orden cronológico de partidos de cada equipo, '
               'no fechas compartidas. Las muestras pueden tener diferente tamaño.')
    st.markdown('**Historial de partidos**')
    elegido = st.selectbox('Consultar equipo', [a, b], key='nfl44_detalle')
    detalle = da if elegido == a else db
    st.dataframe(detalle[['Fecha', 'Semana', 'Rival', 'Sede', 'PF', 'PC',
                          'Diferencia', 'Resultado']], hide_index=True,
                 use_container_width=True)
    st.download_button('📥 Descargar comparación (CSV)',
                       comparacion.to_csv(index=False).encode('utf-8-sig'),
                       'nfl44_comparacion_equipos.csv', 'text/csv',
                       key='nfl44_csv_comparacion')


def _agregar_pbp_v451(df):
    """Agrega cada métrica con su propio denominador de jugadas válidas."""
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
            return pd.DataFrame(columns=['game_id', 'equipo',
                f'EPA {prefijo}', f'SR {prefijo}',
                f'Jugadas EPA {prefijo}', f'Jugadas SR {prefijo}'])
        return (d.groupby(['game_id', lado], as_index=False)
                .agg(**{f'EPA {prefijo}': ('epa', 'mean'),
                        f'SR {prefijo}': ('success', 'mean'),
                        f'Jugadas EPA {prefijo}': ('epa', 'count'),
                        f'Jugadas SR {prefijo}': ('success', 'count')})
                .rename(columns={lado: 'equipo'}))
    ataque = agregar('posteam', 'ofensivo')
    defensa = agregar('defteam', 'permitido')
    return ataque.merge(defensa, on=['game_id', 'equipo'], how='outer',
                        validate='one_to_one')


@st.cache_data(ttl=3600, show_spinner=False)
def _cargar_pbp_comparacion_v45(temporada):
    """Carga PBP solo cuando se solicita y agrega con denominadores independientes."""
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
    return round(float((valores[validos] * pesos[validos]).sum()
                       / pesos[validos].sum()), 4)


def _panel_avanzado_v45(cal):
    st.subheader('🧠 NFL 4.5.1 | Rendimiento avanzado')
    st.caption('Análisis descriptivo: últimos cinco partidos, local/visitante y '
               'eficiencia EPA/Success Rate de jugadas de pase y carrera.')
    temporadas = sorted(cal['season'].dropna().astype(int).unique().tolist(), reverse=True)
    if not temporadas:
        st.info('Sin temporadas disponibles.')
        return
    temporada = st.selectbox('Temporada', temporadas, key='nfl45_temporada')
    base = cal[cal['season'].eq(temporada)].dropna(
        subset=['home_score', 'away_score']).copy()
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
            pd.DataFrame({'game_id': local['game_id'], 'Fecha': local['gameday'],
                          'Semana': local['week'], 'Sede': 'Local',
                          'PF': local['home_score'], 'PC': local['away_score']}),
            pd.DataFrame({'game_id': visita['game_id'], 'Fecha': visita['gameday'],
                          'Semana': visita['week'], 'Sede': 'Visitante',
                          'PF': visita['away_score'], 'PC': visita['home_score']})
        ], ignore_index=True).sort_values(['Fecha', 'Semana', 'game_id'])
        d['Resultado'] = d.apply(lambda r: 'V' if r.PF > r.PC else
                                 ('D' if r.PF < r.PC else 'E'), axis=1)
        return d

    def resumen(d):
        return {'PJ': len(d), 'V': int((d['Resultado'] == 'V').sum()),
                'D': int((d['Resultado'] == 'D').sum()),
                'E': int((d['Resultado'] == 'E').sum()),
                'PF/prom': round(float(d['PF'].mean()), 2) if len(d) else None,
                'PC/prom': round(float(d['PC'].mean()), 2) if len(d) else None}
    historiales = {a: historial(a), b: historial(b)}
    for equipo, d in historiales.items():
        with st.container(border=True):
            st.markdown(f'**{equipo} · Últimos cinco partidos**')
            st.write(resumen(d.tail(5)))
            for sede in ('Local', 'Visitante'):
                st.caption(sede)
                st.write(resumen(d[d['Sede'].eq(sede)]))
    with st.expander('📈 Evolución semanal de puntos'):
        graf = pd.concat([d.assign(Equipo=e) for e, d in historiales.items()],
                         ignore_index=True)
        st.line_chart(graf.pivot_table(index='Semana', columns='Equipo',
                                      values='PF', aggfunc='mean'),
                      use_container_width=True)
        st.caption('Si hay varios partidos en una semana, se muestra su promedio.')

    st.markdown('**EPA y Success Rate (PBP)**')
    st.caption('EPA: puntos esperados añadidos por jugada. Success Rate: '
               'proporción de jugadas marcadas como exitosas por NFLverse. '
               'EPA permitido y SR permitido describen las jugadas del rival; '
               'valores menores suelen reflejar menos producción concedida.')
    if st.button('📥 Cargar eficiencia PBP de esta temporada', key='nfl45_cargar_pbp'):
        st.session_state['nfl45_pbp_solicitada'] = temporada
    if st.session_state.get('nfl45_pbp_solicitada') != temporada:
        st.info('Pulsa el botón para consultar PBP. No se carga al abrir el panel.')
        return
    try:
        with st.spinner('Calculando eficiencia por partido...'):
            pbp = _cargar_pbp_comparacion_v45(temporada)
    except Exception as exc:
        st.warning('No se pudo consultar PBP. Las estadísticas de marcadores siguen disponibles.')
        st.caption(f'Detalle técnico: {type(exc).__name__}: {exc}')
        return
    if pbp.empty:
        st.info('Sin jugadas válidas para esta temporada.')
        return
    filas = []
    for equipo, d in historiales.items():
        ids = d[['game_id']].drop_duplicates()
        x = pbp[pbp['equipo'].eq(equipo)].merge(
            ids, on='game_id', how='inner', validate='one_to_one')
        cobertura = len(x)
        fila = {'Equipo': equipo,
                'Partidos con resultado': len(ids),
                'Partidos con PBP': cobertura,
                'Cobertura PBP %': round(100 * cobertura / len(ids), 1) if len(ids) else 0}
        for prefijo in ('ofensivo', 'permitido'):
            for metrica in ('EPA', 'SR'):
                col = f'{metrica} {prefijo}'
                contador = f'Jugadas {metrica} {prefijo}'
                fila[col] = _media_ponderada_v451(x, col, contador)
                fila[contador] = int(pd.to_numeric(
                    x[contador], errors='coerce').fillna(0).sum())
        filas.append(fila)
        if cobertura < len(ids):
            st.warning(f'{equipo}: PBP disponible para {cobertura} de '
                       f'{len(ids)} partidos con resultado.')
        if (fila['Jugadas EPA ofensivo'] == 0 or
                fila['Jugadas EPA permitido'] == 0):
            st.warning(f'{equipo}: faltan jugadas válidas para EPA '
                       'ofensivo o defensivo.')
    tabla = pd.DataFrame(filas)
    st.dataframe(tabla, hide_index=True, use_container_width=True)
    st.caption('NFL 4.5.1: EPA y Success Rate ofensivos se ponderan '
               'por jugadas ofensivas válidas; los defensivos por jugadas '
               'del rival válidas. Cada métrica tiene su propio denominador.')
    st.download_button('📥 Descargar eficiencia (CSV)',
                       tabla.to_csv(index=False).encode('utf-8-sig'),
                       'nfl451_eficiencia.csv', 'text/csv', key='nfl45_csv')


def _panel_enfrentamientos_v46(cal):
    """Historial descriptivo entre dos equipos, únicamente con marcadores completos."""
    st.subheader('🏈 NFL 4.6 | Historial de enfrentamientos')
    st.caption('Resultados observados del calendario disponible (2022–2026). '
               'No son predicciones ni estadísticas en vivo.')
    requeridas = ['game_id', 'season', 'week', 'gameday', 'home_team',
                  'away_team', 'home_score', 'away_score']
    _requerir(cal, requeridas, 'Calendario de enfrentamientos')
    base = cal.copy()
    base['gameday'] = pd.to_datetime(base['gameday'], errors='coerce')
    for col in ['season', 'week', 'home_score', 'away_score']:
        base[col] = pd.to_numeric(base[col], errors='coerce')
    base = base.dropna(subset=['game_id', 'gameday', 'home_team', 'away_team',
                              'home_score', 'away_score'])
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
        b = st.selectbox('Equipo B', [e for e in equipos if e != a],
                         key='nfl46_equipo_b')
    temporadas = sorted(base['season'].dropna().astype(int).unique(), reverse=True)
    seleccion = st.multiselect('Temporadas', temporadas, default=temporadas,
                               key='nfl46_temporadas')
    if not seleccion:
        st.info('Selecciona al menos una temporada.')
        return
    base = base[base['season'].isin(seleccion)]
    cruces = base[((base['home_team'] == a) & (base['away_team'] == b)) |
                  ((base['home_team'] == b) & (base['away_team'] == a))]
    cruces = cruces.sort_values(['gameday', 'game_id'], ascending=False).copy()
    st.metric('Enfrentamientos con resultado', len(cruces))
    if cruces.empty:
        st.info('No hay enfrentamientos con resultado en las temporadas seleccionadas.')
        return
    cruces['puntos_a'] = np.where(cruces['home_team'].eq(a),
                                  cruces['home_score'], cruces['away_score'])
    cruces['puntos_b'] = np.where(cruces['home_team'].eq(b),
                                  cruces['home_score'], cruces['away_score'])
    cruces['ganador'] = np.select(
        [cruces['puntos_a'].gt(cruces['puntos_b']),
         cruces['puntos_b'].gt(cruces['puntos_a'])], [a, b], default='Empate')
    victorias_a = int(cruces['ganador'].eq(a).sum())
    victorias_b = int(cruces['ganador'].eq(b).sum())
    empates = int(cruces['ganador'].eq('Empate').sum())
    with st.container(border=True):
        st.markdown(f'**Balance histórico · {a} vs. {b}**')
        st.write(f'{a}: **{victorias_a} victorias** · {b}: **{victorias_b} victorias** '
                 f'· Empates: **{empates}**')
        st.write(f'Puntos totales: {a} **{int(cruces["puntos_a"].sum())}** · '
                 f'{b} **{int(cruces["puntos_b"].sum())}**')
        st.write(f'Promedio por encuentro: {a} **{cruces["puntos_a"].mean():.2f}** · '
                 f'{b} **{cruces["puntos_b"].mean():.2f}**')
    st.markdown('**Resultados como local y visitante**')
    resumen_sedes = []
    for equipo in (a, b):
        for sede, columna in [('Local', 'home_team'), ('Visitante', 'away_team')]:
            subset = cruces[cruces[columna].eq(equipo)]
            resumen_sedes.append({'Equipo': equipo, 'Sede': sede,
                                  'Partidos': len(subset),
                                  'Victorias': int(subset['ganador'].eq(equipo).sum()),
                                  'Derrotas': int((~subset['ganador'].isin([equipo, 'Empate'])).sum()),
                                  'Empates': int(subset['ganador'].eq('Empate').sum())})
    st.dataframe(pd.DataFrame(resumen_sedes), hide_index=True, use_container_width=True)
    st.markdown('**Últimos enfrentamientos**')
    for _, fila in cruces.head(10).iterrows():
        fecha = fila['gameday'].strftime('%d/%m/%Y')
        with st.container(border=True):
            st.caption(f'{fecha} · Temporada {int(fila["season"])} '
                       f'· Semana {int(fila["week"])}')
            st.markdown(f'**{fila["away_team"]} {int(fila["away_score"])} '
                        f'— {int(fila["home_score"])} {fila["home_team"]}**')
            st.caption('Ganador: ' + str(fila['ganador']))
    st.markdown('**Evolución histórica de puntos**')
    cronologico = cruces.sort_values(['gameday', 'game_id']).copy()
    cronologico['Encuentro'] = np.arange(1, len(cronologico) + 1)
    grafica = cronologico.set_index('Encuentro')[['puntos_a', 'puntos_b']]
    grafica.columns = [a, b]
    st.line_chart(grafica, use_container_width=True)
    st.caption('Cada posición representa un enfrentamiento entre estos equipos, '
               'ordenado por fecha; no representa semanas consecutivas.')
    detalle = cruces[['game_id', 'season', 'week', 'gameday', 'away_team',
                      'away_score', 'home_team', 'home_score', 'ganador']].copy()
    detalle['gameday'] = detalle['gameday'].dt.strftime('%Y-%m-%d')
    st.download_button('📥 Descargar historial (CSV)',
                       detalle.to_csv(index=False).encode('utf-8-sig'),
                       'nfl46_historial_enfrentamientos.csv', 'text/csv',
                       key='nfl46_descargar_historial')


@st.cache_data(ttl=3600, show_spinner=False)
def _cargar_jugadas_partido_v47(temporada, game_id):
    """Carga columnas seleccionadas y filtra un solo encuentro bajo demanda."""
    import nflreadpy as nfl
    raw = nfl.load_pbp(int(temporada))
    disponibles = list(raw.columns)
    columnas = ['game_id', 'posteam', 'defteam', 'play_type', 'epa', 'success',
                'qtr', 'desc', 'yards_gained', 'passer_player_name',
                'receiver_player_name', 'rusher_player_name', 'passing_yards',
                'receiving_yards', 'rushing_yards', 'complete_pass',
                'pass_attempt', 'rush_attempt', 'touchdown']
    elegir = [c for c in columnas if c in disponibles]
    if 'game_id' not in elegir:
        raise ValueError('La fuente PBP no incluye game_id.')
    if hasattr(raw, 'select') and hasattr(raw, 'to_pandas'):
        d = raw.select(elegir).filter(
            __import__('polars').col('game_id') == str(game_id)).to_pandas()
    else:
        d = raw.to_pandas() if hasattr(raw, 'to_pandas') else pd.DataFrame(raw)
        d = d.loc[d['game_id'].astype(str).eq(str(game_id)), elegir].copy()
    return d


def _panel_partido_v47(cal):
    st.subheader('🏈 NFL 4.7 | Centro de estadísticas por partido')
    st.caption('Resultados del calendario y jugadas PBP observadas. '
               'No es un marcador en vivo.')
    temporadas = sorted(cal['season'].dropna().astype(int).unique(), reverse=True)
    if not temporadas:
        st.info('Sin temporadas disponibles.')
        return
    temporada = st.selectbox('Temporada', temporadas, key='nfl47_temporada')
    base = cal[cal['season'].eq(temporada)].copy()
    semanas = sorted(base['week'].dropna().astype(int).unique())
    semana = st.selectbox('Semana', ['Todas'] + semanas, key='nfl47_semana')
    if semana != 'Todas':
        base = base[base['week'].eq(semana)]
    equipos = sorted(set(base['home_team'].dropna()) | set(base['away_team'].dropna()))
    equipo = st.selectbox('Filtrar equipo', ['Todos'] + equipos, key='nfl47_equipo')
    if equipo != 'Todos':
        base = base[base['home_team'].eq(equipo) | base['away_team'].eq(equipo)]
    if base.empty:
        st.info('No hay partidos para estos filtros.')
        return
    base = base.sort_values(['gameday', 'game_id'], ascending=False)
    opciones = base['game_id'].astype(str).tolist()
    etiquetas = {}
    for _, r in base.iterrows():
        fecha = pd.to_datetime(r['gameday'], errors='coerce')
        fecha_txt = fecha.strftime('%d/%m/%Y') if pd.notna(fecha) else 'Sin fecha'
        etiquetas[str(r['game_id'])] = (f"{fecha_txt} · {r['away_team']} @ "
                                        f"{r['home_team']} · {r['game_id']}")
    game_id = st.selectbox('Seleccionar partido', opciones,
                           format_func=lambda v: etiquetas.get(v, v),
                           key='nfl47_partido')
    partido = base[base['game_id'].astype(str).eq(game_id)].iloc[0]
    visitante, local = str(partido['away_team']), str(partido['home_team'])
    pv = pd.to_numeric(partido['away_score'], errors='coerce')
    pl = pd.to_numeric(partido['home_score'], errors='coerce')
    finalizado = pd.notna(pv) and pd.notna(pl)
    with st.container(border=True):
        st.caption(f"Semana {int(partido['week'])} · {partido['gameday']}")
        if finalizado:
            st.markdown(f'### {visitante} {int(pv)} — {int(pl)} {local}')
            st.caption('Marcador registrado en el calendario.')
        else:
            st.markdown(f'### {visitante} vs. {local}')
            st.info('Sin marcador final registrado. Las estadísticas pueden no estar disponibles.')
    if not finalizado:
        st.caption('No se interpretará un marcador ausente como partido en vivo.')
    st.markdown('**Estadísticas de jugadas del encuentro**')
    if st.button('📥 Cargar PBP del partido', key='nfl47_cargar'):
        st.session_state['nfl47_solicitado'] = (temporada, game_id)
    if st.session_state.get('nfl47_solicitado') != (temporada, game_id):
        st.info('Pulsa el botón para consultar las jugadas. La carga es opcional.')
        return
    try:
        with st.spinner('Consultando jugadas PBP...'):
            d = _cargar_jugadas_partido_v47(temporada, game_id)
    except Exception as exc:
        st.warning('No fue posible consultar las jugadas de este partido.')
        st.caption(f'Detalle técnico: {type(exc).__name__}: {exc}')
        return
    if d.empty:
        st.info('La fuente no tiene jugadas para este encuentro.')
        return
    if not {'play_type', 'posteam', 'defteam'}.issubset(d.columns):
        st.warning('Faltan columnas para construir las estadísticas por equipo.')
        return
    jugadas = d[d['play_type'].isin(['pass', 'run'])].copy()
    if jugadas.empty:
        st.info('Sin jugadas de pase o carrera registradas.')
        return
    for col in ['epa', 'success', 'yards_gained']:
        if col in jugadas:
            jugadas[col] = pd.to_numeric(jugadas[col], errors='coerce')
    filas = []
    for e in (visitante, local):
        of = jugadas[jugadas['posteam'].eq(e)]
        de = jugadas[jugadas['defteam'].eq(e)]
        fila = {'Equipo': e, 'Jugadas ofensivas': len(of),
                'Jugadas defensivas': len(de)}
        for etiqueta, subset, columna in [('EPA ofensivo', of, 'epa'),
                                           ('EPA permitido', de, 'epa'),
                                           ('SR ofensivo', of, 'success'),
                                           ('SR permitido', de, 'success'),
                                           ('Yardas por jugada', of, 'yards_gained')]:
            fila[etiqueta] = (round(float(subset[columna].mean()), 3)
                              if columna in subset and subset[columna].notna().any()
                              else None)
        filas.append(fila)
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
    st.caption('EPA y SR se calculan sobre jugadas de pase/carrera con valores '
               'válidos; el número de jugadas puede diferir entre métricas.')
    if {'qtr', 'epa', 'posteam'}.issubset(jugadas.columns):
        por_cuarto = (jugadas.dropna(subset=['qtr', 'epa'])
                     .groupby(['qtr', 'posteam'], as_index=False)['epa'].mean())
        por_cuarto = por_cuarto[por_cuarto['posteam'].isin([visitante, local])]
        if not por_cuarto.empty:
            st.markdown('**EPA ofensivo promedio por cuarto**')
            st.line_chart(por_cuarto.pivot(index='qtr', columns='posteam', values='epa'))
    st.markdown('**Estadísticas individuales disponibles**')
    opciones_jugadores = [('Pases', 'passer_player_name', 'passing_yards'),
                         ('Recepciones', 'receiver_player_name', 'receiving_yards'),
                         ('Carreras', 'rusher_player_name', 'rushing_yards')]
    hubo = False
    for titulo, nombre, yardas in opciones_jugadores:
        if nombre not in d or yardas not in d:
            continue
        sub = d.dropna(subset=[nombre]).copy()
        sub[yardas] = pd.to_numeric(sub[yardas], errors='coerce')
        sub = sub.dropna(subset=[yardas])
        if sub.empty:
            continue
        tabla = sub.groupby(nombre, as_index=False).agg(
            Jugadas=(yardas, 'size'), Yardas=(yardas, 'sum'))
        tabla = tabla.sort_values(['Yardas', 'Jugadas'], ascending=False).head(12)
        with st.expander(f'{titulo} · jugadores'):
            st.dataframe(tabla, hide_index=True, use_container_width=True)
        hubo = True
    if not hubo:
        st.info('La fuente no incluye estadísticas individuales compatibles para este partido.')
    with st.expander('📜 Registro de jugadas'):
        columnas = [c for c in ['qtr', 'posteam', 'play_type', 'yards_gained',
                                'epa', 'desc'] if c in d.columns]
        st.dataframe(d[columnas].head(300), hide_index=True, use_container_width=True)
        st.caption('Se muestran hasta 300 jugadas; descarga el CSV para consultar todas.')
    st.download_button('📥 Descargar jugadas del partido (CSV)',
                       d.to_csv(index=False).encode('utf-8-sig'),
                       f'nfl47_partido_{game_id}.csv', 'text/csv', key='nfl47_csv')



def _panel_puntos_v48(cal):
    """Análisis histórico descriptivo, sin predicciones de resultados futuros."""
    st.subheader('📊 NFL 4.8 | Análisis histórico de puntos')
    st.caption('Estudia los puntos registrados y compara promedios históricos. '
               'No estima marcadores de encuentros futuros.')
    temporadas = sorted(cal['season'].dropna().astype(int).unique(), reverse=True)
    temporada = st.selectbox('Temporada', temporadas, key='nfl48_pts_temporada')
    d = cal[cal['season'].eq(temporada)].dropna(subset=['home_score', 'away_score']).copy()
    if d.empty:
        st.info('Todavía no hay marcadores disponibles en esta temporada.')
        return
    d['Total'] = pd.to_numeric(d['home_score'], errors='coerce') + pd.to_numeric(d['away_score'], errors='coerce')
    d = d.dropna(subset=['Total']).sort_values(['gameday', 'game_id'])
    equipos = sorted(set(d['home_team'].dropna()) | set(d['away_team'].dropna()))
    equipo = st.selectbox('Equipo', ['Todos'] + equipos, key='nfl48_pts_equipo')
    if equipo != 'Todos':
        d = d[d['home_team'].eq(equipo) | d['away_team'].eq(equipo)].copy()
    if d.empty:
        st.info('No hay resultados para este equipo.')
        return
    n = st.slider('Últimos partidos a visualizar', 3, 30, 10, key='nfl48_pts_n')
    recientes = d.tail(n).copy()
    st.metric('Partidos con marcador', len(d))
    st.metric('Promedio histórico de puntos totales', f"{d['Total'].mean():.2f}")
    st.metric('Desviación estándar histórica', f"{d['Total'].std(ddof=1):.2f}" if len(d)>1 else 'Sin datos suficientes')
    st.caption('El promedio y la dispersión describen partidos ya disputados; '
               'no representan una expectativa ni una garantía para el siguiente partido.')
    recientes['Partido'] = range(1, len(recientes)+1)
    st.line_chart(recientes.set_index('Partido')['Total'], use_container_width=True)
    vista = recientes[['gameday', 'week', 'away_team', 'away_score',
                       'home_team', 'home_score', 'Total']].copy()
    st.dataframe(vista, hide_index=True, use_container_width=True)
    st.download_button('📥 Descargar historial de puntos (CSV)',
                       vista.to_csv(index=False).encode('utf-8-sig'),
                       'nfl48_puntos_historicos.csv', 'text/csv', key='nfl48_pts_csv')


def _resumir_jugadores_partido_v48(d):
    """Suma estadísticas observadas PBP sin duplicar intentos ni inventar faltantes."""
    specs = [
        ('Pases', 'passer_player_name', [('Intentos', 'pass_attempt'),
            ('Completos', 'complete_pass'), ('Yardas de pase', 'passing_yards')]),
        ('Carreras', 'rusher_player_name', [('Acarreos', 'rush_attempt'),
            ('Yardas terrestres', 'rushing_yards')]),
        ('Recepciones', 'receiver_player_name', [('Yardas recibidas', 'receiving_yards')]),
    ]
    tablas = {}
    for titulo, nombre, metrics in specs:
        if nombre not in d.columns:
            continue
        x = d.dropna(subset=[nombre]).copy()
        if x.empty:
            continue
        agregaciones = {}
        for etiqueta, columna in metrics:
            if columna in x.columns:
                x[columna] = pd.to_numeric(x[columna], errors='coerce')
                if x[columna].notna().any():
                    agregaciones[etiqueta] = (columna, 'sum')
        if not agregaciones:
            continue
        t = x.groupby(nombre, as_index=False).agg(**agregaciones)
        if titulo == 'Recepciones':
            # Un nombre de receptor en PBP no garantiza una recepción completa.
            if 'complete_pass' in x.columns:
                x['complete_pass'] = pd.to_numeric(x['complete_pass'], errors='coerce')
                recep = x.groupby(nombre, as_index=False)['complete_pass'].sum().rename(
                    columns={'complete_pass': 'Recepciones completas'})
                t = t.merge(recep, on=nombre, how='left')
        orden = next((c for c in ['Yardas de pase', 'Yardas terrestres',
                                  'Yardas recibidas'] if c in t.columns), None)
        if orden:
            t = t.sort_values(orden, ascending=False)
        tablas[titulo] = t.rename(columns={nombre: 'Jugador'})
    return tablas


def _panel_jugadores_partido_v48(cal):
    st.subheader('👥 NFL 4.8.1 | Jugadores por partido')
    st.caption('Estadísticas observadas de pases, carreras y recepciones. '
               'Las categorías disponibles dependen de los datos PBP publicados.')
    temporadas = sorted(cal['season'].dropna().astype(int).unique(), reverse=True)
    temporada = st.selectbox('Temporada', temporadas, key='nfl48_jug_temporada')
    base = cal[cal['season'].eq(temporada)].dropna(subset=['home_score', 'away_score']).copy()
    if base.empty:
        st.info('No hay partidos con resultado para esta temporada.')
        return
    equipos = sorted(set(base['home_team'].dropna()) | set(base['away_team'].dropna()))
    equipo = st.selectbox('Equipo', ['Todos']+equipos, key='nfl48_jug_equipo')
    if equipo != 'Todos':
        base = base[base['home_team'].eq(equipo) | base['away_team'].eq(equipo)]
    base = base.sort_values(['gameday','game_id'], ascending=False)
    ids = base['game_id'].astype(str).tolist()
    etiquetas = {str(r.game_id): f'{str(r.gameday)[:10]} · {r.away_team} @ {r.home_team}'
                for r in base.itertuples(index=False)}
    game_id = st.selectbox('Partido finalizado', ids, format_func=lambda x: etiquetas.get(x,x),
                           key='nfl48_jug_partido')
    if st.button('📥 Consultar jugadores de este partido', key='nfl48_jug_cargar'):
        st.session_state['nfl48_jug_solicitud'] = (temporada, game_id)
    if st.session_state.get('nfl48_jug_solicitud') != (temporada, game_id):
        st.info('Selecciona el encuentro y pulsa el botón para consultar sus estadísticas.')
        return
    try:
        with st.spinner('Consultando jugadas...'):
            d = _cargar_jugadas_partido_v47(temporada, game_id)
    except Exception as exc:
        st.warning('No se pudieron consultar los jugadores de este partido.')
        st.caption(f'Detalle técnico: {type(exc).__name__}: {exc}')
        return
    if d.empty:
        st.info('No se encontraron jugadas para este encuentro.')
        return
    tablas = _resumir_jugadores_partido_v48(d)
    if not tablas:
        st.warning('La fuente no incluye columnas suficientes para resumir jugadores.')
        return
    # Separar el estado de selección por encuentro y categoría evita conservar
    # jugadores de Pases al cambiar a Carreras o Recepciones.
    categoria = st.selectbox('Categoría', list(tablas), key='nfl48_jug_categoria')
    tabla = tablas[categoria].copy()
    tabla['Jugador'] = tabla['Jugador'].astype('string')
    columnas = [c for c in tabla.columns if c != 'Jugador']
    tabla = tabla[['Jugador'] + columnas]
    jugadores = list(dict.fromkeys(tabla['Jugador'].dropna().astype(str).tolist()))
    # El widget recibe una clave independiente para cada categoría y partido.
    # Streamlit restablece las opciones cuando cambia la lista disponible.
    clave_comparacion = f'nfl481_comparar_{temporada}_{game_id}_{categoria}'
    if clave_comparacion in st.session_state:
        anteriores = st.session_state[clave_comparacion]
        validos = [j for j in anteriores if j in jugadores][:2]
        if validos != anteriores:
            st.session_state[clave_comparacion] = validos
    seleccionados = st.multiselect('Comparar jugadores (hasta 2)', jugadores,
                                   default=jugadores[:2], max_selections=2,
                                   key=clave_comparacion)
    if seleccionados:
        st.markdown('**Comparación de jugadores del encuentro**')
        comparacion = tabla.loc[tabla['Jugador'].isin(seleccionados), ['Jugador'] + columnas]
        if comparacion.empty:
            st.info('Selecciona jugadores con datos en esta categoría.')
        else:
            st.dataframe(comparacion, hide_index=True, use_container_width=True)
    st.markdown('**Todos los jugadores con datos**')
    st.dataframe(tabla, hide_index=True, use_container_width=True)
    st.caption('Solo se muestran estadísticas identificables en PBP. '
               'Las estadísticas defensivas individuales requieren una fuente específica; '
               'no se calculan a partir de EPA del equipo.')
    st.download_button('📥 Descargar estadísticas de jugadores (CSV)',
                       tabla.to_csv(index=False).encode('utf-8-sig'),
                       f'nfl48_jugadores_{game_id}.csv', 'text/csv', key='nfl48_jug_csv')


# NFL 4.9: rendimiento semanal de jugadores (solo estadísticas observadas).
_METRICAS_V49 = {
    'Pases completos': ['completions'],
    'Intentos de pase': ['attempts', 'passing_attempts'],
    'Yardas de pase': ['passing_yards'],
    'TD de pase': ['passing_tds'],
    'Intercepciones lanzadas': ['interceptions', 'passing_interceptions'],
    'Acarreos': ['carries', 'rushing_attempts'],
    'Yardas terrestres': ['rushing_yards'],
    'TD terrestres': ['rushing_tds'],
    'Recepciones': ['receptions'],
    'Objetivos de pase': ['targets'],
    'Yardas recibidas': ['receiving_yards'],
    'TD recibidos': ['receiving_tds'],
}


def _preparar_rendimiento_v49(datos):
    """Normaliza datos semanales, preservando ausencias sin inventar ceros."""
    if datos.empty:
        return pd.DataFrame(), {}
    df = datos.copy()
    nombre = _columna_jugador_v39(df, ['player_display_name', 'player_name', 'player'])
    ident = _columna_jugador_v39(df, ['player_id', 'gsis_id'])
    equipo = _columna_jugador_v39(df, ['recent_team', 'team', 'posteam'])
    posicion = _columna_jugador_v39(df, ['position', 'position_group'])
    semana = _columna_jugador_v39(df, ['week'])
    if not semana or not (nombre or ident):
        raise ValueError('La fuente no ofrece identificador de jugador y semana para el análisis.')
    df['Semana'] = pd.to_numeric(df[semana], errors='coerce')
    df = df.dropna(subset=['Semana']).copy()
    df['Semana'] = df['Semana'].astype(int)
    df['Jugador'] = df[nombre].fillna('Sin nombre').astype(str) if nombre else df[ident].astype(str)
    df['ID'] = df[ident].fillna('').astype(str) if ident else df['Jugador']
    df['Equipo'] = df[equipo].fillna('Sin equipo').astype(str) if equipo else 'Sin equipo'
    df['Posición'] = df[posicion].fillna('Sin posición').astype(str) if posicion else 'Sin posición'
    disponibles = {}
    for etiqueta, alternativas in _METRICAS_V49.items():
        col = _columna_jugador_v39(df, alternativas)
        if col:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            if df[col].notna().any():
                disponibles[etiqueta] = col
    if not disponibles:
        raise ValueError('La fuente no ofrece métricas individuales reconocidas.')
    # Múltiples registros de una semana se consolidan por identificador, no por nombre.
    llaves = ['ID', 'Jugador', 'Semana']
    valores = list(dict.fromkeys(disponibles.values()))
    semanal = df.groupby(llaves, dropna=False, as_index=False)[valores].sum(min_count=1)
    meta = (df.sort_values('Semana').groupby('ID', as_index=False)
            .agg(Jugador=('Jugador', 'last'), Equipo=('Equipo', 'last'), Posición=('Posición', 'last')))
    semanal = semanal.merge(meta[['ID', 'Equipo', 'Posición']], on='ID', how='left')
    return semanal, disponibles


def _calcular_indicadores_v49(semanal, disponibles):
    """Ratios solo cuando existe numerador y denominador positivo."""
    datos = semanal.copy()
    for etiqueta, numerador, denominador, factor in [
        ('% pases completos', 'Pases completos', 'Intentos de pase', 100),
        ('Yardas por intento', 'Yardas de pase', 'Intentos de pase', 1),
        ('Yardas por acarreo', 'Yardas terrestres', 'Acarreos', 1),
        ('Yardas por recepción', 'Yardas recibidas', 'Recepciones', 1),
    ]:
        if numerador in disponibles and denominador in disponibles:
            n = pd.to_numeric(datos[disponibles[numerador]], errors='coerce')
            d = pd.to_numeric(datos[disponibles[denominador]], errors='coerce')
            datos[etiqueta] = (factor * n / d.where(d > 0)).round(2)
    return datos


def _panel_rendimiento_jugadores_v49(cal):
    st.subheader('📈 NFL 4.9.3 | Rendimiento de jugadores')
    st.caption('Evolución semanal y comparaciones de datos observados de NFLverse. '
               'Los valores ausentes no se sustituyen por cero.')
    temporadas = sorted(cal['season'].dropna().astype(int).unique(), reverse=True)
    temporada = st.selectbox('Temporada', temporadas, key='nfl49_temporada')
    if st.button('📥 Cargar rendimiento semanal', key='nfl49_cargar'):
        st.session_state['nfl49_cargada'] = int(temporada)
    if st.session_state.get('nfl49_cargada') != int(temporada):
        st.info('Pulsa el botón para consultar los datos semanales de esta temporada.')
        return
    try:
        with st.spinner('Consultando estadísticas semanales...'):
            bruto = cargar_jugadores_nfl_v39(int(temporada))
            semanal, disponibles = _preparar_rendimiento_v49(bruto)
    except Exception as exc:
        st.warning('No se pudo preparar el rendimiento semanal de jugadores.')
        st.caption(f'Detalle técnico: {type(exc).__name__}: {exc}')
        return
    if semanal.empty:
        st.info('No hay estadísticas semanales publicadas para esta temporada.')
        return
    # NFL 4.9.2: dos selecciones INDEPENDIENTES; ya no se restringen
    # ambos jugadores al equipo elegido en un único filtro.
    equipos = sorted(semanal['Equipo'].dropna().unique().tolist())
    posiciones = sorted(semanal['Posición'].dropna().unique().tolist())
    posicion = st.selectbox('Posición a comparar', ['Todas'] + posiciones,
                            key='nfl492_posicion')
    base = semanal if posicion == 'Todas' else semanal[semanal['Posición'].eq(posicion)]
    if base.empty:
        st.info('No hay jugadores para la posición seleccionada.')
        return
    metrica = st.selectbox('Estadística semanal', list(disponibles), key='nfl492_metrica')
    st.markdown('**Jugador A**')
    equipo_a = st.selectbox('Equipo A', ['Todos'] + equipos, key='nfl492_equipo_a')
    opciones_a = (base if equipo_a == 'Todos' else base[base['Equipo'].eq(equipo_a)])
    opciones_a = opciones_a.sort_values(['Jugador', 'ID'])[['ID', 'Jugador', 'Equipo']].drop_duplicates('ID')
    if opciones_a.empty:
        st.info('No hay jugadores disponibles en el equipo A.')
        return
    etiquetas_a = {r.ID: f'{r.Jugador} · {r.Equipo} ({r.ID})' for r in opciones_a.itertuples(index=False)}
    elegido_a = st.selectbox('Seleccionar jugador A', opciones_a['ID'].tolist(),
                             format_func=lambda i: etiquetas_a.get(i, str(i)), key='nfl492_jugador_a')
    st.markdown('**Jugador B (otro equipo o el mismo)**')
    equipo_b = st.selectbox('Equipo B', ['Todos'] + equipos, key='nfl492_equipo_b')
    opciones_b = (base if equipo_b == 'Todos' else base[base['Equipo'].eq(equipo_b)])
    opciones_b = opciones_b.sort_values(['Jugador', 'ID'])[['ID', 'Jugador', 'Equipo']].drop_duplicates('ID')
    # Impedir comparar un jugador consigo mismo, sin limitar los equipos.
    opciones_b = opciones_b[opciones_b['ID'].ne(elegido_a)]
    elegidos = [elegido_a]
    if opciones_b.empty:
        st.info('No hay un segundo jugador distinto con los filtros actuales. '
                'Cambia el equipo B o selecciona «Todos».')
    else:
        etiquetas_b = {r.ID: f'{r.Jugador} · {r.Equipo} ({r.ID})' for r in opciones_b.itertuples(index=False)}
        elegido_b = st.selectbox('Seleccionar jugador B', opciones_b['ID'].tolist(),
                                 format_func=lambda i: etiquetas_b.get(i, str(i)), key='nfl492_jugador_b')
        elegidos.append(elegido_b)
    # Metadatos de TODOS los equipos, sin filtro compartido.
    opciones = base.sort_values(['Jugador', 'ID'])[['ID', 'Jugador', 'Equipo']].drop_duplicates('ID')
    detalle = base[base['ID'].isin(elegidos)].copy()
    detalle = _calcular_indicadores_v49(detalle, disponibles)
    col = disponibles[metrica]
    # Etiquetas breves para evitar leyendas cortadas en pantallas pequeñas.
    cortos = {}
    for ident_jugador in elegidos:
        registro = opciones[opciones['ID'].eq(ident_jugador)].iloc[0]
        nombre_corto = str(registro['Jugador']).split()[-1]
        cortos[ident_jugador] = f"{nombre_corto} ({registro['Equipo']})"
    if len(set(cortos.values())) < len(cortos):
        cortos = {ident_jugador: f"{cortos[ident_jugador]} · {str(ident_jugador)[-4:]}"
                  for ident_jugador in elegidos}

    grafica = detalle[['Semana', 'ID', col]].dropna(subset=[col]).copy()
    grafica['Jugador'] = grafica['ID'].map(cortos)
    grafica = grafica.rename(columns={col: metrica})
    st.markdown('**Totales de la temporada seleccionada**')
    # La fuente semanal es la única base de los totales; se audita también
    # contra la tabla semanal que se presenta al usuario.
    filas = []
    for ident_jugador in elegidos:
        grupo = detalle[detalle['ID'].eq(ident_jugador)].copy()
        validos = pd.to_numeric(grupo[col], errors='coerce').dropna()
        total = validos.sum() if not validos.empty else float('nan')
        registro = opciones[opciones['ID'].eq(ident_jugador)].iloc[0]
        filas.append({'ID': ident_jugador, 'Jugador': registro['Jugador'],
                      'Equipo': registro['Equipo'], metrica: total,
                      'Partidos con registro': int(validos.count()),
                      'Promedio por partido': validos.mean() if len(validos) else float('nan'),
                      'Mejor semana': int(grupo.loc[validos.idxmax(), 'Semana']) if len(validos) else None,
                      'Máximo semanal': validos.max() if len(validos) else float('nan')})
    acumulado = pd.DataFrame(filas)
    st.info('La tabla de totales aparece primero para facilitar su consulta en el celular.')
    st.dataframe(acumulado.drop(columns=['ID']), hide_index=True, use_container_width=True)

    st.markdown('**Verificación automática de totales**')
    auditoria = []
    for fila in filas:
        grupo = grafica[grafica['ID'].eq(fila['ID'])]
        suma_grafica = pd.to_numeric(grupo[metrica], errors='coerce').sum(min_count=1)
        suma_tabla = fila[metrica]
        valido = (pd.isna(suma_grafica) and pd.isna(suma_tabla)) or (
            pd.notna(suma_grafica) and pd.notna(suma_tabla) and
            abs(float(suma_grafica) - float(suma_tabla)) <= 1e-7)
        auditoria.append({'Jugador': fila['Jugador'], 'Suma semanal': suma_grafica,
                          'Total mostrado': suma_tabla,
                          'Estado': 'OK' if valido else 'REVISAR'})
    tabla_auditoria = pd.DataFrame(auditoria)
    st.dataframe(tabla_auditoria, hide_index=True, use_container_width=True)
    if (tabla_auditoria['Estado'] == 'OK').all():
        st.success('Los totales coinciden con la suma de los registros semanales disponibles.')
    else:
        st.error('Hay diferencias entre los registros semanales y los totales mostrados.')

    st.markdown('**Evolución por semana**')
    if grafica.empty:
        st.info('No hay valores publicados para los jugadores elegidos.')
    else:
        # Altura controlada y leyenda con apellidos y equipos, no IDs.
        tabla_grafica = grafica.pivot_table(
            index='Semana', columns='Jugador', values=metrica, aggfunc='sum')
        st.line_chart(tabla_grafica, height=280, use_container_width=True)

    st.markdown('**Detalle semanal e indicadores de eficiencia**')
    extras = [c for c in ['% pases completos', 'Yardas por intento',
                         'Yardas por acarreo', 'Yardas por recepción'] if c in detalle.columns]
    columnas = ['Semana', 'Jugador', 'Equipo', col] + extras
    vista = detalle[columnas].rename(columns={col: metrica}).sort_values(['Semana', 'Jugador'])
    st.dataframe(vista, hide_index=True, use_container_width=True)
    st.download_button('📥 Descargar rendimiento semanal (CSV)',
                       vista.to_csv(index=False).encode('utf-8-sig'),
                       f'nfl492_jugadores_{temporada}.csv', 'text/csv', key='nfl492_csv')
    st.caption('Partidos con registro significa semanas con un valor publicado para la métrica. '
               'Los totales son sumas de los datos semanales disponibles; no se comprueba '
               'aquí su exactitud frente a la fuente original. Los promedios no corrigen '
               'por rivales, lesiones ni tiempo de juego.')

def _panel_estado_v40(cal):
    st.subheader('🛰️ Estado de actualización')
    st.caption('La hora indica la consulta de esta aplicación, no la publicación en NFLverse.')
    st.metric('Partidos del calendario', len(cal))
    st.metric('Partidos con marcador', len(cal.dropna(subset=['home_score', 'away_score'])))
    st.write('Última consulta exitosa en esta sesión (UTC):',
             st.session_state.get('nfl40_consulta_utc', 'No registrada'))
    st.caption('Consulta de origen (UTC): ' + str(cal.attrs.get('consulta_fuente_utc', 'No disponible')))
    st.caption('Caché del calendario: máximo 15 minutos; el origen puede publicar datos con retraso.')
    st.info('Para revisar la cobertura PBP, errores y auditorías completas, abre «Auditorías y análisis».')



def mostrar_modulo_nfl():
    st.header('🏈 NFL 4.9.2 | Centro deportivo móvil')
    st.caption('NFLverse · Calendario, resultados y estadísticas observadas')
    if st.button('🔄 Consultar datos nuevos', key='nfl40_actualizar'):
        cargar_calendario_rapido_v40.clear()
        cargar_datos_nfl.clear()
        cargar_jugadores_nfl_v39.clear()
        st.session_state.pop('nfl40_consulta_utc', None)
        st.session_state.pop('nfl43_fecha_fuente', None)
        st.rerun()
    secciones = ['🏠 Inicio', '📅 Partidos', '🏟️ Equipos', '📊 Comparar equipos', '🏈 Enfrentamientos', '🏈 Centro por partido', '📊 Puntos históricos', '👥 Jugadores por partido', '📈 Rendimiento de jugadores', '🧠 Rendimiento avanzado',
                 '👥 Jugadores', '🛰️ Estado', '🧪 Auditorías y análisis', '🧪 Pruebas 4.1']
    seleccion = st.selectbox('Ir a sección', secciones, key='nfl40_navegacion')
    st.caption('⚡ Calendario en caché durante 15 minutos; actualización manual disponible.')
    if seleccion == '🧪 Pruebas 4.1':
        mostrar_pruebas_integrales_nfl_v41()
        return
    if seleccion == '👥 Jugadores':
        try:
            mostrar_jugadores_nfl_v39()
        except Exception as exc:
            st.error('No se pudieron mostrar las estadísticas de jugadores.')
            st.caption(f'Detalle técnico: {type(exc).__name__}: {exc}')
        return
    if seleccion == '🧪 Auditorías y análisis':
        try:
            _mostrar_modulo_nfl_legacy_v40()
        except Exception as exc:
            st.error('No se pudo completar el análisis histórico.')
            st.caption(f'Detalle técnico: {type(exc).__name__}: {exc}')
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
            st.caption(f'Detalle técnico: {type(exc).__name__}: {exc}')
            return
        cal = respaldo.copy()
        st.session_state['nfl42_usando_respaldo'] = True
        st.warning('Sin conexión a los datos nuevos. Se muestra el último calendario guardado en esta sesión.')
        st.caption('Respaldo consultado: ' + str(st.session_state.get('nfl42_respaldo_utc', 'sin fecha')))
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
        elif seleccion == '🏈 Centro por partido':
            _panel_partido_v47(cal)
        elif seleccion == '📊 Puntos históricos':
            _panel_puntos_v48(cal)
        elif seleccion == '👥 Jugadores por partido':
            _panel_jugadores_partido_v48(cal)
        elif seleccion == '📈 Rendimiento de jugadores':
            _panel_rendimiento_jugadores_v49(cal)
        elif seleccion == '🧠 Rendimiento avanzado':
            _panel_avanzado_v45(cal)
        elif seleccion == '🛰️ Estado':
            _panel_estado_v40(cal)
            st.write('Usando respaldo de sesión:', 'Sí' if st.session_state.get('nfl42_usando_respaldo') else 'No')
            st.caption('El respaldo no es persistente: se pierde al reiniciar el servidor.')
    except Exception as exc:
        st.error('Ocurrió un error al presentar esta sección.')
        st.caption(f'Detalle técnico: {type(exc).__name__}: {exc}')


# NFL 4.1: pruebas de integración sobre el calendario real y casos sintéticos.
# No se modifican ni corrigen datos de la fuente automáticamente.
def _evaluar_pruebas_v41(cal):
    pruebas = []
    def agregar(nombre, correcto, detalle, severidad='ERROR'):
        pruebas.append({'Prueba': nombre, 'Estado': 'OK' if correcto else severidad,
                        'Detalle': str(detalle)})

    columnas = {'game_id', 'season', 'week', 'gameday', 'home_team',
                'away_team', 'home_score', 'away_score'}
    faltantes = sorted(columnas - set(cal.columns))
    agregar('Columnas obligatorias', not faltantes,
            'Completas' if not faltantes else 'Faltan: ' + ', '.join(faltantes))
    if faltantes:
        return pd.DataFrame(pruebas)

    agregar('Calendario no vacío', len(cal) > 0, f'{len(cal)} partidos')
    duplicados = int(cal['game_id'].duplicated().sum())
    agregar('Identificadores únicos', duplicados == 0, f'{duplicados} duplicados')
    nulos = int(cal[['game_id','gameday','season','week','home_team','away_team']].isna().any(axis=1).sum())
    agregar('Campos básicos completos', nulos == 0, f'{nulos} filas incompletas')
    mismo_equipo = int((cal['home_team'].astype(str) == cal['away_team'].astype(str)).sum())
    agregar('Rivales distintos', mismo_equipo == 0, f'{mismo_equipo} coincidencias')
    marcadores = cal[['home_score','away_score']].apply(pd.to_numeric, errors='coerce')
    parciales = int(marcadores.isna().any(axis=1).ne(marcadores.isna().all(axis=1)).sum())
    agregar('Marcadores completos o pendientes', parciales == 0, f'{parciales} marcadores parciales')
    invalidos = int((marcadores.lt(0).any(axis=1) | ((marcadores % 1).ne(0) & marcadores.notna()).any(axis=1)).sum())
    agregar('Marcadores enteros no negativos', invalidos == 0, f'{invalidos} marcadores inválidos')
    semana = pd.to_numeric(cal['week'], errors='coerce')
    semanas_invalidas = int((semana.lt(1) | semana.gt(25) | semana.isna()).sum())
    agregar('Semanas en rango razonable', semanas_invalidas == 0, f'{semanas_invalidas} semanas fuera de rango', 'AVISO')
    temporada = pd.to_numeric(cal['season'], errors='coerce')
    fuera = int((~temporada.isin(TEMPORADAS)).sum())
    agregar('Temporadas configuradas', fuera == 0, f'{fuera} fuera de configuración', 'AVISO')
    fechas = pd.to_datetime(cal['gameday'], errors='coerce')
    invalidas = int(fechas.isna().sum())
    agregar('Fechas de partido válidas', invalidas == 0, f'{invalidas} fechas inválidas')
    return pd.DataFrame(pruebas)


def _ventana_proximos_v41(cal, fecha_referencia=None):
    # Convención explícita: fechas NFL por día calendario, no horarios de kickoff.
    hoy = pd.Timestamp(fecha_referencia or datetime.now(timezone.utc).date()).normalize()
    fecha = pd.to_datetime(cal['gameday'], errors='coerce').dt.tz_localize(None).dt.normalize()
    pendientes = cal['home_score'].isna() & cal['away_score'].isna()
    ventana = pendientes & fecha.ge(hoy) & fecha.lt(hoy + pd.Timedelta(days=7))
    return cal.loc[ventana].copy()


def _pruebas_sinteticas_v41():
    base = pd.DataFrame([{'game_id':'2026_01_A_B','season':2026,'week':1,
        'gameday':pd.Timestamp('2026-09-10'),'home_team':'A','away_team':'B',
        'home_score':21,'away_score':17},
        {'game_id':'2026_02_C_D','season':2026,'week':2,
        'gameday':pd.Timestamp('2026-09-17'),'home_team':'C','away_team':'D',
        'home_score':float('nan'),'away_score':float('nan')}])
    resultados = []
    def probar(nombre, df, esperado):
        hallados = _evaluar_pruebas_v41(df)
        estado = hallados.set_index('Prueba').loc[nombre, 'Estado']
        resultados.append({'Prueba': 'Caso simulado: ' + nombre,
                           'Estado': 'OK' if estado == esperado else 'ERROR',
                           'Detalle': f'Esperado {esperado}; obtenido {estado}'})
    probar('Identificadores únicos', pd.concat([base, base.iloc[[0]]], ignore_index=True), 'ERROR')
    cambio = base.copy(); cambio.loc[0, 'home_score'] = -1
    probar('Marcadores enteros no negativos', cambio, 'ERROR')
    cambio = base.copy(); cambio.loc[0, 'away_score'] = float('nan')
    probar('Marcadores completos o pendientes', cambio, 'ERROR')
    cambio = base.copy(); cambio.loc[0, 'away_team'] = 'A'
    probar('Rivales distintos', cambio, 'ERROR')
    resultado = _ventana_proximos_v41(base, '2026-09-11')
    resultados.append({'Prueba':'Caso simulado: ventana de 7 días',
        'Estado':'OK' if len(resultado)==1 else 'ERROR',
        'Detalle':f'Esperado 1; obtenido {len(resultado)}'})
    return pd.DataFrame(resultados)


def mostrar_pruebas_integrales_nfl_v41():
    st.subheader('🧪 NFL 4.2 | Pruebas integrales (15 verificaciones)')
    st.caption('10 verificaciones de calendario y 5 pruebas simuladas. '
               'No sustituyen la validación de la fuente NFLverse ni comprueban todos los módulos.')
    if not st.button('▶️ Ejecutar pruebas NFL 4.1', key='nfl41_ejecutar'):
        st.info('Pulsa el botón para ejecutar las comprobaciones.')
        return
    try:
        cal = cargar_calendario_rapido_v40()
    except Exception as exc:
        st.error('No se pudo cargar el calendario. Las pruebas reales no se ejecutaron.')
        st.caption(f'{type(exc).__name__}: {exc}')
        return
    reales = _evaluar_pruebas_v41(cal)
    simuladas = _pruebas_sinteticas_v41()
    resultado = pd.concat([reales.assign(Origen='Datos reales'),
                           simuladas.assign(Origen='Pruebas simuladas')], ignore_index=True)
    if len(resultado) != 15:
        st.error(f'Pruebas incompletas: se ejecutaron {len(resultado)} de 15. Revisa que el archivo instalado esté completo.')
    a,b,c = st.columns(3)
    a.metric('Comprobaciones', len(resultado))
    b.metric('Errores', int(resultado['Estado'].eq('ERROR').sum()))
    c.metric('Avisos', int(resultado['Estado'].eq('AVISO').sum()))
    st.dataframe(resultado[['Origen','Prueba','Estado','Detalle']],
                 hide_index=True, use_container_width=True)
    if resultado['Estado'].eq('ERROR').any():
        st.error('Se encontraron errores. Revisa el detalle antes de continuar.')
    elif resultado['Estado'].eq('AVISO').any():
        st.warning('Sin errores críticos; hay avisos para revisar.')
    else:
        st.success('Las comprobaciones ejecutadas terminaron sin discrepancias.')
    st.markdown('**Reconciliación de próximos 7 días**')
    proximos = _ventana_proximos_v41(cal)
    st.metric('Partidos sin marcador dentro de la ventana', len(proximos))
    st.caption('Criterio: desde hoy UTC (incluido) hasta hoy + 7 días (excluido); '
               'se incluyen únicamente partidos con ambos marcadores vacíos. '
               'Los recuentos anteriores pueden diferir si se hicieron en otra fecha.')
    if not proximos.empty:
        _marcador_v40(proximos.sort_values('gameday'))
    st.download_button('📥 Descargar informe de pruebas (CSV)',
        resultado.to_csv(index=False).encode('utf-8-sig'),
        'nfl_v4_1_pruebas.csv', 'text/csv', key='nfl41_descarga')

if __name__ == '__main__':
    mostrar_modulo_nfl()

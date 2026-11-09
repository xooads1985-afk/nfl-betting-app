"""Funciones del laboratorio 3.12.18 aisladas para ejecutarse fuera de Streamlit."""
import pandas as pd
import numpy as np

def _equipo_resultados(partidos, equipo):
    """Devuelve únicamente juegos finalizados con marcadores verificables."""
    if partidos.empty:
        return partidos.copy()
    d = partidos.loc[(partidos['local'].eq(equipo) | partidos['visitante'].eq(equipo)) & partidos['finalizado'].eq(True)].copy()
    d = d.dropna(subset=['puntos_local', 'puntos_visitante'])
    if d.empty:
        return d
    es_local = d['local'].eq(equipo)
    d['PF'] = d['puntos_local'].where(es_local, d['puntos_visitante'])
    d['PC'] = d['puntos_visitante'].where(es_local, d['puntos_local'])
    d['Rival'] = d['visitante'].where(es_local, d['local'])
    d['Sede'] = es_local.map({True: 'Local', False: 'Visitante'})
    d['Resultado'] = ['V' if a > b else 'D' if a < b else 'E' for a, b in zip(d['PF'], d['PC'])]
    return d.sort_values('fecha_utc')

def _historial_equipo(partidos, equipo, antes=None):
    """Historial cronológico; conserva el esquema aun cuando no haya filas."""
    d = _equipo_resultados(partidos, equipo)
    if d.empty:
        return d
    if 'fecha_utc' not in d.columns:
        return d.iloc[0:0].copy()
    if antes is not None:
        fechas = pd.to_datetime(d['fecha_utc'], utc=True, errors='coerce')
        d = d.loc[fechas.lt(antes)].copy()
    return d.sort_values('fecha_utc')

def _nba_lab_dias_descanso(historial, fecha):
    if historial.empty or pd.isna(fecha):
        return None
    ult = pd.to_datetime(historial['fecha_utc'], utc=True, errors='coerce').dropna()
    if ult.empty:
        return None
    anterior = ult.max().tz_convert('America/Mazatlan').date()
    actual = fecha.tz_convert('America/Mazatlan').date()
    return max(0, (actual - anterior).days - 1)

def _nba_lab_calcular(partidos, partido, ajustes, posesiones=None):
    """Predicción experimental de ambos equipos; no modifica proyecciones originales."""
    fecha = pd.to_datetime(partido['fecha_utc'], utc=True, errors='coerce')
    local, visita = (str(partido['local']), str(partido['visitante']))
    h = {e: _historial_equipo(partidos, e, fecha) for e in (local, visita)}
    resultado = {}
    for equipo, rival, sede in ((local, visita, 'Local'), (visita, local, 'Visitante')):
        propio, contrario = (h[equipo], h[rival])
        if propio.empty or contrario.empty:
            return None
        pf = pd.to_numeric(propio['PF'], errors='coerce').dropna().tail(10)
        pc = pd.to_numeric(contrario['PC'], errors='coerce').dropna().tail(10)
        if min(len(pf), len(pc)) < 3:
            return None
        base = (pf.mean() + pc.mean()) / 2
        pred = float(base)
        componentes = {'Base': round(pred, 2)}
        if ajustes.get('forma') and len(pf) >= 5 and (len(pc) >= 5):
            reciente = (pf.tail(5).mean() + pc.tail(5).mean()) / 2
            pred = 0.7 * pred + 0.3 * reciente
            componentes['Forma 5'] = round(pred - base, 2)
        if ajustes.get('sede'):
            propia_sede = propio.loc[propio['Sede'].eq(sede), 'PF'].tail(10)
            rival_sede = contrario.loc[contrario['Sede'].eq('Visitante' if sede == 'Local' else 'Local'), 'PC'].tail(10)
            if len(propia_sede) >= 5 and len(rival_sede) >= 5:
                especifica = (propia_sede.mean() + rival_sede.mean()) / 2
                antes = pred
                pred = 0.8 * pred + 0.2 * especifica
                componentes['Sede'] = round(pred - antes, 2)
        if ajustes.get('descanso'):
            dias = _nba_lab_dias_descanso(propio, fecha)
            rival_dias = _nba_lab_dias_descanso(contrario, fecha)
            if dias is not None and rival_dias is not None:
                diferencia = max(-2, min(2, dias - rival_dias))
                antes = pred
                pred += 0.5 * diferencia
                componentes['Descanso (experimental)'] = round(pred - antes, 2)
        resultado[equipo] = {'base': float(base), 'pred': pred, 'componentes': componentes, 'descanso': _nba_lab_dias_descanso(propio, fecha)}
    if ajustes.get('pace') and posesiones:
        if all((e in posesiones and len(posesiones[e]) >= 3 for e in (local, visita))):
            import statistics
            pace = statistics.mean([statistics.mean([x['posesiones'] for x in posesiones[e]]) for e in (local, visita)])
            if 60 <= pace <= 140:
                for equipo, rival in ((local, visita), (visita, local)):
                    own = posesiones[equipo]
                    opp = posesiones[rival]
                    off = statistics.mean([x['pf'] / x['posesiones'] * 100 for x in own])
                    defense = statistics.mean([x['pc'] / x['posesiones'] * 100 for x in opp])
                    estimado = pace * (off + defense) / 200
                    if 60 <= estimado <= 180:
                        antes = resultado[equipo]['pred']
                        resultado[equipo]['pred'] = (1 - float(ajustes.get('peso_pace', 0.5))) * antes + float(ajustes.get('peso_pace', 0.5)) * estimado
                        resultado[equipo]['componentes']['Pace + ORtg/DRtg'] = round(resultado[equipo]['pred'] - antes, 2)
                        resultado[equipo]['pace'] = round(pace, 2)
                        resultado[equipo]['ortg'] = round(off, 2)
                        resultado[equipo]['drtg_rival'] = round(defense, 2)
    return resultado

def _nba_lab_modelo_c(partidos, partido, ajustes, posesiones=None):
    """Modelo C: nunca utiliza marcadores de la fecha evaluada o posteriores."""
    import math
    fecha = pd.to_datetime(partido.get('fecha_utc'), utc=True, errors='coerce')
    if pd.isna(fecha):
        return None
    anteriores = partidos.copy()
    anteriores['_fecha_lab'] = pd.to_datetime(anteriores['fecha_utc'], utc=True, errors='coerce')
    anteriores = anteriores.loc[anteriores['_fecha_lab'].lt(fecha) & anteriores['finalizado'].eq(True)].copy()
    anteriores = anteriores.dropna(subset=['puntos_local', 'puntos_visitante'])
    if anteriores.empty:
        return None
    base = _nba_lab_calcular(anteriores, partido, ajustes, posesiones)
    if base is None:
        return None
    totales = pd.concat([pd.to_numeric(anteriores['puntos_local'], errors='coerce'), pd.to_numeric(anteriores['puntos_visitante'], errors='coerce')]).dropna()
    media_liga = float(totales.mean()) if len(totales) >= 20 else None
    for equipo, rival in ((str(partido['local']), str(partido['visitante'])), (str(partido['visitante']), str(partido['local']))):
        dato = base[equipo]
        pred = float(dato['pred'])
        hist = _historial_equipo(anteriores, equipo, fecha)
        rival_hist = _historial_equipo(anteriores, rival, fecha)
        if ajustes.get('fuerza') and media_liga is not None and (len(hist) >= 5):
            ajustes_rival = []
            for fila in hist.tail(10).itertuples(index=False):
                oponente = str(fila.Rival)
                o_hist = _historial_equipo(anteriores, oponente, pd.to_datetime(fila.fecha_utc, utc=True))
                if len(o_hist) >= 3:
                    ajustes_rival.append(float(o_hist['PC'].tail(10).mean()) - media_liga)
            if len(ajustes_rival) >= 3:
                delta = -0.15 * float(sum(ajustes_rival) / len(ajustes_rival))
                pred += delta
                dato['componentes']['Fuerza calendario (exploratorio)'] = round(delta, 2)
        if ajustes.get('regresion') and media_liga is not None:
            n = min(len(hist), len(rival_hist))
            peso = max(0.05, min(0.25, 5.0 / (n + 5.0)))
            anterior = pred
            pred = (1 - peso) * pred + peso * media_liga
            dato['componentes']['Regresión media liga'] = round(pred - anterior, 2)
        dato['pred'] = round(max(60.0, min(180.0, pred)), 3)
        residuos = pd.to_numeric(hist['PF'], errors='coerce').dropna().tail(15)
        dato['desviacion_historica'] = round(float(residuos.std()), 2) if len(residuos) >= 5 else None
        dato['muestra'] = len(hist)
    return base

def _nba_lab_ml_caracteristicas(partidos, juego):
    """Vector prepartido por equipo, sin variables derivadas del resultado objetivo."""
    import numpy as np
    fecha = pd.to_datetime(juego['fecha_utc'], utc=True, errors='coerce')
    if pd.isna(fecha):
        return []
    anteriores = partidos.loc[partidos['_fecha_ml'].lt(fecha)]
    anteriores = anteriores.loc[anteriores['finalizado'].eq(True)].dropna(subset=['puntos_local', 'puntos_visitante'])
    if len(anteriores) < 10:
        return []
    liga = float(pd.concat([anteriores['puntos_local'], anteriores['puntos_visitante']]).mean())
    filas = []
    for equipo, rival, local in ((juego['local'], juego['visitante'], 1), (juego['visitante'], juego['local'], 0)):
        propio = _historial_equipo(anteriores, equipo, fecha)
        contrario = _historial_equipo(anteriores, rival, fecha)
        if min(len(propio), len(contrario)) < 3:
            return []
        pf = pd.to_numeric(propio['PF'], errors='coerce').dropna().tail(10)
        pc = pd.to_numeric(propio['PC'], errors='coerce').dropna().tail(10)
        rp = pd.to_numeric(contrario['PF'], errors='coerce').dropna().tail(10)
        rc = pd.to_numeric(contrario['PC'], errors='coerce').dropna().tail(10)
        if min(len(pf), len(pc), len(rp), len(rc)) < 3:
            return []
        base = (float(pf.mean()) + float(rc.mean())) / 2
        descanso = _nba_lab_dias_descanso(propio, fecha)
        descanso_rival = _nba_lab_dias_descanso(contrario, fecha)
        vector = [base, float(pf.mean()), float(rc.mean()), float(pc.mean()), float(rp.mean()), float(pf.tail(5).mean()), float(rc.tail(5).mean()), float(local), float(max(-3, min(3, (descanso or 0) - (descanso_rival or 0)))), float(min(len(propio), 20)), liga]
        filas.append({'equipo': str(equipo), 'x': np.asarray(vector, dtype=float), 'base': base, 'n': len(propio), 'liga': liga, 'real': float(juego['puntos_local'] if local else juego['puntos_visitante'])})
    return filas

def _nba_lab_ml_entrenar(train_x, train_y):
    """Entrena una vez por fecha, no una vez por equipo."""
    import numpy as np
    x = np.asarray(train_x, dtype=float)
    y = np.asarray(train_y, dtype=float)
    if len(y) < 24:
        return {}
    mu = x.mean(axis=0)
    sigma = x.std(axis=0)
    sigma[sigma < 1e-08] = 1.0
    a = np.column_stack([np.ones(len(y)), (x - mu) / sigma])
    target = y - 110.0
    modelos = {'mu': mu, 'sigma': sigma}
    for nombre, alpha in (('Ridge', 20.0), ('Regresión lineal', 0.001)):
        reg = np.diag([0.0] + [alpha] * x.shape[1])
        coef = np.linalg.solve(a.T @ a + reg, a.T @ target)
        modelos[nombre] = coef
    media = max(float(y.mean()), 1.0)
    var = float(y.var(ddof=1))
    modelos['dispersion_nb'] = max(1.0, media ** 2 / max(var - media, 1.0))
    try:
        from sklearn.ensemble import HistGradientBoostingRegressor
        if len(y) >= 80:
            gb = HistGradientBoostingRegressor(max_iter=35, max_leaf_nodes=5, min_samples_leaf=15, learning_rate=0.045, l2_regularization=20, random_state=17, early_stopping=False)
            gb.fit(x, y)
            modelos['Gradient Boosting'] = gb
    except ImportError:
        pass
    return modelos

def _nba_lab_ml_predecir(modelos, x, base, n, liga):
    """Todos los puntos se estiman con datos anteriores a la fecha objetivo."""
    import numpy as np
    x = np.asarray(x, dtype=float)
    res = {'Bayesiano': float((n * base + 8 * liga) / (n + 8)), 'Posesiones + eficiencia': float('nan')}
    if not modelos:
        return res
    b = np.r_[1.0, (x - modelos['mu']) / modelos['sigma']]
    for nombre in ('Ridge', 'Regresión lineal'):
        res[nombre] = float(np.clip(110 + b @ modelos[nombre], 60, 180))
    media = res['Regresión lineal']
    k = modelos['dispersion_nb']
    var = media + media * media / k
    res['Binomial negativa'] = media
    res['NB desviación'] = float(np.sqrt(var))
    if 'Gradient Boosting' in modelos:
        res['Gradient Boosting'] = float(np.clip(modelos['Gradient Boosting'].predict(x.reshape(1, -1))[0], 60, 180))
    miembros = [res[z] for z in ('Ridge', 'Bayesiano', 'Gradient Boosting') if z in res and np.isfinite(res[z])]
    if len(miembros) >= 2:
        res['Ensemble'] = float(np.mean(miembros))
    return res

def _nba_lab_ml_validacion(partidos, limite=None, minimo_train=24, progreso=None, fechas_objetivo=None):
    """Validación cronológica con caché de features y un entrenamiento por fecha.

    limite=None evalúa todas las fechas con historial suficiente.
    """
    import numpy as np
    datos = partidos.copy()
    datos['_fecha_ml'] = pd.to_datetime(datos['fecha_utc'], utc=True, errors='coerce')
    datos = datos.loc[datos['finalizado'].eq(True)].dropna(subset=['_fecha_ml', 'puntos_local', 'puntos_visitante']).sort_values('_fecha_ml')
    if datos.empty:
        return (pd.DataFrame(), 'Sin historial válido.')
    features = {}
    for juego in datos.to_dict('records'):
        f = _nba_lab_ml_caracteristicas(datos, juego)
        if len(f) == 2:
            features[str(juego.get('id', ''))] = f
    historico = []
    resultados = []
    fechas = datos['_fecha_ml'].drop_duplicates().tolist()
    fechas_evaluar = (set(pd.to_datetime(fechas_objetivo, utc=True)) if fechas_objetivo is not None
                     else set(fechas if limite is None else fechas[-limite:]))
    activos = {'forma': True, 'sede': True, 'descanso': True, 'pace': False, 'fuerza': True, 'regresion': True}
    grupos = list(datos.groupby('_fecha_ml', sort=True))
    for indice, (fecha, grupo) in enumerate(grupos):
        juegos = [(j, features.get(str(j.get('id', '')))) for j in grupo.to_dict('records')]
        juegos = [(j, f) for j, f in juegos if f is not None]
        if fecha in fechas_evaluar and len(historico) >= minimo_train and juegos:
            entrenado = _nba_lab_ml_entrenar([h['x'] for h in historico], [h['real'] for h in historico])
            anteriores = datos.loc[datos['_fecha_ml'].lt(fecha)]
            for juego, caracteristicas in juegos:
                c = _nba_lab_modelo_c(anteriores, juego, activos)
                if c is None:
                    continue
                for item in caracteristicas:
                    modelos = _nba_lab_ml_predecir(entrenado, item['x'], item['base'], item['n'], item['liga'])
                    fila = {'fecha': str(fecha), 'partido': str(juego.get('id', '')), 'equipo': item['equipo'], 'real': item['real'], 'Base': item['base'], 'Modelo C': float(c[item['equipo']]['pred']), 'Entrenamiento': len(historico)}
                    fila.update(modelos)
                    resultados.append(fila)
        for juego, caracteristicas in juegos:
            historico.extend(caracteristicas)
        if progreso is not None:
            progreso((indice + 1) / len(grupos), f'Procesando fecha {indice + 1} de {len(grupos)}')
    df = pd.DataFrame(resultados)
    if df.empty:
        return (df, 'Historial insuficiente para entrenar y evaluar los algoritmos.')
    return (df, 'Posesiones + eficiencia permanece pendiente de boxscores completos. Binomial negativa comparte media con regresión lineal; su aportación se evalúa mediante dispersión e intervalos, no MAE independiente.')

def _nba_lab_ml_resumen(df):
    import numpy as np
    if df.empty:
        return pd.DataFrame()
    columnas = ['Base', 'Modelo C', 'Ridge', 'Bayesiano', 'Gradient Boosting', 'Posesiones + eficiencia', 'Ensemble', 'Regresión lineal', 'Binomial negativa']
    filas = []
    for col in columnas:
        if col not in df:
            filas.append({'Modelo': col, 'Predicciones': 0, 'MAE': np.nan, 'RMSE': np.nan, 'Sesgo': np.nan})
            continue
        validos = df[['real', col]].dropna()
        if validos.empty:
            filas.append({'Modelo': col, 'Predicciones': 0, 'MAE': np.nan, 'RMSE': np.nan, 'Sesgo': np.nan})
            continue
        err = validos[col] - validos['real']
        filas.append({'Modelo': col, 'Predicciones': len(err), 'MAE': round(float(err.abs().mean()), 3), 'RMSE': round(float(np.sqrt((err ** 2).mean())), 3), 'Sesgo': round(float(err.mean()), 3)})
    return pd.DataFrame(filas)


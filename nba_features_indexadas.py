"""Índice de características NBA; mantiene las fórmulas originales de ML."""
import pandas as pd
import numpy as np
from nba_lab_motor_offline import _nba_lab_dias_descanso


def preparar_indice(datos):
    """Crea una función para extraer vectores prepartido sin reconstruir equipos."""
    equipos = pd.unique(pd.concat([datos['local'], datos['visitante']], ignore_index=True))
    grupos = {}
    for equipo in equipos:
        t = datos.loc[datos['local'].eq(equipo) | datos['visitante'].eq(equipo)].copy()
        sede = t['local'].eq(equipo)
        t['PF'] = t['puntos_local'].where(sede, t['puntos_visitante'])
        t['PC'] = t['puntos_visitante'].where(sede, t['puntos_local'])
        t['Rival'] = t['visitante'].where(sede, t['local'])
        t['Sede'] = sede.map({True: 'Local', False: 'Visitante'})
        t['Resultado'] = ['V' if a > b else 'D' if a < b else 'E' for a,b in zip(t['PF'], t['PC'])]
        t = t.sort_values('fecha_utc')
        grupos[equipo] = (t, pd.to_datetime(t['fecha_utc'], utc=True, errors='coerce'))
    fechas = datos['_fecha_ml']

    def calcular(juego):
        fecha = pd.to_datetime(juego['fecha_utc'], utc=True, errors='coerce')
        if pd.isna(fecha):
            return []
        anteriores = datos.loc[fechas.lt(fecha)]
        if len(anteriores) < 10:
            return []
        liga = float(pd.concat([anteriores['puntos_local'], anteriores['puntos_visitante']]).mean())
        filas = []
        for equipo, rival, local in ((juego['local'], juego['visitante'], 1), (juego['visitante'], juego['local'], 0)):
            if equipo not in grupos or rival not in grupos:
                return []
            propio = grupos[equipo][0].loc[grupos[equipo][1].lt(fecha)]
            contrario = grupos[rival][0].loc[grupos[rival][1].lt(fecha)]
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

    return calcular

from calendar import monthrange
from datetime import date
import pandas as pd

def cargar_por_bloques(cargador, desde, hasta):
    desde, hasta = date.fromisoformat(str(desde)), date.fromisoformat(str(hasta))
    if hasta < desde:
        raise ValueError("Intervalo invalido")
    fragmentos, incidencias = [], []
    cursor = desde
    while cursor <= hasta:
        fin = min(date(cursor.year, cursor.month, monthrange(cursor.year,cursor.month)[1]), hasta)
        try:
            tabla, errores = cargador(cursor, fin)
            if tabla is not None and not tabla.empty:
                fragmentos.append(tabla)
            incidencias.extend(f"{cursor} a {fin}: {e}" for e in (errores or []))
        except Exception as exc:
            incidencias.append(f"{cursor} a {fin}: {type(exc).__name__}: {exc}")
        cursor = date.fromordinal(fin.toordinal()+1)
    if not fragmentos:
        return pd.DataFrame(), incidencias
    salida = pd.concat(fragmentos, ignore_index=True)
    if "id" in salida.columns:
        salida["id"] = salida["id"].astype(str)
        salida = salida.drop_duplicates("id", keep="last")
    if "fecha_utc" in salida.columns:
        salida = salida.sort_values("fecha_utc").reset_index(drop=True)
    return salida, incidencias

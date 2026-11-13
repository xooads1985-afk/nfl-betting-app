"""Actualiza en memoria los boxscores Pace faltantes usando ESPN; no escribe archivos ni Supabase."""
import pandas as pd

def completar_pace(historico_nba, historial_pace, partido, cargar_detalle, *, corte_utc, max_consultas=50):
    from nba_pace_historial import construir_historial
    if not callable(cargar_detalle):
        raise TypeError("Falta cargador ESPN de detalles")
    if not 1 <= max_consultas <= 50:
        raise ValueError("Límite de consultas inválido")
    inicio = pd.to_datetime(partido["fecha_utc"], utc=True, errors="coerce")
    corte = pd.to_datetime(corte_utc, utc=True, errors="coerce")
    if pd.isna(inicio) or pd.isna(corte):
        raise ValueError("Fechas inválidas")
    limite = min(inicio, corte)
    h = historico_nba.copy()
    requerido = {"id", "fecha_utc", "finalizado"}
    if not requerido.issubset(h.columns):
        raise ValueError("Calendario sin columnas necesarias")
    h["id"] = h["id"].astype(str)
    fechas = pd.to_datetime(h["fecha_utc"], utc=True, errors="coerce")
    h = h.loc[h["finalizado"].eq(True) & fechas.lt(limite)].drop_duplicates("id")
    previo = historial_pace.copy()
    if not previo.empty:
        previo["partido_id"] = previo["partido_id"].astype(str)
        previo = previo.drop_duplicates("partido_id")
    conocidos = set(previo["partido_id"]) if "partido_id" in previo else set()
    faltantes = h.loc[~h["id"].isin(conocidos)].sort_values("fecha_utc")
    # Priorizar los equipos del encuentro objetivo; con un límite de 50,
    # recuperar simplemente los últimos juegos de toda la liga puede dejar
    # sin antecedentes a uno de los dos equipos.
    equipos = {str(partido["local"]), str(partido["visitante"])}
    prioridad = faltantes.loc[
        faltantes["local"].astype(str).isin(equipos)
        | faltantes["visitante"].astype(str).isin(equipos)
    ] if {"local", "visitante"}.issubset(faltantes.columns) else faltantes
    ids_prioritarios = set(prioridad["id"].astype(str))
    prioridad_seleccionada = prioridad.tail(max_consultas)
    cupo = max_consultas - len(prioridad_seleccionada)
    adicionales = faltantes.loc[~faltantes["id"].isin(ids_prioritarios)].tail(cupo) if cupo else faltantes.iloc[0:0]
    bloque = pd.concat([prioridad_seleccionada, adicionales], ignore_index=True)
    bloque = bloque.drop_duplicates("id").sort_values("fecha_utc")
    nuevos, errores = construir_historial(bloque, cargar_detalle, max_partidos=max_consultas)
    if not nuevos.empty:
        nuevos["partido_id"] = nuevos["partido_id"].astype(str)
    unido = pd.concat([previo, nuevos], ignore_index=True)
    if not unido.empty:
        unido = unido.drop_duplicates("partido_id", keep="first")
        fechas_pace = pd.to_datetime(unido["fecha_utc"], utc=True, errors="coerce")
        finalizados = unido["finalizado"].astype(str).str.lower().eq("true") if "finalizado" in unido else pd.Series(False, index=unido.index)
        unido = unido.loc[fechas_pace.lt(limite) & finalizados & fechas_pace.notna()].copy()
    return unido, {"pendientes":len(faltantes), "consultados":len(bloque),
                   "nuevos":len(nuevos), "errores":len(errores)}

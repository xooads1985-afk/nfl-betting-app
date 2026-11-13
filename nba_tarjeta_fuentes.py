"""Adaptador de fuentes del controlador NBA; no modifica módulos estables.

Carga el historial desde la función existente y el CSV versionado de Pace.
Ante incidencias de cobertura, falla de forma segura en vez de entrenar con
un historial incompleto sin advertirlo.
"""
from datetime import date, datetime, timezone
from pathlib import Path
import pandas as pd

COLUMNAS_PACE = {'partido_id', 'fecha_utc', 'finalizado', 'local', 'visitante',
                 'puntos_local', 'puntos_visitante', 'posesiones_local',
                 'posesiones_visitante', 'minutos_partido'}


def cargar_pace(ruta, partido, *, solicitar_remoto=None, corte_utc=None):
    """Historial anterior al inicio; valida estructura, identidad y cobertura."""
    archivo = Path(ruta)
    if not archivo.is_file() and solicitar_remoto is None:
        raise ValueError('No existe el historial Pace versionado ni fuente remota')
    if solicitar_remoto is None:
        tabla = pd.read_csv(archivo, encoding='utf-8-sig')
    else:
        from nba_pace_fuente_unificada import cargar_historial_unificado
        tabla, _ = cargar_historial_unificado(
            archivo, solicitar_remoto, antes_de=min(
                pd.to_datetime(partido.get('fecha_utc'), utc=True),
                pd.to_datetime(corte_utc if corte_utc is not None else datetime.now(timezone.utc), utc=True)
            ))
    faltantes = COLUMNAS_PACE - set(tabla.columns)
    if faltantes:
        raise ValueError('Columnas Pace faltantes: ' + ', '.join(sorted(faltantes)))
    if tabla['partido_id'].astype(str).duplicated().any():
        raise ValueError('IDs duplicados en el historial Pace')
    fechas = pd.to_datetime(tabla['fecha_utc'], utc=True, errors='coerce')
    inicio = pd.to_datetime(partido.get('fecha_utc'), utc=True, errors='coerce')
    if pd.isna(inicio) or fechas.isna().any():
        raise ValueError('Fechas Pace inválidas')
    corte = pd.to_datetime(corte_utc if corte_utc is not None else datetime.now(timezone.utc), utc=True, errors='coerce')
    if pd.isna(corte):
        raise ValueError('Corte de predicción inválido')
    finalizados = tabla['finalizado'].astype(str).str.lower().eq('true')
    # No incluir partidos futuros, en curso o el encuentro objetivo.
    tabla = tabla.loc[(fechas < inicio) & (fechas < corte) & finalizados &
                      tabla['partido_id'].astype(str).ne(str(partido['id']))].copy()
    for campo in ('puntos_local', 'puntos_visitante', 'posesiones_local',
                  'posesiones_visitante', 'minutos_partido'):
        tabla[campo] = pd.to_numeric(tabla[campo], errors='coerce')
        if tabla[campo].isna().any() or (tabla[campo] <= 0).any():
            raise ValueError('Valores Pace inválidos: ' + campo)
    # No exigir actividad dentro de 72 horas: la temporada puede tener descansos.
    # La suficiencia se valida por antecedentes de cada equipo y por la cobertura
    # del calendario, no por la edad del último encuentro.
    equipos = (str(partido['local']), str(partido['visitante']))
    for equipo in equipos:
        if (tabla['local'].eq(equipo) | tabla['visitante'].eq(equipo)).sum() < 3:
            raise ValueError('Insuficientes antecedentes Pace para ' + equipo)
    return tabla


def cargar_tres(cargador, partido, desde=date(2025, 10, 21), *, corte_utc=None):
    """Usa el cargador cacheado existente; rechaza incidencias de cobertura."""
    inicio = pd.to_datetime(partido.get('fecha_utc'), utc=True, errors='coerce')
    if pd.isna(inicio):
        raise ValueError('Inicio del partido inválido')
    corte = pd.to_datetime(corte_utc if corte_utc is not None else datetime.now(timezone.utc), utc=True, errors='coerce')
    if pd.isna(corte):
        raise ValueError('Corte de predicción inválido')
    hasta = min(inicio, corte).date()
    if hasta < desde:
        raise ValueError('Inicio anterior al período de entrenamiento')
    tabla, incidencias = cargador(desde, hasta)
    if incidencias:
        raise ValueError('Historial NBA con incidencias de cobertura; no calcular automáticamente')
    if tabla is None or tabla.empty:
        raise ValueError('Historial NBA vacío')
    necesarias = {'id', 'fecha_utc', 'finalizado', 'puntos_local', 'puntos_visitante'}
    if not necesarias.issubset(tabla.columns):
        raise ValueError('Faltan columnas en historial NBA')
    fechas = pd.to_datetime(tabla['fecha_utc'], utc=True, errors='coerce')
    if fechas.isna().any():
        raise ValueError('Fechas inválidas en historial NBA')
    filtrado = tabla.loc[(fechas < inicio) & (fechas < corte) & tabla['finalizado'].eq(True)].copy()
    filtrado = filtrado.drop_duplicates('id', keep='last')
    if len(filtrado) < 20:
        raise ValueError('Insuficiente historial NBA para entrenar')
    return filtrado

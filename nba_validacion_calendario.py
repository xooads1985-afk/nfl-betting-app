"""Verificación local del encuentro seleccionado contra el calendario cargado."""
import pandas as pd


def validar_partido_calendario(partido, calendario):
    """Rechaza IDs ambiguos, cambios de equipos o fechas; no consulta red."""
    if calendario is None:
        raise ValueError('Calendario no disponible para validar identidad')
    tabla = calendario if isinstance(calendario, pd.DataFrame) else pd.DataFrame(calendario)
    campos = {'id', 'fecha_utc', 'local', 'visitante'}
    if not campos.issubset(tabla.columns):
        raise ValueError('Calendario sin columnas de identidad requeridas')
    pid = str(partido.get('id', '')).strip()
    if not pid.isdecimal():
        raise ValueError('ID ESPN de selección inválido')
    filas = tabla.loc[tabla['id'].astype(str).eq(pid)]
    if len(filas) != 1:
        raise ValueError('ID de partido ausente o duplicado en calendario')
    fila = filas.iloc[0]
    for lado in ('local', 'visitante'):
        if str(fila[lado]).strip().casefold() != str(partido.get(lado, '')).strip().casefold():
            raise ValueError('Identidad de equipo no coincide: ' + lado)
    inicio = pd.to_datetime(partido.get('fecha_utc'), utc=True, errors='coerce')
    fecha = pd.to_datetime(fila['fecha_utc'], utc=True, errors='coerce')
    if pd.isna(inicio) or pd.isna(fecha) or inicio != fecha:
        raise ValueError('Fecha del encuentro no coincide con calendario')
    return True

"""Cache compartida de historial NBA, solo para la rama experimental."""
from pathlib import Path
import ast

ruta = Path(__file__).resolve().parent / 'nba_conexion_tarjeta.py'
original = ruta.read_text(encoding='utf-8')
marca = 'NBA_CACHE_HISTORIAL_COMPARTIDO_V1'
if marca in original:
    print('La optimización ya estaba aplicada')
else:
    anterior = '''def _historial(desde_iso, hasta_iso):
    tabla, incidencias = cargar_historial_bloques(date.fromisoformat(desde_iso), date.fromisoformat(hasta_iso))
    return tabla, tuple(incidencias)
'''
    nuevo = '''# NBA_CACHE_HISTORIAL_COMPARTIDO_V1
# Reutilizar historial verificado por una hora sin alterar la selección de motores.
import streamlit as st

@st.cache_data(ttl=3600, max_entries=24, show_spinner=False)
def _historial_verificado(desde_iso, hasta_iso):
    tabla, incidencias = cargar_historial_bloques(
        date.fromisoformat(desde_iso), date.fromisoformat(hasta_iso))
    if incidencias:
        raise ValueError('Cobertura histórica incompleta: ' + '; '.join(map(str, incidencias)))
    return tabla

def _historial(desde_iso, hasta_iso):
    try:
        return _historial_verificado(desde_iso, hasta_iso), ()
    except ValueError as exc:
        # No se almacena en cache un historial incompleto o fallido.
        return __import__('pandas').DataFrame(), (str(exc),)
'''
    if original.count(anterior) != 1:
        raise RuntimeError('Ancla de historial no encontrada; no se cambió el archivo')
    actualizado = original.replace(anterior, nuevo, 1)
    ast.parse(actualizado, filename=str(ruta))
    ruta.write_text(actualizado, encoding='utf-8')
    print('Cache compartida instalada sin modificar motores ni diseño')

"""Aplica un cambio mínimo a la tarjeta de la rama experimental."""
from pathlib import Path
ruta = Path(__file__).resolve().parent / 'nba_prediccion_tarjeta.py'
if not ruta.is_file():
    raise SystemExit('Falta nba_prediccion_tarjeta.py en la raíz')
s = ruta.read_text(encoding='utf8')
imp = 'from nba_pace_periodos_tarjeta import completar_filas'
if imp not in s:
    ancla = 'from tarjeta_motor_cuatro import preparar'
    if s.count(ancla) != 1: raise SystemExit('Importación original no encontrada')
    s = s.replace(ancla, ancla + '\n' + imp)
original = "st.markdown(_tabla_periodos(datos['periodos'],local,visitante),unsafe_allow_html=True)"
reemplazo = "filas_periodos, nota_periodos = completar_filas(datos['periodos'], partido)\n        st.markdown(_tabla_periodos(filas_periodos,local,visitante),unsafe_allow_html=True)"
if original in s:
    s = s.replace(original, reemplazo, 1)
elif 'filas_periodos, nota_periodos = completar_filas' not in s:
    raise SystemExit('Tabla original no encontrada')
nota = "st.caption('Primer cuarto y primera mitad: sin predicciones validadas; no se reparten puntos artificialmente.')"
if nota in s: s = s.replace(nota, 'st.caption(nota_periodos)', 1)
if 'st.caption(nota_periodos)' not in s: raise SystemExit('Nota original no encontrada')
ruta.write_text(s,encoding='utf8')
print('Cambio Q1/1H aplicado a tarjeta experimental')

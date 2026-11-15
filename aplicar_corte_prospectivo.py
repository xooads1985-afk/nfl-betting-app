"""Corrige corte temporal del seguimiento experimental, sin alterar registros."""
from pathlib import Path
import ast
ROOT=Path(__file__).resolve().parent
modelo=ROOT/'nba_pace_periodos_modelo.py'
seguimiento=ROOT/'nba_seguimiento_periodos.py'
if not modelo.exists() or not seguimiento.exists():
    raise SystemExit('Faltan los dos archivos Python en la raiz experimental')
m=modelo.read_text(encoding='utf-8')
s=seguimiento.read_text(encoding='utf-8')
old="def proyectar_periodos(historial, partido, *, ventana=10, minimo=5):"
new="def proyectar_periodos(historial, partido, *, ventana=10, minimo=5, corte_utc=None):"
if old in m:
    m=m.replace(old,new,1)
elif new not in m:
    raise SystemExit('Firma del modelo desconocida')
old="    h = _preparar(historial, partido['fecha_utc'], partido.get('id'))"
new="""    # El corte de generación evita usar partidos posteriores al pronóstico.
    limite = partido['fecha_utc']
    if corte_utc is not None:
        fecha_objetivo = pd.to_datetime(partido['fecha_utc'], utc=True, errors='raise')
        fecha_corte = pd.to_datetime(corte_utc, utc=True, errors='raise')
        limite = min(fecha_objetivo, fecha_corte)
    h = _preparar(historial, limite, partido.get('id'))"""
if old in m:
    m=m.replace(old,new,1)
elif new not in m:
    raise SystemExit('Corte temporal desconocido')
old="pred=proyectar_periodos(h,p,ventana=10,minimo=5)"
new="pred=proyectar_periodos(h,p,ventana=10,minimo=5,corte_utc=ahora)"
if old in s:
    s=s.replace(old,new,1)
elif new not in s:
    raise SystemExit('Llamada prospectiva desconocida')
for path,content in ((modelo,m),(seguimiento,s)):
    ast.parse(content,filename=str(path))
    path.write_text(content,encoding='utf-8')
print('Corte temporal aplicado; pronosticos existentes intactos')

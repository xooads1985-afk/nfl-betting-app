"""Auditoría estática de prepublicación. No modifica archivos."""
import ast, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
MODULOS=["main.py","nba_lab_panel_movil.py","nba_prediccion_tarjeta.py","tarjeta_motor_cuatro.py","nba_selector_objetivos.py","nba_pace_periodos_tarjeta.py","nba_pace_periodos_modelo.py"]
resultado={"archivos":{},"errores":[],"advertencias":[]}
for nombre in MODULOS:
    p=ROOT/nombre
    if not p.is_file():
        resultado["errores"].append(f"Falta {nombre}")
        continue
    try:
        arbol=ast.parse(p.read_text(encoding="utf-8-sig"),filename=nombre)
        imports=sorted(set(n.module.split(".")[0] for n in ast.walk(arbol) if isinstance(n,ast.ImportFrom) and n.module))
        resultado["archivos"][nombre]={"sintaxis":"OK","imports":imports}
    except SyntaxError as e:
        resultado["errores"].append(f"Sintaxis {nombre}: {e}")
main=(ROOT/"main.py").read_text(encoding="utf-8-sig") if (ROOT/"main.py").exists() else ""
panel=(ROOT/"nba_lab_panel_movil.py").read_text(encoding="utf-8-sig") if (ROOT/"nba_lab_panel_movil.py").exists() else ""
tarjeta=(ROOT/"nba_prediccion_tarjeta.py").read_text(encoding="utf-8-sig") if (ROOT/"nba_prediccion_tarjeta.py").exists() else ""
resultado["menu_laboratorio"]= 'import nba_lab_panel_movil' in main
resultado["tarjeta_tiene_entrada"]= 'def mostrar_tarjeta(' in tarjeta
resultado["panel_invoca_tarjeta"]= 'mostrar_tarjeta(' in panel
if not resultado["menu_laboratorio"]:resultado["errores"].append("El menú no carga el panel NBA")
if not resultado["tarjeta_tiene_entrada"]:resultado["errores"].append("No existe mostrar_tarjeta")
if not resultado["panel_invoca_tarjeta"]:resultado["advertencias"].append("El panel NBA todavía no invoca mostrar_tarjeta: falta integración selectiva")
resultado["apto_para_publicar"]=not resultado["errores"] and resultado["panel_invoca_tarjeta"]
out=ROOT/"nba_prepublicacion_reporte.json"
out.write_text(json.dumps(resultado,indent=2,ensure_ascii=False),encoding="utf-8")
print(json.dumps(resultado,indent=2,ensure_ascii=False))
sys.exit(1 if resultado["errores"] else 0)

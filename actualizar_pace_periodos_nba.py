"""Actualización conservadora del historial Pace + Q1/1H en rama experimental."""
import csv
import json
import shutil
import tempfile
from pathlib import Path
from enriquecer_historial_pace import CAMPOS, consultar, extraer_marcadores
from actualizar_pace_incremental_nba import actualizar

ROOT = Path(__file__).resolve().parent
PACE = ROOT / "nba_historial_pace.csv"
PERIODOS = ROOT / "nba_historial_pace_periodos_validado.csv"
REPORTE = ROOT / "nba_pace_actualizacion_reporte.json"

def leer(ruta):
    with ruta.open(newline="", encoding="utf-8-sig") as f:
        r=csv.DictReader(f)
        return list(r.fieldnames or []), list(r)

def ejecutar():
    if not PACE.is_file() or not PERIODOS.is_file():
        raise FileNotFoundError("Faltan los dos CSV históricos; no se modificó nada")
    with tempfile.TemporaryDirectory() as d:
        respaldo=Path(d)/"pace.csv"
        shutil.copy2(PACE,respaldo)
        try:
            actualizar(dias=7,max_partidos=100)
            cols, base=leer(PACE)
            cp, previos=leer(PERIODOS)
            ids=[r["partido_id"] for r in previos]
            if len(ids)!=len(set(ids)):
                raise ValueError("IDs duplicados en períodos anteriores")
            conocidos=set(ids)
            pendientes=[r for r in base if r["partido_id"] not in conocidos]
            if len({r["partido_id"] for r in base})!=len(base):
                raise ValueError("IDs duplicados en Pace")
            if not set(cols).issubset(cp) or not set(CAMPOS).issubset(cp):
                raise ValueError("Esquema histórico incompatible")
            nuevos=[]
            for fila in pendientes:
                if str(fila["finalizado"]).lower()!="true":
                    raise ValueError("Partido no finalizado: "+fila["partido_id"])
                puntos=extraer_marcadores(consultar(fila["partido_id"]),fila)
                nuevos.append({**fila,**puntos})
            combinados=previos+nuevos
            if len(combinados)!=len(base):
                raise ValueError("Cobertura incompleta: se conserva el historial")
            salida=Path(d)/"periodos.csv"
            with salida.open("w",newline="",encoding="utf-8-sig") as f:
                w=csv.DictWriter(f,fieldnames=cp,extrasaction="ignore")
                w.writeheader()
                w.writerows(combinados)
            salida.replace(PERIODOS)
            REPORTE.write_text(json.dumps({"pace_total":len(base),"periodos_total":len(combinados),
                "nuevos_periodos":len(nuevos),"estado":"completo"},indent=2),encoding="utf-8")
            print(REPORTE.read_text())
        except Exception:
            shutil.copy2(respaldo,PACE)
            raise

if __name__=="__main__":
    ejecutar()

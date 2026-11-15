"""Actualiza ambos historiales experimentales exclusivamente desde ESPN."""
import csv
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from enriquecer_historial_pace import CAMPOS, extraer_marcadores, consultar
from nba_pace_historial import extraer_partido

ROOT=Path(__file__).resolve().parent
PACE=ROOT/"nba_historial_pace.csv"
PERIODOS=ROOT/"nba_historial_pace_periodos_validado.csv"
REPORT=ROOT/"nba_pace_actualizacion_reporte.json"
SCOREBOARD="https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"

def leer(path):
    with path.open(newline="",encoding="utf-8-sig") as f:
        reader=csv.DictReader(f)
        return list(reader.fieldnames or []),list(reader)

def escribir(path,cols,rows):
    with path.open("w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=cols,extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

def descubrir(dia):
    req=Request(SCOREBOARD+"?"+urlencode({"dates":dia.strftime("%Y%m%d"),"limit":100}),
                headers={"User-Agent":"NBA-Lab-Pace-Periodos/1.0"})
    with urlopen(req,timeout=30) as r:
        payload=json.load(r)
    if "events" not in payload:
        raise ValueError("Respuesta ESPN sin eventos")
    return [str(e["id"]) for e in payload["events"]
            if (e.get("status") or {}).get("type",{}).get("completed") is True]

def ejecutar():
    if not PACE.is_file() or not PERIODOS.is_file():
        raise FileNotFoundError("Faltan los CSV originales")
    cpace,pace=leer(PACE)
    cper,periodos=leer(PERIODOS)
    if not pace or not periodos or not {"partido_id","fecha_utc"}.issubset(cpace):
        raise ValueError("Historial base incompleto")
    if not set(cpace).issubset(cper) or not set(CAMPOS).issubset(cper):
        raise ValueError("Esquema incompatible")
    for rows in (pace,periodos):
        ids=[r["partido_id"] for r in rows]
        if len(ids)!=len(set(ids)):raise ValueError("IDs duplicados")
    bypace={r["partido_id"]:r for r in pace}
    byper={r["partido_id"]:r for r in periodos}
    today=datetime.now(timezone.utc).date()
    ids=set()
    for n in range(8):
        ids.update(descubrir(today-timedelta(days=n)))
    nuevos_pace=0
    nuevos_periodos=0
    for pid in sorted(ids):
        if pid in byper:continue
        detalle=consultar(pid)
        if pid in bypace:
            fila=bypace[pid]
        else:
            fila=extraer_partido(detalle,pid)
            if fila is None:raise ValueError("Pace incompleto para "+pid)
            fila={k:str(v) for k,v in fila.items()}
            if not set(cpace).issubset(fila):raise ValueError("Columnas Pace faltantes: "+pid)
            bypace[pid]=fila
            nuevos_pace+=1
        valores=extraer_marcadores(detalle,fila)
        byper[pid]={**fila,**valores}
        nuevos_periodos+=1
    # Reconciliar filas Pace previas sin períodos; nunca publicar cobertura parcial.
    faltantes=set(bypace)-set(byper)
    for pid in sorted(faltantes):
        fila=bypace[pid]
        valores=extraer_marcadores(consultar(pid),fila)
        byper[pid]={**fila,**valores}
        nuevos_periodos+=1
    if set(bypace)!=set(byper):raise ValueError("Cobertura inconsistente")
    pace_final=sorted(bypace.values(),key=lambda x:(x["fecha_utc"],x["partido_id"]))
    per_final=sorted(byper.values(),key=lambda x:(x["fecha_utc"],x["partido_id"]))
    # Preparar todos los archivos antes de reemplazar los originales.
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        temp=Path(td)
        p=temp/"pace.csv";q=temp/"periodos.csv"
        escribir(p,cpace,pace_final)
        escribir(q,cper,per_final)
        # Solo se llega aquí cuando ESPN validó todos los partidos.
        os.replace(p,PACE)
        os.replace(q,PERIODOS)
    resumen={"pace_total":len(pace_final),"periodos_total":len(per_final),
             "nuevos_pace":nuevos_pace,"nuevos_periodos":nuevos_periodos,
             "fuente":"ESPN","estado":"completo"}
    REPORT.write_text(json.dumps(resumen,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(resumen,ensure_ascii=False,indent=2))

if __name__=="__main__":
    ejecutar()


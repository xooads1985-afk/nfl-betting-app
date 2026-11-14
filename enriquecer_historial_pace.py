"""Enriquece un CSV Pace histórico con marcadores Q1/Q2 de ESPN, sin sobrescribirlo.

Ejecutar sobre una copia en la rama experimental. No cambia proyecciones ni motores.
"""
import argparse
import csv
import json
import math
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CAMPOS = ["puntos_q1_local", "puntos_q1_visitante", "puntos_q2_local", "puntos_q2_visitante", "puntos_mitad_local", "puntos_mitad_visitante"]
BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event="


def entero(valor):
    try:
        n = float(valor)
        if math.isfinite(n) and n >= 0 and n.is_integer():
            return int(n)
    except (TypeError, ValueError):
        pass
    return None


def extraer_marcadores(detalle, fila):
    """Rechaza resultados no finalizados, equipos/identidades o sumas inconsistentes."""
    comp = (detalle.get("header") or {}).get("competitions") or []
    if len(comp) != 1:
        raise ValueError("competencia ausente")
    comp = comp[0]
    if str(comp.get("id")) != str(fila["partido_id"]):
        raise ValueError("ID de partido distinto")
    if not ((comp.get("status") or {}).get("type") or {}).get("completed"):
        raise ValueError("partido no finalizado")
    rivales = comp.get("competitors") or []
    if len(rivales) != 2:
        raise ValueError("competidores distintos de dos")
    datos = {}
    for c in rivales:
        lado = {"home": "local", "away": "visitante"}.get(c.get("homeAway"))
        if lado is None or lado in datos:
            raise ValueError("local/visitante inválido")
        if (c.get("team") or {}).get("displayName") != fila[lado]:
            raise ValueError("nombre de equipo no coincide")
        puntos = entero(c.get("score"))
        esperado = entero(fila["puntos_" + lado])
        lines = c.get("linescores") or []
        periodos = [entero(x.get("displayValue", x.get("value"))) for x in lines]
        if len(periodos) < 4 or None in periodos or puntos != esperado or sum(periodos) != puntos:
            raise ValueError("marcadores de cuartos no coinciden con resultado final")
        datos[lado] = periodos
    if set(datos) != {"local", "visitante"}:
        raise ValueError("faltan equipos")
    if len(datos["local"]) != len(datos["visitante"]):
        raise ValueError("duración inconsistente")
    return {**{f"puntos_q1_{lado}": p[0] for lado, p in datos.items()},
            **{f"puntos_q2_{lado}": p[1] for lado, p in datos.items()},
            **{f"puntos_mitad_{lado}": p[0] + p[1] for lado, p in datos.items()}}


def consultar(partido_id, intentos=3):
    req = Request(BASE + str(partido_id), headers={"User-Agent": "NBA-Lab-Periodos/1.0", "Accept": "application/json"})
    for intento in range(intentos):
        try:
            with urlopen(req, timeout=25) as respuesta:
                return json.load(respuesta)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            if intento == intentos - 1:
                raise RuntimeError(f"ESPN no disponible: {type(exc).__name__}") from exc
            time.sleep(2 * (intento + 1))


def enriquecer(entrada, salida, informe, pausa=1.1):
    entrada, salida, informe = map(Path, (entrada, salida, informe))
    if entrada.resolve() == salida.resolve():
        raise ValueError("La salida no puede sobrescribir el historial original")
    with entrada.open(newline="", encoding="utf-8-sig") as f:
        lector = csv.DictReader(f)
        originales = list(lector)
        columnas = list(lector.fieldnames or [])
    obligatorias = {"partido_id", "local", "visitante", "puntos_local", "puntos_visitante", "finalizado"}
    if not obligatorias.issubset(columnas):
        raise ValueError("Faltan columnas originales")
    if len({r["partido_id"] for r in originales}) != len(originales):
        raise ValueError("IDs duplicados")
    columnas_salida = columnas + [c for c in CAMPOS if c not in columnas]
    completos, errores = [], []
    for i, fila in enumerate(originales, 1):
        if str(fila["finalizado"]).lower() != "true":
            errores.append({"partido_id": fila["partido_id"], "motivo": "no finalizado"})
            continue
        try:
            puntos = extraer_marcadores(consultar(fila["partido_id"]), fila)
            completos.append({**fila, **puntos})
        except (RuntimeError, ValueError, KeyError, TypeError) as exc:
            errores.append({"partido_id": fila["partido_id"], "motivo": str(exc)})
        print(f"{i}/{len(originales)} - correctos: {len(completos)}, pendientes: {len(errores)}", flush=True)
        if i < len(originales):
            time.sleep(pausa)
    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", newline="", encoding="utf-8-sig") as f:
        escritor = csv.DictWriter(f, fieldnames=columnas_salida)
        escritor.writeheader()
        escritor.writerows(completos)
    reporte = {"registros_originales": len(originales), "enriquecidos_verificados": len(completos),
               "pendientes": len(errores), "errores": errores,
               "advertencia": "Archivo de salida solo contiene partidos comprobados; no reemplazar el CSV original."}
    informe.write_text(json.dumps(reporte, ensure_ascii=False, indent=2), encoding="utf-8")
    return reporte


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--entrada", default="nba_historial_pace.csv")
    ap.add_argument("--salida", default="nba_historial_pace_periodos_validado.csv")
    ap.add_argument("--informe", default="nba_pace_periodos_cobertura.json")
    args = ap.parse_args()
    print(json.dumps(enriquecer(args.entrada, args.salida, args.informe), ensure_ascii=False, indent=2))

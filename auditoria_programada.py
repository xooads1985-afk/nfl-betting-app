#!/usr/bin/env python3
"""Auditoría descriptiva diaria. Ejecutar desde la raíz del repositorio."""
import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from promedios_diferencias_nfl import (cargar_resultados, cargar_marcadores_espn,
                                       comparar_fuentes_nfl)

TEMPORADA = int(os.getenv("NFL_TEMPORADA", str(datetime.now(timezone.utc).year)))
CARPETA = Path("datos_auditoria")
CARPETA.mkdir(parents=True, exist_ok=True)
HISTORIAL = CARPETA / f"historial_{TEMPORADA}.csv"
SNAPSHOT = CARPETA / f"ultimo_estado_{TEMPORADA}.json"
CAMPOS = ["fecha_utc", "temporada", "partidos", "coinciden", "diferentes",
          "sin_verificar", "errores_consulta", "partidos_nuevos", "marcadores_cambiados"]


def ejecutar():
    partidos = cargar_resultados(TEMPORADA)
    externos, errores = cargar_marcadores_espn(TEMPORADA)
    comparados, coinciden, sin_verificar, diferentes = comparar_fuentes_nfl(
        partidos, externos, errores)
    actual = {
        str(fila.game_id): [int(fila.home_score), int(fila.away_score)]
        for fila in partidos.itertuples()
    }
    anterior = {}
    if SNAPSHOT.exists():
        anterior = json.loads(SNAPSHOT.read_text(encoding="utf-8")).get("marcadores", {})
    nuevos = sorted(set(actual) - set(anterior))
    cambiados = sorted(k for k in set(actual) & set(anterior) if actual[k] != anterior[k])
    fila = {
        "fecha_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "temporada": TEMPORADA, "partidos": len(partidos),
        "coinciden": coinciden, "diferentes": diferentes,
        "sin_verificar": sin_verificar, "errores_consulta": len(errores),
        "partidos_nuevos": len(nuevos), "marcadores_cambiados": len(cambiados),
    }
    # Nunca reemplazar una referencia válida con un resultado parcial de red.
    if errores or externos.empty or len(partidos) == 0 or sin_verificar > 0:
        raise RuntimeError(f"Consulta incompleta: {fila}. No se guardó revisión parcial.")
    with HISTORIAL.open("a", newline="", encoding="utf-8") as archivo:
        writer = csv.DictWriter(archivo, fieldnames=CAMPOS)
        if archivo.tell() == 0:
            writer.writeheader()
        writer.writerow(fila)
    SNAPSHOT.write_text(json.dumps({"fecha_utc": fila["fecha_utc"],
                                    "marcadores": actual, "nuevos": nuevos,
                                    "cambiados": cambiados}, indent=2), encoding="utf-8")
    print(json.dumps(fila, ensure_ascii=False))


if __name__ == "__main__":
    ejecutar()


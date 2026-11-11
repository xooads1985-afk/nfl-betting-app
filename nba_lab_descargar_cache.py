
"""Descarga segura de eventos ESPN para el Laboratorio NBA."""

from datetime import date, timedelta
from pathlib import Path
import json
import time

import requests

URL = (
    "https://site.api.espn.com/apis/site/v2/"
    "sports/basketball/nba/scoreboard"
)


def descargar_dia(dia, carpeta="nba_lab_cache"):
    carpeta = Path(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / f"{dia.isoformat()}.json"

    if destino.exists():
        try:
            datos = json.loads(
                destino.read_text(encoding="utf-8")
            )
            if isinstance(datos.get("events"), list):
                return datos
        except (OSError, ValueError, AttributeError):
            pass

    for intento in range(3):
        try:
            respuesta = requests.get(
                URL,
                params={
                    "dates": dia.strftime("%Y%m%d"),
                    "limit": 100,
                },
                timeout=25,
            )
            respuesta.raise_for_status()
            datos = respuesta.json()

            if not isinstance(datos.get("events"), list):
                raise ValueError("Respuesta ESPN inválida")

            temporal = destino.with_suffix(".tmp")
            temporal.write_text(
                json.dumps(datos, ensure_ascii=False),
                encoding="utf-8",
            )
            temporal.replace(destino)
            return datos
        except (requests.RequestException, ValueError):
            if intento == 2:
                raise
            time.sleep(2 * (intento + 1))


def descargar_periodo(inicio, fin, carpeta="nba_lab_cache"):
    actual = date.fromisoformat(inicio)
    ultimo = date.fromisoformat(fin)

    if ultimo < actual:
        raise ValueError("Intervalo inválido")

    total = 0
    while actual <= ultimo:
        descargar_dia(actual, carpeta)
        total += 1
        actual += timedelta(days=1)

    return total

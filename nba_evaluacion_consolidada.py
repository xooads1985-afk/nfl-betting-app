"""Evaluación histórica de instantáneas NBA. No realiza escrituras."""
import hashlib
import json
import math
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TABLA = "nba_proyecciones_consolidadas"


def _fecha(valor):
    dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Fecha sin zona horaria")
    return dt.astimezone(timezone.utc)


def consultar_guardados(*, url, clave, abrir=urlopen):
    """Lectura paginada de instantáneas originales."""
    if not url.startswith("https://") or not clave:
        raise ValueError("Credenciales Supabase ausentes")
    salida = []
    offset = 0
    while True:
        query = urlencode({"select": "clave_unica,partido_id,inicio_utc,creado_utc,huella_sha256,registro",
                           "order": "creado_utc.asc", "limit": "500", "offset": str(offset)})
        req = Request(url.rstrip("/") + "/rest/v1/" + TABLA + "?" + query,
                      headers={"apikey": clave, "Authorization": "Bearer " + clave,
                               "Accept": "application/json"}, method="GET")
        with abrir(req, timeout=20) as response:
            lote = json.load(response)
        if not isinstance(lote, list):
            raise ValueError("Respuesta Supabase inválida")
        salida.extend(lote)
        if len(lote) < 500:
            return salida
        offset += 500


def evaluar_guardados(guardados, resultados):
    """resultados: iterable con id, fecha_utc, local, visitante, finalizado,
    puntos_local y puntos_visitante reglamentarios (sin prórrogas).
    Solo se evalúan resultados completos, coherentes y posteriores al guardado.
    """
    partidos = {str(p["id"]): p for p in resultados if p.get("id") is not None}
    filas = []
    descartes = {}
    vistos = set()

    def descartar(motivo):
        descartes[motivo] = descartes.get(motivo, 0) + 1

    for item in guardados:
        try:
            reg = item["registro"]
            pid = str(reg["partido_id"])
            if pid in vistos:
                descartar("duplicado")
                continue
            vistos.add(pid)
            if item["clave_unica"] != "nba-consolidado-v1:" + pid or str(item["partido_id"]) != pid:
                descartar("identidad")
                continue
            canon = json.dumps(reg, sort_keys=True, ensure_ascii=False,
                               separators=(",", ":"), allow_nan=False)
            digest = hashlib.sha256(canon.encode("utf-8")).hexdigest()
            if digest != item["huella_sha256"]:
                descartar("huella")
                continue
            inicio = _fecha(reg["inicio_utc"])
            if _fecha(item["inicio_utc"]) != inicio or _fecha(item["creado_utc"]) >= inicio:
                descartar("registro_tardio")
                continue
            real = partidos.get(pid)
            if not real or real.get("finalizado") is not True:
                descartar("sin_resultado_final")
                continue
            if _fecha(real["fecha_utc"]) != inicio:
                descartar("fecha_inconsistente")
                continue
            if (str(real["local"]) != reg["equipos"]["local"] or
                    str(real["visitante"]) != reg["equipos"]["visitante"]):
                descartar("equipos_inconsistentes")
                continue
            locales = float(real["puntos_local"])
            visitantes = float(real["puntos_visitante"])
            if not all(math.isfinite(x) and x >= 0 for x in (locales, visitantes)):
                descartar("marcador_invalido")
                continue
            for objetivo, proy, observado in (
                ("local", reg["proyecciones"]["local"], locales),
                ("visitante", reg["proyecciones"]["visitante"], visitantes),
                ("total", reg["proyecciones"]["total"], locales + visitantes),
            ):
                p = float(proy)
                if not math.isfinite(p):
                    raise ValueError("Proyección inválida")
                filas.append({"partido_id": pid, "objetivo": objetivo,
                              "motor": reg["seleccion"]["total" if objetivo == "total" else "puntos_por_equipo"]["motor"],
                              "proyeccion": p, "real": observado, "error": p - observado})
        except (ValueError, TypeError, KeyError, OverflowError):
            descartar("datos_incompletos")
    resumen = []
    for objetivo in ("local", "visitante", "total"):
        muestra = [r["error"] for r in filas if r["objetivo"] == objetivo]
        if muestra:
            resumen.append({"objetivo": objetivo, "n": len(muestra),
                            "MAE": round(sum(abs(e) for e in muestra) / len(muestra), 3),
                            "sesgo": round(sum(muestra) / len(muestra), 3)})
    equipos = [r["error"] for r in filas if r["objetivo"] in ("local", "visitante")]
    if equipos:
        resumen.append({"objetivo": "puntos_por_equipo", "n": len(equipos),
                        "MAE": round(sum(abs(e) for e in equipos) / len(equipos), 3),
                        "sesgo": round(sum(equipos) / len(equipos), 3)})
    return {"detalle": filas, "resumen": resumen, "descartes": descartes}

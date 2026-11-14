"""Guardado manual e inmutable de proyecciones NBA en tabla independiente."""
import json
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlencode

TABLA = "nba_proyecciones_consolidadas"


def guardar_preparado(preparado, *, url, clave, abrir=urlopen, ahora=None):
    """Solo INSERT. La PK y UNIQUE de Supabase resuelven carreras/duplicados."""
    if not url.startswith("https://") or not clave:
        raise ValueError("Conexión Supabase no disponible")
    if preparado.get("estado") != "validado_sin_guardar":
        raise ValueError("Se requiere un registro previamente validado")
    registro = preparado["registro"]
    instante = ahora or datetime.now(timezone.utc)
    if instante.tzinfo is None:
        raise ValueError("Reloj sin zona horaria")
    inicio = datetime.fromisoformat(registro["inicio_utc"].replace("Z", "+00:00"))
    if instante.astimezone(timezone.utc) >= inicio:
        return {"estado": "partido_iniciado"}
    clave_unica = preparado["clave_unica"]
    if clave_unica != "nba-consolidado-v1:" + str(registro["partido_id"]):
        raise ValueError("Identidad de partido inconsistente")
    from nba_registro_consolidado import construir_registro
    nuevo = construir_registro({
        "partido_id": registro["partido_id"], "inicio_utc": registro["inicio_utc"],
        "equipos": registro["equipos"], "seleccion": registro["seleccion"],
        "proyecciones": registro["proyecciones"], "referencias": registro["referencias"],
        "edge": registro["edge"], "cuatro_motores": registro["cuatro_motores"],
    }, ahora=instante)
    if nuevo["huella_sha256"] != preparado["huella_sha256"]:
        raise ValueError("Huella inconsistente; registro alterado")
    payload = {
        "clave_unica": clave_unica,
        "partido_id": str(registro["partido_id"]),
        "inicio_utc": registro["inicio_utc"],
        "huella_sha256": preparado["huella_sha256"],
        "registro": registro,
    }
    request = Request(
        url.rstrip("/") + "/rest/v1/" + TABLA,
        data=json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8"),
        headers={"apikey": clave, "Authorization": "Bearer " + clave,
                 "Content-Type": "application/json", "Accept": "application/json",
                 "Prefer": "return=representation"},
        method="POST",
    )
    try:
        with abrir(request, timeout=15) as respuesta:
            filas = json.load(respuesta)
    except HTTPError as exc:
        if exc.code == 409:
            return {"estado": "ya_existe", "detalle": "Registro original protegido"}
        return {"estado": "error_http", "codigo_http": exc.code}
    except (URLError, TimeoutError):
        return {"estado": "sin_confirmacion", "detalle": "Consultar antes de reintentar"}
    if not isinstance(filas, list) or len(filas) != 1:
        return {"estado": "sin_confirmacion"}
    fila = filas[0]
    if (fila.get("clave_unica") != clave_unica or
            fila.get("huella_sha256") != preparado["huella_sha256"] or
            fila.get("registro") != registro):
        return {"estado": "verificacion_fallida"}
    return {"estado": "guardado_verificado", "clave_unica": clave_unica,
            "huella_sha256": preparado["huella_sha256"]}

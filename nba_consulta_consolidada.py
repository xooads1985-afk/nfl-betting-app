"""Diagnóstico de solo lectura de la tabla consolidada NBA."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TABLA = "nba_proyecciones_consolidadas"


def comprobar_registro(clave_unica, *, url, clave, abrir=urlopen):
    """Consulta una clave. No ejecuta INSERT, UPDATE ni DELETE."""
    if not isinstance(clave_unica, str) or not clave_unica.startswith("nba-consolidado-v1:"):
        raise ValueError("Clave de registro inválida")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("URL de Supabase inválida")
    if not clave:
        raise ValueError("Credencial de consulta ausente")
    params = urlencode({"select": "clave_unica,huella_sha256,partido_id,inicio_utc",
                        "clave_unica": "eq." + clave_unica, "limit": "1"})
    req = Request(url.rstrip("/") + "/rest/v1/" + TABLA + "?" + params,
                  headers={"apikey": clave, "Authorization": "Bearer " + clave,
                           "Accept": "application/json"}, method="GET")
    try:
        with abrir(req, timeout=10) as response:
            filas = json.load(response)
    except HTTPError as exc:
        if exc.code in (401, 403):
            return {"estado": "sin_permiso_lectura", "codigo_http": exc.code}
        if exc.code == 404:
            return {"estado": "tabla_no_disponible", "codigo_http": 404}
        return {"estado": "error_http", "codigo_http": exc.code}
    except (URLError, TimeoutError):
        return {"estado": "sin_conexion"}
    if not isinstance(filas, list):
        return {"estado": "respuesta_inesperada"}
    if not filas:
        return {"estado": "sin_registro"}
    return {"estado": "registro_existente",
            "clave_unica": filas[0].get("clave_unica"),
            "huella_sha256": filas[0].get("huella_sha256")}

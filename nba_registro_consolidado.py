"""Validación pura del registro NBA; no accede a Supabase."""
from datetime import datetime, timezone
import hashlib
import json
import math

VERSION = "nba-consolidado-v1"


def _fecha(valor):
    if not isinstance(valor, str):
        raise ValueError("Fecha UTC ausente")
    dt = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("La fecha requiere zona horaria")
    return dt.astimezone(timezone.utc)


def _numero(valor, nombre):
    if isinstance(valor, bool) or not isinstance(valor, (float, int)):
        raise ValueError(f"{nombre}: valor numérico requerido")
    if not math.isfinite(valor):
        raise ValueError(f"{nombre}: valor no finito")
    return round(float(valor), 3)


def construir_registro(auditoria, ahora=None):
    """Construye una instantánea verificable; no la persiste."""
    ahora = ahora or datetime.now(timezone.utc)
    if ahora.tzinfo is None:
        raise ValueError("El reloj debe incluir zona horaria")
    inicio = _fecha(auditoria.get("inicio_utc"))
    if ahora.astimezone(timezone.utc) >= inicio:
        raise ValueError("Partido iniciado: guardado bloqueado")

    partido = str(auditoria.get("partido_id") or "").strip()
    if not partido:
        raise ValueError("Identificador de partido ausente")
    equipos = auditoria.get("equipos") or {}
    local = str(equipos.get("local") or "").strip()
    visitante = str(equipos.get("visitante") or "").strip()
    if not local or not visitante or local == visitante:
        raise ValueError("Equipos no válidos")

    seleccion = auditoria.get("seleccion") or {}
    motores = {}
    for objetivo in ("puntos_por_equipo", "total"):
        info = seleccion.get(objetivo) or {}
        motor = str(info.get("motor") or "").strip()
        if not motor:
            raise ValueError(f"Falta motor de {objetivo}")
        muestra = info.get("muestra")
        if isinstance(muestra, bool) or not isinstance(muestra, int) or muestra <= 0:
            raise ValueError(f"Muestra histórica inválida: {objetivo}")
        mae = _numero(info.get("MAE"), f"MAE {objetivo}")
        if mae < 0:
            raise ValueError(f"MAE inválido: {objetivo}")
        motores[objetivo] = {
            "motor": motor,
            "MAE": mae,
            "muestra": muestra,
            "sesgo": None if info.get("sesgo") is None else _numero(info["sesgo"], f"sesgo {objetivo}"),
        }

    campos = ("local", "visitante", "total")
    proy = auditoria.get("proyecciones") or {}
    refs = auditoria.get("referencias") or {}
    edges = auditoria.get("edge") or {}
    proyecciones = {k: _numero(proy.get(k), f"proyección {k}") for k in campos}
    referencias = {k: _numero(refs.get(k), f"referencia {k}") for k in campos}
    edge = {k: _numero(edges.get(k), f"Edge {k}") for k in campos}
    for k in campos:
        if abs(edge[k] - (proyecciones[k] - referencias[k])) > 0.002:
            raise ValueError(f"Edge inconsistente: {k}")
    if any(v < 0 for v in proyecciones.values()):
        raise ValueError("Proyecciones negativas")

    modelos = auditoria.get("cuatro_motores")
    if not isinstance(modelos, list) or len(modelos) != 4:
        raise ValueError("Se requieren cuatro motores")
    registro = {
        "version": VERSION,
        "partido_id": partido,
        "inicio_utc": inicio.isoformat().replace("+00:00", "Z"),
        "equipos": {"local": local, "visitante": visitante},
        "seleccion": motores,
        "proyecciones": proyecciones,
        "referencias": referencias,
        "edge": edge,
        "cuatro_motores": modelos,
    }
    canon = json.dumps(registro, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return {
        "clave_unica": f"{VERSION}:{partido}",
        "huella_sha256": hashlib.sha256(canon.encode("utf-8")).hexdigest(),
        "registro": registro,
        "estado": "validado_sin_guardar",
    }

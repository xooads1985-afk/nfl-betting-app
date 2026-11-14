"""Resultados NBA reglamentarios para evaluación consolidada (solo lectura)."""
import math


def resultados_reglamentarios(partidos, cargar_detalle, extraer_periodos):
    """Devuelve resultados de 4 cuartos, sin prórrogas, con errores diagnosticables."""
    salida, descartes = [], {}
    for partido in partidos:
        try:
            if not bool(partido["finalizado"]):
                continue
            pid = str(partido["id"])
            local, visitante = str(partido["local"]), str(partido["visitante"])
            detalle = cargar_detalle(pid)
            periodos = extraer_periodos(detalle)
            def cuatro(equipo):
                valores = periodos[equipo]
                if not isinstance(valores, dict) or not all(k in valores for k in (1,2,3,4)):
                    raise ValueError("faltan cuatro cuartos")
                puntos = [float(valores[k]) for k in (1,2,3,4)]
                if not all(math.isfinite(x) and x >= 0 for x in puntos):
                    raise ValueError("cuartos invalidos")
                return sum(puntos)
            salida.append({"id": pid, "fecha_utc": str(partido["fecha_utc"]),
                           "local": local, "visitante": visitante, "finalizado": True,
                           "puntos_local": cuatro(local), "puntos_visitante": cuatro(visitante)})
        except (KeyError, TypeError, ValueError, RuntimeError, OverflowError) as exc:
            descartes[str(partido.get("id","desconocido"))] = str(exc)[:150]
    return salida, descartes

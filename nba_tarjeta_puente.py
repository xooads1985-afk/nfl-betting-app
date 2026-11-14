"""Puente aislado para integrar tarjeta NBA.

NBA_PACE_CSV_PRIMERO_V1
Prioriza el historial Pace publicado por GitHub Actions.
No modifica los módulos estables ni escribe en Supabase por defecto.
"""

from pathlib import Path
from time import perf_counter
from datetime import datetime, timezone

from nba_tarjeta_controlador import diagnosticar, ejecutar, fecha_utc
from nba_tarjeta_fuentes import cargar_pace, cargar_tres


def preparar_y_ejecutar(
    partido,
    *,
    consultar,
    cargador_historial,
    calcular_tres,
    guardar_tres,
    calcular_pace,
    guardar_pace,
    ruta_pace,
    modo_prueba=True,
    reloj=None,
    solicitar_remoto=None,
    cargar_detalle=None,
):
    """Consulta registros y carga únicamente los motores pendientes."""

    _tiempos = {}
    _inicio_puente = perf_counter()

    _t = perf_counter()
    registros = consultar(partido["id"])
    _tiempos["Consulta de registros"] = round(
        perf_counter() - _t, 2
    )

    faltantes = diagnosticar(partido, registros)

    if not faltantes:
        return {
            "estado": "completo",
            "faltantes": (),
            "nuevos": 0,
            "registros": registros,
        }

    if partido.get("finalizado") is True:
        return {
            "estado": "iniciado",
            "faltantes": tuple(sorted(faltantes)),
            "nuevos": 0,
            "registros": registros,
        }

    ahora = fecha_utc(
        reloj() if reloj else datetime.now(timezone.utc)
    )
    inicio = fecha_utc(partido["fecha_utc"])

    if inicio is None or ahora is None or ahora >= inicio:
        return {
            "estado": "iniciado",
            "faltantes": tuple(sorted(faltantes)),
            "nuevos": 0,
            "registros": registros,
        }

    tres = None
    pace = None
    incidencias = {}

    necesita_tres = any(
        modelo in ("Base", "Modelo C", "Ensemble")
        for _, modelo in faltantes
    )

    necesita_pace = any(
        modelo == "Pace + Eficiencia"
        for _, modelo in faltantes
    )

    # Los tres motores originales conservan su funcionamiento.
    if necesita_tres:
        try:
            _t = perf_counter()
            try:
                tres = cargar_tres(
                    cargador_historial,
                    partido,
                    corte_utc=ahora,
                )
            finally:
                _tiempos["Historial tres motores"] = round(
                    perf_counter() - _t, 2
                )

        except (
            ValueError,
            RuntimeError,
            OSError,
            TimeoutError,
            ImportError,
        ) as exc:
            incidencias["tres"] = (
                f"{type(exc).__name__}: {exc}"
            )

    # PACE: primero consultar el CSV del workflow.
    if necesita_pace:
        _t = perf_counter()

        try:
            pace = cargar_pace(
                Path(ruta_pace),
                partido,
                solicitar_remoto=None,
                corte_utc=ahora,
            )

            _tiempos["Origen Pace"] = (
                "CSV validado por workflow"
            )

        except (
            ValueError,
            RuntimeError,
            OSError,
            TimeoutError,
            ImportError,
        ) as exc:
            pace = None
            _tiempos["Origen Pace"] = (
                "Respaldo histórico ESPN"
            )
            _tiempos["Motivo respaldo Pace"] = (
                f"{type(exc).__name__}: {exc}"
            )

        finally:
            _tiempos["Lectura CSV Pace"] = round(
                perf_counter() - _t, 2
            )

        # Solo consultar ESPN cuando el CSV no sea suficiente.
        if pace is None:
            try:
                if cargar_detalle is not None:
                    from nba_pace_actualizacion_auto import (
                        completar_pace,
                    )
                    from nba_tarjeta_fuentes import COLUMNAS_PACE
                    import pandas as pd

                    if tres is None:
                        _t = perf_counter()
                        try:
                            tres = cargar_tres(
                                cargador_historial,
                                partido,
                                corte_utc=ahora,
                            )
                        finally:
                            _tiempos[
                                "Segunda carga histórica para Pace"
                            ] = round(perf_counter() - _t, 2)

                    ruta = Path(ruta_pace)

                    previo = (
                        pd.read_csv(
                            ruta,
                            encoding="utf-8-sig",
                        )
                        if ruta.is_file()
                        else pd.DataFrame()
                    )

                    _t = perf_counter()

                    try:
                        pace, cobertura = completar_pace(
                            tres,
                            previo,
                            partido,
                            cargar_detalle,
                            corte_utc=ahora,
                        )
                    finally:
                        _tiempos[
                            "Pace / detalles ESPN"
                        ] = round(perf_counter() - _t, 2)

                    if not COLUMNAS_PACE.issubset(
                        pace.columns
                    ):
                        raise ValueError(
                            "Historial Pace incompleto "
                            "después de actualizar ESPN"
                        )

                    for equipo in (
                        str(partido["local"]),
                        str(partido["visitante"]),
                    ):
                        antecedentes = (
                            pace["local"].eq(equipo)
                            | pace["visitante"].eq(equipo)
                        ).sum()

                        if antecedentes < 3:
                            raise ValueError(
                                "Insuficientes antecedentes "
                                "Pace para " + equipo
                            )

                else:
                    pace = cargar_pace(
                        Path(ruta_pace),
                        partido,
                        solicitar_remoto=solicitar_remoto,
                        corte_utc=ahora,
                    )

            except (
                ValueError,
                RuntimeError,
                OSError,
                TimeoutError,
                ImportError,
            ) as exc:
                pace = None
                incidencias["pace"] = (
                    f"{type(exc).__name__}: {exc}"
                )

    if modo_prueba:
        calculados = {}

        if tres is not None and necesita_tres:
            try:
                _t = perf_counter()

                try:
                    calculados["tres"] = calcular_tres(
                        tres,
                        partido,
                    )
                finally:
                    _tiempos[
                        "Cálculo Base / C / Ensemble"
                    ] = round(perf_counter() - _t, 2)

                # NBA_PERFIL_PUENTE_V1
                from nba_laboratorio_prospectivo import ultimo_perfil_tres
                perfil_tres = ultimo_perfil_tres()
                if perfil_tres:
                    _tiempos.update(perfil_tres)

            except (
                ValueError,
                KeyError,
                TypeError,
                RuntimeError,
                OSError,
                TimeoutError,
            ) as exc:
                incidencias["motor_tres"] = (
                    f"{type(exc).__name__}: {exc}"
                )

        if pace is not None and necesita_pace:
            try:
                _t = perf_counter()

                try:
                    calculados["pace"] = calcular_pace(
                        pace,
                        partido,
                        ahora=ahora,
                    )
                finally:
                    _tiempos["Cálculo Pace"] = round(
                        perf_counter() - _t, 2
                    )

            except (
                ValueError,
                KeyError,
                TypeError,
                RuntimeError,
                OSError,
                TimeoutError,
            ) as exc:
                incidencias["motor_pace"] = (
                    f"{type(exc).__name__}: {exc}"
                )

        _tiempos["Total puente"] = round(
            perf_counter() - _inicio_puente, 2
        )

        _tiempos["Estado historial tres motores"] = (
            "disponible"
            if tres is not None
            else "no disponible"
        )

        _tiempos["Estado Pace"] = (
            "disponible"
            if pace is not None
            else "no disponible"
        )

        _tiempos["Incidencias detectadas"] = len(
            incidencias
        )

        return {
            "estado": "simulacion",
            "faltantes": tuple(sorted(faltantes)),
            "nuevos": 0,
            "registros": registros,
            "calculados": calculados,
            "incidencias_fuentes": incidencias,
            "diagnostico_tiempos": _tiempos,
        }

    resultado = ejecutar(
        partido,
        consultar,
        calcular_tres,
        guardar_tres,
        calcular_pace,
        guardar_pace,
        historial_tres=tres,
        historial_pace=pace,
        modo_prueba=False,
        ahora=ahora,
        reloj=reloj,
    )

    if incidencias:
        resultado["incidencias_fuentes"] = incidencias

    return resultado


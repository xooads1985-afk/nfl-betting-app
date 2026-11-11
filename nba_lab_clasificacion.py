
"""Clasificación de partidos del Laboratorio NBA."""

from __future__ import annotations


def clasificar_evento(event: dict) -> str:
    season = event.get("season") or {}
    raw = season.get("type")

    try:
        kind = int(raw)
    except (ValueError, TypeError):
        return "sin_verificar"

    return {
        1: "pretemporada",
        2: "regular",
        3: "postemporada",
        4: "especial",
    }.get(kind, "sin_verificar")


def filtrar_regular(df):
    if "tipo_competicion" not in df.columns:
        raise ValueError(
            "Faltan metadatos de competición"
        )

    return df.loc[
        df["tipo_competicion"].eq("regular")
    ].copy()


"""Adaptador experimental NFLverse -> motor prospectivo.

FINAL inferido es una etiqueta operativa, NO confirmación oficial.

Solo se utilizan marcadores cuando:
- Existen ambos resultados.
- El inicio del partido más el margen de seguridad
  es anterior o igual al corte de datos.

Los marcadores demasiado recientes se excluyen
sin interrumpir el laboratorio.
"""

import pandas as pd
from preparar_calendario import preparar


COLS = [
    "game_id",
    "season",
    "week",
    "gameday",
    "gametime",
    "home_team",
    "away_team",
    "home_score",
    "away_score",
]


def adaptar(raw, corte_utc, margen_horas=24):

    if margen_horas < 6:
        raise ValueError(
            "Margen de seguridad menor de 6 horas"
        )

    data = raw.copy()

    if not set(COLS).issubset(data.columns):
        raise ValueError(
            "Faltan campos del calendario NFLverse"
        )

    corte = pd.Timestamp(corte_utc)

    if corte.tzinfo is None:
        raise ValueError(
            "Corte sin zona horaria"
        )

    corte = corte.tz_convert("UTC")

    # Preparar calendario y comprobar integridad.
    # Se mantiene la protección contra resultados futuros.
    base, reporte = preparar(data, corte)

    completos = (
        base["home_score"].notna()
        & base["away_score"].notna()
    )

    # Solo entrenar con marcadores suficientemente antiguos.
    seguros = (
        completos
        & (
            base["kickoff_utc"]
            + pd.Timedelta(hours=margen_horas)
            <= corte
        )
    )

    # Resultados recientes: excluir, nunca entrenar con ellos.
    sin_confirmar = completos & ~seguros

    excluidos_recientes = int(sin_confirmar.sum())

    # Únicamente partidos futuros sin marcador.
    futuros = (
        (base["kickoff_utc"] > corte)
        & ~completos
    )

    # Conservar solamente históricos seguros y futuros.
    output = base.loc[
        seguros | futuros
    ].copy()

    # Clasificación operativa.
    output["game_status"] = ""

    output.loc[
        seguros.loc[output.index],
        "game_status"
    ] = "FINAL"

    output.loc[
        futuros.loc[output.index],
        "game_status"
    ] = "SCHEDULED"

    # Documentar el origen de la clasificación.
    output["clasificacion_origen"] = ""

    output.loc[
        seguros.loc[output.index],
        "clasificacion_origen"
    ] = "inferido_por_marcador_y_margen"

    output.loc[
        futuros.loc[output.index],
        "clasificacion_origen"
    ] = "futuro_sin_marcador"

    # Auditoría del filtrado.
    reporte.update(
        entrenables_inferidos=int(seguros.sum()),
        futuros=int(futuros.sum()),
        excluidos_recientes=excluidos_recientes,
        margen_horas=margen_horas,
        limitacion=(
            "FINAL inferido no es estado oficial "
            "ni prueba de disponibilidad del marcador "
            "en backtests"
        ),
    )

    return output.reset_index(drop=True), reporte

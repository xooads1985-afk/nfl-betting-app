
"""Fast history adapter with integrity checks and live recent-day refresh."""
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
import hashlib
import json
import pandas as pd

BASE = Path(__file__).resolve().parent / "nba_cache_preparada"
NEEDED = {"id", "fecha_utc", "local", "visitante", "finalizado",
          "puntos_local", "puntos_visitante"}

def cargar_historial_rapido(cargador, desde, hasta):
    """Snapshot through yesterday, fresh source for yesterday and today.

    Fallback to original complete loader on any uncertainty.
    """
    def original():
        from nba_historial_bloques import cargar_por_bloques
        return cargar_por_bloques(cargador, desde, hasta)
    try:
        desde = date.fromisoformat(str(desde))
        hasta = date.fromisoformat(str(hasta))
        hoy = datetime.now(timezone.utc).date()
        if hasta < desde or hasta > hoy:
            return original()
        manifest = json.loads((BASE / "manifiesto.json").read_text())
        raw = (BASE / "historial_finalizados.csv").read_bytes()
        if hashlib.sha256(raw).hexdigest() != manifest["sha256"]:
            return original()
        snap = pd.read_csv(BASE / "historial_finalizados.csv", dtype={"id": str})
        if not NEEDED.issubset(snap.columns) or len(snap) != manifest["partidos"]:
            return original()
        if snap["id"].duplicated().any() or not snap["finalizado"].eq(True).all():
            return original()
        fechas = pd.to_datetime(snap["fecha_utc"], utc=True, errors="coerce")
        if fechas.isna().any() or snap[["local", "visitante", "puntos_local", "puntos_visitante"]].isna().any().any():
            return original()
        inicio_snapshot = date.fromisoformat(manifest["desde"])
        fin_snapshot = date.fromisoformat(manifest["hasta"])
        # Require a current daily snapshot. Older snapshots must use original loader.
        if inicio_snapshot > desde or fin_snapshot < hoy - timedelta(days=1):
            return original()
        # Refresh last 2 calendar days to catch newly finalized and corrected scores.
        refrescar_desde = max(desde, hoy - timedelta(days=1))
        if hasta < refrescar_desde:
            # Past-only requests can use the snapshot without live calls.
            tabla = snap.loc[fechas.dt.date.between(desde, hasta)].copy()
            return tabla, []
        reciente, errores = cargador(refrescar_desde, hasta)
        if errores or reciente is None or not NEEDED.issubset(reciente.columns):
            return original()
        if reciente.empty and refrescar_desde <= hasta:
            # An empty ESPN response could be valid; conservative fallback.
            return original()
        # Drop all overlapping snapshot dates, replace with live source data.
        antiguo = snap.loc[fechas.dt.date.between(desde, refrescar_desde - timedelta(days=1))].copy()
        combinado = pd.concat([antiguo, reciente], ignore_index=True)
        combinado["id"] = combinado["id"].astype(str)
        combinado = combinado.drop_duplicates("id", keep="last")
        combinado = combinado.sort_values("fecha_utc").reset_index(drop=True)
        if not NEEDED.issubset(combinado.columns):
            return original()
        return combinado, []
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, OverflowError):
        return original()


"""Use only a verified, exactly matching historical vector snapshot."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd

BASE = Path(__file__).resolve().parent / "nba_cache_preparada"
FIELDS = ("id", "fecha_utc", "local", "visitante", "puntos_local", "puntos_visitante")

def normalized(df):
    t = df.loc[:, list(FIELDS)].copy()
    t["id"] = t["id"].astype(str)
    t["fecha_utc"] = pd.to_datetime(t["fecha_utc"], utc=True, errors="raise").dt.strftime("%Y-%m-%dT%H:%M:%S.%f%z")
    for c in ("local", "visitante"):
        t[c] = t[c].astype(str)
    for c in ("puntos_local", "puntos_visitante"):
        t[c] = pd.to_numeric(t[c], errors="raise").astype(float)
    if t["id"].duplicated().any() or t.isna().any().any():
        raise ValueError("Invalid history")
    return t.sort_values("id").reset_index(drop=True)

def cargar_preparado(datos):
    """Return None unless all historical identities and values match exactly."""
    try:
        mh = json.loads((BASE / "manifiesto.json").read_text())
        mv = json.loads((BASE / "manifiesto_entrenamiento.json").read_text())
        raw = (BASE / "historial_finalizados.csv").read_bytes()
        vectors = (BASE / "entrenamiento_indexado.jsonl").read_bytes()
        if hashlib.sha256(raw).hexdigest() != mh["sha256"]:
            return None
        if hashlib.sha256(vectors).hexdigest() != mv["vectores_sha256"]:
            return None
        if mh["sha256"] != mv["historial_sha256"]:
            return None
        hist = pd.read_csv(BASE / "historial_finalizados.csv", dtype={"id": str})
        if len(hist) != mh["partidos"] or len(hist) != mv["partidos"]:
            return None
        if not hist["finalizado"].eq(True).all():
            return None
        cutoff = pd.to_datetime(datos["fecha_utc"], utc=True).max()
        hist = hist.loc[pd.to_datetime(hist["fecha_utc"], utc=True).le(cutoff)]
        if len(hist) != len(datos) or not normalized(hist).equals(normalized(datos)):
            return None
        ids = set(datos["id"].astype(str))
        result = []
        for line in vectors.splitlines():
            item = json.loads(line)
            if str(item["partido_id"]) not in ids:
                continue
            x = np.asarray(item["x"], dtype=float)
            if x.shape != (11,) or not np.isfinite(x).all():
                return None
            if not all(np.isfinite(float(item[k])) for k in ("real", "base", "liga")):
                return None
            result.append({"equipo": str(item["equipo"]), "x": x,
                           "real": float(item["real"]), "base": float(item["base"]),
                           "liga": float(item["liga"]), "n": int(item["n"])})
        if len(result) < 24:
            return None
        return result
    except (OSError, ValueError, TypeError, KeyError, UnicodeError, OverflowError):
        return None

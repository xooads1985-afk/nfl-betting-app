"""Pipeline experimental portable: calendario original -> auditoría -> predicciones.
No modifica módulos estables ni presupone acceso a red.
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import shutil
import uuid
import pandas as pd
from puente_calendario_real import adaptar
from generar_prospectivas import generar


def ejecutar(origen, destino, corte_utc=None, minimo=150):
    corte = pd.Timestamp(corte_utc or datetime.now(timezone.utc))
    if corte.tzinfo is None:
        raise ValueError('Corte UTC sin zona horaria')
    origen, destino = Path(origen), Path(destino)
    raw = pd.read_parquet(origen) if origen.suffix.lower() == '.parquet' else pd.read_csv(origen)
    preparado, auditoria = adaptar(raw, corte)
    # Construir fuera del destino y publicar los tres archivos como una unidad.
    destino.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=destino.parent) as temporal:
        tmp = Path(temporal)
        preparado.to_csv(tmp/'calendario_modelo.csv', index=False)
        cantidad = generar(preparado, tmp/'prospectivas.csv', corte, minimo=minimo)
        auditoria['predicciones'] = cantidad
        (tmp/'auditoria.json').write_text(json.dumps(auditoria, ensure_ascii=False, indent=2), encoding='utf-8')
        respaldo = destino.with_name(destino.name + '.backup-' + uuid.uuid4().hex)
        anterior = destino.exists()
        if anterior:
            os.replace(destino, respaldo)
        try:
            os.replace(tmp, destino)
        except BaseException:
            if anterior:
                os.replace(respaldo, destino)
            raise
        if anterior:
            shutil.rmtree(respaldo)
    return auditoria

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--origen',required=True);p.add_argument('--destino',required=True)
    p.add_argument('--corte-utc');p.add_argument('--minimo',type=int,default=150)
    a=p.parse_args()
    print(json.dumps(ejecutar(a.origen,a.destino,a.corte_utc,a.minimo),ensure_ascii=False))

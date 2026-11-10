"""Puente entre salida prospectiva y registro inmutable; sin tocar app estable."""
from pathlib import Path
import csv
import math
from datetime import datetime, timezone
from registro_prospectivo import CAMPOS, _fecha
from historial_persistente import fusionar

REQUIRED = {'game_id','kickoff_utc','generated_utc','model','version','home','away','total','margin','train_n','last_train_kickoff_utc'}

def convertir_filas(rows):
    result=[]
    seen=set()
    for row in rows:
        if not REQUIRED.issubset(row):
            raise ValueError('Predicción incompleta')
        kickoff=_fecha(row['kickoff_utc'])
        generated=_fecha(row['generated_utc'])
        last=_fecha(row['last_train_kickoff_utc'])
        if not (last < generated < kickoff):
            raise ValueError('Fechas de entrenamiento, generación o partido inconsistentes')
        if int(row['train_n']) < 1:
            raise ValueError('Entrenamiento vacío')
        home,away,total,margin=map(float,(row['home'],row['away'],row['total'],row['margin']))
        if not all(map(math.isfinite,(home,away,total,margin))) or min(home,away)<0:
            raise ValueError('Valores no válidos')
        if abs(home+away-total)>1e-6 or abs(home-away-margin)>1e-6:
            raise ValueError('Total o margen incoherentes')
        if not all(str(row[x]).strip() for x in ('game_id','model','version')):
            raise ValueError('Clave vacía')
        key=(str(row['game_id']),str(row['model']),str(row['version']))
        if key in seen: raise ValueError('Predicción duplicada en lote')
        seen.add(key)
        result.append(dict(game_id=key[0],fecha_partido_utc=kickoff.isoformat(),modelo=key[1],
            generado_utc=generated.isoformat(),puntos_local=home,puntos_visitante=away,
            total=total,margen=margin,version=key[2]))
    return result

def guardar_lote(ruta,rows):
    """Valida el lote completo antes de modificar el historial."""
    datos=convertir_filas(rows)
    if not datos: return {'total':0,'nuevos':0}
    ruta=Path(ruta)
    ruta.parent.mkdir(parents=True,exist_ok=True)
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as tmp:
        nuevo=Path(tmp)/'nuevo.csv'
        with nuevo.open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=CAMPOS);w.writeheader();w.writerows(datos)
        return fusionar(ruta,nuevo)

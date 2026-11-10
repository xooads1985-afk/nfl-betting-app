import csv
from datetime import datetime, timezone
from pathlib import Path
CAMPOS = ('game_id','fecha_partido_utc','modelo','generado_utc','puntos_local','puntos_visitante','total','margen','version')
def _fecha(s):
 d=datetime.fromisoformat(str(s).replace('Z','+00:00'))
 if d.tzinfo is None: raise ValueError('Fecha sin zona horaria')
 return d.astimezone(timezone.utc)
def registrar(ruta,game_id,fecha_partido_utc,modelo,puntos_local,puntos_visitante,version,generado_utc=None):
 ahora=_fecha(generado_utc) if generado_utc else datetime.now(timezone.utc)
 inicio=_fecha(fecha_partido_utc)
 if ahora>=inicio: raise ValueError('No se permite guardar predicción después del inicio')
 if not str(game_id).strip() or not str(modelo).strip(): raise ValueError('ID/modelo vacíos')
 a,b=float(puntos_local),float(puntos_visitante)
 import math
 if not all(map(math.isfinite,(a,b))) or min(a,b)<0: raise ValueError('Puntos inválidos')
 ruta=Path(ruta);ruta.parent.mkdir(parents=True,exist_ok=True);existe=ruta.exists()
 if existe:
  with ruta.open(newline='',encoding='utf-8') as f:
   for fila in csv.DictReader(f):
    if fila['game_id']==str(game_id) and fila['modelo']==str(modelo) and fila['version']==str(version): return False
 with ruta.open('a',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=CAMPOS)
  if not existe:w.writeheader()
  w.writerow(dict(game_id=game_id,fecha_partido_utc=inicio.isoformat(),modelo=modelo,generado_utc=ahora.isoformat(),puntos_local=a,puntos_visitante=b,total=a+b,margen=a-b,version=version))
 return True

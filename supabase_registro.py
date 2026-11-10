"""Exportación opcional de predicciones previas al partido a Supabase.

Nunca actualiza filas existentes: requiere índice único y RLS configurado.
No hace llamadas de red al importar el módulo.
"""
import csv
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen

FIELDS = ('game_id','fecha_partido_utc','modelo','generado_utc',
          'puntos_local','puntos_visitante','total','margen','version')

def preparar(ruta):
    with Path(ruta).open(newline='',encoding='utf-8') as f:
        rows=list(csv.DictReader(f))
    if not rows: return []
    if any(not set(FIELDS).issubset(row) for row in rows):
        raise ValueError('CSV sin columnas obligatorias')
    result=[]; seen=set()
    for r in rows:
        key=(r['game_id'],r['modelo'],r['version'])
        if key in seen: raise ValueError('CSV contiene predicciones duplicadas')
        seen.add(key)
        from registro_prospectivo import _fecha
        if _fecha(r['generado_utc']) >= _fecha(r['fecha_partido_utc']):
            raise ValueError('Predicción posterior al inicio del partido')
        a,b=float(r['puntos_local']),float(r['puntos_visitante'])
        import math
        if not all(map(math.isfinite,(a,b))) or min(a,b)<0: raise ValueError('Puntos inválidos')
        if abs(a+b-float(r['total']))>0.0001 or abs(a-b-float(r['margen']))>0.0001:
            raise ValueError('Total/margen inconsistentes')
        result.append({k:(float(r[k]) if k in ('puntos_local','puntos_visitante','total','margen') else r[k]) for k in FIELDS})
    return result

def enviar(ruta, dry_run=True, url=None, key=None, opener=urlopen):
    rows=preparar(ruta)
    if dry_run: return {'modo':'dry_run','registros_validados':len(rows),'enviados':0}
    if not rows: return {'modo':'save','registros_validados':0,'enviados':0}
    url=(url or os.environ.get('SUPABASE_URL','')).rstrip('/')
    key=key or os.environ.get('SUPABASE_SERVICE_ROLE_KEY','')
    if not url.startswith('https://') or not key: raise ValueError('Falta SUPABASE_URL HTTPS o SERVICE_ROLE_KEY')
    endpoint=url+'/rest/v1/nfl_lab_predicciones'
    req=Request(endpoint,data=json.dumps(rows).encode('utf-8'),method='POST',headers={
        'apikey':key,'Authorization':'Bearer '+key,'Content-Type':'application/json',
        'Prefer':'resolution=ignore-duplicates,return=minimal'})
    with opener(req,timeout=30) as response:
        if response.status not in (200,201,204): raise RuntimeError('Error al guardar en Supabase')
    return {'modo':'save','registros_validados':len(rows),
            'enviados':'solicitados (duplicados ignorados por Supabase)'}

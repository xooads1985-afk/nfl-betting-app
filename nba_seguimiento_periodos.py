"""Registro inmutable de pronósticos prospectivos Q1/1H y evaluación ESPN.
Solo rama experimental. Nunca genera pronósticos de juegos ya iniciados.
"""
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import pandas as pd
from nba_pace_periodos_modelo import proyectar_periodos
from enriquecer_historial_pace import extraer_marcadores, consultar

ROOT=Path(__file__).resolve().parent
HIST=ROOT/'nba_historial_pace_periodos_validado.csv'
OUT=ROOT/'nba_seguimiento_prospectivo'
REG=OUT/'pronosticos_q1_mitad.csv'
EVAL=OUT/'evaluaciones_q1_mitad.csv'
RES=OUT/'resumen_q1_mitad.json'
URL='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard'
CAMPOS=['partido_id','fecha_utc','generado_utc','local','visitante','q1_local','q1_visitante','q1_total','mitad_local','mitad_visitante','mitad_total','muestra_local','muestra_visitante']
ECAMPOS=['partido_id','fecha_utc','local','visitante','evaluado_utc','q1_local_real','q1_visitante_real','q1_total_real','mitad_local_real','mitad_visitante_real','mitad_total_real','q1_local_error','q1_visitante_error','q1_total_error','mitad_local_error','mitad_visitante_error','mitad_total_error']

def leer(path):
    if not path.exists():return []
    with path.open(newline='',encoding='utf-8-sig') as f:return list(csv.DictReader(f))

def guardar(path,campos,filas):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp')
    with temp.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=campos,extrasaction='ignore');w.writeheader();w.writerows(filas)
    temp.replace(path)

def calendario(dia):
    req=Request(URL+'?'+urlencode({'dates':dia.strftime('%Y%m%d'),'limit':100}),headers={'User-Agent':'NBA-Lab-Prospectivo/1.0'})
    with urlopen(req,timeout=30) as f: data=json.load(f)
    if 'events' not in data:raise ValueError('ESPN no devolvió eventos')
    return data['events']

def competidores(evento):
    comps=evento.get('competitions') or []
    if len(comps)!=1:return None
    lados={c.get('homeAway'):c for c in comps[0].get('competitors',[])}
    if set(lados)!={'home','away'}:return None
    local=lados['home'].get('team',{}).get('displayName')
    visita=lados['away'].get('team',{}).get('displayName')
    if not local or not visita:return None
    return {'id':str(evento['id']),'fecha_utc':evento.get('date'),'local':local,'visitante':visita}

def ejecutar():
    ahora=datetime.now(timezone.utc)
    if not HIST.exists():raise FileNotFoundError('Falta historial de períodos')
    h=pd.read_csv(HIST,encoding='utf-8-sig',dtype={'partido_id':str})
    if h['partido_id'].duplicated().any():raise ValueError('IDs duplicados en historial')
    registros=leer(REG);evaluaciones=leer(EVAL)
    ids_reg={x['partido_id'] for x in registros};ids_eval={x['partido_id'] for x in evaluaciones}
    if len(ids_reg)!=len(registros) or len(ids_eval)!=len(evaluaciones):raise ValueError('IDs duplicados en seguimiento')
    eventos={}
    for desplazamiento in (-2,-1,0,1,2):
        for e in calendario((ahora+timedelta(days=desplazamiento)).date()):
            eventos[str(e['id'])]=e
    nuevos=[];evaluados=[];pendientes=0
    # Evaluar primero solo registros ya guardados en ejecuciones anteriores.
    for r in registros:
        pid=r['partido_id']
        if pid in ids_eval:continue
        evento=eventos.get(pid)
        if not evento:continue
        status=(evento.get('status') or {}).get('type') or {}
        if not status.get('completed'):continue
        detalle=consultar(pid)
        # Comprobar identidad, lados, marcadores finales y sumas de cuartos.
        comps=(detalle.get('header') or {}).get('competitions') or []
        if len(comps)!=1 or str(comps[0].get('id'))!=pid:raise ValueError('Identidad de partido inválida '+pid)
        rivales={c.get('homeAway'):c for c in comps[0].get('competitors',[])}
        if set(rivales)!={'home','away'}:raise ValueError('Lados inválidos '+pid)
        fila={'partido_id':pid,'local':r['local'],'visitante':r['visitante'],
              'puntos_local':rivales['home'].get('score'),'puntos_visitante':rivales['away'].get('score')}
        if rivales['home']['team']['displayName']!=r['local'] or rivales['away']['team']['displayName']!=r['visitante']:
            raise ValueError('Equipos distintos '+pid)
        valores=extraer_marcadores(detalle,fila)
        salida={'partido_id':pid,'fecha_utc':r['fecha_utc'],'local':r['local'],'visitante':r['visitante'],'evaluado_utc':ahora.isoformat()}
        for prefijo,clave in [('q1','q1'),('mitad','mitad')]:
            for lado in ('local','visitante'):
                real=int(valores[f'puntos_{clave}_{lado}'])
                salida[f'{prefijo}_{lado}_real']=real
                salida[f'{prefijo}_{lado}_error']=round(float(r[f'{prefijo}_{lado}'])-real,3)
            total=salida[f'{prefijo}_local_real']+salida[f'{prefijo}_visitante_real']
            salida[f'{prefijo}_total_real']=total
            salida[f'{prefijo}_total_error']=round(float(r[f'{prefijo}_total'])-total,3)
        evaluados.append(salida)
    # Nuevos pronósticos: evento no iniciado y horario al menos 10 minutos futuro.
    for pid,e in eventos.items():
        if pid in ids_reg:continue
        p=competidores(e)
        if not p:continue
        fecha=pd.to_datetime(p['fecha_utc'],utc=True,errors='coerce')
        if pd.isna(fecha) or fecha.to_pydatetime()<=ahora+timedelta(minutes=10):continue
        estado=(e.get('status') or {}).get('type') or {}
        if estado.get('completed') or estado.get('state')!='pre':continue
        pred=proyectar_periodos(h,p,ventana=10,minimo=5)
        if pred is None:pendientes+=1;continue
        registro={'partido_id':pid,'fecha_utc':p['fecha_utc'],'generado_utc':ahora.isoformat(),
                  'local':p['local'],'visitante':p['visitante'],
                  'muestra_local':pred['muestras'][p['local']],
                  'muestra_visitante':pred['muestras'][p['visitante']]}
        for clave in ('q1','mitad'):
            for lado in ('local','visitante','total'):
                registro[f'{clave}_{lado}']=pred['periodos'][clave][lado]
        nuevos.append(registro)
    registros.extend(nuevos);evaluaciones.extend(evaluados)
    # Persistir solo después de validar todas las nuevas evaluaciones.
    guardar(REG,CAMPOS,registros)
    guardar(EVAL,ECAMPOS,evaluaciones)
    metricas={}
    for periodo in ('q1','mitad'):
        metricas[periodo]={}
        for lado in ('local','visitante','total'):
            errores=[float(x[f'{periodo}_{lado}_error']) for x in evaluaciones]
            metricas[periodo][lado]={'n':len(errores),'mae':round(sum(map(abs,errores))/len(errores),3) if errores else None,
                                     'sesgo':round(sum(errores)/len(errores),3) if errores else None}
    resumen={'generado_utc':ahora.isoformat(),'pronosticos_guardados':len(registros),
             'nuevos_pronosticos':len(nuevos),'partidos_evaluados':len(evaluaciones),
             'nuevas_evaluaciones':len(evaluados),'sin_muestra_suficiente':pendientes,
             'metricas':metricas,'nota':'Solo se evalúan predicciones registradas en ejecuciones anteriores.'}
    RES.write_text(json.dumps(resumen,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(resumen,indent=2,ensure_ascii=False))

if __name__=='__main__':ejecutar()

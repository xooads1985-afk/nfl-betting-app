"""Puente validado entre salida del motor y el historial inmutable."""
import argparse
import csv
from pathlib import Path
from tempfile import TemporaryDirectory
from registro_prospectivo import CAMPOS, registrar
from historial_persistente import fusionar, leer

COLUMNAS = ('game_id','kickoff_utc','generated_utc','model','version','home','away','total','margin','train_n','last_train_kickoff_utc')

def publicar(prospectivas, historial, omitir_existentes=False):
    prospectivas, historial = Path(prospectivas), Path(historial)
    with prospectivas.open(newline='', encoding='utf-8') as f:
        lector=csv.DictReader(f)
        if tuple(lector.fieldnames or ()) != COLUMNAS:
            raise ValueError('Esquema de prospectivas incompatible')
        filas=list(lector)
    if not filas:
        # Sin encuentros futuros: conservar intacto el historial anterior.
        return {'nuevos': 0, 'sin_partidos_futuros': True}
    with TemporaryDirectory() as tmp:
        nuevo=Path(tmp)/'nuevas.csv'
        claves=set()
        anteriores = leer(historial) if omitir_existentes else {}
        omitidas = 0
        for fila in filas:
            if any(fila.get(c) is None or not str(fila[c]).strip() for c in COLUMNAS):
                raise ValueError('Predicción incompleta')
            clave=(fila['game_id'],fila['model'],fila['version'])
            if clave in claves: raise ValueError('Predicción duplicada en lote')
            claves.add(clave)
            # Verificar campos derivados ANTES de registrar, que recalcula total/margen.
            a,b=float(fila['home']),float(fila['away'])
            if abs(a+b-float(fila['total']))>1e-6 or abs(a-b-float(fila['margin']))>1e-6:
                raise ValueError('Total o margen incompatible')
            from datetime import datetime
            def fecha(v):
                d=datetime.fromisoformat(v.replace('Z','+00:00'))
                if d.tzinfo is None: raise ValueError('Fecha sin zona horaria')
                return d
            if fecha(fila['last_train_kickoff_utc']) >= fecha(fila['generated_utc']):
                raise ValueError('Entrenamiento posterior a la generación')
            if int(fila['train_n'])<=0:raise ValueError('Entrenamiento vacío')
            if omitir_existentes and (fila['game_id'], fila['model'], fila['version']) in anteriores:
                omitidas += 1
                continue
            registrar(nuevo, fila['game_id'],fila['kickoff_utc'],fila['model'],a,b,fila['version'],fila['generated_utc'])
        if omitir_existentes and omitidas == len(filas):
            return {'total': len(anteriores), 'nuevos': 0, 'omitidas': omitidas}
        resultado = fusionar(historial,nuevo)
        resultado['omitidas'] = omitidas
        return resultado

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--prospectivas',required=True);p.add_argument('--historial',required=True);p.add_argument('--omitir-existentes',action='store_true')
    a=p.parse_args();print(publicar(a.prospectivas,a.historial,a.omitir_existentes))

"""Publica solamente tarjetas previamente validadas, sin tocar la aplicación estable."""
import argparse
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from nba_lab_lector_tarjetas import leer_tarjeta


def publicar(origen='nba_lab_resultados_futuro/lotes', destino='nba_lab_publicado', ahora_utc=None):
    origen, destino = Path(origen), Path(destino)
    indice = json.loads((origen / 'indice_tarjetas.json').read_text(encoding='utf-8'))
    entradas = indice.get('tarjetas')
    if not isinstance(entradas, list) or not entradas or indice.get('errores'):
        raise ValueError('Lote vacío o con errores: no se publica')
    ids = set()
    ahora = ahora_utc or datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix='nba-publicar-') as tmp:
        staging = Path(tmp)
        tarjetas = []
        for entrada in entradas:
            pid = str(entrada.get('id', ''))
            if not pid.isdigit() or pid in ids or entrada.get('archivo') != f'tarjeta_{pid}.json':
                raise ValueError('Índice con ID duplicado o nombre inconsistente')
            ids.add(pid)
            vista = leer_tarjeta(origen, pid, ahora_utc=ahora)
            if vista['partido_id'] != pid:
                raise ValueError('ID no coincide')
            nombre = f'tarjeta_{pid}.json'
            shutil.copyfile(origen / nombre, staging / nombre)
            tarjetas.append({'id':pid,'archivo':nombre,'fecha_utc':vista['fecha_utc'],
                             'generado_utc':vista['generado_utc'],
                             'local':vista['local'],'visitante':vista['visitante']})
        publicado = {'esquema':'nba_indice_publicado_v1','generado_utc':ahora,
                     'cantidad':len(tarjetas),'tarjetas':tarjetas,'errores':[]}
        (staging / 'indice_tarjetas.json').write_text(
            json.dumps(publicado,ensure_ascii=False,indent=2),encoding='utf-8')
        destino.mkdir(parents=True,exist_ok=True)
        # Retirar tarjetas de ejecuciones anteriores para evitar datos obsoletos.
        for previo in destino.glob('tarjeta_*.json'):
            previo.unlink()
        for tarjeta in tarjetas:
            shutil.copyfile(staging / tarjeta['archivo'], destino / tarjeta['archivo'])
        # El índice se publica al final.
        shutil.copyfile(staging / 'indice_tarjetas.json',destino / 'indice_tarjetas.json')
    return publicado

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--origen',default='nba_lab_resultados_futuro/lotes')
    p.add_argument('--destino',default='nba_lab_publicado')
    args=p.parse_args()
    print(json.dumps(publicar(args.origen,args.destino),ensure_ascii=False,indent=2))

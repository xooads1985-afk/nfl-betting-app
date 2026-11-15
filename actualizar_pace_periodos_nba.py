"""Actualización incremental NBA Pace/Q1/1H; solo CSV experimentales."""
import csv
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from enriquecer_historial_pace import CAMPOS, extraer_marcadores, consultar
from nba_pace_historial import extraer_partido

ROOT = Path(__file__).resolve().parent
PACE = ROOT / 'nba_historial_pace.csv'
PERIODOS = ROOT / 'nba_historial_pace_periodos_validado.csv'
REPORT = ROOT / 'nba_pace_actualizacion_reporte.json'
SCOREBOARD = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard'


def leer(path):
    with path.open(newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def escribir(path, cols, rows):
    with path.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def descubrir(dia):
    req = Request(SCOREBOARD + '?' + urlencode({'dates': dia.strftime('%Y%m%d'), 'limit': 100}),
                  headers={'User-Agent': 'NBA-Lab-Pace-Periodos/2.0'})
    with urlopen(req, timeout=30) as response:
        data = json.load(response)
    if not isinstance(data.get('events'), list):
        raise ValueError('ESPN no devolvió lista de eventos')
    return {str(e['id']) for e in data['events']
            if e.get('id') is not None and ((e.get('status') or {}).get('type') or {}).get('completed') is True}


def ejecutar():
    if not PACE.is_file() or not PERIODOS.is_file():
        raise FileNotFoundError('Faltan los CSV originales')
    cpace, pace = leer(PACE)
    cper, periodos = leer(PERIODOS)
    if not pace or not periodos or not {'partido_id', 'fecha_utc'}.issubset(cpace):
        raise ValueError('Historial base incompleto')
    if not set(cpace).issubset(cper) or not set(CAMPOS).issubset(cper):
        raise ValueError('Esquema incompatible')
    for filas in (pace, periodos):
        ids = [r['partido_id'] for r in filas]
        if len(ids) != len(set(ids)):
            raise ValueError('IDs duplicados')
    bypace = {r['partido_id']: r for r in pace}
    byper = {r['partido_id']: r for r in periodos}
    # La cobertura inicial debe ser consistente; no corregir silenciosamente historiales dañados.
    if set(byper) - set(bypace):
        raise ValueError('Períodos contienen partidos ausentes de Pace')

    ahora = datetime.now(timezone.utc)
    ids = set()
    for n in range(-1, 8):
        ids.update(descubrir((ahora + timedelta(days=-n)).date()))
    pendientes = []
    nuevos_pace = 0
    nuevos_periodos = 0
    # Incluir pendientes históricos Pace sin período para reconciliación.
    candidatos = sorted(ids | (set(bypace) - set(byper)))
    for pid in candidatos:
        if pid in byper:
            continue
        try:
            detalle = consultar(pid)
            if pid in bypace:
                fila = bypace[pid]
            else:
                raw = extraer_partido(detalle, pid)
                if raw is None:
                    raise ValueError('Pace incompleto')
                fila = {k: str(v) for k, v in raw.items()}
                if not set(cpace).issubset(fila):
                    raise ValueError('Columnas Pace faltantes')
            valores = extraer_marcadores(detalle, fila)
            # Publicar ambas tablas solo si el mismo partido tiene Pace y períodos válidos.
            if pid not in bypace:
                bypace[pid] = fila
                nuevos_pace += 1
            byper[pid] = {**fila, **valores}
            nuevos_periodos += 1
        except (ValueError, KeyError, TypeError, RuntimeError, OSError) as exc:
            pendientes.append({'partido_id': pid, 'motivo': f'{type(exc).__name__}: {str(exc)[:180]}'})
    # No publicar CSV si había cobertura parcial preexistente aún sin resolver.
    faltantes = sorted(set(bypace) - set(byper))
    if faltantes:
        estado = 'pendiente_cobertura_preexistente'
        nuevos_pace = nuevos_periodos = 0
    else:
        estado = 'completo' if not pendientes else 'parcial_validado'
        pfinal = sorted(bypace.values(), key=lambda r: (r['fecha_utc'], r['partido_id']))
        qfinal = sorted(byper.values(), key=lambda r: (r['fecha_utc'], r['partido_id']))
        # Validación final de identidad y cobertura antes de tocar archivos.
        if set(byper) != set(bypace):
            raise ValueError('Cobertura inconsistente')
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            p = Path(tmp) / 'pace.csv'
            q = Path(tmp) / 'periodos.csv'
            escribir(p, cpace, pfinal)
            escribir(q, cper, qfinal)
            # Copias de seguridad recuperables por si falla el segundo reemplazo.
            backup_p = Path(tmp) / 'pace.backup'
            backup_q = Path(tmp) / 'periodos.backup'
            backup_p.write_bytes(PACE.read_bytes())
            backup_q.write_bytes(PERIODOS.read_bytes())
            try:
                os.replace(p, PACE)
                os.replace(q, PERIODOS)
            except OSError:
                os.replace(backup_p, PACE)
                os.replace(backup_q, PERIODOS)
                raise
    resumen = {'generado_utc': ahora.isoformat(), 'estado': estado,
               'pace_total': len(bypace), 'periodos_total': len(byper),
               'nuevos_pace': nuevos_pace, 'nuevos_periodos': nuevos_periodos,
               'pendientes': pendientes, 'pendientes_total': len(pendientes),
               'cobertura_preexistente_pendiente': faltantes,
               'fuente': 'ESPN', 'solo_finalizados': True}
    REPORT.write_text(json.dumps(resumen, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(resumen, ensure_ascii=False, indent=2))
    if faltantes:
        raise ValueError('Cobertura histórica previa incompleta; CSV no reemplazados')

if __name__ == '__main__':
    ejecutar()

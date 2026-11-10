"""Consolidación determinista de registros prospectivos entre ejecuciones.

El almacenamiento duradero debe ser aportado por un backend externo; este
módulo solo valida y fusiona archivos sin alterar registros ya emitidos.
"""
import csv
import os
import tempfile
from pathlib import Path
from registro_prospectivo import CAMPOS, _fecha

CLAVE = ('game_id', 'modelo', 'version')

def leer(ruta):
    ruta = Path(ruta)
    if not ruta.exists():
        return {}
    with ruta.open(newline='', encoding='utf-8') as f:
        lector = csv.DictReader(f)
        if lector.fieldnames != list(CAMPOS):
            raise ValueError('Esquema de historial incompatible')
        datos = {}
        for fila in lector:
            if any(fila.get(c) is None or not str(fila[c]).strip() for c in CAMPOS):
                raise ValueError('Fila incompleta en historial')
            clave = tuple(fila[c] for c in CLAVE)
            if clave in datos:
                raise ValueError('Clave duplicada en historial')
            inicio, creado = _fecha(fila['fecha_partido_utc']), _fecha(fila['generado_utc'])
            if creado >= inicio:
                raise ValueError('Predicción creada después del inicio')
            local, visitante = float(fila['puntos_local']), float(fila['puntos_visitante'])
            total, margen = float(fila['total']), float(fila['margen'])
            import math
            if not all(map(math.isfinite, (local, visitante, total, margen))) or min(local, visitante) < 0:
                raise ValueError('Valores inválidos en historial')
            if abs(local + visitante - total) > 1e-6 or abs(local - visitante - margen) > 1e-6:
                raise ValueError('Total/margen incoherentes')
            datos[clave] = fila
        return datos

def fusionar(destino, *fuentes):
    """Fusiona sin reescribir claves previas; conflictos explícitos fallan.

    Escribir a un archivo temporal y reemplazar atómicamente protege ante
    escrituras parciales, pero NO evita carreras entre procesos concurrentes.
    """
    destino = Path(destino)
    datos = leer(destino)
    nuevos = 0
    for fuente in fuentes:
        for clave, fila in leer(fuente).items():
            if clave in datos:
                if datos[clave] != fila:
                    raise ValueError('Conflicto en predicción existente: ' + '/'.join(clave))
            else:
                datos[clave] = fila
                nuevos += 1
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, temporal = tempfile.mkstemp(prefix='.historial_', suffix='.csv', dir=destino.parent)
    try:
        with os.fdopen(fd, 'w', newline='', encoding='utf-8') as f:
            escritor = csv.DictWriter(f, fieldnames=CAMPOS)
            escritor.writeheader()
            for clave in sorted(datos):
                escritor.writerow(datos[clave])
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporal, destino)
    finally:
        if os.path.exists(temporal):
            os.unlink(temporal)
    return {'total': len(datos), 'nuevos': nuevos}

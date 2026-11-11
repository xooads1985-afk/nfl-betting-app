"""Consulta tarjetas NBA experimentales publicadas en GitHub, sin tocar módulos estables."""
import json
import tempfile
from pathlib import Path
from urllib.request import urlopen
from urllib.error import HTTPError, URLError
from nba_lab_lector_tarjetas import leer_tarjeta

BASE_URL = ('https://raw.githubusercontent.com/xooads1985-afk/'
            'nfl-betting-app/nba-lab-pruebas/nba_lab_publicado')


def _descargar_json(url, timeout=12):
    with urlopen(url, timeout=timeout) as respuesta:
        contenido = respuesta.read(2_000_001)
    if len(contenido) > 2_000_000:
        raise ValueError('Archivo remoto demasiado grande')
    return json.loads(contenido.decode('utf-8'))


def obtener_tarjeta_remota(partido_id, ahora_utc=None, base_url=BASE_URL):
    """Retorna tarjeta validada o lanza excepción. No usa datos futuros."""
    pid = str(partido_id)
    if not pid.isdigit():
        raise ValueError('ID inválido')
    indice = _descargar_json(base_url.rstrip('/') + '/indice_tarjetas.json')
    if not any(str(x.get('id')) == pid for x in indice.get('tarjetas', [])):
        raise FileNotFoundError('Partido ausente del índice publicado')
    tarjeta = _descargar_json(base_url.rstrip('/') + '/tarjeta_' + pid + '.json')
    with tempfile.TemporaryDirectory() as d:
        Path(d, 'tarjeta_' + pid + '.json').write_text(
            json.dumps(tarjeta, ensure_ascii=False), encoding='utf-8')
        return leer_tarjeta(d, pid, ahora_utc=ahora_utc)


def obtener_tarjeta_segura(partido_id, ahora_utc=None, base_url=BASE_URL):
    """Interfaz tolerante a fallos para Streamlit: (tarjeta, motivo)."""
    try:
        return obtener_tarjeta_remota(partido_id, ahora_utc, base_url), None
    except (ValueError, TypeError, KeyError, FileNotFoundError, OSError,
            HTTPError, URLError, json.JSONDecodeError) as exc:
        return None, str(exc)

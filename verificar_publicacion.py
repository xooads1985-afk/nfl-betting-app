"""Preflight offline para la publicacion experimental, sin escribir en GitHub."""
from pathlib import Path
import ast
import re

REQUERIDOS = ('descargar_original.py','orquestar_experimental.py','publicar_historial.py',
              'generar_prospectivas.py','proyeccion_prospectiva.py','puente_calendario_real.py',
              'preparar_calendario.py','registro_prospectivo.py','historial_persistente.py',
              'nfl_lab_precision.py')
PROHIBIDOS = ('main.py','modulo_nfl.py','modulo_nba.py')

def verificar(raiz):
    raiz=Path(raiz)
    faltantes=[n for n in REQUERIDOS if not (raiz/n).is_file()]
    if faltantes: raise ValueError('Faltan archivos: '+', '.join(faltantes))
    for n in REQUERIDOS:
        ast.parse((raiz/n).read_text(encoding='utf-8'),filename=n)
    if any((raiz/n).exists() for n in PROHIBIDOS):
        raise ValueError('El paquete incluye un modulo estable')
    workflow=raiz/'.github/workflows/laboratorio-nfl-integral.yml'
    if not workflow.is_file(): raise ValueError('Falta workflow')
    txt=workflow.read_text(encoding='utf-8')
    for token in ('laboratorio-nfl-validacion','historial-nfl-lab','descargar_original.py',
                  'orquestar_experimental.py','publicar_historial.py','git push origin HEAD:historial-nfl-lab'):
        if token not in txt: raise ValueError('Falta etapa o rama: '+token)
    if re.search(r'git\s+push\s+[^\n]*--force',txt):raise ValueError('Push forzado prohibido')
    return {'archivos_python_verificados':len(REQUERIDOS),'workflow':str(workflow.relative_to(raiz)),
            'modulos_estables_incluidos':0}

if __name__=='__main__':
    import json
    print(json.dumps(verificar(Path(__file__).parent),ensure_ascii=False,indent=2))

"""Pruebas aisladas del puente Q1/1H sin red ni escritura en datos reales."""
import ast
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
REPORTE = ROOT / 'nba_prueba_funcional_reporte.json'
resultado = {'pruebas': {}, 'aprobado': False}

def verificar(nombre, condicion, detalle=''):
    resultado['pruebas'][nombre] = {'ok': bool(condicion), 'detalle': detalle}

try:
    import pandas as pd
    import nba_q1_integracion_tarjeta as puente
    import nba_conexion_tarjeta as conexion
    from datetime import datetime, timedelta, timezone
    ahora = datetime.now(timezone.utc)
    futuro = {'id':'prueba-001', 'fecha_utc':(ahora+timedelta(hours=12)).isoformat(), 'local':'Equipo Local', 'visitante':'Equipo Visitante'}
    pasado = dict(futuro, fecha_utc=(ahora-timedelta(hours=2)).isoformat())
    verificar('partido_iniciado_bloqueado', puente.periodos_para_tarjeta(pasado) is None)
    datos = {'periodos': {'q1': {'local':26.,'visitante':24.,'total':50.},'mitad':{'local':55.,'visitante':51.,'total':106.}}}
    with tempfile.TemporaryDirectory() as tmp:
        archivo=Path(tmp)/'historial.csv'
        archivo.write_text('partido_id,fecha_utc\n1,2025-01-01\n',encoding='utf-8')
        with patch.object(puente, 'Path', wraps=Path) as mocked_path:
            # Use an isolated file without changing the actual historical dataset.
            original_is_file = Path.is_file
            with patch.object(Path,'is_file',autospec=True,side_effect=lambda self: True if self.name=='nba_historial_pace_periodos_validado.csv' else original_is_file(self)):
                with patch.object(pd,'read_csv',return_value=pd.DataFrame({'partido_id':['1']})):
                    with patch.object(puente,'proyectar_periodos',return_value=datos) as motor:
                        tabla=puente.periodos_para_tarjeta(futuro)
                        verificar('q1_y_mitad_generados',isinstance(tabla,pd.DataFrame) and list(tabla['Período'])==['Q1','Primera mitad'])
                        verificar('valores_q1',tabla.iloc[0]['Total']==50 and tabla.iloc[0]['Local']==26)
                        verificar('valores_mitad',tabla.iloc[1]['Total']==106 and tabla.iloc[1]['Visitante']==51)
                        verificar('corte_temporal_enviado',motor.call_args.kwargs.get('corte_utc') is not None)
    # Test the connector by replacing the downstream renderer with a stub.
    import types
    fake=types.ModuleType('nba_tarjeta_auto')
    llamadas=[]
    def mostrar_tarjeta_auto(partido,**kwargs):
        llamadas.append((partido,kwargs)); return {'estado':'prueba'}
    fake.mostrar_tarjeta_auto=mostrar_tarjeta_auto
    with patch.dict(sys.modules,{'nba_tarjeta_auto':fake}):
        with patch.object(puente,'periodos_para_tarjeta',return_value=pd.DataFrame([{'Período':'Q1','Local':26,'Visitante':24,'Total':50}])):
            conexion.mostrar_tarjeta_conectada(futuro,escritura_habilitada=False,historial_remoto_habilitado=False)
    verificar('conexion_entrega_periodos',len(llamadas)==1 and isinstance(llamadas[0][1].get('periodos_resumen'),pd.DataFrame))
    verificar('sin_escritura',len(llamadas)==1 and llamadas[0][1].get('escritura_habilitada') is False)
    verificar('sin_historial_remoto',len(llamadas)==1 and llamadas[0][1].get('historial_remoto_habilitado') is False)
    # Verify unchanged full-game engines via import-only and source inspection.
    archivo=ROOT/'nba_conexion_tarjeta.py'
    verificar('conexion_sintaxis',bool(ast.parse(archivo.read_text(encoding='utf-8'))))
except Exception as exc:
    resultado['error']=f'{type(exc).__name__}: {exc}'
resultado['aprobado']=all(x['ok'] for x in resultado['pruebas'].values()) and 'error' not in resultado
REPORTE.write_text(json.dumps(resultado,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(resultado,ensure_ascii=False,indent=2))
sys.exit(0 if resultado['aprobado'] else 1)

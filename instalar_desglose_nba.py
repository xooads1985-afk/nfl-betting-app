from pathlib import Path
import ast
base=Path(__file__).resolve().parent
p=base/'nba_tarjeta_puente.py'
s=p.read_text(encoding='utf-8')
marker='NBA_DIAGNOSTICO_DESGLOSE_V1'
if marker not in s:
    s=s.replace('from pathlib import Path\n','from pathlib import Path\nfrom time import perf_counter\n',1)
    s=s.replace('    registros = consultar(partido[\'id\'])', '''    # NBA_DIAGNOSTICO_DESGLOSE_V1
    _tiempos = {}
    _t = perf_counter()
    registros = consultar(partido['id'])
    _tiempos['Consulta de registros'] = round(perf_counter()-_t, 2)''',1)
    s=s.replace('            tres = cargar_tres(cargador_historial, partido, corte_utc=ahora)', '''            _t = perf_counter()
            try:
                tres = cargar_tres(cargador_historial, partido, corte_utc=ahora)
            finally:
                _tiempos['Historial tres motores'] = round(perf_counter()-_t, 2)''',1)
    s=s.replace('                pace, cobertura = completar_pace(\n                    tres, previo, partido, cargar_detalle, corte_utc=ahora)', '''                _t = perf_counter()
                try:
                    pace, cobertura = completar_pace(
                        tres, previo, partido, cargar_detalle, corte_utc=ahora)
                finally:
                    _tiempos['Pace / detalles ESPN'] = round(perf_counter()-_t, 2)''',1)
    s=s.replace("                calculados['tres'] = calcular_tres(tres, partido)",'''                _t = perf_counter()
                try:
                    calculados['tres'] = calcular_tres(tres, partido)
                finally:
                    _tiempos['Cálculo Base / C / Ensemble'] = round(perf_counter()-_t, 2)''',1)
    s=s.replace("                calculados['pace'] = calcular_pace(pace, partido, ahora=ahora)",'''                _t = perf_counter()
                try:
                    calculados['pace'] = calcular_pace(pace, partido, ahora=ahora)
                finally:
                    _tiempos['Cálculo Pace'] = round(perf_counter()-_t, 2)''',1)
    s=s.replace("'incidencias_fuentes':incidencias}","'incidencias_fuentes':incidencias, 'diagnostico_tiempos':_tiempos}",1)
    ast.parse(s)
    p.write_text(s,encoding='utf-8')
    print('Puente instrumentado')
else:print('Puente ya instrumentado')
p=base/'nba_tarjeta_auto.py';s=p.read_text(encoding='utf-8')
marker='NBA_DIAGNOSTICO_DESGLOSE_V1'
if marker not in s:
    old="        st.caption('Este tiempo incluye el controlador y sus fuentes, no la preparación previa de períodos ESPN.')"
    new="""        st.caption('Este tiempo incluye el controlador y sus fuentes, no la preparación previa de períodos ESPN.')
        # NBA_DIAGNOSTICO_DESGLOSE_V1
        _desglose = resultado.get('diagnostico_tiempos') or {}
        if _desglose:
            for _etapa, _segundos in _desglose.items():
                st.caption(f'{_etapa}: {_segundos:.2f} s')
            if reutilizar:
                st.caption('Desglose de la ejecución original conservada en caché.')
        else:
            st.caption('Desglose no disponible para esta ejecución.')"""
    assert s.count(old)==1,'No se encontró el panel diagnóstico esperado'
    s=s.replace(old,new,1)
    ast.parse(s)
    p.write_text(s,encoding='utf-8')
    print('Panel instrumentado')
else:print('Panel ya instrumentado')

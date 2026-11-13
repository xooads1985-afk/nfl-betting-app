from pathlib import Path
import ast
p=Path(__file__).resolve().parent/'nba_tarjeta_puente.py'
s=p.read_text(encoding='utf-8')
marker='NBA_DIAGNOSTICO_SEGUNDA_CARGA_V1'
if marker in s:
    print('Diagnostico ya instalado')
else:
    old='''                if tres is None:
                    tres = cargar_tres(cargador_historial, partido, corte_utc=ahora)
'''
    new='''                if tres is None:
                    # NBA_DIAGNOSTICO_SEGUNDA_CARGA_V1
                    _t = perf_counter()
                    try:
                        tres = cargar_tres(cargador_historial, partido, corte_utc=ahora)
                    finally:
                        _tiempos['Segunda carga histórica para Pace'] = round(perf_counter()-_t, 2)
'''
    if s.count(old)!=1: raise RuntimeError('No se encontró la segunda carga histórica exacta; no se modificó nada')
    s=s.replace(old,new,1)
    old="    _tiempos = {}\n    _t = perf_counter()\n"
    new="    _tiempos = {}\n    _inicio_puente = perf_counter()\n    _t = perf_counter()\n"
    if s.count(old)!=1: raise RuntimeError('No se encontró el inicio del diagnóstico')
    s=s.replace(old,new,1)
    old="""        return {'estado':'simulacion', 'faltantes':tuple(sorted(faltantes)),
                'nuevos':0, 'registros':registros, 'calculados':calculados,
                'incidencias_fuentes':incidencias, 'diagnostico_tiempos':_tiempos}
"""
    new="""        _tiempos['Total puente'] = round(perf_counter()-_inicio_puente, 2)
        _tiempos['Estado historial tres motores'] = ('disponible' if tres is not None else 'no disponible')
        _tiempos['Estado Pace'] = ('disponible' if pace is not None else 'no disponible')
        _tiempos['Incidencias detectadas'] = len(incidencias)
        return {'estado':'simulacion', 'faltantes':tuple(sorted(faltantes)),
                'nuevos':0, 'registros':registros, 'calculados':calculados,
                'incidencias_fuentes':incidencias, 'diagnostico_tiempos':_tiempos}
"""
    if s.count(old)!=1: raise RuntimeError('No se encontró la devolución de simulación')
    s=s.replace(old,new,1)
    ast.parse(s)
    p.write_text(s,encoding='utf-8')
    print('Diagnostico ampliado instalado')

p=Path(__file__).resolve().parent/'nba_tarjeta_auto.py'
s=p.read_text(encoding='utf-8')
marker='NBA_DIAGNOSTICO_ESTADOS_V1'
if marker not in s:
    old="""            for _etapa, _segundos in _desglose.items():
                st.caption(f'{_etapa}: {_segundos} s')
"""
    if old not in s:
        # Preserve existing display if the implementation has a different formatting.
        print('Vista actual de desglose conservada; estados se mostrarán con el formato actual')
    else:
        new="""            # NBA_DIAGNOSTICO_ESTADOS_V1
            for _etapa, _valor in _desglose.items():
                if isinstance(_valor, (int, float)) and _etapa not in ('Incidencias detectadas',):
                    st.caption(f'{_etapa}: {_valor} s')
                else:
                    st.caption(f'{_etapa}: {_valor}')
"""
        s=s.replace(old,new,1)
        ast.parse(s)
        p.write_text(s,encoding='utf-8')
        print('Vista de estados instalada')

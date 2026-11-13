from pathlib import Path
import ast
p=Path(__file__).resolve().parent/'nba_tarjeta_auto.py'
s=p.read_text(encoding='utf-8')
marker='NBA_DIAGNOSTICO_TIEMPOS_V1'
if marker in s:
    print('Diagnostico ya instalado')
else:
    old="""    if reutilizar:
        resultado = anterior['resultado']
    else:
        try:
"""
    new="""    # NBA_DIAGNOSTICO_TIEMPOS_V1
    from time import perf_counter
    _inicio_motores = perf_counter()
    if reutilizar:
        resultado = anterior['resultado']
    else:
        try:
"""
    assert s.count(old)==1, 'No se encontró el bloque de ejecución esperado'
    s=s.replace(old,new,1)
    old="""    if not resultado.get('ok'):
        st.warning('Automatización no disponible: ' + resultado.get('mensaje', 'Error desconocido'))
"""
    new="""    _segundos_motores = perf_counter() - _inicio_motores
    with st.expander('⏱️ Diagnóstico de velocidad · tarjeta NBA'):
        st.caption(f\"Motores y fuentes: {_segundos_motores:.2f} s · {'caché de tarjeta' if reutilizar else 'cálculo/consulta'}\")
        st.caption('Este tiempo incluye el controlador y sus fuentes, no la preparación previa de períodos ESPN.')
    if not resultado.get('ok'):
        st.warning('Automatización no disponible: ' + resultado.get('mensaje', 'Error desconocido'))
"""
    assert s.count(old)==1, 'No se encontró el bloque de visualización esperado'
    s=s.replace(old,new,1)
    ast.parse(s)
    p.write_text(s,encoding='utf-8')
    print('Diagnóstico instalado y sintaxis verificada')

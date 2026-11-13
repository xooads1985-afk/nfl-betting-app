"""Integración acotada: reutilizar Q1, primera mitad y Edge del resumen existente.
Ejecutar en la raíz de la rama de pruebas. Crea copias .bak antes de escribir.
"""
from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parent

def sustituir(texto, anterior, nuevo, etiqueta):
    n = texto.count(anterior)
    if n != 1:
        raise RuntimeError(f'{etiqueta}: se esperaba una coincidencia, encontradas {n}; no se modifica nada')
    return texto.replace(anterior, nuevo, 1)


def aplicar():
    resumen = ROOT / 'resumen_inteligente_nba.py'
    auto = ROOT / 'nba_tarjeta_auto.py'
    if not resumen.exists() or not auto.exists():
        raise RuntimeError('Coloca este script en la raíz del repositorio, junto a los dos archivos')
    s = resumen.read_text(encoding='utf-8')
    a = auto.read_text(encoding='utf-8')
    if 'NBA_TARJETA_INTEGRADA_Q1_MITAD_V1' in s:
        print('La integración ya está instalada; sin cambios')
        return

    inicio = "    # Panel prospectivo aislado: solo lectura, sin alterar estimaciones estables.\n"
    fin = "    _nba_panel_disponibilidad_jugadores([local, visita])\n"
    x = s.find(inicio, s.index('def _tarjeta_unica_partido('))
    y = s.find(fin, x)
    if x < 0 or y < 0 or y <= x:
        raise RuntimeError('No se localizó el bloque de tarjeta original')
    # Mover el bloque de conexión, conservando sus flags y control de errores.
    bloque = s[x:y]
    s = s[:x] + s[y:]

    # El total anterior se mantiene disponible en el análisis original, pero no se
    # presenta como una segunda predicción principal cuando se activa la tarjeta.
    viejo = "    st.markdown('**🏆 Partido completo · puntos esperados**')\n"
    nuevo = "    if not bool(st.secrets.get('NBA_TARJETA_AUTOMATICA', False)):\n        st.markdown('**🏆 Partido completo · puntos esperados**')\n"
    s = sustituir(s, viejo, nuevo, 'encabezado total antiguo')
    viejo = "    if len(proy) == 2:\n        st.metric('Media ataque/defensa (marcadores finales históricos)', f\"{sum(proy.values()):.1f} pts\")\n        st.caption(f\"{visita}: {proy[visita]:.1f} · {local}: {proy[local]:.1f} · diferencia: {proy[local]-proy[visita]:+.1f} local\")\n    else:\n        st.info('Faltan al menos 3 partidos anteriores por equipo para estimar el marcador completo.')\n"
    nuevo = "    if not bool(st.secrets.get('NBA_TARJETA_AUTOMATICA', False)):\n" + ''.join('    '+line if line.strip() else line for line in viejo.splitlines(keepends=True))
    s = sustituir(s, viejo, nuevo, 'métrica duplicada')

    ancla = '    tabla_periodos = pd.DataFrame(filas)\n'
    # No reimportar Streamlit ni recalcular Q1/mitad. Se pasan las filas originales.
    inyeccion = '''    # NBA_TARJETA_INTEGRADA_Q1_MITAD_V1: reutiliza cálculos existentes, sin recálculo.
    if bool(st.secrets.get('NBA_TARJETA_AUTOMATICA', False)):
        try:
            from nba_conexion_tarjeta import mostrar_tarjeta_conectada
            mostrar_tarjeta_conectada(
                partido, partidos=partidos,
                escritura_habilitada=bool(st.secrets.get('NBA_TARJETA_ESCRITURA', False)),
                historial_remoto_habilitado=bool(st.secrets.get('NBA_PACE_REMOTO', False)),
                periodos_resumen=tabla_periodos,
            )
        except Exception as exc:
            with st.expander('Tarjeta automática · diagnóstico'):
                st.warning(f'{type(exc).__name__}: {exc}')
'''
    s = sustituir(s, ancla, ancla + inyeccion, 'ancla de períodos')
    # Retirar la tarjeta original de la parte superior. Su llamada se encuentra
    # ahora justo después de tabla_periodos. La lógica antigua queda en main.
    if 'mostrar_tarjeta_conectada' not in bloque:
        raise RuntimeError('La conexión esperada no estaba en el bloque original')

    # Con tarjeta activada, la tabla de períodos antigua no se repite abajo.
    viejo = "    st.dataframe(tabla_periodos[['Período', 'Visitante', 'Local', 'Total']],\n                 hide_index=True, use_container_width=True)\n"
    nuevo = "    if not bool(st.secrets.get('NBA_TARJETA_AUTOMATICA', False)):\n" + ''.join('    '+line for line in viejo.splitlines(keepends=True))
    s = sustituir(s, viejo, nuevo, 'tabla de períodos duplicada')

    # Adaptador: acepta períodos sin alterar consultas ni cálculos.
    conexion = ROOT / 'nba_conexion_tarjeta.py'
    c = conexion.read_text(encoding='utf-8')
    c = sustituir(c,
        '                              historial_remoto_habilitado=False):',
        '                              historial_remoto_habilitado=False, periodos_resumen=None):',
        'firma conexión')
    c = sustituir(c,
        '                               historial_remoto_habilitado=historial_remoto_habilitado)',
        '                               historial_remoto_habilitado=historial_remoto_habilitado,\n                               periodos_resumen=periodos_resumen)',
        'paso de períodos conexión')

    # Tarjeta: sólo cambia presentación, no el cálculo de los motores.
    a = sustituir(a,
        'def _mostrar_previa(st, partido, resultado):',
        'def _mostrar_previa(st, partido, resultado, periodos_resumen=None):',
        'firma vista previa')
    a = sustituir(a,
        "        st.caption('Margen: pendiente de validación. El total puede diferir de la suma de equipos.')",
        """        if p.get('local') is not None and p.get('visitante') is not None:
            diferencia = p['local'] - p['visitante']
            favorito = datos['local'] if diferencia > 0 else datos['visitante'] if diferencia < 0 else 'Empate proyectado'
            st.caption(f'Diferencia matemática: {abs(diferencia):.1f} pts · {favorito}. No es un margen validado.')
        st.caption('El total puede diferir de la suma de equipos porque proviene de otro motor.')""",
        'diferencia descriptiva')
    viejo = """        st.markdown('**Proyecciones por período**')
        st.markdown(_tabla_periodos(datos['periodos'], datos['local'], datos['visitante']),
                    unsafe_allow_html=True)
        st.caption('Cuartos y mitades: N/D por falta de validación.')"""
    nuevo = """        _mostrar_periodos_resumen(st, periodos_resumen)
"""
    a = sustituir(a, viejo, nuevo.rstrip(), 'periodos en vista previa')
    a = sustituir(a,
        '                         intervalo_minutos=10, historial_remoto_habilitado=False):',
        '                         intervalo_minutos=10, historial_remoto_habilitado=False,\n                         periodos_resumen=None):',
        'firma tarjeta automática')
    a = sustituir(a, '_mostrar_previa(st, partido, resultado)',
                   '_mostrar_previa(st, partido, resultado, periodos_resumen=periodos_resumen)',
                   'paso períodos vista previa')

    helper = '''

def _mostrar_periodos_resumen(st, tabla):
    """Q1 y mitad del resumen original. No hace consultas ni predicciones."""
    st.markdown('**Primer cuarto y primera mitad · Resumen Inteligente NBA**')
    if tabla is None or not hasattr(tabla, 'columns'):
        st.caption('Períodos del resumen no disponibles en esta vista.')
        return
    columnas = ['Período', 'Visitante', 'Local', 'Total', 'Referencia total', 'Edge descriptivo']
    if not set(columnas).issubset(tabla.columns):
        st.caption('Faltan columnas del resumen para mostrar los períodos.')
        return
    datos = tabla.loc[tabla['Período'].isin(['Q1', 'Primera mitad']), columnas].copy()
    if datos.empty:
        st.caption('Primer cuarto y primera mitad sin datos históricos suficientes.')
        return
    datos = datos.rename(columns={'Referencia total': 'Referencia', 'Edge descriptivo': 'Edge'})
    st.dataframe(datos, hide_index=True, use_container_width=True)
    st.caption('Edge = proyección − referencia histórica; no representa probabilidad.')
'''
    a += helper
    # La ruta de registros completos usa el mismo resumen, sin cambiar su lectura.
    a = sustituir(a,
        '    mostrar_tarjeta(partido, referencias=referencias, pace=pace, partidos=partidos)\n',
        '    mostrar_tarjeta(partido, referencias=referencias, pace=pace, partidos=partidos)\n'
        '    if periodos_resumen is not None:\n'
        '        _mostrar_periodos_resumen(st, periodos_resumen)\n',
        'períodos en ruta completa')

    archivos = [(resumen,s),(auto,a),(conexion,c)]
    for ruta, contenido in archivos:
        ast.parse(contenido, filename=ruta.name)
    for ruta, contenido in archivos:
        ruta.with_suffix(ruta.suffix + '.bak').write_text(ruta.read_text(encoding='utf-8'), encoding='utf-8')
        ruta.write_text(contenido, encoding='utf-8')
    print('Integración aplicada y sintaxis verificada en:', ', '.join(p.name for p,_ in archivos))

if __name__ == '__main__':
    aplicar()

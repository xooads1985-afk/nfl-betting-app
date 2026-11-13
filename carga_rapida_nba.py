"""Optimización de lectura de tarjeta NBA: evita ESPN histórico durante el render.
Ejecutar en rama pruebas-integracion-nba-4-motores.
"""
from pathlib import Path
import ast

BASE=Path(__file__).resolve().parent
def reemplazar(s, viejo, nuevo, nombre):
    n=s.count(viejo)
    if n != 1:
        raise RuntimeError(f"{nombre}: se esperaban 1 coincidencia; encontradas {n}")
    return s.replace(viejo,nuevo,1)

def main():
    puente=BASE/'nba_tarjeta_puente.py'
    resumen=BASE/'resumen_inteligente_nba.py'
    p=puente.read_text(encoding='utf-8')
    r=resumen.read_text(encoding='utf-8')
    marca='NBA_CARGA_RAPIDA_SIN_ESPN_HISTORICO_V1'
    if marca in p and marca in r:
        print('Integración ya aplicada')
        return
    if marca in p or marca in r:
        raise RuntimeError('Integración parcial; revisar antes de repetir')
    inicio=p.index("    if any(modelo == 'Pace + Eficiencia' for _,modelo in faltantes):")
    fin=p.index("    if modo_prueba:", inicio)
    nuevo_p="""    # NBA_CARGA_RAPIDA_SIN_ESPN_HISTORICO_V1
    # Durante la presentación solo usar historial Pace local ya validado.
    # La actualización de ESPN corresponde al proceso de actualización diaria.
    if any(modelo == 'Pace + Eficiencia' for _, modelo in faltantes):
        try:
            pace = cargar_pace(Path(ruta_pace), partido,
                              solicitar_remoto=None, corte_utc=ahora)
        except (ValueError, RuntimeError, OSError, TimeoutError, ImportError) as exc:
            incidencias['pace'] = ('Pendiente de actualización histórica externa: '
                                   + f'{type(exc).__name__}: {exc}')
"""
    p=p[:inicio]+nuevo_p+p[fin:]
    viejo="""    for ident in juegos:
        if ident not in cache:
            try:
                detalle = cargar_detalle(ident)
                cache[ident] = _puntos_periodos(detalle)
                cache_detalles[ident] = detalle
            except Exception:
                cache[ident] = None
"""
    nuevo="""    # NBA_CARGA_RAPIDA_SIN_ESPN_HISTORICO_V1
    # Reutilizar únicamente boxscores que ya estén en la sesión.
    # No descargar 20 partidos históricos mientras se construye la tarjeta.
    # Si falta cobertura, Q1/primera mitad se muestran como N/D.
    for ident in juegos:
        if ident not in cache and ident in cache_detalles:
            try:
                cache[ident] = _puntos_periodos(cache_detalles[ident])
            except (ValueError, TypeError, KeyError):
                cache[ident] = None
"""
    r=reemplazar(r,viejo,nuevo,'detalle histórico tarjeta')
    for nombre,contenido in [('puente',p),('resumen',r)]:
        ast.parse(contenido,filename=nombre)
    # Escribir solo después de validar ambos.
    puente.write_text(p,encoding='utf-8')
    resumen.write_text(r,encoding='utf-8')
    print('Integración aplicada. Sin consultas ESPN históricas en la tarjeta.')
if __name__=='__main__':
    main()

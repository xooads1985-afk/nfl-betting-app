"""Aplicar en copia del repositorio experimental; crea respaldo del archivo modificado."""
from pathlib import Path
import ast
import shutil

raiz = Path(__file__).resolve().parent
objetivo = raiz / 'nba_tarjeta_auto.py'
if not objetivo.exists():
    raise SystemExit('Falta nba_tarjeta_auto.py: colocar este paquete en la raiz de la rama experimental.')
original = objetivo.read_text(encoding='utf-8')
antes = '''            # NBA_HISTORIAL_MENSUAL_CACHE_V1
            from nba_historial_bloques import cargar_por_bloques
            def _historial_mensual(desde, hasta):
                return cargar_por_bloques(cargador_historial, desde, hasta)
            dependencias = adaptadores_reales(
                cargador_historial=_historial_mensual
            )'''
despues = '''            # NBA_SNAPSHOT_VERIFICADO_V1: misma tarjeta, sin alterar motores.
            from nba_historial_bloques import cargar_por_bloques
            from nba_historial_snapshot_validado import cargar_snapshot
            def _historial_mensual(desde, hasta):
                try:
                    return cargar_snapshot(desde, hasta)
                except (ValueError, KeyError, OSError, TypeError) as error_snapshot:
                    # Si el snapshot no cubre la fecha, usar el cargador anterior.
                    if cargador_historial is None:
                        raise ValueError(
                            'Snapshot no disponible y no hay cargador histórico: '
                            + str(error_snapshot)
                        ) from error_snapshot
                    return cargar_por_bloques(cargador_historial, desde, hasta)
            dependencias = adaptadores_reales(
                cargador_historial=_historial_mensual
            )'''
if despues in original:
    print('Corrección ya aplicada; no se realizaron cambios.')
elif original.count(antes) != 1:
    raise SystemExit('No coincide el bloque esperado; no se modificó ningún archivo.')
else:
    actualizado = original.replace(antes, despues)
    ast.parse(actualizado)
    respaldo = objetivo.with_suffix('.py.respaldo_pre_snapshot')
    if respaldo.exists():
        raise SystemExit('Ya existe un respaldo; no se sobrescribió.')
    shutil.copy2(objetivo, respaldo)
    objetivo.write_text(actualizado, encoding='utf-8')
    print('Corrección aplicada; respaldo:', respaldo.name)

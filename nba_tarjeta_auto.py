
"""Tarjeta automática NBA: cuatro motores y resultado compartido.

NBA_TARJETA_COMPARTIDA_V1
No escribe en Supabase por defecto.
Conserva la validación previa al inicio del encuentro.
"""

from datetime import datetime, timezone, timedelta
from time import perf_counter

CLAVE_COMPARTIDA = "nba_proyeccion_consolidada_v1"


def _numero(valor):
    """Convierte únicamente valores numéricos válidos."""
    import math

    try:
        numero = float(valor)
        return numero if math.isfinite(numero) else None
    except (TypeError, ValueError):
        return None


def _publicar_resultado(st, partido, datos, tabla=None):
    """Comparte la proyección sin ejecutar motores adicionales."""

    principal = datos["principal"]
    seleccion = datos["seleccion_objetivos"]

    # NBA_EDGE_EQUIPOS_V2
    referencia_total = None
    referencia_local = None
    referencia_visitante = None

    if tabla is not None and hasattr(tabla, "columns"):
        requeridas = {"Período", "Referencia total"}

        if requeridas.issubset(tabla.columns):
            filas = tabla.loc[
                tabla["Período"].eq("Final reglamentario")
            ]

            if not filas.empty:
                fila = filas.iloc[0]
                referencia_total = _numero(fila["Referencia total"])
                referencia_local = _numero(fila.get("Referencia local"))
                referencia_visitante = _numero(fila.get("Referencia visitante"))

    total = _numero(principal.get("total"))

    compartido = {
        "partido_id": str(partido["id"]),
        "fecha_utc": str(partido["fecha_utc"]),
        "local": datos["local"],
        "visitante": datos["visitante"],
        "puntos_local": _numero(principal.get("local")),
        "puntos_visitante": _numero(
            principal.get("visitante")
        ),
        "total": total,
        "referencia_total": referencia_total,
        "referencia_local": referencia_local,
        "referencia_visitante": referencia_visitante,
        "edge_local": (
            _numero(principal.get("local")) - referencia_local
            if _numero(principal.get("local")) is not None and referencia_local is not None
            else None
        ),
        "edge_visitante": (
            _numero(principal.get("visitante")) - referencia_visitante
            if _numero(principal.get("visitante")) is not None and referencia_visitante is not None
            else None
        ),
        "edge_total": (
            total - referencia_total
            if total is not None
            and referencia_total is not None
            else None
        ),
        "motor_equipos": (
            seleccion.get("equipo") or {}
        ).get("modelo"),
        "motor_total": (
            seleccion.get("total") or {}
        ).get("modelo"),
        "modelos": datos["modelos"],
        "seleccion_objetivos": seleccion,
    }

    st.session_state[CLAVE_COMPARTIDA] = compartido

    return compartido


def obtener_resultado_compartido(partido):
    """Devuelve datos solo si corresponden al partido solicitado."""
    import streamlit as st

    datos = st.session_state.get(CLAVE_COMPARTIDA)

    if not isinstance(datos, dict):
        return None

    if str(datos.get("partido_id")) != str(partido.get("id")):
        return None

    if str(datos.get("fecha_utc")) != str(
        partido.get("fecha_utc")
    ):
        return None

    return datos


def _mostrar_edge(st, compartido):
    """Edge por equipo y total, sin nuevas consultas."""
    import pandas as pd
    st.markdown("**📐 Proyección, referencia y Edge**")
    filas = []
    for nombre, proy, ref, edge, motor in (
        (compartido["visitante"], compartido.get("puntos_visitante"), compartido.get("referencia_visitante"), compartido.get("edge_visitante"), compartido.get("motor_equipos")),
        (compartido["local"], compartido.get("puntos_local"), compartido.get("referencia_local"), compartido.get("edge_local"), compartido.get("motor_equipos")),
        ("Total del partido", compartido.get("total"), compartido.get("referencia_total"), compartido.get("edge_total"), compartido.get("motor_total")),
    ):
        filas.append({
            "Estadística": nombre,
            "Motor": motor or "Sin validar",
            "Proyección": round(proy, 1) if proy is not None else None,
            "Referencia": round(ref, 1) if ref is not None else None,
            "Edge": round(edge, 1) if edge is not None else None,
        })
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)
    st.caption("Edge = proyección seleccionada − referencia histórica. No representa probabilidad.")

    # NBA_AUDITORIA_SOLO_LECTURA_V1
    with st.expander("🧾 Auditoría consolidada · solo lectura"):
        seleccion = compartido.get("seleccion_objetivos") or {}
        def validacion(objetivo):
            fila = seleccion.get(objetivo) or {}
            return {
                "motor": fila.get("modelo"),
                "MAE": fila.get("mae"),
                "muestra": fila.get("muestra"),
                "sesgo": fila.get("sesgo"),
            }
        registro = {
            "partido_id": compartido.get("partido_id"),
            "inicio_utc": compartido.get("fecha_utc"),
            "estado": "vista de auditoría, no guardada",
            "equipos": {
                "local": compartido.get("local"),
                "visitante": compartido.get("visitante"),
            },
            "seleccion": {
                "puntos_por_equipo": validacion("equipo"),
                "total": validacion("total"),
            },
            "proyecciones": {
                "local": compartido.get("puntos_local"),
                "visitante": compartido.get("puntos_visitante"),
                "total": compartido.get("total"),
            },
            "referencias": {
                "local": compartido.get("referencia_local"),
                "visitante": compartido.get("referencia_visitante"),
                "total": compartido.get("referencia_total"),
            },
            "edge": {
                "local": compartido.get("edge_local"),
                "visitante": compartido.get("edge_visitante"),
                "total": compartido.get("edge_total"),
            },
            "cuatro_motores": compartido.get("modelos"),
        }
        st.json(registro, expanded=False)
        # NBA_PREGUARDADO_SEGURO_V1
        from nba_registro_consolidado import construir_registro
        try:
            preparado = construir_registro(registro)
            st.success("Registro validado · sin guardar")
            st.caption("Clave única: " + preparado["clave_unica"])
            st.caption("SHA-256: " + preparado["huella_sha256"])
        except (ValueError, TypeError, KeyError) as exc:
            st.warning("Registro aún no apto para guardar: " + str(exc))
        st.caption("No escribe ni modifica registros en Supabase.")

        # NBA_DIAGNOSTICO_SUPABASE_SOLO_GET_V1
        with st.expander("🔍 Supabase · diagnóstico de solo lectura"):
            from nba_consulta_consolidada import comprobar_registro
            clave_registro = "nba-consolidado-v1:" + str(compartido["partido_id"])
            url_sb = str(st.secrets.get("SUPABASE_URL", ""))
            clave_sb = str(st.secrets.get("SUPABASE_SECRET_KEY", ""))
            if not url_sb or not clave_sb:
                st.warning("Falta la conexión existente de Supabase.")
            else:
                resultado_sb = comprobar_registro(
                    clave_registro, url=url_sb, clave=clave_sb
                )
                st.write("Estado de consulta:", resultado_sb["estado"])
                if resultado_sb["estado"] == "registro_existente":
                    st.caption("Clave: " + str(resultado_sb.get("clave_unica", "")))
                    st.caption("SHA-256: " + str(resultado_sb.get("huella_sha256", "")))
                elif resultado_sb["estado"] == "tabla_no_disponible":
                    st.info("La tabla consolidada aún no está disponible.")
                elif resultado_sb["estado"] == "sin_registro":
                    st.info("La tabla responde, pero este partido aún no tiene registro.")
                else:
                    st.caption("No se han modificado datos.")
            st.caption("Consulta GET exclusivamente; no guarda ni actualiza.")

def _mostrar_previa(
    st,
    partido,
    resultado,
    periodos_resumen=None,
):
    from nba_tarjeta_vista_previa import preparar_vista_previa
    from nba_prediccion_tarjeta import _cabecera_compacta

    datos = preparar_vista_previa(partido, resultado)

    principal = datos["principal"]
    seleccion = datos["seleccion_objetivos"]

    compartido = _publicar_resultado(
        st,
        partido,
        datos,
        periodos_resumen,
    )

    with st.container(border=True):
        st.markdown("### 🏀 Proyección Inteligente NBA")
        st.caption(
            "Cuatro motores · resultado consolidado · "
            "vista previa anterior al inicio"
        )

        st.markdown(
            _cabecera_compacta(
                datos["visitante"],
                datos["local"],
                principal,
                datos["favorito"],
            ),
            unsafe_allow_html=True,
        )

        for etiqueta, clave in (
            ("Puntos por equipo", "equipo"),
            ("Total del partido", "total"),
        ):
            motor = seleccion.get(clave)

            if motor:
                st.caption(
                    f"{etiqueta}: {motor['modelo']} · "
                    f"MAE {motor['mae']:.3f} · "
                    f"n={motor['muestra']}"
                )
            else:
                st.caption(
                    f"{etiqueta}: sin validación suficiente"
                )

        local = compartido["puntos_local"]
        visitante = compartido["puntos_visitante"]

        if local is not None and visitante is not None:
            diferencia = local - visitante

            superior = (
                datos["local"] if diferencia > 0
                else datos["visitante"] if diferencia < 0
                else "Equilibrio matemático"
            )

            st.caption(
                f"Diferencia: {abs(diferencia):.1f} pts · "
                f"{superior}. Margen no validado."
            )

        st.caption(
            "El total puede diferir de la suma de equipos "
            "porque procede de un motor distinto."
        )

        _mostrar_edge(st, compartido)

        _periodos_compactos(
            st,
            periodos_resumen,
            datos["visitante"],
            datos["local"],
            principal,
        )

        with st.expander("🔎 Auditoría · cuatro motores"):
            st.dataframe(
                datos["modelos"],
                hide_index=True,
                use_container_width=True,
            )

            st.caption(
                "Predicciones calculadas sin guardar: "
                f"{datos['provisionales']}"
            )

    return datos


def mostrar_tarjeta_auto(
    partido,
    referencias=None,
    pace=None,
    partidos=None,
    *,
    cargador_historial=None,
    escritura_habilitada=False,
    intervalo_minutos=30,
    historial_remoto_habilitado=False,
    periodos_resumen=None,
):
    import streamlit as st

    from nba_prediccion_tarjeta import mostrar_tarjeta
    from nba_tarjeta_interfaz import (
        obtener_tarjeta,
        adaptadores_reales,
    )
    from nba_validacion_calendario import (
        validar_partido_calendario,
    )

    # Impedir que una tarjeta anterior se use en otro partido.
    st.session_state.pop(CLAVE_COMPARTIDA, None)

    try:
        validar_partido_calendario(partido, partidos)
    except (ValueError, TypeError, KeyError) as exc:
        st.warning(
            f"No se puede verificar el encuentro: {exc}"
        )
        return {
            "ok": False,
            "estado": "identidad_invalida",
            "mensaje": str(exc),
        }

    clave = (
        "nba_auto_v3",
        str(partido.get("id")),
        str(partido.get("fecha_utc")),
        bool(escritura_habilitada),
    )

    ahora = datetime.now(timezone.utc)

    cache = st.session_state.setdefault(
        "nba_auto_intentos_por_partido_v3",
        {},
    )

    anterior = cache.get(clave)

    reutilizar = (
        isinstance(anterior, dict)
        and isinstance(anterior.get("hora"), datetime)
        and timedelta(0)
        <= ahora - anterior["hora"]
        < timedelta(minutes=intervalo_minutos)
        and anterior.get("resultado", {}).get("ok") is True
        and anterior["resultado"].get("estado")
        in ("completo", "simulacion")
    )

    inicio_motores = perf_counter()

    if reutilizar:
        resultado = anterior["resultado"]
    else:
        try:
            if historial_remoto_habilitado:
                raise ValueError(
                    "Fuente Pace remota no instalada: "
                    "desactive NBA_PACE_REMOTO"
                )

            dependencias = adaptadores_reales(
                cargador_historial=cargador_historial
            )

            resultado = obtener_tarjeta(
                partido,
                escritura_habilitada=escritura_habilitada,
                solicitar_remoto=None,
                **dependencias,
            )

        except Exception as exc:
            resultado = {
                "ok": False,
                "estado": "error",
                "mensaje": (
                    f"{type(exc).__name__}: {exc}"
                ),
            }

        if (
            resultado.get("ok")
            and resultado.get("estado")
            in ("completo", "simulacion")
        ):
            cache[clave] = {
                "hora": ahora,
                "resultado": resultado,
            }
        else:
            cache.pop(clave, None)

    segundos_motores = perf_counter() - inicio_motores

    with st.expander(
        "⏱️ Diagnóstico de velocidad · tarjeta NBA"
    ):
        st.caption(
            f"Motores y fuentes: {segundos_motores:.2f} s · "
            f"{'caché de tarjeta' if reutilizar else 'cálculo/consulta'}"
        )

        st.caption(
            "No incluye la preparación previa "
            "de períodos ESPN."
        )

        desglose = (
            resultado.get("diagnostico_tiempos") or {}
        )

        if desglose:
            for etapa, valor in desglose.items():
                if (
                    isinstance(valor, (int, float))
                    and not isinstance(valor, bool)
                ):
                    st.caption(
                        f"{etapa}: {valor:.2f} s"
                    )
                else:
                    st.caption(
                        f"{etapa}: {valor}"
                    )

            if reutilizar:
                st.caption(
                    "Desglose original conservado en caché."
                )
        else:
            st.caption(
                "Desglose no disponible."
            )

    if not resultado.get("ok"):
        st.warning(
            "Automatización no disponible: "
            + resultado.get(
                "mensaje",
                "Error desconocido",
            )
        )
        return resultado

    if resultado.get("estado") == "simulacion":
        try:
            _mostrar_previa(
                st,
                partido,
                resultado,
                periodos_resumen=periodos_resumen,
            )
            return resultado

        except (ValueError, KeyError, TypeError) as exc:
            st.info(
                "Vista previa pendiente: " + str(exc)
            )

            incidencias = (
                resultado.get("incidencias_fuentes") or {}
            )

            if incidencias:
                with st.expander(
                    "Diagnóstico de motores"
                ):
                    for nombre, detalle in sorted(
                        incidencias.items()
                    ):
                        st.caption(
                            f"{nombre}: {detalle}"
                        )

            return resultado

    if resultado.get("estado") == "incompleto":
        st.info(
            "Registros incompletos; no se presentan "
            "proyecciones sin verificar."
        )
        return resultado

    if (
        resultado.get("estado") == "iniciado"
        and resultado.get("faltantes")
    ):
        st.info(
            "Partido iniciado: no se generan "
            "predicciones retrospectivas."
        )
        return resultado

    # NBA_GUARDADOS_COMPARTIDOS_V1
    datos_guardados = mostrar_tarjeta(
        partido,
        referencias=referencias,
        pace=pace,
        partidos=partidos,
    )
    if isinstance(datos_guardados, dict):
        compartido = _publicar_resultado(
            st, partido, datos_guardados, periodos_resumen
        )
        _mostrar_edge(st, compartido)

    if periodos_resumen is not None:
        _mostrar_periodos_resumen(
            st,
            periodos_resumen,
        )

    return resultado


def _mostrar_periodos_resumen(st, tabla):
    """Muestra períodos existentes sin recalcularlos."""

    st.markdown(
        "**Primer cuarto y primera mitad · "
        "Resumen Inteligente NBA**"
    )

    if tabla is None or not hasattr(tabla, "columns"):
        st.caption("Períodos no disponibles.")
        return

    columnas = [
        "Período",
        "Visitante",
        "Local",
        "Total",
        "Referencia total",
        "Edge descriptivo",
    ]

    if not set(columnas).issubset(tabla.columns):
        st.caption(
            "Faltan columnas históricas para los períodos."
        )
        return

    datos = tabla.loc[
        tabla["Período"].isin(
            ["Q1", "Primera mitad"]
        ),
        columnas,
    ].copy()

    if datos.empty:
        st.caption(
            "Sin antecedentes suficientes por período."
        )
        return

    st.dataframe(
        datos[
            ["Período", "Visitante", "Local", "Total"]
        ],
        hide_index=True,
        use_container_width=True,
    )

    st.markdown("**Referencia histórica y Edge**")

    st.dataframe(
        datos[
            [
                "Período",
                "Referencia total",
                "Edge descriptivo",
            ]
        ],
        hide_index=True,
        use_container_width=True,
    )

    st.caption(
        "Edge descriptivo de los períodos históricos; "
        "no corresponde al motor del total del partido."
    )


def _periodos_compactos(
    st,
    tabla,
    visitante,
    local,
    principal,
):
    import pandas as pd

    if tabla is None or not hasattr(tabla, "columns"):
        st.caption(
            "Períodos pendientes de datos históricos."
        )
        return

    campos = {
        "Período",
        "Visitante",
        "Local",
        "Total",
    }

    if not campos.issubset(tabla.columns):
        st.caption(
            "Períodos pendientes de datos históricos."
        )
        return

    filas = []

    for clave, nombre in (
        ("Q1", "1.er cuarto"),
        ("Primera mitad", "1.ª mitad"),
    ):
        encontrados = tabla.loc[
            tabla["Período"].eq(clave)
        ]

        if not encontrados.empty:
            fila = encontrados.iloc[0]

            filas.append({
                "Período": nombre,
                visitante: fila["Visitante"],
                local: fila["Local"],
                "Ambos": fila["Total"],
            })

    filas.append({
        "Período": "Partido",
        visitante: principal.get("visitante"),
        local: principal.get("local"),
        "Ambos": principal.get("total"),
    })

    st.dataframe(
        pd.DataFrame(filas),
        hide_index=True,
        use_container_width=True,
    )

    if {
        "Referencia total",
        "Edge descriptivo",
    }.issubset(tabla.columns):
        with st.expander(
            "Referencia y Edge por períodos"
        ):
            st.dataframe(
                tabla.loc[
                    tabla["Período"].isin(
                        ["Q1", "Primera mitad"]
                    ),
                    [
                        "Período",
                        "Referencia total",
                        "Edge descriptivo",
                    ],
                ],
                hide_index=True,
                use_container_width=True,
            )

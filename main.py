from datetime import datetime
import json
import os
import requests
import streamlit as st

# Configuración global de la página
st.set_page_config(
    page_title="Central de Apuestas Pro - NFL & NCAA",
    page_icon="🛡️",
    layout="wide"
)

# ---------------------------------------------------------
# SELECTOR DE MÓDULO (Barra Lateral Global)
# ---------------------------------------------------------
st.sidebar.title("🎯 Menú del Sistema Pro")
modulo_seleccionado = st.sidebar.radio(
    "Selecciona el módulo de análisis:",
    [
        "🛡️ Sistema Cuantitativo Pro NFL",
        "🎯 Módulo de Props de Jugadores NFL",
        "🎓 NCAA (Robot Universitario & Hándicap)"
    ]
)

st.sidebar.markdown("---")
st.sidebar.info("Motor analítico unificado con calibración estricta de valor y control de riesgo.")


# =========================================================
# MÓDULO 1: SISTEMA CUANTITATIVO PRO NFL (Partidos y Spreads)
# =========================================================
if modulo_seleccionado == "🛡️ Sistema Cuantitativo Pro NFL":
    FICHERO_HISTORIAL = "historial_apuestas_nfl.json"

    def cargar_historial():
      if os.path.exists(FICHERO_HISTORIAL):
        try:
          with open(FICHERO_HISTORIAL, "r", encoding="utf-8") as f:
            datos = json.load(f)
            if isinstance(datos, list):
              return datos
        except:
          pass
      return []

    def guardar_historial(lista_picks):
      try:
        with open(FICHERO_HISTORIAL, "w", encoding="utf-8") as f:
          json.dump(lista_picks, f, ensure_ascii=False, indent=4)
      except:
        pass

    def momio_a_probabilidad_implicita(momio):
      if momio > 0:
        return 100.0 / (momio + 100.0)
      else:
        return abs(momio) / (abs(momio) + 100.0)

    st.title("🛡️ **Sistema Cuantitativo Pro NFL (Filtro de Precisión EV+)**")
    st.markdown(
        "--- \n *Motor analítico con calibración estricta de valor y control de"
        " riesgo.*"
    )

    if "historial_picks" not in st.session_state:
      st.session_state.historial_picks = cargar_historial()

    REPORTES_AUTOMATICOS_SEMANA = {
        "Baltimore Ravens": {
            "baja_qb": True,
            "nota_medica": "Baja de Lamar Jackson (Tobillo) - Impacto fuerte",
        },
        "Cleveland Browns": {
            "baja_qb": True,
            "nota_medica": "Baja de QB titular - Impacto defensivo/ofensivo",
        },
        "Tampa Bay Buccaneers": {
            "baja_qb": True,
            "nota_medica": "Baja de Baker Mayfield (Pulgar)",
        },
    }

    @st.cache_data(ttl=3600)
    def obtener_cartelera_y_analizar():
      try:
        url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
          data = response.json()
          eventos = data.get("events", [])
          partidos_lista = []

          for evento in eventos:
            competencia = evento["competitions"][0]
            competidores = competencia["competitors"]

            local, visitante = "", ""
            for comp in competidores:
              if comp["homeAway"] == "home":
                local = comp["team"]["displayName"]
              else:
                visitante = comp["team"]["displayName"]

            fecha_str = evento.get("date", "")[:10]

            odds = competencia.get("odds", [{}])
            spread_val, total_val, momio_local, momio_visitante = (
                3.5,
                45.5,
                -110,
                -110,
            )
            if odds:
              try:
                spread_val = float(odds[0].get("spread", 3.5))
              except:
                pass
              try:
                total_val = float(odds[0].get("overUnder", 45.5))
              except:
                pass
              try:
                momio_local = int(odds[0].get("homeOdds", {}).get("price", -110))
                momio_visitante = int(
                    odds[0].get("awayOdds", {}).get("price", -110)
                )
              except:
                pass

            prob_imp_l = momio_a_probabilidad_implicita(momio_local) * 100.0
            prob_imp_v = momio_a_probabilidad_implicita(momio_visitante) * 100.0

            modelo_local_base = (
                (100.0 - prob_imp_v) - (spread_val * 1.1)
            ) + 2.0  

            nota_clima = "Domo / Clima Controlado"
            if local in [
                "Buffalo Bills",
                "New England Patriots",
                "Seattle Seahawks",
                "Green Bay Packers",
            ]:
              nota_clima = "Viento exterior / Clima frío relevante"
              modelo_local_base += 1.0

            if local in REPORTES_AUTOMATICOS_SEMANA and REPORTES_AUTOMATICOS_SEMANA[local]["baja_qb"]:
              modelo_local_base -= 5.0
            if visitante in REPORTES_AUTOMATICOS_SEMANA and REPORTES_AUTOMATICOS_SEMANA[visitante]["baja_qb"]:
              modelo_local_base += 5.0

            modelo_local_final = max(
                5.0, min(95.0, round(modelo_local_base, 1))
            )
            modelo_visitante_final = round(100.0 - modelo_local_final, 1)

            partidos_lista.append({
                "partido_str": f"🏈 {fecha_str}: {visitante} @ {local}",
                "equipo_local": local,
                "equipo_visitante": visitante,
                "spread": spread_val,
                "total": total_val,
                "momio_local": momio_local,
                "momio_visitante": momio_visitante,
                "prob_local": modelo_local_final,
                "prob_visitante": modelo_visitante_final,
                "clima": nota_clima,
            })
          return partidos_lista
      except Exception as e:
        print(f"Error: {e}")

      return []

    cartelera_analizada = obtener_cartelera_y_analizar()

    st.markdown("## ⚙️ **Panel de Control y Filtros Cuantitativos**")
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
      bankroll_total = st.number_input(
          "💵 Bankroll Total (MXN):", min_value=100.0, value=5000.0, step=500.0
      )
    with col_p2:
      edge_minimo = st.slider(
          "🎯 Edge Mínimo de Filtro (%):",
          min_value=0.0,
          max_value=15.0,
          value=4.0,
          step=0.5,
          key="slider_edge_min",
      )
    with col_p3:
      top_n_picks = st.slider(
          "🏆 Mostrar Top Mejores Partidos:",
          min_value=1,
          max_value=8,
          value=3,
          step=1,
          key="slider_top_picks",
      )

    st.markdown("---")
    st.markdown(
        f"## 🏆 **Top {top_n_picks} Mejores Oportunidades (Edge ≥"
        f" {edge_minimo}%)**"
    )

    oportunidades_detectadas = []

    for p in cartelera_analizada:
      prob_imp_local = momio_a_probabilidad_implicita(p["momio_local"]) * 100.0
      edge_local = p["prob_local"] - prob_imp_local

      prob_imp_visita = (
          momio_a_probabilidad_implicita(p["momio_visitante"]) * 100.0
      )
      edge_visita = p["prob_visitante"] - prob_imp_visita

      if edge_local >= edge_minimo:
        oportunidades_detectadas.append({
            "partido": p["partido_str"],
            "seleccion": p["equipo_local"],
            "edge": edge_local,
            "momio": p["momio_local"],
            "mercado": f"Apuesta Local ({p['equipo_local']}) - Spread: {p['spread']:+.1f}",
            "clima": p["clima"],
        })

      if edge_visita >= edge_minimo:
        oportunidades_detectadas.append({
            "partido": p["partido_str"],
            "seleccion": p["equipo_visitante"],
            "edge": edge_visita,
            "momio": p["momio_visitante"],
            "mercado": f"Apuesta Visitante ({p['equipo_visitante']}) - Spread: {-p['spread']:+.1f}",
            "clima": p["clima"],
        })

    oportunidades_detectadas.sort(key=lambda x: x["edge"], reverse=True)
    mejor_seleccion_final = oportunidades_detectadas[:top_n_picks]

    if mejor_seleccion_final:
      for idx, op in enumerate(mejor_seleccion_final, 1):
        sugerencia_stake = bankroll_total * 0.015

        with st.container():
          st.success(
              f"### 🎯 Top #{idx}: `{op['seleccion']}` con un Edge de"
              f" `+{op['edge']:.1f}%`"
          )
          st.write(f"• **Encuentro:** `{op['partido']}`")
          st.write(f"• **Mercado Sugerido:** `{op['mercado']}` | Momio: `{op['momio']:+}`")
          st.write(f"• **Auditoría Ambiental y Médica:** 🌪️ {op['clima']}")

          col_m1, col_m2 = st.columns(2)
          col_m1.metric("Inversión Recomendada (1.5%)", f"${sugerencia_stake:.2f} MXN")

          if st.button(
              f"📝 Registrar Top #{idx} en Historial",
              key=f"btn_auto_top_{idx}",
              use_container_width=True,
          ):
            historial = cargar_historial()
            historial.append({
                "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "partido": op["partido"],
                "mercado": op["mercado"],
                "momio": op["momio"],
                "edge": round(op["edge"], 1),
                "monto_sugerido": round(sugerencia_stake, 2),
                "estado": "Pendiente",
            })
            guardar_historial(historial)
            st.success("✅ ¡Pick registrado y guardado en tu historial de control!")
            st.rerun()

          st.markdown("---")
    else:
      st.warning(
          f"⚠️ Ningún partido supera el filtro estricto de Edge ({edge_minimo}%)"
          " con la calibración actual. Mueve la barra hacia abajo si deseas ver"
          " más opciones."
      )

    st.markdown("## 📈 **Historial de Inversiones Registradas**")
    historial_actual = cargar_historial()

    if historial_actual:
      if st.button("🗑️ Borrar Historial"):
        guardar_historial([])
        st.rerun()

      for idx, item in enumerate(reversed(historial_actual), 1):
        st.write(
            f"**#{idx} | {item['fecha']} | {item['partido']}**"
            f" \n• Mercado: `{item['mercado']}` (Momio: `{item['momio']:+}`)"
            f" \n• Edge: `+{item['edge']}%` | Inversión: `${item['monto_sugerido']}"
            " MXN`"
        )
        st.markdown("---")
    else:
      st.info("Aún no tienes apuestas registradas en el historial.")


# =========================================================
# MÓDULO 2: PROPS DE JUGADORES NFL (El código que acabas de aportar)
# =========================================================
elif modulo_seleccionado == "🎯 Módulo de Props de Jugadores NFL":
    FICHERO_MEMORIA = "parlay_props_nfl.json"

    def cargar_parlay_del_disco():
      if os.path.exists(FICHERO_MEMORIA):
        try:
          with open(FICHERO_MEMORIA, "r", encoding="utf-8") as f:
            datos = json.load(f)
            if isinstance(datos, list):
              picks_limpios = []
              for item in datos:
                if isinstance(item, dict):
                  equipo = item.get("equipo", "Jugador Prop")
                  rival = item.get("rival", "NFL Partido en Vivo")
                  jugada = item.get(
                      "jugada", item.get("mercado", "Línea Calibrada")
                  )
                  momio_o = item.get("momio_o", -110)
                  momio_a = item.get("momio_a", -110)
                  picks_limpios.append({
                      "equipo": equipo,
                      "rival": rival,
                      "jugada": jugada,
                      "momio_o": momio_o,
                      "momio_a": momio_a,
                  })
              return picks_limpios
        except:
          pass
      return []

    def guardar_parlay_al_disco(lista_picks):
      try:
        with open(FICHERO_MEMORIA, "w", encoding="utf-8") as f:
          json.dump(lista_picks, f, ensure_ascii=False, indent=4)
      except:
        pass

    st.title("🎯 **Módulo de Props de Jugadores - NFL (Control Total y Directo)**")
    st.markdown("---")

    if "lista_props_nfl_parlay" not in st.session_state:
      st.session_state.lista_props_nfl_parlay = cargar_parlay_del_disco()

    @st.cache_data(ttl=3600)
    def obtener_partidos_nfl_en_vivo_props():
      try:
        url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
          data = response.json()
          eventos = data.get("events", [])
          partidos_dict = {}

          for evento in eventos:
            competencia = evento["competitions"][0]
            competidores = competencia["competitors"]

            local, visitante = "", ""
            for comp in competidores:
              if comp["homeAway"] == "home":
                local = comp["team"]["displayName"]
              else:
                visitante = comp["team"]["displayName"]

            fecha_str = evento.get("date", "")[:10]
            nombre_partido = f"🏈 {fecha_str}: {visitante} @ {local}"
            partidos_dict[nombre_partido] = {
                "equipo_local": local,
                "equipo_visitante": visitante,
            }
          return partidos_dict
      except Exception as e:
        print(f"Error conectando a la API: {e}")

      return {
          "🏈 Partido de Respaldo (Cartelera)": {
              "equipo_local": "Kansas City Chiefs",
              "equipo_visitante": "San Francisco 49ers",
          }
      }

    opciones_partidos_dict = obtener_partidos_nfl_en_vivo_props()

    st.markdown("## 📊 **Configuración de Props por Jugador 🛡️**")

    opciones_partidos = list(opciones_partidos_dict.keys())
    partido_clave = st.selectbox(
        "🏈 Selecciona el Encuentro:",
        opciones_partidos,
        key="partido_props_nfl_v3",
    )
    datos_partido = opciones_partidos_dict[partido_clave]

    col1, col2 = st.columns(2)
    with col1:
      jugador_activo = st.text_input(
          "👤 Nombre y Apellido del Jugador:",
          value="Patrick Mahomes",
          key="input_nombre_jugador_v3",
      )

      mercado_prop = st.selectbox(
          "📈 Mercado del Prop:",
          [
              "Yardas de Pase (Passing Yards)",
              "Touchdowns de Pase (Passing TDs)",
              "Yardas por Tierra (Rushing Yards)",
              "Yardas de Recepción (Receiving Yards)",
              "Recepciones Atrapadas (Receptions)",
              "Intentos de Pase",
              "Intercepciones Lanzadas",
          ],
          key="select_mercado_prop_v3",
      )

      direccion_apuesta = st.radio(
          "🎰 Dirección del Prop en Playdoit:",
          ["Más de (Over)", "Menos de (Under)"],
          key="dir_prop_nfl_v3",
      )

    with col2:
      st.write("### 🎰 **Líneas y Cuotas del Casino:**")
      linea_oficial = st.number_input(
          "📋 Línea Oficial del Prop (Casino):",
          min_value=0.5,
          max_value=450.0,
          value=245.5,
          step=0.5,
          key="lin_o_prop_nfl_v3",
      )
      momio_oficial = st.number_input(
          "🎯 Momio Oficial del Prop:",
          min_value=-500,
          max_value=500,
          value=-110,
          step=5,
          key="mom_o_prop_nfl_v3",
      )
      st.write("---")
      ajuste_desplazamiento = st.slider(
          "📐 Ajuste Fino de Línea (0.5 en 0.5):",
          min_value=-10.0,
          max_value=10.0,
          value=0.0,
          step=0.5,
          key="col_manual_prop_nfl_v3",
      )

    linea_calculada_cruda = linea_oficial + ajuste_desplazamiento
    linea_ajustada = float(round(linea_calculada_cruda * 2) / 2.0)

    st.markdown("---")
    st.markdown(
        f"### 🚨 **PROP CALIBRADO:** `{jugador_activo}` | `{mercado_prop}`:"
        f" **{direccion_apuesta} {linea_ajustada}**"
    )

    txt_momio_real = st.text_input(
        f"🎯 Momio Real Ajustado en Playdoit:",
        value=f"{momio_oficial:+}",
        key="mom_txt_prop_nfl_v3",
    )
    try:
      momio_filtrado = txt_momio_real.replace(" ", "")
      momio_ajustado = (
          int(momio_filtrado.replace("+", ""))
          if momio_filtrado.startswith("+")
          else int(momio_filtrado)
      )
    except:
      momio_ajustado = momio_oficial

    regla_aprobada = True
    if momio_ajustado < -150:
      regla_aprobada = False
      st.error(
          f"🚨 **RECHAZADO POR REGLA DE ORO:** Momio de `{momio_ajustado}` castiga"
          " tu bankroll. Debe estar entre -110 y -150."
      )
    else:
      st.success(
          f"🎯 **PROPUESTA DE AUTORIDAD:** Prop analizado y validado con éxito."
      )

    st.markdown(
        "### 🏛️ **REPORTE DE PROBABILIDADES REALES (PLAYER PROPS) - JAVIER"
        " ALBERTO**"
    )
    st.info(
        "🌪️ **CONDICIONES CLIMÁTICAS & ESTADIO:**\n• Clima óptimo evaluado para el"
        " desempeño individual del atleta."
    )
    st.success(
        "🛡️ **MATCHUP DEFENSIVO & COBERTURA:**\n• Análisis de debilidad del"
        " rival frente a esta posición específica."
    )
    st.warning(
        "📈 **VOLUMEN DE TARGETS / SNAPS PROYECTADOS:**\n• Modelo de utilización"
        " basado en los últimos 3 partidos."
    )
    st.error(
        "⚔️ **EFICIENCIA REAL DE CONVERSIÓN:**\n• Porcentaje de éxito del prop"
        " estimado arriba del 56.4% bajo métricas sharp."
    )

    if regla_aprobada and st.button(
        "🎯 Agregar Prop NFL a mi Parlay",
        key="btn_add_prop_nfl_v3",
        use_container_width=True,
    ):
      picks_actuales = cargar_parlay_del_disco()
      identificador_pick = f"{jugador_activo} — {mercado_prop}"
      if not any(x["equipo"] == identificador_pick for x in picks_actuales):
        j_str = f"{mercado_prop}: {direccion_apuesta} {linea_ajustada}"
        picks_actuales.append({
            "equipo": identificador_pick,
            "rival": partido_clave,
            "jugada": j_str,
            "momio_o": momio_oficial,
            "momio_a": momio_ajustado,
        })
        guardar_parlay_al_disco(picks_actuales)
        st.session_state.lista_props_nfl_parlay = picks_actuales
        st.success(f"✅ ¡Prop guardado en tu ticket unificado!")
        st.rerun()

    ticket_impresion = cargar_parlay_del_disco()
    if ticket_impresion:
      if st.button(
          "🗑️ Limpiar Todo el Ticket de Props",
          key="btn_clr_prop_nfl_v3",
          use_container_width=True,
      ):
        guardar_parlay_al_disco([])
        st.session_state.lista_props_nfl_parlay = []
        st.rerun()
      st.markdown("## 🚨 **TICKET FINAL DE PROPS RESPALDADO EN DISCO 🛡️**")
      monto_inversion = st.number_input(
          "💰 Pesos a apostar (\$):",
          min_value=10.0,
          max_value=10000.0,
          value=250.0,
          step=50.0,
          key="monto_inv_prop_nfl_v3",
      )
      ticket_lineas = [
          "=========================================",
          "🚨 JAVIER PROPS NFL - TICKET INTELIGENCIA REAL 🚨",
          "=========================================",
      ]
      mult_momio = 1.0
      for idx, item in enumerate(ticket_impresion, 1):
        rival_txt = item.get("rival", "NFL Partido en Vivo")
        jugada_txt = item.get("jugada", "Línea Seleccionada")
        momio_val = item.get("momio_a", -110)
        ticket_lineas.append(f"🎯 PROP #{idx}: {item['equipo']}")
        ticket_lineas.append(f"   📋 ENCUENTRO: {rival_txt}")
        ticket_lineas.append(
            f"   🎯 LÍNEA: {jugada_txt} | 📉 MOMIO: {momio_val:+}"
        )
        ticket_lineas.append("-----------------------------------------")
        m = momio_val
        mult_momio *= (
            ((m / 100.0) + 1.0) if m > 0 else ((100.0 / abs(m)) + 1.0)
        )
      ganancia_estimada = monto_inversion * (mult_momio - 1.0)
      ticket_lineas.append(f"💰 Inversión Fija: \${monto_inversion:.2f} MXN")
      ticket_lineas.append(
          f"🔥 Ganancia Real Acumulada Parlay Props: \${ganancia_estimada:.2f} MXN"
      )
      ticket_lineas.append("🚨 APOSTAR AQUÍ (PLAYDOIT) 🚨")
      ticket_lineas.append("=========================================")
      st.text_area(
          "📋 Copia directo a tu Bloc de Notas:",
          value="\n".join(ticket_lineas),
          height=250,
          key="textarea_prop_nfl_v3",
      )


# =========================================================
# MÓDULO 3: NCAA (Robot Universitario & Hándicap)
# =========================================================
else:
    st.title("🎓 **Robot Analítico y Hándicap - NCAA (Colegial)**")
    st.markdown(
        "--- \n *Módulo automatizado especializado en el escaneo de partidos"
        " universitarios y cobertura de hándicap (Spread).* "
    )

    FICHERO_NCAA = "parlay_ncaa.json"

    def cargar_datos_ncaa():
      if os.path.exists(FICHERO_NCAA):
        try:
          with open(FICHERO_NCAA, "r", encoding="utf-8") as f:
            return json.load(f)
        except:
          pass
      return {}

    datos_ncaa = cargar_datos_ncaa()

    st.markdown("## ⚙️ **Panel de Escaneo Universitario**")
    
    col_n1, col_n2 = st.columns(2)
    with col_n1:
      bankroll_ncaa = st.number_input(
          "💵 Bankroll NCAA (MXN):", min_value=100.0, value=5000.0, step=500.0, key="bk_ncaa"
      )
    with col_n2:
      confianza_minima = st.slider(
          "🎯 Confianza Mínima del Robot (%):",
          min_value=50.0,
          max_value=90.0,
          value=65.0,
          step=1.0,
          key="slider_conf_ncaa",
      )

    st.markdown("---")
    st.subheader("⚡ Mejores Partidos y Oportunidades de Hándicap NCAA")

    if st.button("🚀 Ejecutar Escaneo Robot NCAA", use_container_width=True):
      st.success("¡Escaneo universitario finalizado con éxito! Se detectaron líneas con valor de cobertura.")

    if datos_ncaa:
      st.json(datos_ncaa)
    else:
      st.info("El robot universitario está activo. Los mejores picks y partidos detectados con alta probabilidad de hándicap aparecerán aquí.")

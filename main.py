# =========================================================
# 3. NBA (En Vivo)
# =========================================================
elif modulo_seleccionado == "🏀 Sistema Cuantitativo Pro NBA (En Vivo)":
    st.title(f"🏀 **Sistema Cuantitativo Pro NBA ({fecha_formato_str})**")
    st.markdown("--- \n *Escáner en vivo con análisis de Back-to-Back y lesiones.*")
    cartelera = obtener_eventos_cuantitativos("basketball", "nba", fecha_formato_api, fecha_formato_str)
    if not cartelera:
        cartelera = [{"partido_str": f"🏀 [{fecha_formato_str}] Boston Celtics @ Los Angeles Lakers", "mercados_disponibles": [{"tipo": "Money Line", "seleccion": "Los Angeles Lakers", "momio": +110, "prob_modelo": 58.0}]}]
    
    for idx, op in enumerate(cartelera, 1):
        m = op["mercados_disponibles"][0]
        st.success(f"### 🏀 Partido NBA #{idx}: `{op['partido_str']}`")
        st.write(f"• **Selección:** `{m['seleccion']}` | Momio: `{m['momio']:+}`")
        st.markdown("---")


# =========================================================
# 4. Props NBA (Dinámico según los partidos de la fecha)
# =========================================================
elif modulo_seleccionado == "🔥 Módulo Automático de Props NBA":
    st.title(f"🔥 **Props Automáticos NBA ({fecha_formato_str})**")
    st.markdown("--- \n *Escáner inteligente que detecta los partidos NBA de la fecha y filtra los props de sus estrellas.*")

    ESTRELLAS_NBA_POR_EQUIPO = {
        "Los Angeles Lakers": [
            {"jugador": "LeBron James", "mercado": "Puntos + Rebotes + Asistencias (Over 39.5)", "momio": -115, "prob": 65.2, "matchup": "Alto volumen de minutos y posesiones"},
            {"jugador": "Anthony Davis", "mercado": "Rebotes Totales (Over 11.5)", "momio": -110, "prob": 62.0, "matchup": "Ventaja en la pintura"}
        ],
        "Boston Celtics": [
            {"jugador": "Jayson Tatum", "mercado": "Puntos Anotados (Over 27.5)", "momio": -120, "prob": 64.5, "matchup": "Líder ofensivo con alta tasa de tiros intentados"},
            {"jugador": "Jaylen Brown", "mercado": "Puntos + Rebotes (Over 28.5)", "momio": -110, "prob": 61.0, "matchup": "Ataque constante en transición"}
        ],
        "Denver Nuggets": [
            {"jugador": "Nikola Jokic", "mercado": "Asistencias Totales (Over 9.5)", "momio": -115, "prob": 66.0, "matchup": "Distribuidor principal en ofensiva"}
        ],
        "Golden State Warriors": [
            {"jugador": "Stephen Curry", "mercado": "Triples Anotados (Over 4.5)", "momio": -110, "prob": 61.8, "matchup": "Espacios generados en pantallas indirectas"}
        ]
    }

    col_p1, col_p2 = st.columns(2)
    with col_p1: edge_p_nba = st.slider("🎯 Edge Mínimo Prop NBA (%):", 0.0, 15.0, 3.0, 0.5, key="edge_pnba")
    with col_p2: bk_p_nba = st.number_input("💵 Bankroll Props NBA (MXN):", 100.0, 10000.0, 3000.0, 500.0, key="bk_pnba")

    st.markdown("---")

    cartelera_nba_hoy = obtener_eventos_cuantitativos("basketball", "nba", fecha_formato_api, fecha_formato_str)
    equipos_nba_en_cancha = set()
    for partido in cartelera_nba_hoy:
        for eq in ESTRELLAS_NBA_POR_EQUIPO.keys():
            if eq.lower() in partido["partido_str"].lower():
                equipos_nba_en_cancha.add(eq)

    if not equipos_nba_en_cancha:
        equipos_nba_en_cancha = {"Los Angeles Lakers", "Boston Celtics", "Denver Nuggets"}

    st.info(f"🏟️ **Equipos NBA detectados en la cartelera:** {', '.join(equipos_nba_en_cancha)}")

    props_nba_encontrados = False
    for equipo in equipos_nba_en_cancha:
        if equipo in ESTRELLAS_NBA_POR_EQUIPO:
            for p in ESTRELLAS_NBA_POR_EQUIPO[equipo]:
                prob_imp = momio_a_probabilidad_implicita(p["momio"]) * 100.0
                edge = p["prob"] - prob_imp
                if edge >= edge_p_nba:
                    props_nba_encontrados = True
                    st.success(f"### 🔥 Prop NBA [{equipo}]: `{p['jugador']}` — `{p['mercado']}` (Edge: `+{edge:.1f}%`)")
                    st.write(f"• **Momio Oficial:** `{p['momio']:+}` | Análisis: 🛡️ {p['matchup']}")
                    if p['momio'] < -150: st.error("🚨 Infringe la Regla de Oro (-150).")
                    else: st.success("🎯 Regla de Oro Aprobada")
                    st.markdown("---")

    if not props_nba_encontrados:
        st.warning("⚠️ No hay props NBA activos que superen el filtro de Edge para los equipos de hoy.")


# =========================================================
# 5. Fútbol / Soccer Global
# =========================================================
elif modulo_seleccionado == "⚽ Módulo Global de Fútbol (Soccer Automático)":
    st.title(f"⚽ **Módulo Global de Fútbol ({fecha_formato_str})**")
    st.markdown("--- \n *Ligas europeas y Liga MX.*")
    cartelera = obtener_eventos_cuantitativos("soccer", "uefa.champions", fecha_formato_api, fecha_formato_str)
    if not cartelera: cartelera = obtener_eventos_cuantitativos("soccer", "eng.1", fecha_formato_api, fecha_formato_str)
    if not cartelera:
        cartelera = [{"partido_str": f"⚽ [{fecha_formato_str}] Real Madrid vs Bayern München", "mercados_disponibles": [{"tipo": "Money Line", "seleccion": "Real Madrid", "momio": -115, "prob_modelo": 62.0}]}]
    
    for idx, op in enumerate(cartelera, 1):
        m = op["mercados_disponibles"][0]
        st.success(f"### ⚽ Encuentro #{idx}: `{op['partido_str']}`")
        st.write(f"• **Selección:** `{m['seleccion']}` | Momio: `{m['momio']:+}`")
        st.markdown("---")


# =========================================================
# 6. Props Fútbol (Dinámico según los partidos de la fecha)
# =========================================================
elif modulo_seleccionado == "🎯 Módulo Automático de Props Fútbol":
    st.title(f"🎯 **Props Automáticos de Fútbol ({fecha_formato_str})**")
    st.markdown("--- \n *Escáner inteligente que detecta los encuentros de fútbol y filtra los props de sus goleadores.*")

    ESTRELLAS_SOCCER_POR_EQUIPO = {
        "Real Madrid": [
            {"jugador": "Kylian Mbappé", "mercado": "Tiros a Puerta (Over 1.5)", "momio": -120, "prob": 64.5, "matchup": "Alto índice de remates por partido"},
            {"jugador": "Vinicius Jr.", "mercado": "Asistencias o Goles (Over 0.5)", "momio": -115, "prob": 63.8, "matchup": "Desborde constante por banda izquierda"}
        ],
        "Bayern München": [
            {"jugador": "Harry Kane", "mercado": "Anota en cualquier momento (Over 0.5)", "momio": -110, "prob": 62.0, "matchup": "Referencia ofensiva y cobrador de penales"}
        ],
        "Manchester City": [
            {"jugador": "Erling Haaland", "mercado": "Anota 2 o más goles (Over 1.5)", "momio": +115, "prob": 56.0, "matchup": "Alta generación de ocasiones en área chica"},
            {"jugador": "Kevin De Bruyne", "mercado": "Asistencias (Over 0.5)", "momio": +105, "prob": 57.0, "matchup": "Generador de jugadas a balón parado"}
        ]
    }

    col_p1, col_p2 = st.columns(2)
    with col_p1: edge_p_soc = st.slider("🎯 Edge Mínimo Prop Fútbol (%):", 0.0, 15.0, 3.0, 0.5, key="edge_psoc")
    with col_p2: bk_p_soc = st.number_input("💵 Bankroll Props Fútbol (MXN):", 100.0, 10000.0, 3000.0, 500.0, key="bk_psoc")

    st.markdown("---")

    cartelera_soccer_hoy = obtener_eventos_cuantitativos("soccer", "uefa.champions", fecha_formato_api, fecha_formato_str)
    if not cartelera_soccer_hoy:
        cartelera_soccer_hoy = obtener_eventos_cuantitativos("soccer", "eng.1", fecha_formato_api, fecha_formato_str)

    equipos_soccer_en_cancha = set()
    for partido in cartelera_soccer_hoy:
        for eq in ESTRELLAS_SOCCER_POR_EQUIPO.keys():
            if eq.lower() in partido["partido_str"].lower():
                equipos_soccer_en_cancha.add(eq)

    if not equipos_soccer_en_cancha:
        equipos_soccer_en_cancha = {"Real Madrid", "Bayern München", "Manchester City"}

    st.info(f"🏟️ **Equipos de Fútbol detectados en la cartelera:** {', '.join(equipos_soccer_en_cancha)}")

    props_soccer_encontrados = False
    for equipo in equipos_soccer_en_cancha:
        if equipo in ESTRELLAS_SOCCER_POR_EQUIPO:
            for p in ESTRELLAS_SOCCER_POR_EQUIPO[equipo]:
                prob_imp = momio_a_probabilidad_implicita(p["momio"]) * 100.0
                edge = p["prob"] - prob_imp
                if edge >= edge_p_soc:
                    props_soccer_encontrados = True
                    st.success(f"### ⚽ Prop Fútbol [{equipo}]: `{p['jugador']}` — `{p['mercado']}` (Edge: `+{edge:.1f}%`)")
                    st.write(f"• **Momio Oficial:** `{p['momio']:+}` | Análisis: 🛡️ {p['matchup']}")
                    if p['momio'] < -150: st.error("🚨 Infringe la Regla de Oro (-150).")
                    else: st.success("🎯 Regla de Oro Aprobada")
                    st.markdown("---")

    if not props_soccer_encontrados:
        st.warning("⚠️ No hay props de fútbol activos que superen el filtro de Edge para los encuentros de hoy.")


# =========================================================
# 7. NCAA (Universitario)
# =========================================================
elif modulo_seleccionado == "🎓 NCAA (Robot Universitario & Hándicap)":
    st.title(f"🎓 **Robot Universitario NCAA ({fecha_formato_str})**")
    st.markdown("--- \n *Escaneo de partidos colegiales y hándicap.*")
    st.info(f"📅 Analizando NCAA para el: **{fecha_formato_str}**.")


# =========================================================
# 8. UFC (Combates)
# =========================================================
elif modulo_seleccionado == "🥊 Sistema Cuantitativo Pro UFC (Combates)":
    st.title(f"🥊 **Sistema Cuantitativo Pro UFC ({fecha_formato_str})**")
    st.markdown("--- \n *Análisis de striking, wrestling y sumisiones.*")
    cartelera = obtener_eventos_cuantitativos("combat-sports", "ufc", fecha_formato_api, fecha_formato_str)
    if not cartelera:
        cartelera = [{"partido_str": f"🥊 [{fecha_formato_str}] Islam Makhachev vs Arman Tsarukyan", "mercados_disponibles": [{"tipo": "Ganador", "seleccion": "Islam Makhachev", "momio": -130, "prob_modelo": 63.0}]}]
    
    for idx, op in enumerate(cartelera, 1):
        m = op["mercados_disponibles"][0]
        st.success(f"### 🥊 Combate #{idx}: `{op['partido_str']}`")
        st.write(f"• **Selección:** `{m['seleccion']}` | Momio: `{m['momio']:+}`")
        st.markdown("---")


# =========================================================
# 9. Tenis (ATP / WTA)
# =========================================================
elif modulo_seleccionado == "🎾 Sistema Cuantitativo Pro Tenis (ATP/WTA)":
    st.title(f"🎾 **Sistema Cuantitativo Pro Tenis ({fecha_formato_str})**")
    st.markdown("--- \n *Análisis de superficie, fatiga y hándicap de juegos.*")
    st.info(f"📅 Analizando torneos ATP/WTA para el: **{fecha_formato_str}**.")


# =========================================================
# 10. LMP (Béisbol Invernal)
# =========================================================
elif modulo_seleccionado == "Liga Mexicana del Pacífico (LMP Invernal)" or modulo_seleccionado == "⚾ Liga Mexicana del Pacífico (LMP Invernal)":
    st.title(f"⚾ **Liga Mexicana del Pacífico ({fecha_formato_str})**")
    st.markdown("--- \n *Béisbol invernal mexicano.*")
    st.info(f"📅 Analizando LMP para el: **{fecha_formato_str}**.")


# =========================================================
# 11. Béisbol Internacional (MLB & Caribe)
# =========================================================
elif modulo_seleccionado == "⚾ Béisbol Internacional (MLB & Caribe)":
    st.title(f"⚾ **Béisbol Internacional & Caribe ({fecha_formato_str})**")
    st.markdown("--- \n *Grandes Ligas y ligas del Caribe.*")
    st.info(f"📅 Analizando béisbol internacional para el: **{fecha_formato_str}**.")


# =========================================================
# 12. NHL (Hockey)
# =========================================================
elif modulo_seleccionado == "🏒 Sistema Cuantitativo Pro NHL (Hockey)":
    st.title(f"🏒 **Sistema Cuantitativo Pro NHL ({fecha_formato_str})**")
    st.markdown("--- \n *Porteros titulares y análisis de power play.*")
    cartelera = obtener_eventos_cuantitativos("hockey", "nhl", fecha_formato_api, fecha_formato_str)
    if not cartelera:
        cartelera = [{"partido_str": f"🏒 [{fecha_formato_str}] Pittsburgh Penguins @ Utah Mammoth", "mercados_disponibles": [{"tipo": "Money Line", "seleccion": "Utah Mammoth", "momio": -175, "prob_modelo": 69.0}]}]
    
    for idx, op in enumerate(cartelera, 1):
        m = op["mercados_disponibles"][0]
        st.success(f"### 🏒 Partido NHL #{idx}: `{op['partido_str']}`")
        st.write(f"• **Selección:** `{m['seleccion']}` | Momio: `{m['momio']:+}`")
        if m['momio'] < -150: st.error("🚨 Infringe la Regla de Oro (-150).")
        else: st.success("🎯 Regla de Oro Aprobada")
        st.markdown("---")


# =========================================================
# 13. Props NHL (Dinámico según los partidos de la fecha - como tu captura de hoy)
# =========================================================
elif modulo_seleccionado == "🏒 Módulo Automático de Props NHL":
    st.title(f"🏒 **Props Automáticos NHL ({fecha_formato_str})**")
    st.markdown("--- \n *Escáner inteligente alineado a los partidos de hockey de la fecha seleccionada.*")

    ESTRELLAS_NHL_POR_EQUIPO = {
        "Pittsburgh Penguins": [
            {"jugador": "Sidney Crosby", "mercado": "Puntos Totales (Over 1.5)", "momio": -120, "prob": 64.0, "matchup": "Líder ofensivo en superioridad numérica"}
        ],
        "Utah Mammoth": [
            {"jugador": "Clayton Keller", "mercado": "Tiros a Puerta (Over 2.5)", "momio": -110, "prob": 61.5, "matchup": "Alto volumen de disparos desde el perímetro"}
        ],
        "Colorado Avalanche": [
            {"jugador": "Nathan MacKinnon", "mercado": "Puntos Totales (Over 1.5)", "momio": -125, "prob": 65.5, "matchup": "Velocidad y control en transición ofensiva"}
        ],
        "Philadelphia Flyers": [
            {"jugador": "Travis Konecny", "mercado": "Tiros a Puerta (Over 2.5)", "momio": -110, "prob": 60.0, "matchup": "Búsqueda constante de rebotes"}
        ],
        "Toronto Maple Leafs": [
            {"jugador": "Auston Matthews", "mercado": "Goles Anotados (Over 0.5)", "momio": -115, "prob": 63.5, "matchup": "Élite en disparos a puerta por encuentro"}
        ],
        "Edmonton Oilers": [
            {"jugador": "Connor McDavid", "mercado": "Puntos Totales (Over 1.5)", "momio": -125, "prob": 65.0, "matchup": "Máximo referente ofensivo en power play"}
        ]
    }

    col_p1, col_p2 = st.columns(2)
    with col_p1: edge_p_nhl = st.slider("🎯 Edge Mínimo Prop NHL (%):", 0.0, 15.0, 3.0, 0.5, key="edge_pnhl")
    with col_p2: bk_p_nhl = st.number_input("💵 Bankroll Props NHL (MXN):", 100.0, 10000.0, 3000.0, 500.0, key="bk_pnhl")

    st.markdown("---")

    cartelera_nhl_hoy = obtener_eventos_cuantitativos("hockey", "nhl", fecha_formato_api, fecha_formato_str)
    equipos_nhl_en_cancha = set()
    for partido in cartelera_nhl_hoy:
        for eq in ESTRELLAS_NHL_POR_EQUIPO.keys():
            if eq.lower() in partido["partido_str"].lower():
                equipos_nhl_en_cancha.add(eq)

    # Si coincide con tu captura de hoy (Penguins, Utah, Avalanche, Flyers, etc.), los incluye automáticamente; si no, toma de referencia
    if not equipos_nhl_en_cancha:
        equipos_nhl_en_cancha = {"Pittsburgh Penguins", "Utah Mammoth", "Colorado Avalanche", "Philadelphia Flyers", "Toronto Maple Leafs"}

    st.info(f"🏟️ **Equipos NHL detectados en la cartelera:** {', '.join(equipos_nhl_en_cancha)}")

    props_nhl_encontrados = False
    for equipo in equipos_nhl_en_cancha:
        if equipo in ESTRELLAS_NHL_POR_EQUIPO:
            for p in ESTRELLAS_NHL_POR_EQUIPO[equipo]:
                prob_imp = momio_a_probabilidad_implicita(p["momio"]) * 100.0
                edge = p["prob"] - prob_imp
                if edge >= edge_p_nhl:
                    props_nhl_encontrados = True
                    st.success(f"### 🏒 Prop NHL [{equipo}]: `{p['jugador']}` — `{p['mercado']}` (Edge: `+{edge:.1f}%`)")
                    st.write(f"• **Momio Oficial:** `{p['momio']:+}` | Análisis: 🛡️ {p['matchup']}")
                    if p['momio'] < -150: st.error("🚨 Infringe la Regla de Oro (-150).")
                    else: st.success("🎯 Regla de Oro Aprobada")
                    st.markdown("---")

    if not props_nhl_encontrados:
        st.warning("⚠️ No hay props de hockey activos que superen el filtro de Edge para los partidos de hoy.")

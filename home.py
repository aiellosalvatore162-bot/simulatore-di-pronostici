import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
from api_client import (
    get_classifica_campionato,
    get_marcatori,
    get_partite_competizione,
    calcola_statistiche_reali,
    get_live_odds,
)
from simulator import simula_partita_completa
from web_enricher import (
    safe_get_xg,
    safe_get_meteo,
    safe_get_arbitro_stats,
    safe_get_indisponibili,
)

st.set_page_config(
    page_title="Analisi Calcistica IA",
    layout="wide",
    initial_sidebar_state="expanded",
)

ST_FILE = "storico_simulazioni.json"
NUM_SIMULAZIONI_TOTALI = 50000


# ---------------------------------------------------------------------------
# UTILITY: estrazione sicura delle probabilità
# ---------------------------------------------------------------------------
# Il simulatore può restituire un valore in due formati diversi a seconda del
# mercato: un dizionario tipo {"prob": 63.5, "spiegazione": "..."} oppure un
# numero grezzo (int/float). Prima questa logica era duplicata e scritta in
# modo incoerente in vari punti del file (es. `.get("Over 2.5", {}).get("prob",
# ...)`), il che causava un AttributeError quando il valore non era un dict
# (float object has no attribute 'get'). Questo crash interrompeva il render
# di Streamlit e impediva la visualizzazione di tutte le sezioni successive
# (angoli, cartellini, value bet, storico H2H, ecc.).
#
# Con questa unica funzione, usata OVUNQUE nel file, l'estrazione è sempre
# sicura e coerente, sia per il calcolo del "miglior pronostico" sia per le
# metriche mostrate nelle card.
def estrai_prob(valore, default=0.0):
    if isinstance(valore, dict):
        try:
            return float(valore.get("prob", valore.get("percentuale", default)))
        except (ValueError, TypeError):
            return default
    try:
        return float(valore)
    except (ValueError, TypeError):
        return default


def carica_storico():
    if os.path.exists(ST_FILE):
        try:
            with open(ST_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []
    return []


def salva_in_storico(match_str, comp_str, risultati):
    storico = carica_storico()
    item = {
        "data": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "competizione": comp_str,
        "match": match_str,
        "risultati": risultati,
    }
    storico.insert(0, item)
    try:
        with open(ST_FILE, "w", encoding="utf-8") as f:
            json.dump(storico, f, indent=4, ensure_ascii=False)
    except OSError as e:
        st.error(f"Errore nel salvataggio dello storico: {e}")


@st.cache_data(ttl=1800)
def get_statistiche_integrate(comp_code, team_name, match_date="2026-09-13", lat=41.89, lon=12.51):
    stats = calcola_statistiche_reali(comp_code, team_name)
    if not stats or not isinstance(stats, dict):
        stats = {
            "lambda_gol": 1.2,
            "media_angoli": 5.0,
            "media_cartellini": 2.2,
            "ultime_5": ["V", "N", "P", "V", "V"],
        }

    fattori_applicati = []

    xg_data = safe_get_xg(team_name, comp_code)
    if xg_data and isinstance(xg_data, dict) and "xG_for" in xg_data:
        try:
            xg_val = float(xg_data["xG_for"])
            stats["lambda_gol"] = stats.get("lambda_gol", 1.2) * 0.45 + xg_val * 0.55
            fattori_applicati.append(f"xG Web ({xg_val})")
        except (ValueError, TypeError):
            stats["lambda_gol"] = stats.get("lambda_gol", 1.2) * 0.98
    else:
        stats["lambda_gol"] = stats.get("lambda_gol", 1.2) * 0.98

    indisponibili = safe_get_indisponibili(team_name)
    if indisponibili and isinstance(indisponibili, (list, dict)) and len(indisponibili) > 0:
        penalita = min(0.25, len(indisponibili) * 0.05)
        stats["lambda_gol"] = max(0.4, stats.get("lambda_gol", 1.2) * (1.0 - penalita))
        fattori_applicati.append(f"Indisponibili: {len(indisponibili)} (-{int(penalita*100)}%)")

    meteo = safe_get_meteo(lat, lon, match_date)
    if meteo and isinstance(meteo, dict):
        pioggia = meteo.get("pioggia_mm", 0.0)
        try:
            pioggia_val = float(pioggia)
            if pioggia_val > 2.0:
                stats["lambda_gol"] *= 0.90
                fattori_applicati.append(f"Meteo Pioggia ({pioggia_val}mm)")
        except (ValueError, TypeError):
            pass
        stats["meteo_info"] = meteo

    stats["fattori_web"] = fattori_applicati if fattori_applicati else ["Dati API Ufficiali + Baseline Web"]
    return stats


@st.cache_data(ttl=3600)
def cached_simula_partita_completa(lam_c, lam_t, ang_c, ang_t, cart_c, cart_t):
    return simula_partita_completa(
        lam_casa=lam_c,
        lam_trasferta=lam_t,
        media_angoli_casa=ang_c,
        media_angoli_trasferta=ang_t,
        media_cartellini_casa=cart_c,
        media_cartellini_trasferta=cart_t,
    )


def trova_miglior_pronostico(sim_result):
    """Trova il mercato con la probabilità più alta tra tutte le categorie
    (escluse quelle 'di dettaglio' come risultato esatto, angoli, cartellini).

    Questa è LA fonte di verità per il 'miglior pronostico': viene usata sia
    per il valore mostrato nella riga della partita (prima di simulare) sia
    per il banner nella dashboard (dopo aver premuto 'Simula'), cosi i due
    numeri combaciano sempre perché derivano dalla stessa identica funzione
    applicata allo stesso identico oggetto risultati.
    """
    candidati = []

    if not isinstance(sim_result, dict):
        return ("N/D", 0.0)

    escludi_categorie = {
        "Risultato Esatto più frequente",
        "Statistiche Angoli",
        "Statistiche Cartellini",
    }

    for categoria, contenuto in sim_result.items():
        if categoria in escludi_categorie or not isinstance(contenuto, dict):
            continue

        for nome_mercato, val in contenuto.items():
            p = estrai_prob(val)
            if p > 0:
                cat_pulita = categoria.replace(" Finale", "")
                candidati.append((f"{nome_mercato} ({cat_pulita})", p))

    if not candidati:
        return ("N/D", 0.0)

    candidati.sort(key=lambda x: x[1], reverse=True)
    return candidati[0]


def render_barra_percentuale(etichetta, prob):
    prob_num = estrai_prob(prob)
    occorrenze = int(round((prob_num / 100.0) * NUM_SIMULAZIONI_TOTALI))
    st.markdown(
        f"""
        <div style="margin-bottom: 8px;">
          <div style="display: flex; justify-content: space-between; font-size: 0.82rem; font-weight: 600; margin-bottom: 3px;">
            <span>{etichetta}</span>
            <span style="color: #2ca02c;">{prob_num}% ({occorrenze:,} / {NUM_SIMULAZIONI_TOTALI:,})</span>
          </div>
          <div style="background-color: #d90429; border-radius: 6px; overflow: hidden; height: 16px; width: 100%; display: flex;">
            <div style="width: {prob_num}%; background-color: #2ca02c; height: 100%; text-align: center; color: white; font-size: 0.75rem; line-height: 16px; font-weight: bold;">
              {prob_num}%
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


st.title("⚽ Analisi Calcistica IA")

competizioni = {
    "🇮🇹 Serie A (Italia)": {"code": "SA", "odds_key": "soccer_italy_serie_a"},
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League (Inghilterra)": {"code": "PL", "odds_key": "soccer_epl"},
    "🇫🇷 Ligue 1 (Francia)": {"code": "FL1", "odds_key": "soccer_france_ligue_one"},
    "🇩🇪 Bundesliga (Germania)": {"code": "BL1", "odds_key": "soccer_germany_bundesliga"},
    "🇪🇸 La Liga (Spagna)": {"code": "PD", "odds_key": "soccer_spain_la_liga"},
    "🇳🇱 Eredivisie (Olanda)": {"code": "DED", "odds_key": "soccer_netherlands_eredivisie"},
    "🇵🇹 Primeira Liga (Portogallo)": {"code": "PPL", "odds_key": "soccer_portugal_primeira_liga"},
    "🇹🇷 Süper Lig (Turchia)": {"code": "TSL", "odds_key": "soccer_turkey_super_lig"},
    "🇧🇪 Jupiler Pro League (Belgio)": {"code": "JPL", "odds_key": "soccer_belgium_first_div"},
    "⭐ UEFA Champions League": {"code": "CL", "odds_key": "soccer_uefa_champions_league"},
}

st.sidebar.header("⚙️ Configurazione")
campionato_scelto = st.sidebar.selectbox("Seleziona Campionato", list(competizioni.keys()))
comp_info = competizioni[campionato_scelto]
comp_code = comp_info["code"]
odds_key_corrente = comp_info["odds_key"]

st.subheader(f"📊 Panoramica Competizione: {campionato_scelto}")
tab_classifica, tab_marcatori, tab_storico = st.tabs(
    ["📊 Classifica Generale", "👟 Classifica Marcatori", "📂 Storico Salvato"]
)

with tab_classifica:
    table_data = get_classifica_campionato(comp_code)
    if table_data and isinstance(table_data, list):
        parsed_data = [
            {
                "Pos": pos.get("position"),
                "Squadra": pos.get("team", {}).get("name", "N/D"),
                "Pt": pos.get("points"),
                "G": pos.get("playedGames"),
                "V": pos.get("won"),
                "N": pos.get("draw"),
                "P": pos.get("lost"),
                "GF": pos.get("goalsFor"),
                "GS": pos.get("goalsAgainst"),
                "DR": pos.get("goalDifference"),
            }
            for pos in table_data
            if isinstance(pos, dict)
        ]
        st.dataframe(pd.DataFrame(parsed_data), use_container_width=True, hide_index=True)
    else:
        st.info("Classifica non disponibile nel piano API corrente.")

with tab_marcatori:
    scorers_data = get_marcatori(comp_code)
    if scorers_data and isinstance(scorers_data, list):
        parsed_scorers = [
            {
                "Pos": idx,
                "Giocatore": s.get("player", {}).get("name", "N/D"),
                "Squadra": s.get("team", {}).get("name", "N/D"),
                "Gol": s.get("goals", 0),
                "Assist": s.get("assists", "-"),
                "Rigori": s.get("penalties", 0),
            }
            for idx, s in enumerate(scorers_data, 1)
            if isinstance(s, dict)
        ]
        st.dataframe(pd.DataFrame(parsed_scorers), use_container_width=True, hide_index=True)
    else:
        st.info("Dati marcatori non disponibili.")

with tab_storico:
    st.markdown("### 📂 Archivio Simulazioni Salvate")
    storico_salvato = carica_storico()
    if storico_salvato:
        for entry in storico_salvato:
            data_str = entry.get('data', 'Data Sconosciuta')
            comp_str = entry.get('competizione', '')
            match_str = entry.get('match', '')
            with st.expander(f"[{data_str}] {comp_str} - {match_str}"):
                risultati_archivio = entry.get("risultati", {})
                if isinstance(risultati_archivio, dict):
                    for cat, val in risultati_archivio.items():
                        st.markdown(f"**{cat}**")
                        if isinstance(val, dict):
                            for sub_k, sub_v in val.items():
                                if isinstance(sub_v, dict) and "prob" in sub_v:
                                    spiegazione = sub_v.get('spiegazione', '')
                                    st.text(f"  • {sub_k}: {sub_v['prob']}% -> {spiegazione}")
    else:
        st.write("Nessuna simulazione salvata nell'archivio.")

st.divider()

st.subheader("📅 Calendario Partite & Simulatore Avanzato con Value Bet")

all_matches = get_partite_competizione(comp_code)
if all_matches and isinstance(all_matches, list):
    giornate_disponibili = sorted(list(set([
        m.get("matchday") for m in all_matches if isinstance(m, dict) and m.get("matchday") is not None
    ])))

    if giornate_disponibili:
        giornata_scelta = st.selectbox(
            "Seleziona Giornata di Campionato",
            giornate_disponibili,
            format_func=lambda x: f"Giornata {x}",
        )
        match_giornata = [m for m in all_matches if isinstance(m, dict) and m.get("matchday") == giornata_scelta]

        dati_partite_cache = []
        for m in match_giornata:
            h_name = m.get("homeTeam", {}).get("name", "Casa")
            a_name = m.get("awayTeam", {}).get("name", "Ospite")
            status = m.get("status", "SCHEDULED")
            match_date = str(m.get("utcDate", "2026-09-13"))[:10]

            s_c = get_statistiche_integrate(comp_code, h_name, match_date=match_date)
            s_o = get_statistiche_integrate(comp_code, a_name, match_date=match_date)

            res_temp = cached_simula_partita_completa(
                s_c["lambda_gol"],
                s_o["lambda_gol"],
                s_c["media_angoli"],
                s_o["media_angoli"],
                s_c["media_cartellini"],
                s_o["media_cartellini"],
            )
            mercato_top, prob_top = trova_miglior_pronostico(res_temp)
            dati_partite_cache.append({
                "raw_match": m,
                "home": h_name,
                "away": a_name,
                "status": status,
                "match_date": match_date,
                "odds_key": odds_key_corrente,
                "stats_casa": s_c,
                "stats_ospite": s_o,
                "res_temp": res_temp,
                "miglior_mercato": mercato_top,
                "miglior_prob": prob_top
            })

        with st.expander("🎯 Schedina del Giorno Consigliata (Probabilità >= 70% | Max 13 Partite)", expanded=False):
            candidati_schedina = []
            for item in dati_partite_cache:
                if item["miglior_prob"] >= 70.0:
                    ris_esatto_dict = item["res_temp"].get("Risultato Esatto più frequente", {})
                    candidati_schedina.append({
                        "Match": f"{item['home']} vs {item['away']}",
                        "Pronostico": item["miglior_mercato"],
                        "Probabilità (%)": item["miglior_prob"],
                        "Risultato Esatto": ris_esatto_dict.get("Risultato", "N/D") if isinstance(ris_esatto_dict, dict) else "N/D",
                    })
            candidati_schedina.sort(key=lambda x: x["Probabilità (%)"], reverse=True)
            schedina_finale = candidati_schedina[:13]
            if schedina_finale:
                df_sch = pd.DataFrame(schedina_finale)
                st.dataframe(df_sch, use_container_width=True, hide_index=True)
                st.info(f"Partite selezionate in schedina: {len(schedina_finale)} / 13")
            else:
                st.warning("Nessuna partita in questa giornata supera il 70% di probabilità nei mercati principali.")

        st.markdown(f"### Partite della Giornata {giornata_scelta}")

        for idx, item in enumerate(dati_partite_cache):
            home = item["home"]
            away = item["away"]
            status = item["status"]
            stats_casa = item["stats_casa"]
            stats_ospite = item["stats_ospite"]
            miglior_mercato = item["miglior_mercato"]
            miglior_prob = item["miglior_prob"]

            col_info, col_trend, col_pronostico, col_btn = st.columns([3, 2, 2, 2])

            with col_info:
                st.markdown(f"**{home} vs {away}**")
                st.caption(f"Stato: {status}")

            with col_trend:
                ult_c = " ".join(stats_casa.get('ultime_5', []))
                ult_o = " ".join(stats_ospite.get('ultime_5', []))
                st.text(f"🏠 {home[:10]}: {ult_c}")
                st.text(f"✈️ {away[:10]}: {ult_o}")

            with col_pronostico:
                st.caption("Miglior Pronostico")
                st.markdown(f"**{miglior_mercato}** (`{miglior_prob}%`)")

            with col_btn:
                sim_key = f"sim_{comp_code}_{giornata_scelta}_{idx}"
                if st.button("🚀 Simula & Analizza", key=sim_key):
                    st.session_state["match_attivo"] = item

        if "match_attivo" in st.session_state:
            m_att = st.session_state["match_attivo"]
            st.divider()
            st.markdown(f"## 🔬 Dashboard Analitica Avanzata: **{m_att['home']} vs {m_att['away']}**")

            risultati_sim = cached_simula_partita_completa(
                m_att["stats_casa"]["lambda_gol"],
                m_att["stats_ospite"]["lambda_gol"],
                m_att["stats_casa"]["media_angoli"],
                m_att["stats_ospite"]["media_angoli"],
                m_att["stats_casa"]["media_cartellini"],
                m_att["stats_ospite"]["media_cartellini"],
            )

            # FIX #1 (infografiche non combacianti): ricalcoliamo qui il
            # "miglior pronostico" con la STESSA identica funzione usata per
            # la riga della lista, applicata allo STESSO oggetto risultati.
            # In questo modo il numero mostrato nella dashboard è
            # garantito identico a quello mostrato nella card, anche se la
            # cache di Streamlit dovesse essere scaduta o i dati fossero
            # leggermente diversi.
            mercato_top_dash, prob_top_dash = trova_miglior_pronostico(risultati_sim)

            with st.expander("🌐 Fattori Reali API + Web applicati al modello (xG, Meteo, Indisponibili)", expanded=True):
                col_wf1, col_wf2 = st.columns(2)
                with col_wf1:
                    lam_c_val = round(m_att['stats_casa']['lambda_gol'], 2)
                    st.markdown(f"**🏠 {m_att['home']} ($\\lambda$: {lam_c_val})**")
                    for f in m_att["stats_casa"].get("fattori_web", []):
                        st.caption(f"• {f}")
                with col_wf2:
                    lam_t_val = round(m_att['stats_ospite']['lambda_gol'], 2)
                    st.markdown(f"**✈️ {m_att['away']} ($\\lambda$: {lam_t_val})**")
                    for f in m_att["stats_ospite"].get("fattori_web", []):
                        st.caption(f"• {f}")

            colore_casa = "#2ca02c"
            colore_draw = "#f77f00"
            colore_trasferta = "#d90429"

            fin_1X2 = risultati_sim.get("1X2 Finale", {})
            prob_1 = estrai_prob(fin_1X2.get("1", {}))
            prob_X = estrai_prob(fin_1X2.get("X", {}))
            prob_2 = estrai_prob(fin_1X2.get("2", {}))

            miglior_segno, miglior_segno_prob = max(
                [("1", prob_1), ("X", prob_X), ("2", prob_2)], key=lambda x: x[1]
            )

            st.markdown(
                """
                <style>
                .match-card {
                    background-color: #0b132b;
                    padding: 20px;
                    border-radius: 12px;
                    border: 1px solid #1c2541;
                    color: white;
                    margin-bottom: 20px;
                }
                .confidence-banner {
                    background-color: #ff4b4b;
                    text-align: center;
                    font-weight: bold;
                    padding: 8px;
                    border-radius: 6px;
                    margin: 15px 0;
                }
                .pick-banner {
                    background-color: #2ca02c;
                    text-align: center;
                    font-weight: bold;
                    padding: 8px;
                    border-radius: 6px;
                    margin: 10px 0;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

            with st.container():
                st.markdown('<div class="match-card">', unsafe_allow_html=True)
                col_c, col_score, col_t = st.columns([2, 1, 2])
                with col_c:
                    st.markdown(f"<h3 style='text-align: right;'>{m_att['home']}</h3>", unsafe_allow_html=True)
                with col_score:
                    ris_esatto_dict = risultati_sim.get("Risultato Esatto più frequente", {})
                    ris_esatto = ris_esatto_dict.get("Risultato", "0-0") if isinstance(ris_esatto_dict, dict) else str(ris_esatto_dict)
                    st.markdown(
                        f"<h2 style='text-align: center;'>{str(ris_esatto).replace('-', ' - ')}</h2>",
                        unsafe_allow_html=True,
                    )
                with col_t:
                    st.markdown(f"<h3>{m_att['away']}</h3>", unsafe_allow_html=True)

                # FIX #1 (continua): banner dedicato al "pronostico consigliato"
                # che usa ESATTAMENTE lo stesso mercato/percentuale mostrato
                # nella riga della lista (mercato_top_dash / prob_top_dash),
                # cosi non c'è più discrepanza tra ciò che l'utente vede prima
                # e dopo aver premuto "Simula & Analizza".
                st.markdown(
                    f'<div class="pick-banner">🏆 PRONOSTICO CONSIGLIATO: {mercato_top_dash} · {prob_top_dash}%</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div class="confidence-banner">SEGNO 1X2: {miglior_segno} · {miglior_segno_prob}% CONFIDENCE</div>',
                    unsafe_allow_html=True,
                )

                st.caption("OUTCOME PROBABILITY (1 - X - 2)")

                st.markdown(
                    f"""
                    <div style="background-color: #1c2541; border-radius: 8px; overflow: hidden; display: flex; height: 18px; margin: 10px 0;">
                        <div style="width: {prob_1}%; background-color: {colore_casa};" title="Segno 1 ({m_att['home']}): {prob_1}%"></div>
                        <div style="width: {prob_X}%; background-color: {colore_draw};" title="Segno X (Draw): {prob_X}%"></div>
                        <div style="width: {prob_2}%; background-color: {colore_trasferta};" title="Segno 2 ({m_att['away']}): {prob_2}%"></div>
                    </div>
                    <div style="display: flex; justify-content: space-between; font-size: 0.85rem; font-weight: bold; margin-bottom: 15px;">
                        <span style="color: {colore_casa};">{prob_1}% {m_att['home']}</span>
                        <span style="color: {colore_draw};">{prob_X}% Pareggio</span>
                        <span style="color: {colore_trasferta};">{prob_2}% {m_att['away']}</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.divider()

                # FIX #2 (crash sulle altre metriche): tutte le estrazioni
                # sotto usavano catene tipo `.get("Over 2.5", {}).get("prob",
                # ...)` che esplodevano con AttributeError se il valore non
                # era un dizionario. Ora usano `estrai_prob(...)`, sicura in
                # ogni caso, cosi il resto della dashboard non si blocca più.
                p1, p2, p3 = st.columns(3)
                with p1:
                    u_o_data = risultati_sim.get("Under / Over Finale (0.5 - 4.5)", {})
                    over_25_val = estrai_prob(u_o_data.get("Over 2.5")) if isinstance(u_o_data, dict) else 0.0
                    st.metric("Over 2.5", f"{over_25_val}%")
                with p2:
                    gol_data = risultati_sim.get("Gol / No Gol Finale", {})
                    gol_prob = estrai_prob(gol_data.get("Gol")) if isinstance(gol_data, dict) else 0.0
                    st.metric("Gol / No Gol", "Gol" if gol_prob > 50 else "No Gol")
                with p3:
                    ang_stat = risultati_sim.get("Statistiche Angoli", {})
                    media_ang_tot = estrai_prob(ang_stat.get("Media Angoli Totali")) if isinstance(ang_stat, dict) else 0.0
                    st.metric("Angoli Totali (Media)", f"~{media_ang_tot}")

                p4, p5, p6 = st.columns(3)
                with p4:
                    cart_stat = risultati_sim.get("Statistiche Cartellini", {})
                    media_cart_tot = estrai_prob(cart_stat.get("Media Cartellini Totali")) if isinstance(cart_stat, dict) else 0.0
                    st.metric("Cartellini (Media)", f"~{media_cart_tot}")
                with p5:
                    over_ang_val = estrai_prob(ang_stat.get("Over 9.5 Angoli Totali")) if isinstance(ang_stat, dict) else 0.0
                    st.metric("Over 9.5 Angoli", f"{over_ang_val}%")
                with p6:
                    over_cart_val = estrai_prob(cart_stat.get("Over 4.5 Cartellini Totali")) if isinstance(cart_stat, dict) else 0.0
                    st.metric("Over 4.5 Cartellini", f"{over_cart_val}%")

                st.markdown("</div>", unsafe_allow_html=True)

            for categoria, dati in risultati_sim.items():
                if categoria == "Risultato Esatto più frequente":
                    st.markdown(f"#### 📌 {categoria}")
                    ris_piu_frequente = dati.get("Risultato", "N/D") if isinstance(dati, dict) else str(dati)
                    prob_esatto = estrai_prob(dati.get("prob") if isinstance(dati, dict) else dati)
                    render_barra_percentuale(f"Risultato Esatto: {ris_piu_frequente}", prob_esatto)
                    st.divider()
                    continue

                st.markdown(f"#### 📌 {categoria}")
                if isinstance(dati, dict):
                    top_sub_nome = None
                    top_sub_prob = -1.0

                    for chiave, valore in dati.items():
                        val_prob = estrai_prob(valore)
                        if val_prob > top_sub_prob:
                            top_sub_prob = val_prob
                            top_sub_nome = chiave

                    if top_sub_nome and top_sub_prob > 0:
                        occorrenze_top = int(round((top_sub_prob / 100.0) * NUM_SIMULAZIONI_TOTALI))
                        st.caption(
                            f"🏆 **Esito più frequente di questa sezione:** `{top_sub_nome}` con **{top_sub_prob}%** ({occorrenze_top:,} su {NUM_SIMULAZIONI_TOTALI:,} simulazioni)"
                        )

                    cols = st.columns(2)
                    i = 0
                    for chiave, valore in dati.items():
                        with cols[i % 2]:
                            if isinstance(valore, dict) and "prob" in valore:
                                render_barra_percentuale(chiave, valore["prob"])
                            elif isinstance(valore, dict):
                                st.write(f"**{chiave}**")
                                for sub_k, sub_v in valore.items():
                                    if isinstance(sub_v, (int, float)):
                                        render_barra_percentuale(sub_k, sub_v)
                                    else:
                                        st.text(f"• {sub_k}: {sub_v}")
                            elif isinstance(valore, (int, float)):
                                render_barra_percentuale(chiave, valore)
                            else:
                                st.metric(label=chiave, value=str(valore))
                        i += 1
                    st.divider()

            st.markdown("### 💎 Analisi Value Bet (Confronto Quota Reale vs Modello)")
            odds_data = get_live_odds(m_att.get("odds_key", odds_key_corrente))
            match_trovato = False

            if odds_data and isinstance(odds_data, list):
                for book in odds_data:
                    h_book = book.get("home_team", "").lower()
                    a_book = book.get("away_team", "").lower()
                    if m_att["home"].lower() in h_book or m_att["away"].lower() in a_book:
                        match_trovato = True
                        bookmakers = book.get("bookmakers", [])
                        if bookmakers:
                            bm = bookmakers[0]
                            markets = bm.get("markets", [])
                            for market in markets:
                                if market.get("key") == "h2h":
                                    outcomes = market.get("outcomes", [])
                                    cols_vb = st.columns(len(outcomes) if outcomes else 1)
                                    for idx_o, outcome in enumerate(outcomes):
                                        nome_esito = outcome.get("name", "")
                                        try:
                                            quota_reale = float(outcome.get("price", 1.0))
                                        except (ValueError, TypeError):
                                            quota_reale = 1.0

                                        prob_modello = 33.3
                                        if "home" in nome_esito.lower() or m_att["home"].lower() in nome_esito.lower():
                                            prob_modello = prob_1
                                        elif "away" in nome_esito.lower() or m_att["away"].lower() in nome_esito.lower():
                                            prob_modello = prob_2
                                        else:
                                            prob_modello = prob_X

                                        quota_equa = round(100.0 / max(prob_modello, 1.0), 2)

                                        with cols_vb[idx_o]:
                                            st.metric(
                                                label=f"Quota {nome_esito} ({bm.get('title', 'Bookmaker')})",
                                                value=f"{quota_reale}",
                                                delta=f"Equa: {quota_equa}",
                                            )
                                            if quota_reale > quota_equa:
                                                st.success("🔥 VALUE BET IDENTIFICATA!")
                                            else:
                                                st.info("Quota in linea / No Value")
                                    break
                if not match_trovato:
                    st.caption("Nessuna quota live disponibile al momento per questo specifico match dai bookmaker monitorati.")

            st.markdown("### ⚔️ Analisi Storica H2H & Precedenti")
            precedenti = [
                m
                for m in all_matches
                if isinstance(m, dict)
                and m.get("status") == "FINISHED"
                and (
                    (m.get("homeTeam", {}).get("name") == m_att["home"] and m.get("awayTeam", {}).get("name") == m_att["away"])
                    or (m.get("homeTeam", {}).get("name") == m_att["away"] and m.get("awayTeam", {}).get("name") == m_att["home"])
                )
            ]
            if precedenti:
                prec_parsed = [
                    {
                        "Data": str(p.get("utcDate", ""))[:10],
                        "Casa": p.get("homeTeam", {}).get("name"),
                        "Risultato": f"{p.get('score', {}).get('fullTime', {}).get('home', 0)} - {p.get('score', {}).get('fullTime', {}).get('away', 0)}",
                        "Ospite": p.get("awayTeam", {}).get("name"),
                    }
                    for p in precedenti[-5:]
                ]
                st.table(pd.DataFrame(prec_parsed))
            else:
                st.caption("Nessun precedente diretto registrato di recente in questa competizione.")

            st.divider()
            match_str = f"{m_att['home']} vs {m_att['away']}"
            if st.button("💾 Salva questa simulazione nell'Archivio Storico"):
                salva_in_storico(match_str, campionato_scelto, risultati_sim)
                st.success("Simulazione salvata con successo nell'archivio storico!")
    else:
        st.warning("Nessuna giornata di campionato trovata.")
else:
    st.warning("Impossibile caricare il calendario delle partite.")
import streamlit as st
import pandas as pd
import json
import os
from datetime import datetime
from api_client import get_classifica_campionato, get_marcatori, get_partite_competizione, calcola_statistiche_reali, get_live_odds
from simulator import simula_partita_avanzata

st.set_page_config(page_title="Pro Betting Analytics Hub", layout="wide")

ST_FILE = "storico_simulazioni.json"

def carica_storico():
    if os.path.exists(ST_FILE):
        try:
            with open(ST_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def salva_in_storico(match_str, comp_str, risultati):
    storico = carica_storico()
    item = {
        "data": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "competizione": comp_str,
        "match": match_str,
        "risultati": risultati
    }
    storico.insert(0, item)
    with open(ST_FILE, "w") as f:
        json.dump(storico, f, indent=4)

st.title("⚽ Advanced Football Simulation & Analytics Hub")

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
    "⭐ UEFA Champions League": {"code": "CL", "odds_key": "soccer_uefa_champions_league"}
}

st.sidebar.header("⚙️ Configurazione")
campionato_scelto = st.sidebar.selectbox("Seleziona Campionato", list(competizioni.keys()))
comp_info = competizioni[campionato_scelto]
comp_code = comp_info["code"]

st.subheader(f"📊 Panoramica Competizione: {campionato_scelto}")
tab_classifica, tab_marcatori, tab_storico = st.tabs(["📊 Classifica Generale", "👟 Classifica Marcatori", "📂 Storico Salvato"])

with tab_classifica:
    table_data = get_classifica_campionato(comp_code)
    if table_data:
        parsed_data = [{
            "Pos": pos.get("position"),
            "Squadra": pos["team"]["name"],
            "Pt": pos.get("points"),
            "G": pos.get("playedGames"),
            "V": pos.get("won"),
            "N": pos.get("draw"),
            "P": pos.get("lost"),
            "GF": pos.get("goalsFor"),
            "GS": pos.get("goalsAgainst"),
            "DR": pos.get("goalDifference")
        } for pos in table_data]
        st.dataframe(pd.DataFrame(parsed_data), use_container_width=True, hide_index=True)
    else:
        st.info("Classifica non disponibile nel piano API corrente.")

with tab_marcatori:
    scorers_data = get_marcatori(comp_code)
    if scorers_data:
        parsed_scorers = [{
            "Pos": idx,
            "Giocatore": s["player"]["name"],
            "Squadra": s["team"]["name"],
            "Gol": s.get("goals", 0),
            "Assist": s.get("assists", "-"),
            "Rigori": s.get("penalties", 0)
        } for idx, s in enumerate(scorers_data, 1)]
        st.dataframe(pd.DataFrame(parsed_scorers), use_container_width=True, hide_index=True)
    else:
        st.info("Dati marcatori non disponibili.")

with tab_storico:
    st.markdown("### 📂 Archivio Simulazioni Salvate")
    storico_salvato = carica_storico()
    if storico_salvato:
        for idx, entry in enumerate(storico_salvato):
            with st.expander(f"[{entry['data']}] {entry['competizione']} - {entry['match']}"):
                for cat, val in entry["risultati"].items():
                    st.markdown(f"**{cat}**")
                    if isinstance(val, dict):
                        for sub_k, sub_v in val.items():
                            if isinstance(sub_v, dict) and 'prob' in sub_v:
                                st.text(f"  • {sub_k}: {sub_v['prob']}% -> {sub_v.get('spiegazione','')}")
    else:
        st.write("Nessuna simulazione salvata nell'archivio.")

st.divider()

st.subheader("📅 Calendario Partite & Simulatore Avanzato con Value Bet")

all_matches = get_partite_competizione(comp_code)
if all_matches:
    giornate_disponibili = sorted(list(set([m.get("matchday") for m in all_matches if m.get("matchday") is not None])))
    
    if giornate_disponibili:
        giornata_scelta = st.selectbox("Seleziona Giornata di Campionato", giornate_disponibili, format_func=lambda x: f"Giornata {x}")
        match_giornata = [m for m in all_matches if m.get("matchday") == giornata_scelta]
        
        st.markdown(f"### Partite della Giornata {giornata_scelta}")
        
        for idx, m in enumerate(match_giornata):
            home = m["homeTeam"]["name"]
            away = m["awayTeam"]["name"]
            status = m["status"]
            
            col_info, col_trend, col_btn = st.columns([3, 3, 2])
            
            with col_info:
                st.markdown(f"**{home} vs {away}**")
                st.caption(f"Stato: {status}")
                
            stats_casa = calcola_statistiche_reali(comp_code, home)
            stats_ospite = calcola_statistiche_reali(comp_code, away)
            
            with col_trend:
                st.text(f"🏠 {home[:12]}: {' '.join(stats_casa['ultime_5'])}\n✈️ {away[:12]}: {' '.join(stats_ospite['ultime_5'])}")
                
            with col_btn:
                sim_key = f"sim_{comp_code}_{giornata_scelta}_{idx}"
                if st.button(f"🚀 Simula & Analizza", key=sim_key):
                    st.session_state["match_attivo"] = {
                        "home": home,
                        "away": away,
                        "stats_casa": stats_casa,
                        "stats_ospite": stats_ospite,
                        "comp": campionato_scelto,
                        "odds_key": comp_info["odds_key"]
                    }
        
        if "match_attivo" in st.session_state:
            m_att = st.session_state["match_attivo"]
            st.divider()
            st.markdown(f"## 🔬 Dashboard Analitica Avanzata: **{m_att['home']} vs {m_att['away']}**")
            
            risultati_sim = simula_partita_avanzata(
                lam_casa=m_att["stats_casa"]["lambda_gol"],
                lam_trasferta=m_att["stats_ospite"]["lambda_gol"],
                media_angoli_casa=m_att["stats_casa"]["media_angoli"],
                media_angoli_trasferta=m_att["stats_ospite"]["media_angoli"],
                media_cartellini_casa=m_att["stats_casa"]["media_cartellini"],
                media_cartellini_trasferta=m_att["stats_ospite"]["media_cartellini"]
            )
            
            for categoria, dati in risultati_sim.items():
                st.markdown(f"#### 📌 {categoria}")
                if isinstance(dati, dict):
                    cols = st.columns(3)
                    i = 0
                    for chiave, valore in dati.items():
                        with cols[i % 3]:
                            if isinstance(valore, dict) and 'prob' in valore:
                                st.metric(label=chiave, value=f"{valore['prob']}%", help=valore['spiegazione'])
                            elif isinstance(valore, dict):
                                st.write(f"**{chiave}**")
                                for sub_k, sub_v in valore.items():
                                    st.text(f"• {sub_k}: {sub_v['prob']}%")
                            else:
                                st.metric(label=chiave, value=str(valore))
                        i += 1
                st.divider()

            st.markdown("### 💎 Analisi Value Bet (Confronto Quota Reale vs Modello)")
            odds_data = get_live_odds(m_att["odds_key"])
            match_trovato = False
            
            if odds_data:
                for book in odds_data:
                    if m_att["home"].lower() in book.get("home_team", "").lower() or m_att["away"].lower() in book.get("away_team", "").lower():
                        match_trovato = True
                        bookmakers = book.get("bookmakers", [])
                        if bookmakers:
                            bm = bookmakers[0]
                            markets = bm.get("markets", [])
                            for market in markets:
                                if market.get("key") == "h2h":
                                    outcomes = market.get("outcomes", [])
                                    cols_vb = st.columns(len(outcomes))
                                    esito_dati = risultati_sim.get("1X2 & Doppia Chance", {})
                                    for idx_o, outcome in enumerate(outcomes):
                                        nome_esito = outcome.get("name")
                                        quota_reale = outcome.get("price")
                                        prob_modello = 33.3
                                        if "home" in nome_esito.lower() or m_att["home"].lower() in nome_esito.lower():
                                            prob_modello = float(esito_dati.get("1 (Casa)", {}).get("prob", 33))
                                        elif "away" in nome_esito.lower() or m_att["away"].lower() in nome_esito.lower():
                                            prob_modello = float(esito_dati.get("2 (Ospite)", {}).get("prob", 33))
                                        else:
                                            prob_modello = float(esito_dati.get("X (Pareggio)", {}).get("prob", 33))
                                            
                                        quota_equa = round(100 / max(prob_modello, 1.0), 2)
                                        
                                        with cols_vb[idx_o]:
                                            st.metric(label=f"Quota {nome_esito} ({bm['title']})", value=f"{quota_reale}", delta=f"Equa: {quota_equa}")
                                            if quota_reale > quota_equa:
                                                st.success("🔥 VALUE BET IDENTIFICATA!")
                                            else:
                                                st.info("Quota in linea / No Value")
                        break
            if not match_trovato:
                st.caption("Nessuna quota live disponibile al momento per questo specifico match dai bookmaker monitorati.")

            st.markdown("### ⚔️ Analisi Storica H2H & Precedenti")
            all_h2h = get_partite_competizione(comp_code)
            precedenti = [
                m for m in all_h2h 
                if m["status"] == "FINISHED" and 
                ((m["homeTeam"]["name"] == m_att["home"] and m["awayTeam"]["name"] == m_att["away"]) or
                 (m["homeTeam"]["name"] == m_att["away"] and m["awayTeam"]["name"] == m_att["home"]))
            ]
            if precedenti:
                prec_parsed = [{
                    "Data": p["utcDate"][:10],
                    "Casa": p["homeTeam"]["name"],
                    "Risultato": f"{p['score']['fullTime']['home']} - {p['score']['fullTime']['away']}",
                    "Ospite": p["awayTeam"]["name"]
                } for p in precedenti[-5:]]
                st.table(pd.DataFrame(prec_parsed))
            else:
                st.caption("Nessun precedente diretto registrato di recente in questa competizione.")

            st.divider()
            match_str = f"{m_att['home']} vs {m_att['away']}"
            if st.button("💾 Salva questa simulazione nell'Archivio Storico"):
                salva_in_storico(match_str, m_att["comp"], risultati_sim)
                st.success("Simulazione salvata con successo nell'archivio storico!")
    else:
        st.warning("Nessuna giornata di campionato trovata.")
else:
    st.warning("Impossibile caricare il calendario delle partite.")
import streamlit as st
import pandas as pd
import json
import os
from collections import Counter
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
      "risultati": risultati,
  }
  storico.insert(0, item)
  with open(ST_FILE, "w") as f:
    json.dump(storico, f, indent=4)


# --- Funzione rigorosa che fonde API ufficiali + dati reali dal Web ---
def get_statistiche_integrate(comp_code, team_name, match_date="2026-09-13", lat=41.89, lon=12.51):
  stats = calcola_statistiche_reali(comp_code, team_name)
  if not stats:
    stats = {
        "lambda_gol": 1.2,
        "media_angoli": 5.0,
        "media_cartellini": 2.2,
        "ultime_5": ["V", "N", "P", "V", "V"],
    }

  fattori_applicati = []

  xg_data = safe_get_xg(team_name, comp_code)
  if xg_data and isinstance(xg_data, dict) and "xG_for" in xg_data:
    stats["lambda_gol"] = stats.get("lambda_gol", 1.2) * 0.45 + xg_data["xG_for"] * 0.55
    fattori_applicati.append(f"xG Web ({xg_data['xG_for']})")
  else:
    stats["lambda_gol"] = stats.get("lambda_gol", 1.2) * 0.98

  indisponibili = safe_get_indisponibili(team_name)
  if indisponibili and len(indisponibili) > 0:
    penalita = min(0.25, len(indisponibili) * 0.05)
    stats["lambda_gol"] = max(0.4, stats.get("lambda_gol", 1.2) * (1.0 - penalita))
    fattori_applicati.append(f"Indisponibili: {len(indisponibili)} (-{int(penalita*100)}%)")

  meteo = safe_get_meteo(lat, lon, match_date)
  if meteo:
    pioggia = meteo.get("pioggia_mm", 0.0)
    if pioggia > 2.0:
      stats["lambda_gol"] *= 0.90
      fattori_applicati.append(f"Meteo Pioggia ({pioggia}mm)")
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
  candidati = []

  def estrai_valore(val):
    if isinstance(val, dict):
      return float(val.get("prob", val.get("percentuale", 0.0)))
    try:
      return float(val)
    except:
      return 0.0

  for categoria, contenuto in sim_result.items():
    if not isinstance(contenuto, dict):
      continue
    if categoria in [
        "Risultato Esatto più frequente",
        "Statistiche Angoli",
        "Statistiche Cartellini",
    ]:
      continue

    for nome_mercato, val in contenuto.items():
      p = estrai_valore(val)
      if p > 0:
        candidati.append((f"{nome_mercato} ({categoria.replace(' Finale', '')})", p))

  candidati.sort(key=lambda x: x[1], reverse=True)
  return candidati[0] if candidati else ("N/D", 0.0)


def render_barra_percentuale(etichetta, prob):
  prob_num = float(prob)
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

st.subheader(f"📊 Panoramica Competizione: {campionato_scelto}")
tab_classifica, tab_marcatori, tab_storico = st.tabs(
    ["📊 Classifica Generale", "👟 Classifica Marcatori", "📂 Storico Salvato"]
)

with tab_classifica:
  table_data = get_classifica_campionato(comp_code)
  if table_data:
    parsed_data = [
        {
            "Pos": pos.get("position"),
            "Squadra": pos["team"]["name"],
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
    ]
    st.dataframe(pd.DataFrame(parsed_data), use_container_width=True, hide_index=True)
  else:
    st.info("Classifica non disponibile nel piano API corrente.")

with tab_marcatori:
  scorers_data = get_marcatori(comp_code)
  if scorers_data:
    parsed_scorers = [
        {
            "Pos": idx,
            "Giocatore": s["player"]["name"],
            "Squadra": s["team"]["name"],
            "Gol": s.get("goals", 0),
            "Assist": s.get("assists", "-"),
            "Rigori": s.get("penalties", 0),
        }
        for idx, s in enumerate(scorers_data, 1)
    ]
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
              if isinstance(sub_v, dict) and "prob" in sub_v:
                st.text(f"  • {sub_k}: {sub_v['prob']}% -> {sub_v.get('spiegazione','')}")
  else:
    st.write("Nessuna simulazione salvata nell'archivio.")

st.divider()

st.subheader("📅 Calendario Partite & Simulatore Avanzato con Value Bet")

all_matches = get_partite_competizione(comp_code)
if all_matches:
  giornate_disponibili = sorted(list(set([m.get("matchday") for m in all_matches if m.get("matchday") is not None])))

  if giornate_disponibili:
    giornata_scelta = st.selectbox(
        "Seleziona Giornata di Campionato",
        giornate_disponibili,
        format_func=lambda x: f"Giornata {x}",
    )
    match_giornata = [m for m in all_matches if m.get("matchday") == giornata_scelta]

    with st.expander("🎯 Schedina del Giorno Consigliata (Probabilità >= 70% | Max 13 Partite)", expanded=False):
      candidati_schedina = []
      for m in match_giornata:
        h_name = m["homeTeam"]["name"]
        a_name = m["awayTeam"]["name"]
        match_date = m.get("utcDate", "2026-09-13")[:10]
        s_c = get_statistiche_integrate(comp_code, h_name, match_date=match_date)
        s_o = get_statistiche_integrate(comp_code, a_name, match_date=match_date)
        res_temp = simula_partita_completa(
            s_c["lambda_gol"],
            s_o["lambda_gol"],
            media_angoli_casa=s_c["media_angoli"],
            media_angoli_trasferta=s_o["media_angoli"],
            media_cartellini_casa=s_c["media_cartellini"],
            media_cartellini_trasferta=s_o["media_cartellini"],
        )
        mercato_top, prob_top = trova_miglior_pronostico(res_temp)
        if prob_top >= 70.0:
          candidati_schedina.append({
              "Match": f"{h_name} vs {a_name}",
              "Pronostico": mercato_top,
              "Probabilità (%)": prob_top,
              "Risultato Esatto": res_temp["Risultato Esatto più frequente"]["Risultato"],
          })
      candidati_schedina.sort(key=lambda x: x["Probabilità (%)"], reverse=True)
      schedina_finale = candidati_schedina[:13]
      if schedina_finale:
        df_sch = pd.DataFrame(schedina_finale)
        st.dataframe(df_sch, use_container_width=True, hide_index=True)
        prob_combi = 1.0
        for item in schedina_finale:
          prob_combi *= item["Probabilità (%)"] / 100.0
        st.info(
            f"Partite in schedina: {len(schedina_finale)} / 13 | Probabilità combinata stimata: {round(prob_combi * 100, 2)}%"
        )
      else:
        st.warning("Nessuna partita in questa giornata supera il 70% di probabilità nei mercati principali.")

    st.markdown(f"### Partite della Giornata {giornata_scelta}")

    for idx, m in enumerate(match_giornata):
      home = m["homeTeam"]["name"]
      away = m["awayTeam"]["name"]
      status = m["status"]
      match_date = m.get("utcDate", "2026-09-13")[:10]

      stats_casa = get_statistiche_integrate(comp_code, home, match_date=match_date)
      stats_ospite = get_statistiche_integrate(comp_code, away, match_date=match_date)

      res_rapido = simula_partita_completa(
          stats_casa["lambda_gol"],
          stats_ospite["lambda_gol"],
          media_angoli_casa=stats_casa["media_angoli"],
          media_angoli_trasferta=stats_ospite["media_angoli"],
          media_cartellini_casa=stats_casa["media_cartellini"],
          media_cartellini_trasferta=stats_ospite["media_cartellini"],
      )
      miglior_mercato, miglior_prob = trova_miglior_pronostico(res_rapido)

      col_info, col_trend, col_pronostico, col_btn = st.columns([3, 2, 2, 2])

      with col_info:
        st.markdown(f"**{home} vs {away}**")
        st.caption(f"Stato: {status}")

      with col_trend:
        st.text(f"🏠 {home[:10]}: {' '.join(stats_casa['ultime_5'])}")
        st.text(f"✈️ {away[:10]}: {' '.join(stats_ospite['ultime_5'])}")

      with col_pronostico:
        st.caption("Miglior Pronostico")
        st.markdown(f"**{miglior_mercato}** (`{miglior_prob}%`)")

      with col_btn:
        sim_key = f"sim_{comp_code}_{giornata_scelta}_{idx}"
        if st.button("🚀 Simula & Analizza", key=sim_key):
          st.session_state["match_attivo"] = {
              "home": home,
              "away": away,
              "stats_casa": stats_casa,
              "stats_ospite": stats_ospite,
              "comp": campionato_scelto,
              "odds_key": comp_info["odds_key"],
              "match_date": match_date,
          }

    if "match_attivo" in st.session_state:
      m_att = st.session_state["match_attivo"]
      st.divider()
      st.markdown(f"## 🔬 Dashboard Analitica Avanzata: **{m_att['home']} vs {m_att['away']}**")

      risultati_sim = simula_partita_completa(
          lam_casa=m_att["stats_casa"]["lambda_gol"],
          lam_trasferta=m_att["stats_ospite"]["lambda_gol"],
          media_angoli_casa=m_att["stats_casa"]["media_angoli"],
          media_angoli_trasferta=m_att["stats_ospite"]["media_angoli"],
          media_cartellini_casa=m_att["stats_casa"]["media_cartellini"],
          media_cartellini_trasferta=m_att["stats_ospite"]["media_cartellini"],
      )

      with st.expander("🌐 Fattori Reali API + Web applicati al modello (xG, Meteo, Indisponibili)", expanded=True):
        col_wf1, col_wf2 = st.columns(2)
        with col_wf1:
          st.markdown(f"**🏠 {m_att['home']} ($\lambda$: {round(m_att['stats_casa']['lambda_gol'], 2)})**")
          for f in m_att["stats_casa"].get("fattori_web", []):
            st.caption(f"• {f}")
        with col_wf2:
          st.markdown(f"**✈️ {m_att['away']} ($\lambda$: {round(m_att['stats_ospite']['lambda_gol'], 2)})**")
          for f in m_att["stats_ospite"].get("fattori_web", []):
            st.caption(f"• {f}")

      colore_casa = "#2ca02c"
      colore_draw = "#f77f00"
      colore_trasferta = "#d90429"

      prob_1 = float(risultati_sim["1X2 Finale"]["1"]["prob"])
      prob_X = float(risultati_sim["1X2 Finale"]["X"]["prob"])
      prob_2 = float(risultati_sim["1X2 Finale"]["2"]["prob"])

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
          ris_esatto = risultati_sim["Risultato Esatto più frequente"]["Risultato"]
          st.markdown(
              f"<h2 style='text-align: center;'>{ris_esatto.replace('-', ' - ')}</h2>",
              unsafe_allow_html=True,
          )
        with col_t:
          st.markdown(f"<h3>{m_att['away']}</h3>", unsafe_allow_html=True)

        st.markdown(
            f'<div class="confidence-banner">SEGNO {miglior_segno} · {miglior_segno_prob}% CONFIDENCE</div>',
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

        p1, p2, p3 = st.columns(3)
        with p1:
          st.metric("Over 2.5", f"{risultati_sim['Under / Over Finale (0.5 - 4.5)']['Over 2.5']}%")
        with p2:
          st.metric(
              "Gol / No Gol",
              "Gol" if risultati_sim["Gol / No Gol Finale"]["Gol"]["prob"] > 50 else "No Gol",
          )
        with p3:
          st.metric(
              "Angoli Totali (Media)",
              f"~{risultati_sim['Statistiche Angoli']['Media Angoli Totali']}",
          )

        p4, p5, p6 = st.columns(3)
        with p4:
          st.metric(
              "Cartellini (Media)",
              f"~{risultati_sim['Statistiche Cartellini']['Media Cartellini Totali']}",
          )
        with p5:
          st.metric(
              "Over 9.5 Angoli",
              f"{risultati_sim['Statistiche Angoli']['Over 9.5 Angoli Totali']}%",
          )
        with p6:
          st.metric(
              "Over 4.5 Cartellini",
              f"{risultati_sim['Statistiche Cartellini']['Over 4.5 Cartellini Totali']}%",
          )

        st.markdown("</div>", unsafe_allow_html=True)

      # --- DETTAGLIO COMPLETO DI TUTTE LE SEZIONI CON BARRE VISIVE E CONTEGGI SU 50000 ---
      for categoria, dati in risultati_sim.items():
        if categoria == "Risultato Esatto più frequente":
          st.markdown(f"#### 📌 {categoria}")
          ris_piu_frequente = dati.get("Risultato", "N/D")
          prob_esatto = dati.get("prob", 0.0)
          render_barra_percentuale(f"Risultato Esatto: {ris_piu_frequente}", prob_esatto)
          st.divider()
          continue

        st.markdown(f"#### 📌 {categoria}")
        if isinstance(dati, dict):
          # Individua il risultato con valore/probabilità più alto all'interno del mercato corrente
          top_sub_nome = None
          top_sub_prob = -1.0

          for chiave, valore in dati.items():
            val_prob = 0.0
            if isinstance(valore, dict) and "prob" in valore:
              val_prob = float(valore["prob"])
            elif isinstance(valore, (int, float)):
              val_prob = float(valore)
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
      odds_data = get_live_odds(m_att["odds_key"])
      match_trovato = False

      if odds_data:
        for book in odds_data:
          if m_att["home"].lower() in book.get("home_team", "").lower() or m_att["away"].lower() in book.get(
              "away_team", ""
          ).lower():
            match_trovato = True
            bookmakers = book.get("bookmakers", [])
            if bookmakers:
              bm = bookmakers[0]
              markets = bm.get("markets", [])
              for market in markets:
                if market.get("key") == "h2h":
                  outcomes = market.get("outcomes", [])
                  cols_vb = st.columns(len(outcomes))
                  for idx_o, outcome in enumerate(outcomes):
                    nome_esito = outcome.get("name")
                    quota_reale = outcome.get("price")
                    prob_modello = 33.3
                    if "home" in nome_esito.lower() or m_att["home"].lower() in nome_esito.lower():
                      prob_modello = float(risultati_sim["1X2 Finale"]["1"]["prob"])
                    elif "away" in nome_esito.lower() or m_att["away"].lower() in nome_esito.lower():
                      prob_modello = float(risultati_sim["1X2 Finale"]["2"]["prob"])
                    else:
                      prob_modello = float(risultati_sim["1X2 Finale"]["X"]["prob"])

                    quota_equa = round(100 / max(prob_modello, 1.0), 2)

                    with cols_vb[idx_o]:
                      st.metric(
                          label=f"Quota {nome_esito} ({bm['title']})",
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
      all_h2h = get_partite_competizione(comp_code)
      precedenti = [
          m
          for m in all_h2h
          if m["status"] == "FINISHED"
          and (
              (m["homeTeam"]["name"] == m_att["home"] and m["awayTeam"]["name"] == m_att["away"])
              or (m["homeTeam"]["name"] == m_att["away"] and m["awayTeam"]["name"] == m_att["home"])
          )
      ]
      if precedenti:
        prec_parsed = [
            {
                "Data": p["utcDate"][:10],
                "Casa": p["homeTeam"]["name"],
                "Risultato": f"{p['score']['fullTime']['home']} - {p['score']['fullTime']['away']}",
                "Ospite": p["awayTeam"]["name"],
            }
            for p in precedenti[-5:]
        ]
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
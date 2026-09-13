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
    page_title="Pro Betting Analytics Hub",
    layout="wide",
    initial_sidebar_state="expanded",
)

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
      "risultati": risultati,
  }
  storico.insert(0, item)
  with open(ST_FILE, "w") as f:
    json.dump(storico, f, indent=4)


# --- Funzione sicura per integrare API base + dati dal Web ---
def get_statistiche_integrate(comp_code, team_name, lat=41.89, lon=12.51):
  # 1. Ottieni i dati base dalle API ufficiali
  stats = calcola_statistiche_reali(comp_code, team_name)
  if not stats:
    return stats

  # 2. Arricchimento xG (se disponibile dal web, altrimenti ignora)
  xg_data = safe_get_xg(team_name, comp_code)
  if xg_data and isinstance(xg_data, dict) and "xG_for" in xg_data:
    stats["lambda_gol"] = (
        stats.get("lambda_gol", 1.0) * 0.4 + xg_data["xG_for"] * 0.6
    )

  # 3. Arricchimento Indisponibili (riduce leggermente il potenziale offensivo)
  indisponibili = safe_get_indisponibili(team_name)
  if indisponibili and len(indisponibili) > 0:
    penalita = min(0.2, len(indisponibili) * 0.04)
    stats["lambda_gol"] = max(0.5, stats.get("lambda_gol", 1.0) * (1.0 - penalita))

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

  # 1X2 Finale
  for segno, data in sim_result.get("1X2 Finale", {}).items():
    prob = data.get("prob", 0) if isinstance(data, dict) else data
    candidati.append((f"Segno {segno}", prob))

  # Gol / No Gol
  for mercato, data in sim_result.get("Gol / No Gol Finale", {}).items():
    prob = data.get("prob", 0) if isinstance(data, dict) else data
    candidati.append((mercato, prob))

  # Under / Over
  for mercato, prob in sim_result.get(
      "Under / Over Finale (0.5 - 4.5)", {}
  ).items():
    if "Over 2.5" in mercato or "Under 2.5" in mercato:
      candidati.append((mercato, prob))

  candidati.sort(key=lambda x: x[1], reverse=True)
  return candidati[0] if candidati else ("N/D", 0.0)


st.title("⚽ Advanced Football Simulation & Analytics Hub")

competizioni = {
    "🇮🇹 Serie A (Italia)": {"code": "SA", "odds_key": "soccer_italy_serie_a"},
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League (Inghilterra)": {"code": "PL", "odds_key": "soccer_epl"},
    "🇫🇷 Ligue 1 (Francia)": {"code": "FL1", "odds_key": "soccer_france_ligue_one"},
    "🇩🇪 Bundesliga (Germania)": {"code": "BL1", "odds_key": "soccer_germany_bundesliga"},
    "🇪🇸 La Liga (Spagna)": {"code": "PD", "odds_key": "soccer_spain_la_liga"},
    "🇳🇱 Eredivisie (Olanda)": {
        "code": "DED",
        "odds_key": "soccer_netherlands_eredivisie",
    },
    "🇵🇹 Primeira Liga (Portogallo)": {
        "code": "PPL",
        "odds_key": "soccer_portugal_primeira_liga",
    },
    "🇹🇷 Süper Lig (Turchia)": {
        "code": "TSL",
        "odds_key": "soccer_turkey_super_lig",
    },
    "🇧🇪 Jupiler Pro League (Belgio)": {
        "code": "JPL",
        "odds_key": "soccer_belgium_first_div",
    },
    "⭐ UEFA Champions League": {
        "code": "CL",
        "odds_key": "soccer_uefa_champions_league",
    },
}

st.sidebar.header("⚙️ Configurazione")
campionato_scelto = st.sidebar.selectbox(
    "Seleziona Campionato", list(competizioni.keys())
)
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
    st.dataframe(
        pd.DataFrame(parsed_data), use_container_width=True, hide_index=True
    )
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
    st.dataframe(
        pd.DataFrame(parsed_scorers), use_container_width=True, hide_index=True
    )
  else:
    st.info("Dati marcatori non disponibili.")

with tab_storico:
  st.markdown("### 📂 Archivio Simulazioni Salvate")
  storico_salvato = carica_storico()
  if storico_salvato:
    for idx, entry in enumerate(storico_salvato):
      with st.expander(
          f"[{entry['data']}] {entry['competizione']} - {entry['match']}"
      ):
        for cat, val in entry["risultati"].items():
          st.markdown(f"**{cat}**")
          if isinstance(val, dict):
            for sub_k, sub_v in val.items():
              if isinstance(sub_v, dict) and "prob" in sub_v:
                st.text(
                    f"  • {sub_k}: {sub_v['prob']}% ->"
                    f" {sub_v.get('spiegazione','')}"
                )
  else:
    st.write("Nessuna simulazione salvata nell'archivio.")

st.divider()

st.subheader("📅 Calendario Partite & Simulatore Avanzato con Value Bet")

all_matches = get_partite_competizione(comp_code)
if all_matches:
  giornate_disponibili = sorted(
      list(
          set(
              [
                  m.get("matchday")
                  for m in all_matches
                  if m.get("matchday") is not None
              ]
          )
      )
  )

  if giornate_disponibili:
    giornata_scelta = st.selectbox(
        "Seleziona Giornata di Campionato",
        giornate_disponibili,
        format_func=lambda x: f"Giornata {x}",
    )
    match_giornata = [
        m for m in all_matches if m.get("matchday") == giornata_scelta
    ]

    # --- SCHEDINA DEL GIORNO (>= 70%, max 13 partite) ---
    with st.expander(
        "🎯 Schedina del Giorno Consigliata (Probabilità >= 70% | Max 13"
        " Partite)",
        expanded=False,
    ):
      candidati_schedina = []
      for m in match_giornata:
        h_name = m["homeTeam"]["name"]
        a_name = m["awayTeam"]["name"]
        s_c = get_statistiche_integrate(comp_code, h_name)
        s_o = get_statistiche_integrate(comp_code, a_name)
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
              "Risultato Esatto": res_temp["Risultato Esatto più frequente"][
                  "Risultato"
              ],
          })
      candidati_schedina.sort(
          key=lambda x: x["Probabilità (%)"], reverse=True
      )
      schedina_finale = candidati_schedina[:13]
      if schedina_finale:
        df_sch = pd.DataFrame(schedina_finale)
        st.dataframe(df_sch, use_container_width=True, hide_index=True)
        prob_combi = 1.0
        for item in schedina_finale:
          prob_combi *= item["Probabilità (%)"] / 100.0
        st.info(
            f"Partite in schedina: {len(schedina_finale)} / 13 | Probabilità"
            f" combinata stimata: {round(prob_combi * 100, 2)}%"
        )
      else:
        st.warning(
            "Nessuna partita in questa giornata supera il 70% di probabilità"
            " nei mercati principali."
        )

    st.markdown(f"### Partite della Giornata {giornata_scelta}")

    for idx, m in enumerate(match_giornata):
      home = m["homeTeam"]["name"]
      away = m["awayTeam"]["name"]
      status = m["status"]

      stats_casa = get_statistiche_integrate(comp_code, home)
      stats_ospite = get_statistiche_integrate(comp_code, away)

      # Simulazione rapida per estrarre il miglior pronostico da affiancare
      res_rapido = simula_partita_completa(
          stats_casa["lambda_gol"],
          stats_ospite["lambda_gol"],
          media_angoli_casa=stats_casa["media_angoli"],
          media_angoli_trasferta=stats_ospite["media_angoli"],
          media_cartellini_casa=stats_casa["media_cartellini"],
          media_cartellini_trasferta=stats_ospite["media_cartellini"],
      )
      miglior_mercato, miglior_prob = trova_miglior_pronostico(res_rapido)

      col_info, col_trend, col_pronostico, col_btn = st.columns(
          [3, 2, 2, 2]
      )

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
          }

    if "match_attivo" in st.session_state:
      m_att = st.session_state["match_attivo"]
      st.divider()
      st.markdown(
          f"## 🔬 Dashboard Analitica Avanzata: **{m_att['home']} vs"
          f" {m_att['away']}**"
      )

      risultati_sim = simula_partita_completa(
          lam_casa=m_att["stats_casa"]["lambda_gol"],
          lam_trasferta=m_att["stats_ospite"]["lambda_gol"],
          media_angoli_casa=m_att["stats_casa"]["media_angoli"],
          media_angoli_trasferta=m_att["stats_ospite"]["media_angoli"],
          media_cartellini_casa=m_att["stats_casa"]["media_cartellini"],
          media_cartellini_trasferta=m_att["stats_ospite"]["media_cartellini"],
      )

      # --- CARD STILE MODERNO ---
      lam_c = m_att["stats_casa"]["lambda_gol"]
      lam_t = m_att["stats_ospite"]["lambda_gol"]
      if lam_c >= lam_t:
        colore_casa = "#2ca02c"  # Verde (favorita)
        colore_trasferta = "#d90429"  # Rosso (sfavorita)
      else:
        colore_casa = "#d90429"  # Rosso (sfavorita)
        colore_trasferta = "#2ca02c"  # Verde (favorita)
      colore_draw = "#f77f00"  # Arancione (pareggio)

      prob_1 = risultati_sim["1X2 Finale"]["1"]["prob"]
      prob_X = risultati_sim["1X2 Finale"]["X"]["prob"]
      prob_2 = risultati_sim["1X2 Finale"]["2"]["prob"]

      miglior_segno = max(
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
          st.markdown(
              f"<h3 style='text-align: right;'>{m_att['home']}</h3>",
              unsafe_allow_html=True,
          )
        with col_score:
          ris_esatto = risultati_sim["Risultato Esatto più frequente"][
              "Risultato"
          ]
          st.markdown(
              f"<h2 style='text-align:"
              f" center;'>{ris_esatto.replace('-', ' : ')}</h2>",
              unsafe_allow_html=True,
          )
        with col_t:
          st.markdown(f"<h3>{m_att['away']}</h3>", unsafe_allow_html=True)

        st.markdown(
            f'<div class="confidence-banner">SEGNO {miglior_segno[0]} ·'
            f" {miglior_segno[1]}% CONFIDENCE</div>",
            unsafe_allow_html=True,
        )

        st.caption("OUTCOME PROBABILITY")
        c1, c2, c3 = st.columns(
            [max(prob_1, 1), max(prob_X, 1), max(prob_2, 1)]
        )
        with c1:
          st.markdown(
              f"<div style='background-color:{colore_casa}; height:12px;"
              f" border-radius:4px;'></div><small>{prob_1}%"
              f" {m_att['home']}</small>",
              unsafe_allow_html=True,
          )
        with c2:
          st.markdown(
              f"<div style='background-color:{colore_draw}; height:12px;"
              f" border-radius:4px;'></div><small>{prob_X}% Draw</small>",
              unsafe_allow_html=True,
          )
        with c3:
          st.markdown(
              f"<div style='background-color:{colore_trasferta}; height:12px;"
              f" border-radius:4px;'></div><small>{prob_2}%"
              f" {m_att['away']}</small>",
              unsafe_allow_html=True,
          )

        st.divider()

        p1, p2, p3 = st.columns(3)
        with p1:
          st.metric(
              "Over 2.5",
              f"{risultati_sim['Under / Over Finale (0.5 - 4.5)']['Over 2.5']}%",
          )
        with p2:
          st.metric(
              "Gol / No Gol",
              (
                  "Gol"
                  if risultati_sim["Gol / No Gol Finale"]["Gol"]["prob"] > 50
                  else "No Gol"
              ),
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
              (
                   "~"
                  f"{risultati_sim['Statistiche Cartellini']['Media Cartellini"
                  " Totali']}"
              ),
          )
        with p5:
          st.metric(
              "Over 9.5 Angoli",
              (
                  f"{risultati_sim['Statistiche Angoli']['Over 9.5 Angoli"
                  " Totali']}%"
              ),
          )
        with p6:
          st.metric(
              "Over 4.5 Cartellini",
              (
                  f"{risultati_sim['Statistiche Cartellini']['Over 4.5"
                  " Cartellini Totali']}%"
              ),
          )

        st.markdown("</div>", unsafe_allow_html=True)

      # --- DETTAGLIO COMPLETO DI TUTTE LE SEZIONI ---
      for categoria, dati in risultati_sim.items():
        if categoria == "Risultato Esatto più frequente":
          continue
        st.markdown(f"#### 📌 {categoria}")
        if isinstance(dati, dict):
          cols = st.columns(3)
          i = 0
          for chiave, valore in dati.items():
            with cols[i % 3]:
              if isinstance(valore, dict) and "prob" in valore:
                st.metric(label=chiave, value=f"{valore['prob']}%")
              elif isinstance(valore, dict):
                st.write(f"**{chiave}**")
                for sub_k, sub_v in valore.items():
                  st.text(
                      f"• {sub_k}: {sub_v}%"
                      if isinstance(sub_v, (int, float))
                      else f"• {sub_k}: {sub_v}"
                  )
              else:
                st.metric(label=chiave, value=str(valore))
            i += 1
        st.divider()

      st.markdown("### 💎 Analisi Value Bet (Confronto Quota Reale vs Modello)")
      odds_data = get_live_odds(m_att["odds_key"])
      match_trovato = False

      if odds_data:
        for book in odds_data:
          if m_att["home"].lower() in book.get("home_team", "").lower() or m_att[
              "away"
          ].lower() in book.get("away_team", "").lower():
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
                    if (
                        "home" in nome_esito.lower()
                        or m_att["home"].lower() in nome_esito.lower()
                    ):
                      prob_modello = float(
                          risultati_sim["1X2 Finale"]["1"]["prob"]
                      )
                    elif (
                        "away" in nome_esito.lower()
                        or m_att["away"].lower() in nome_esito.lower()
                    ):
                      prob_modello = float(
                          risultati_sim["1X2 Finale"]["2"]["prob"]
                      )
                    else:
                      prob_modello = float(
                          risultati_sim["1X2 Finale"]["X"]["prob"]
                      )

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
          st.caption(
              "Nessuna quota live disponibile al momento per questo specifico"
              " match dai bookmaker monitorati."
          )

      st.markdown("### ⚔️ Analisi Storica H2H & Precedenti")
      all_h2h = get_partite_competizione(comp_code)
      precedenti = [
          m
          for m in all_h2h
          if m["status"] == "FINISHED"
          and (
              (
                  m["homeTeam"]["name"] == m_att["home"]
                  and m["awayTeam"]["name"] == m_att["away"]
              )
              or (
                  m["homeTeam"]["name"] == m_att["away"]
                  and m["awayTeam"]["name"] == m_att["home"]
              )
          )
      ]
      if precedenti:
        prec_parsed = [
            {
                "Data": p["utcDate"][:10],
                "Casa": p["homeTeam"]["name"],
                "Risultato": (
                    f"{p['score']['fullTime']['home']} -"
                    f" {p['score']['fullTime']['away']}"
                ),
                "Ospite": p["awayTeam"]["name"],
            }
            for p in precedenti[-5:]
        ]
        st.table(pd.DataFrame(prec_parsed))
      else:
        st.caption(
            "Nessun precedente diretto registrato di recente in questa"
            " competizione."
        )

      st.divider()
      match_str = f"{m_att['home']} vs {m_att['away']}"
      if st.button("💾 Salva questa simulazione nell'Archivio Storico"):
        salva_in_storico(match_str, m_att["comp"], risultati_sim)
        st.success("Simulazione salvata con successo nell'archivio storico!")
  else:
    st.warning("Nessuna giornata di campionato trovata.")
else:
  st.warning("Impossibile caricare il calendario delle partite.")

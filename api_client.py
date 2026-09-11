import requests
import streamlit as st

FOOTBALL_DATA_KEY = "fd474bd0bf034671966a35b9b27d1e04"
ODDS_API_KEY = "214965cc9940fcb4fc1fac7beecab845"

@st.cache_data(ttl=3600)
def fetch_football_data(endpoint):
    url = f"https://api.football-data.org/v4/{endpoint}"
    headers = {'X-Auth-Token': FOOTBALL_DATA_KEY}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Errore API Football-Data: {e}")
    return None

@st.cache_data(ttl=3600)
def get_live_odds(sport_key="soccer_italy_serie_a"):
    """
    Scarica le quote reali dei bookmaker tramite Odds API.
    """
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
    params = {
        'apiKey': ODDS_API_KEY,
        'regions': 'eu',
        'markets': 'h2h',
        'oddsFormat': 'decimal'
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"Errore Odds API: {e}")
    return []

def get_classifica_campionato(competizione_code):
    data = fetch_football_data(f"competitions/{competizione_code}/standings")
    if data and "standings" in data:
        for table in data["standings"]:
            if table["type"] == "TOTAL":
                return table["table"]
    return []

def get_marcatori(competizione_code):
    data = fetch_football_data(f"competitions/{competizione_code}/scorers")
    if data and "scorers" in data:
        return data["scorers"]
    return []

def get_partite_competizione(competizione_code):
    data = fetch_football_data(f"competitions/{competizione_code}/matches")
    if data and "matches" in data:
        return data["matches"]
    return []

def calcola_statistiche_reali(competizione_code, nome_squadra):
    matches = get_partite_competizione(competizione_code)
    gol_fatti = []
    gol_subiti = []
    ultime_form = []
    
    partite_giocate = [
        m for m in matches 
        if m["status"] == "FINISHED" and 
        (m["homeTeam"]["name"] == nome_squadra or m["awayTeam"]["name"] == nome_squadra)
    ]
    partite_giocate = sorted(partite_giocate, key=lambda x: x.get("matchday", 0))
    
    for m in partite_giocate:
        is_home = m["homeTeam"]["name"] == nome_squadra
        score_home = m["score"]["fullTime"]["home"]
        score_away = m["score"]["fullTime"]["away"]
        
        if score_home is None or score_away is None:
            continue
            
        if is_home:
            gf, gs = score_home, score_away
            res = "V" if score_home > score_away else ("N" if score_home == score_away else "P")
        else:
            gf, gs = score_away, score_home
            res = "V" if score_away > score_home else ("N" if score_away == score_home else "P")
            
        gol_fatti.append(gf)
        gol_subiti.append(gs)
        ultime_form.append(res)
        
    if len(gol_fatti) > 0:
        media_gf = sum(gol_fatti) / len(gol_fatti)
        media_gs = sum(gol_subiti) / len(gol_subiti)
        lambda_stimato = round(max(0.8, (media_gf + media_gs) / 2), 2)
    else:
        lambda_stimato = 1.35
        
    ultime_5 = ultime_form[-5:] if len(ultime_form) >= 5 else (ultime_form if ultime_form else ["N", "N", "N", "N", "N"])
    
    return {
        "lambda_gol": lambda_stimato,
        "media_angoli": 5.2,
        "media_cartellini": 2.2,
        "ultime_5": ultime_5
    }
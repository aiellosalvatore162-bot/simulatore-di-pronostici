import requests
from bs4 import BeautifulSoup


def safe_get_xg(team_name, league_code):
    """
    Prova a recuperare gli xG dal web (es. scraping leggero o API gratuita).
    Se fallisce, ritorna None e usiamo i gol reali come fallback.
    """
    try:
        # Esempio di richiesta/scraping (adatta l'URL al tuo provider xG preferito)
        # url = f"https://.../team/{team_name}"
        # r = requests.get(url, timeout=3)
        # if r.status_code == 200:
        #     parsing della pagina...
        #     return {"xG_for": 1.45, "xG_against": 1.10}
        return None  # Placeholder se non implementato lo scraper specifico
    except Exception as e:
        # Logga silenziosamente o ignora, continuando con le API base
        return None


def safe_get_meteo(lat, lon, match_date):
    """
    Recupera il meteo tramite Open-Meteo (API gratuita, niente chiavi).
    Fallback: meteo neutro (temperatura 20°C, pioggia 0mm).
    """
    try:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,precipitation&start_date={match_date}&end_date={match_date}"
        r = requests.get(url, timeout=3)
        if r.status_code == 200:
            data = r.json()
            # Estrai temperatura media e pioggia
            temp = data["hourly"]["temperature_2m"][15]  # es. ore 15:00
            rain = sum(data["hourly"]["precipitation"])
            return {"temp": temp, "pioggia_mm": rain}
    except Exception:
        pass

    # Fallback sicuro
    return {"temp": 20.0, "pioggia_mm": 0.0}


def safe_get_arbitro_stats(arbitro_nome):
    """
    Cerca le medie dell'arbitro (falli/cartellini).
    Fallback: medie standard del campionato.
    """
    try:
        # Scraping o ricerca su database arbitri
        # ...
        return None
    except Exception:
        return None


def safe_get_indisponibili(team_name):
    """
    Cerca infortunati/squalificati chiave.
    Fallback: lista vuota (nessun peso sottratto al lambda).
    """
    try:
        # Scraping da siti sportivi
        return []
    except Exception:
        return []

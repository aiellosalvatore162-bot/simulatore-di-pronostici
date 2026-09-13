import numpy as np
from collections import Counter

# ---------------------------------------------------------------------------
# NUMERO DI SIMULAZIONI MONTE CARLO — FORZATO
# ---------------------------------------------------------------------------
# Prima questo era solo il valore di default del parametro `num_simulazioni`:
# se in futuro qualcuno avesse passato un numero diverso (o cambiato il
# default qui senza aggiornare NUM_SIMULAZIONI_TOTALI in app.py), il modello
# avrebbe eseguito silenziosamente meno simulazioni di quelle dichiarate
# all'utente, e i conteggi mostrati in dashboard (es. "32.150 / 50.000")
# sarebbero stati sbagliati.
#
# Ora è una costante esplicita e la funzione IGNORA sempre qualsiasi valore
# diverso venga passato: gira sempre e solo su 50.000 simulazioni.
SIMULAZIONI_MONTECARLO_FORZATE = 50000


def calcola_lambda_aggiustato(lam_offensiva, lam_difensiva_avversaria, fattore_campo=1.1, modifier_web=1.0):
    """
    Calcola il vero lambda atteso incrociando l'attacco di A con la difesa di B,
    applicando il fattore campo e i moltiplicatori esterni (xG, infortuni, meteo).
    """
    base = (lam_offensiva * lam_difensiva_avversaria) * fattore_campo
    return max(0.1, base * modifier_web)


def _valida_dato_reale(valore, nome_campo):
    """
    Validazione dei dati reali in ingresso.

    Il Monte Carlo deve girare su dati reali (lambda gol calcolati dalle
    statistiche vere delle squadre, medie angoli/cartellini reali), non su
    valori nulli, negativi o non numerici che produrrebbero una simulazione
    fittizia senza che nessuno se ne accorga. Meglio fallire subito con un
    errore chiaro piuttosto che restituire un risultato silenziosamente
    inventato.
    """
    try:
        valore_f = float(valore)
    except (TypeError, ValueError):
        raise ValueError(
            f"Dato non reale/non numerico per '{nome_campo}': {valore!r}. "
            f"Il modello richiede statistiche reali per generare le 50.000 simulazioni."
        )
    if valore_f <= 0:
        raise ValueError(
            f"Dato non valido per '{nome_campo}': {valore_f}. "
            f"Deve essere un valore reale positivo (lambda gol, media angoli o cartellini)."
        )
    return valore_f


def simula_partita_completa(
    lam_casa,
    lam_trasferta,
    # Parametri opzionali per la forza difensiva avversaria
    def_avversaria_casa=1.0,   # Difesa della squadra in trasferta
    def_avversaria_ospite=1.0, # Difesa della squadra in casa
    fattore_campo=1.15,
    modifier_web_casa=1.0,     # Es. derivato da xG o assenze (es. 0.90 se manca il bomber)
    modifier_web_ospite=1.0,
    lam_casa_pt=None,
    lam_trasferta_pt=None,
    media_angoli_casa=5.0,
    media_angoli_trasferta=4.5,
    media_cartellini_casa=2.2,
    media_cartellini_trasferta=2.5,
    num_simulazioni=SIMULAZIONI_MONTECARLO_FORZATE,
):
    # --- FORZATURA 50.000 SIMULAZIONI ---
    # Qualsiasi valore venga passato per `num_simulazioni` viene ignorato:
    # il modello Monte Carlo gira sempre su un campione di 50.000 esiti,
    # cosi il numero dichiarato in dashboard (NUM_SIMULAZIONI_TOTALI) e
    # quello realmente eseguito coincidono sempre.
    num_simulazioni = SIMULAZIONI_MONTECARLO_FORZATE

    # --- VALIDAZIONE DATI REALI IN INGRESSO ---
    lam_casa = _valida_dato_reale(lam_casa, "lam_casa")
    lam_trasferta = _valida_dato_reale(lam_trasferta, "lam_trasferta")
    media_angoli_casa = _valida_dato_reale(media_angoli_casa, "media_angoli_casa")
    media_angoli_trasferta = _valida_dato_reale(media_angoli_trasferta, "media_angoli_trasferta")
    media_cartellini_casa = _valida_dato_reale(media_cartellini_casa, "media_cartellini_casa")
    media_cartellini_trasferta = _valida_dato_reale(media_cartellini_trasferta, "media_cartellini_trasferta")

    # --- 0. ANCORAGGIO AI DATI REALI (Aggiustamento Poisson) ---
    # Invece di usare lam 'nudo', lo calcoliamo come Attacco_A * Difesa_B * Contesto_Web
    lam_casa_reale = calcola_lambda_aggiustato(
        lam_offensiva=lam_casa,
        lam_difensiva_avversaria=def_avversaria_casa,
        fattore_campo=fattore_campo,
        modifier_web=modifier_web_casa
    )

    lam_trasferta_reale = calcola_lambda_aggiustato(
        lam_offensiva=lam_trasferta,
        lam_difensiva_avversaria=def_avversaria_ospite,
        fattore_campo=1.0, # Il fattore campo non si applica agli ospiti
        modifier_web=modifier_web_ospite
    )

    # Se non specificati, stima del primo tempo come ~45% del dato reale complessivo
    if lam_casa_pt is None:
        lam_casa_pt = lam_casa_reale * 0.45
    if lam_trasferta_pt is None:
        lam_trasferta_pt = lam_trasferta_reale * 0.45

    # --- 1. SIMULAZIONE GOL FINALE (Poisson ricalibrata sui reali) ---
    gol_casa = np.random.poisson(lam_casa_reale, num_simulazioni)
    gol_trasferta = np.random.poisson(lam_trasferta_reale, num_simulazioni)
    gol_totali = gol_casa + gol_trasferta

    # Esito 1X2 Finale
    v_casa = int(np.sum(gol_casa > gol_trasferta))
    pareggi = int(np.sum(gol_casa == gol_trasferta))
    v_trasferta = int(np.sum(gol_casa < gol_trasferta))

    ris_1x2 = {
        "1": {"prob": round((v_casa / num_simulazioni) * 100, 2), "conteggio": v_casa},
        "X": {"prob": round((pareggi / num_simulazioni) * 100, 2), "conteggio": pareggi},
        "2": {"prob": round((v_trasferta / num_simulazioni) * 100, 2), "conteggio": v_trasferta}
    }

    # Risultato esatto più frequente
    coppie_risultati = [f"{c}-{t}" for c, t in zip(gol_casa, gol_trasferta)]
    conteggio_risultati = Counter(coppie_risultati)
    risultato_top, freq_top = conteggio_risultati.most_common(1)[0]
    risultato_piu_frequente = {
        "Risultato": risultato_top,
        # FIX: la chiave era "Probabilità" (con la P maiuscola e diversa da
        # tutte le altre sezioni), mentre app.py legge sempre "prob". Con la
        # chiave sbagliata, il "Risultato Esatto più frequente" veniva
        # mostrato sempre a 0% in dashboard. Ora è coerente col resto.
        "prob": round((freq_top / num_simulazioni) * 100, 2),
        "conteggio": freq_top,
        "Lambda_effettivo_casa": round(lam_casa_reale, 2),
        "Lambda_effettivo_ospite": round(lam_trasferta_reale, 2)
    }

    # --- 2. GOL / NO GOL FINALE ---
    c_gol = int(np.sum((gol_casa > 0) & (gol_trasferta > 0)))
    c_nogol = num_simulazioni - c_gol
    gol_nogol = {
        "Gol": {"prob": round((c_gol / num_simulazioni) * 100, 2)},
        "No Gol": {"prob": round((c_nogol / num_simulazioni) * 100, 2)}
    }

    # --- 3. UNDER / OVER FINALE (da 0.5 a 4.5) ---
    # FIX: prima questi valori erano numeri grezzi mentre altre sezioni
    # (1X2, Gol/No Gol) usavano {"prob": x}. Standardizzato per coerenza.
    under_over = {}
    for soglia in [0.5, 1.5, 2.5, 3.5, 4.5]:
        c_over = int(np.sum(gol_totali > soglia))
        c_under = num_simulazioni - c_over
        under_over[f"Over {soglia}"] = {"prob": round((c_over / num_simulazioni) * 100, 2)}
        under_over[f"Under {soglia}"] = {"prob": round((c_under / num_simulazioni) * 100, 2)}

    # --- 4. PRIMO TEMPO (PT) 1X2, GOL/NOGOL & UNDER/OVER (da 0.5 a 4.5) ---
    gol_casa_pt = np.random.poisson(lam_casa_pt, num_simulazioni)
    gol_trasferta_pt = np.random.poisson(lam_trasferta_pt, num_simulazioni)
    gol_totali_pt = gol_casa_pt + gol_trasferta_pt

    v_c_pt = int(np.sum(gol_casa_pt > gol_trasferta_pt))
    p_pt = int(np.sum(gol_casa_pt == gol_trasferta_pt))
    v_t_pt = int(np.sum(gol_casa_pt < gol_trasferta_pt))

    ris_1x2_pt = {
        "1 PT": {"prob": round((v_c_pt / num_simulazioni) * 100, 2)},
        "X PT": {"prob": round((p_pt / num_simulazioni) * 100, 2)},
        "2 PT": {"prob": round((v_t_pt / num_simulazioni) * 100, 2)}
    }

    c_gol_pt = int(np.sum((gol_casa_pt > 0) & (gol_trasferta_pt > 0)))
    c_nogol_pt = num_simulazioni - c_gol_pt
    gol_nogol_pt = {
        "Gol PT": {"prob": round((c_gol_pt / num_simulazioni) * 100, 2)},
        "No Gol PT": {"prob": round((c_nogol_pt / num_simulazioni) * 100, 2)}
    }

    under_over_pt = {}
    for soglia in [0.5, 1.5, 2.5, 3.5, 4.5]:
        c_over_pt = int(np.sum(gol_totali_pt > soglia))
        c_under_pt = num_simulazioni - c_over_pt
        under_over_pt[f"Over {soglia} PT"] = {"prob": round((c_over_pt / num_simulazioni) * 100, 2)}
        under_over_pt[f"Under {soglia} PT"] = {"prob": round((c_under_pt / num_simulazioni) * 100, 2)}

    # --- 5. MULTIGOL (Partita, Casa, Ospite) ---
    # Nota: qui i valori restano numeri grezzi (non {"prob": x}) perché
    # app.py renderizza questa sezione con un livello di annidamento in
    # più (categoria -> Partita/Casa/Ospite -> range) e si aspetta un
    # numero semplice come foglia finale.
    def calcola_multigol(array_gol):
        m = {}
        ranges = [
            ("0-1", 0, 1), ("1-2", 1, 2), ("1-3", 1, 3), ("1-4", 1, 4),
            ("2-3", 2, 3), ("2-4", 2, 4), ("2-5", 2, 5), ("3-6", 3, 6)
        ]
        for nome, inf, sup in ranges:
            c = int(np.sum((array_gol >= inf) & (array_gol <= sup)))
            m[nome] = round((c / num_simulazioni) * 100, 2)
        return m

    multigol = {
        "Partita": calcola_multigol(gol_totali),
        "Casa": calcola_multigol(gol_casa),
        "Ospite": calcola_multigol(gol_trasferta)
    }

    # --- 6. CALCI D'ANGOLO ---
    angoli_c = np.random.poisson(media_angoli_casa, num_simulazioni)
    angoli_t = np.random.poisson(media_angoli_trasferta, num_simulazioni)
    angoli_tot = angoli_c + angoli_t

    stat_angoli = {
        # Le medie NON sono percentuali: restano numeri semplici.
        "Media Angoli Casa": round(float(np.mean(angoli_c)), 2),
        "Media Angoli Ospite": round(float(np.mean(angoli_t)), 2),
        "Media Angoli Totali": round(float(np.mean(angoli_tot)), 2),
        # Le soglie Over sono probabilità: formato {"prob": x} per coerenza.
        "Over 8.5 Angoli Totali": {"prob": round((int(np.sum(angoli_tot > 8.5)) / num_simulazioni) * 100, 2)},
        "Over 9.5 Angoli Totali": {"prob": round((int(np.sum(angoli_tot > 9.5)) / num_simulazioni) * 100, 2)},
        "Over 10.5 Angoli Totali": {"prob": round((int(np.sum(angoli_tot > 10.5)) / num_simulazioni) * 100, 2)},
    }

    # --- 7. CARTELLINI ---
    cart_c = np.random.poisson(media_cartellini_casa, num_simulazioni)
    cart_t = np.random.poisson(media_cartellini_trasferta, num_simulazioni)
    cart_tot = cart_c + cart_t

    stat_cartellini = {
        "Media Cartellini Casa": round(float(np.mean(cart_c)), 2),
        "Media Cartellini Ospite": round(float(np.mean(cart_t)), 2),
        "Media Cartellini Totali": round(float(np.mean(cart_tot)), 2),
        "Over 3.5 Cartellini Totali": {"prob": round((int(np.sum(cart_tot > 3.5)) / num_simulazioni) * 100, 2)},
        "Over 4.5 Cartellini Totali": {"prob": round((int(np.sum(cart_tot > 4.5)) / num_simulazioni) * 100, 2)},
        "Over 5.5 Cartellini Totali": {"prob": round((int(np.sum(cart_tot > 5.5)) / num_simulazioni) * 100, 2)},
    }

    return {
        "1X2 Finale": ris_1x2,
        "Risultato Esatto più frequente": risultato_piu_frequente,
        "Gol / No Gol Finale": gol_nogol,
        "Under / Over Finale (0.5 - 4.5)": under_over,
        "1X2 Primo Tempo": ris_1x2_pt,
        "Gol / No Gol Primo Tempo": gol_nogol_pt,
        "Under / Over Primo Tempo (0.5 - 4.5)": under_over_pt,
        "Multigol": multigol,
        "Statistiche Angoli": stat_angoli,
        "Statistiche Cartellini": stat_cartellini
    }
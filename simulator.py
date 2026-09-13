import numpy as np
from collections import Counter

def simula_partita_completa(
    lam_casa,
    lam_trasferta,
    lam_casa_pt=None,
    lam_trasferta_pt=None,
    media_angoli_casa=5.0,
    media_angoli_trasferta=4.5,
    media_cartellini_casa=2.2,
    media_cartellini_trasferta=2.5,
    num_simulazioni=50000
):
    # Se non specificati, stima del primo tempo come ~45% del dato complessivo
    if lam_casa_pt is None:
        lam_casa_pt = lam_casa * 0.45
    if lam_trasferta_pt is None:
        lam_trasferta_pt = lam_trasferta * 0.45

    # --- 1. SIMULAZIONE GOL FINALE (Poisson) ---
    gol_casa = np.random.poisson(lam_casa, num_simulazioni)
    gol_trasferta = np.random.poisson(lam_trasferta, num_simulazioni)
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
        "Probabilità": round((freq_top / num_simulazioni) * 100, 2),
        "Conteggio": freq_top
    }

    # --- 2. GOL / NO GOL FINALE ---
    c_gol = int(np.sum((gol_casa > 0) & (gol_trasferta > 0)))
    c_nogol = num_simulazioni - c_gol
    gol_nogol = {
        "Gol": {"prob": round((c_gol / num_simulazioni) * 100, 2)},
        "No Gol": {"prob": round((c_nogol / num_simulazioni) * 100, 2)}
    }

    # --- 3. UNDER / OVER FINALE (da 0.5 a 4.5) ---
    under_over = {}
    for soglia in [0.5, 1.5, 2.5, 3.5, 4.5]:
        c_over = int(np.sum(gol_totali > soglia))
        c_under = num_simulazioni - c_over
        under_over[f"Over {soglia}"] = round((c_over / num_simulazioni) * 100, 2)
        under_over[f"Under {soglia}"] = round((c_under / num_simulazioni) * 100, 2)

    # --- 4. PRIMO TEMPO (PT) 1X2, GOL/NOGOL & UNDER/OVER (da 0.5 a 4.5) ---
    gol_casa_pt = np.random.poisson(lam_casa_pt, num_simulazioni)
    gol_trasferta_pt = np.random.poisson(lam_trasferta_pt, num_simulazioni)
    gol_totali_pt = gol_casa_pt + gol_trasferta_pt

    v_c_pt = int(np.sum(gol_casa_pt > gol_trasferta_pt))
    p_pt = int(np.sum(gol_casa_pt == gol_trasferta_pt))
    v_t_pt = int(np.sum(gol_casa_pt < gol_trasferta_pt))

    ris_1x2_pt = {
        "1 PT": round((v_c_pt / num_simulazioni) * 100, 2),
        "X PT": round((p_pt / num_simulazioni) * 100, 2),
        "2 PT": round((v_t_pt / num_simulazioni) * 100, 2)
    }

    c_gol_pt = int(np.sum((gol_casa_pt > 0) & (gol_trasferta_pt > 0)))
    c_nogol_pt = num_simulazioni - c_gol_pt
    gol_nogol_pt = {
        "Gol PT": round((c_gol_pt / num_simulazioni) * 100, 2),
        "No Gol PT": round((c_nogol_pt / num_simulazioni) * 100, 2)
    }

    under_over_pt = {}
    for soglia in [0.5, 1.5, 2.5, 3.5, 4.5]:
        c_over_pt = int(np.sum(gol_totali_pt > soglia))
        c_under_pt = num_simulazioni - c_over_pt
        under_over_pt[f"Over {soglia} PT"] = round((c_over_pt / num_simulazioni) * 100, 2)
        under_over_pt[f"Under {soglia} PT"] = round((c_under_pt / num_simulazioni) * 100, 2)

    # --- 5. MULTIGOL (Partita, Casa, Ospite) ---
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

    # --- 6. CALCI D'ANGOLO (variabili per squadra e totali) ---
    angoli_c = np.random.poisson(media_angoli_casa, num_simulazioni)
    angoli_t = np.random.poisson(media_angoli_trasferta, num_simulazioni)
    angoli_tot = angoli_c + angoli_t

    stat_angoli = {
        "Media Angoli Casa": round(float(np.mean(angoli_c)), 2),
        "Media Angoli Ospite": round(float(np.mean(angoli_t)), 2),
        "Media Angoli Totali": round(float(np.mean(angoli_tot)), 2),
        "Over 8.5 Angoli Totali": round((int(np.sum(angoli_tot > 8.5)) / num_simulazioni) * 100, 2),
        "Over 9.5 Angoli Totali": round((int(np.sum(angoli_tot > 9.5)) / num_simulazioni) * 100, 2),
        "Over 10.5 Angoli Totali": round((int(np.sum(angoli_tot > 10.5)) / num_simulazioni) * 100, 2),
    }

    # --- 7. CARTELLINI (variabili per squadra e totali) ---
    cart_c = np.random.poisson(media_cartellini_casa, num_simulazioni)
    cart_t = np.random.poisson(media_cartellini_trasferta, num_simulazioni)
    cart_tot = cart_c + cart_t

    stat_cartellini = {
        "Media Cartellini Casa": round(float(np.mean(cart_c)), 2),
        "Media Cartellini Ospite": round(float(np.mean(cart_t)), 2),
        "Media Cartellini Totali": round(float(np.mean(cart_tot)), 2),
        "Over 3.5 Cartellini Totali": round((int(np.sum(cart_tot > 3.5)) / num_simulazioni) * 100, 2),
        "Over 4.5 Cartellini Totali": round((int(np.sum(cart_tot > 4.5)) / num_simulazioni) * 100, 2),
        "Over 5.5 Cartellini Totali": round((int(np.sum(cart_tot > 5.5)) / num_simulazioni) * 100, 2),
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

import numpy as np

def simula_partita_avanzata(
    lam_casa, lam_trasferta, 
    media_angoli_casa=5.0, media_angoli_trasferta=4.5,
    media_cartellini_casa=2.2, media_cartellini_trasferta=2.5,
    giocatori_casa=None, 
    num_simulazioni=10000
):
    # --- 1. SIMULAZIONE GOL FINALE (Poisson) ---
    gol_casa = np.random.poisson(lam_casa, num_simulazioni)
    gol_trasferta = np.random.poisson(lam_trasferta, num_simulazioni)
    gol_totali = gol_casa + gol_trasferta
    
    # Esito 1X2 Finale
    v_casa = int(np.sum(gol_casa > gol_trasferta))
    pareggi = int(np.sum(gol_casa == gol_trasferta))
    v_trasferta = int(np.sum(gol_casa < gol_trasferta))
    
    ris_1x2 = {
        "1": {"prob": round((v_casa / num_simulazioni) * 100, 2), "spiegazione": f"Verificato {v_casa} volte su {num_simulazioni} simulazioni"},
        "X": {"prob": round((pareggi / num_simulazioni) * 100, 2), "spiegazione": f"Verificato {pareggi} volte su {num_simulazioni} simulazioni"},
        "2": {"prob": round((v_trasferta / num_simulazioni) * 100, 2), "spiegazione": f"Verificato {v_trasferta} volte su {num_simulazioni} simulazioni"}
    }
    
    # --- 2. GOL / NO GOL FINALE ---
    c_gol = int(np.sum((gol_casa > 0) & (gol_trasferta > 0)))
    c_nogol = int(np.sum((gol_casa == 0) | (gol_trasferta == 0)))
    gol_nogol = {
        "Gol": {"prob": round((c_gol / num_simulazioni) * 100, 2), "spiegazione": f"Entrambe hanno segnato in {c_gol} simulazioni su {num_simulazioni}"},
        "No Gol": {"prob": round((c_nogol / num_simulazioni) * 100, 2), "spiegazione": f"Almeno una squadra a 0 in {c_nogol} simulazioni su {num_simulazioni}"}
    }
    
    # --- 3. UNDER / OVER FINALE (da 0.5 a 4.5) ---
    under_over = {}
    for soglia in [0.5, 1.5, 2.5, 3.5, 4.5]:
        c_over = int(np.sum(gol_totali > soglia))
        c_under = num_simulazioni - c_over
        under_over[f"Over {soglia}"] = {"prob": round((c_over / num_simulazioni) * 100, 2), "spiegazione": f"Gol totali > {soglia} in {c_over} simulazioni"}
        under_over[f"Under {soglia}"] = {"prob": round((c_under / num_simulazioni) * 100, 2), "spiegazione": f"Gol totali <= {soglia} in {c_under} simulazioni"}

    # --- 4. PRIMO TEMPO (PT) ---
    lam_casa_pt = lam_casa * 0.45
    lam_trasferta_pt = lam_trasferta * 0.45
    gol_casa_pt = np.random.poisson(lam_casa_pt, num_simulazioni)
    gol_trasferta_pt = np.random.poisson(lam_trasferta_pt, num_simulazioni)
    gol_totali_pt = gol_casa_pt + gol_trasferta_pt
    
    v_c_pt = int(np.sum(gol_casa_pt > gol_trasferta_pt))
    p_pt = int(np.sum(gol_casa_pt == gol_trasferta_pt))
    v_t_pt = int(np.sum(gol_casa_pt < gol_trasferta_pt))
    
    ris_1x2_pt = {
        "1 PT": {"prob": round((v_c_pt / num_simulazioni) * 100, 2), "spiegazione": f"Verificato {v_c_pt} volte nel primo tempo"},
        "X PT": {"prob": round((p_pt / num_simulazioni) * 100, 2), "spiegazione": f"Verificato {p_pt} volte nel primo tempo"},
        "2 PT": {"prob": round((v_t_pt / num_simulazioni) * 100, 2), "spiegazione": f"Verificato {v_t_pt} volte nel primo tempo"}
    }

    # --- 5. MULTIGOL ---
    def calcola_multigol(array_gol):
        m = {}
        ranges = [("1-2", 1, 2), ("1-3", 1, 3), ("2-3", 2, 3), ("2-4", 2, 4), ("1-4", 1, 4), ("3-6", 3, 6)]
        for nome, inf, sup in ranges:
            c = int(np.sum((array_gol >= inf) & (array_gol <= sup)))
            m[nome] = {"prob": round((c / num_simulazioni) * 100, 2), "spiegazione": f"Uscito {c} volte su {num_simulazioni}"}
        return m

    multigol = {
        "Multigol Partita": calcola_multigol(gol_totali),
        "Multigol Casa": calcola_multigol(gol_casa),
        "Multigol Ospite": calcola_multigol(gol_trasferta)
    }

    # --- 6. STATISTICHE EXTRA (Angoli e Cartellini) ---
    angoli_t = np.random.poisson(media_angoli_casa, num_simulazioni) + np.random.poisson(media_angoli_trasferta, num_simulazioni)
    cartellini_t = np.random.poisson(media_cartellini_casa, num_simulazioni) + np.random.poisson(media_cartellini_trasferta, num_simulazioni)
    
    c_ang_95 = int(np.sum(angoli_t > 9.5))
    c_cart_35 = int(np.sum(cartellini_t > 3.5))

    statistiche_extra = {
        "Media Angoli Totali stimati": round(float(np.mean(angoli_t)), 1),
        "Over 9.5 Angoli": {"prob": round((c_ang_95 / num_simulazioni) * 100, 2), "spiegazione": f"Superato 9.5 angoli in {c_ang_95} simulazioni"},
        "Media Cartellini Totali stimati": round(float(np.mean(cartellini_t)), 1),
        "Over 3.5 Cartellini": {"prob": round((c_cart_35 / num_simulazioni) * 100, 2), "spiegazione": f"Superato 3.5 cartellini in {c_cart_35} simulazioni"}
    }

    # --- 7. MARCATORI E TIRI IN PORTA ---
    report_giocatori = []
    if giocatori_casa:
        for g in giocatori_casa:
            tiri_sim = np.random.poisson(g['media_tiri_porta'], num_simulazioni)
            c_tiro1 = int(np.sum(tiri_sim >= 1))
            gol_giocatore = np.random.binomial(tiri_sim, g['prob_conversione'])
            c_gol_gioc = int(np.sum(gol_giocatore >= 1))
            
            report_giocatori.append({
                "Giocatore": g['nome'],
                "Almeno 1 tiro in porta": {"prob": round((c_tiro1 / num_simulazioni) * 100, 2), "spiegazione": f"Verificato in {c_tiro1} simulazioni"},
                "Gol (Marcatore)": {"prob": round((c_gol_gioc / num_simulazioni) * 100, 2), "spiegazione": f"Segnato in {c_gol_gioc} simulazioni"}
            })

    return {
        "1X2 Finale": ris_1x2,
        "1X2 Primo Tempo": ris_1x2_pt,
        "Gol / No Gol Finale": gol_nogol,
        "Under / Over Finale": under_over,
        "Multigol": multigol,
        "Statistiche Extra": statistiche_extra,
        "Analisi Giocatori": report_giocatori
    } 
from simulator import simula_partita_avanzata

attaccanti_casa = [
    {"nome": "Bomber Casa", "media_tiri_porta": 1.8, "prob_conversione": 0.35}
]

risultati_match = simula_partita_avanzata(
    lam_casa=1.65, 
    lam_trasferta=1.10,
    giocatori_casa=attaccanti_casa
)

print("=== REPORT MONTE CARLO CON SPIEGAZIONE STATISTICA ===")
for categoria, dati in risultati_match.items():
    print(f"\n[{categoria}]")
    if isinstance(dati, dict):
        for chiave, valore in dati.items():
            if isinstance(valore, dict) and 'prob' in valore:
                print(f"  - {chiave}: {valore['prob']}% -> {valore['spiegazione']}")
            elif isinstance(valore, dict):
                # Gestione dei dizionari annidati (es. Multigol)
                print(f"  [{chiave}]")
                for sub_k, sub_v in valore.items():
                    print(f"    - {sub_k}: {sub_v['prob']}% -> {sub_v['spiegazione']}")
            else:
                print(f"  - {chiave}: {valore}")
    elif isinstance(dati, list):
        for item in dati:
            print(f"  - Giocatore: {item['Giocatore']}")
            for k, v in item.items():
                if k != "Giocatore":
                    print(f"    * {k}: {v['prob']}% -> {v['spiegazione']}")
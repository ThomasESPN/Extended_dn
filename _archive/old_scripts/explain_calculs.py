"""
Explication Interactive des Calculs
Montre étape par étape comment le profit est calculé
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.data.loris_api import get_loris_api


def explain_calculation(symbol="ARK", position_size=10000):
    """Explique les calculs pour un symbole donné"""
    
    print("\n" + "="*100)
    print(f"🧮 EXPLICATION DES CALCULS POUR {symbol}")
    print("="*100 + "\n")
    
    # Récupérer les données
    loris = get_loris_api()
    data = loris.fetch_all_funding_rates()
    
    if not data:
        print("❌ Erreur de connexion à Loris Tools")
        return
    
    # Trouver les meilleurs rates
    extended_exchanges = loris.get_extended_like_exchanges(data)
    variational_exchanges = loris.get_variational_like_exchanges(data)
    
    print(f"📊 Symbole: {symbol}")
    print(f"💵 Taille position: ${position_size:,}\n")
    
    # Extended (1h)
    best_ext_rate = None
    best_ext_exchange = None
    
    print("🔍 Recherche du meilleur rate 1h parmi les exchanges Extended-like:")
    for i, exchange in enumerate(extended_exchanges, 1):
        rate = loris.get_funding_rate(data, exchange, symbol)
        if rate is not None:
            exchange_name = exchange.split('_')[0].upper()
            print(f"   {i}. {exchange_name:15} : {rate:+.6f}")
            
            if best_ext_rate is None or rate < best_ext_rate:
                best_ext_rate = rate
                best_ext_exchange = exchange_name
    
    print(f"\n   ✅ Meilleur 1h: {best_ext_exchange} @ {best_ext_rate:+.6f}\n")
    
    # Variational (8h)
    best_var_rate = None
    best_var_exchange = None
    
    print("🔍 Recherche du meilleur rate 8h parmi les exchanges Variational-like:")
    for i, exchange in enumerate(variational_exchanges[:10], 1):  # Afficher top 10
        rate = loris.get_funding_rate(data, exchange, symbol)
        if rate is not None:
            exchange_name = exchange.split('_')[0].upper()
            print(f"   {i}. {exchange_name:15} : {rate:+.6f}")
            
            if best_var_rate is None or rate < best_var_rate:
                best_var_rate = rate
                best_var_exchange = exchange_name
    
    print(f"\n   ✅ Meilleur 8h: {best_var_exchange} @ {best_var_rate:+.6f}\n")
    
    # Déterminer le type
    if best_ext_rate < 0 and best_var_rate < 0:
        position_type = "both_negative"
    elif best_ext_rate > 0 and best_var_rate > 0:
        position_type = "both_positive"
    elif best_ext_rate < 0 and best_var_rate > 0:
        position_type = "standard"
    else:
        position_type = "mixed"
    
    print("="*100)
    print("🧮 CALCULS ÉTAPE PAR ÉTAPE")
    print("="*100 + "\n")
    
    # Étape 1: Paiements unitaires
    print("📍 ÉTAPE 1: Calcul des paiements unitaires")
    print("-" * 100)
    
    ext_payment = position_size * abs(best_ext_rate)
    var_payment = position_size * abs(best_var_rate)
    
    print(f"\n   Extended (1h):")
    print(f"   Payment = Position × |Rate|")
    print(f"   Payment = ${position_size:,} × {abs(best_ext_rate):.6f}")
    print(f"   Payment = ${ext_payment:.2f} par paiement")
    
    print(f"\n   Variational (8h):")
    print(f"   Payment = Position × |Rate|")
    print(f"   Payment = ${position_size:,} × {abs(best_var_rate):.6f}")
    print(f"   Payment = ${var_payment:.2f} par paiement\n")
    
    # Étape 2: Nombre de paiements
    print("📍 ÉTAPE 2: Nombre de paiements sur 8h")
    print("-" * 100)
    
    num_ext_payments = 8  # 8h / 1h
    
    print(f"\n   Extended paie toutes les 1h")
    print(f"   Sur 8h → {num_ext_payments} paiements\n")
    print(f"   Variational paie toutes les 8h")
    print(f"   Sur 8h → 1 paiement\n")
    
    # Étape 3: Stratégie
    print("📍 ÉTAPE 3: Calcul selon la stratégie")
    print("-" * 100)
    print(f"\n   Type détecté: {position_type}\n")
    
    if position_type == "both_negative":
        print("   🎯 STRATÉGIE: Both Negative")
        print("   " + "─" * 96)
        print(f"   LONG {best_ext_exchange} @ {best_ext_rate:.6f} (négatif → on REÇOIT)")
        print(f"   SHORT {best_var_exchange} @ {best_var_rate:.6f} (négatif → on REÇOIT aussi)\n")
        
        # Option A: Full cycle
        print("   ▶️  Option A: FULL CYCLE (rester 8h)")
        total_ext = ext_payment * num_ext_payments
        profit_full = total_ext - var_payment
        
        print(f"      Extended:     {num_ext_payments} paiements × ${ext_payment:.2f} = +${total_ext:.2f}")
        print(f"      Variational:  1 paiement × ${var_payment:.2f} = -${var_payment:.2f}")
        print(f"      TOTAL:        ${profit_full:.2f}")
        print(f"      Par heure:    ${profit_full/8:.2f}/h\n")
        
        # Option B: Early close
        print("   ▶️  Option B: EARLY CLOSE (fermer à 7h avant Variational) ⭐")
        num_early = num_ext_payments - 1
        total_ext_early = ext_payment * num_early
        profit_early = total_ext_early
        
        print(f"      Extended:     {num_early} paiements × ${ext_payment:.2f} = +${total_ext_early:.2f}")
        print(f"      Variational:  0 paiement (fermé avant!) = $0.00")
        print(f"      TOTAL:        ${profit_early:.2f}")
        print(f"      Par heure:    ${profit_early/7:.2f}/h ← MEILLEUR!\n")
        
        # Comparaison
        print("   📊 COMPARAISON:")
        print(f"      Full cycle:   ${profit_full/8:.2f}/h")
        print(f"      Early close:  ${profit_early/7:.2f}/h ← Le bot choisit ça!\n")
        
        best_profit = profit_early
        best_strategy = "early_close"
        best_hours = 7
        
    elif position_type == "standard":
        print("   🎯 STRATÉGIE: Standard")
        print("   " + "─" * 96)
        
        if best_ext_rate < 0:
            print(f"   LONG {best_ext_exchange} @ {best_ext_rate:.6f} (négatif → on REÇOIT)")
            print(f"   SHORT {best_var_exchange} @ {best_var_rate:.6f} (positif → on REÇOIT)\n")
            
            total_ext = ext_payment * num_ext_payments
            profit_full = total_ext + var_payment
        else:
            print(f"   SHORT {best_ext_exchange} @ {best_ext_rate:.6f}")
            print(f"   LONG {best_var_exchange} @ {best_var_rate:.6f}\n")
            
            total_ext = ext_payment * num_ext_payments
            profit_full = var_payment - total_ext
        
        print(f"      Extended:     {num_ext_payments} paiements × ${ext_payment:.2f} = ${total_ext:.2f}")
        print(f"      Variational:  1 paiement × ${var_payment:.2f} = ${var_payment:.2f}")
        print(f"      TOTAL:        ${profit_full:.2f}")
        print(f"      Par heure:    ${profit_full/8:.2f}/h\n")
        
        best_profit = profit_full
        best_strategy = "full_cycle"
        best_hours = 8
    
    else:
        print(f"   Stratégie {position_type} - Voir code pour détails\n")
        best_profit = 0
        best_strategy = "unknown"
        best_hours = 8
    
    # Résumé final
    print("="*100)
    print("💰 RÉSULTAT FINAL")
    print("="*100 + "\n")
    
    print(f"   Symbole:          {symbol}")
    print(f"   Position:         ${position_size:,}")
    print(f"   Type:             {position_type}")
    print(f"   Stratégie:        {best_strategy}")
    print(f"   Profit total:     ${best_profit:.2f}")
    print(f"   Durée:            {best_hours}h")
    print(f"   Profit/heure:     ${best_profit/best_hours:.2f}/h")
    print("\n" + "="*100 + "\n")
    
    print("✅ Voilà comment le calcul est fait !")
    print("🔗 Données de https://api.loris.tools/funding")
    print(f"📊 {len(extended_exchanges)} exchanges 1h analysés")
    print(f"📊 {len(variational_exchanges)} exchanges 8h analysés\n")


def show_timeline(symbol="ARK", ext_payment=58.90, hours=7):
    """Affiche une timeline visuelle"""
    
    print("\n" + "="*100)
    print(f"📅 TIMELINE {symbol} - Stratégie Early Close")
    print("="*100 + "\n")
    
    total = 0
    
    print("   Heure    Extended    Variational    Cumul      Action")
    print("   " + "─" * 90)
    
    for h in range(hours):
        total += ext_payment
        print(f"   {h:02d}:00    +${ext_payment:6.2f}     -              ${total:7.2f}    ✅ Reçu Extended")
    
    print("   " + "─" * 90)
    print(f"   {hours:02d}:00    -            -              ${total:7.2f}    🚪 FERMETURE")
    print("   " + "─" * 90)
    print(f"   08:00    +${ext_payment:6.2f}     -$88.10        -          ❌ Évité (déjà fermé)")
    print("\n   " + "─" * 90)
    print(f"   TOTAL:   ${total:.2f} sur {hours}h = ${total/hours:.2f}/h")
    print("\n" + "="*100 + "\n")


if __name__ == "__main__":
    import sys
    
    # Symbole passé en argument ou ARK par défaut
    symbol = sys.argv[1] if len(sys.argv) > 1 else "ARK"
    
    explain_calculation(symbol, position_size=10000)
    
    # Timeline pour ARK
    if symbol == "ARK":
        show_timeline("ARK", ext_payment=58.90, hours=7)
    
    print("\n💡 Pour tester un autre symbole:")
    print(f"   py explain_calculs.py BTC")
    print(f"   py explain_calculs.py ETH")
    print(f"   py explain_calculs.py DOOD\n")

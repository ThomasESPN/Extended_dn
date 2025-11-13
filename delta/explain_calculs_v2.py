"""
Explication Interactive des Calculs - VERSION EXTENDED + VARIATIONAL UNIQUEMENT
Montre étape par étape comment le profit est calculé entre Extended et Variational
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.data.loris_api import get_loris_api


def explain_calculation(symbol="AVNT", position_size=10000):
    """Explique les calculs pour un symbole donné entre Extended et Variational"""
    
    print("\n" + "="*100)
    print(f"🧮 EXPLICATION DES CALCULS POUR {symbol} (Extended vs Variational)")
    print("="*100 + "\n")
    
    # Récupérer les données
    loris = get_loris_api()
    data = loris.fetch_all_funding_rates()
    
    if not data:
        print("❌ Erreur de connexion à Loris Tools")
        return
    
    print(f"📊 Symbole: {symbol}")
    print(f"💵 Taille position: ${position_size:,}\n")
    
    # Chercher Extended et Variational
    exchanges_info = loris.get_exchange_info(data)
    
    extended_rate = None
    variational_rate = None
    extended_exchange = None
    variational_exchange = None
    
    print("🔍 Récupération des funding rates:")
    
    for exchange_name, info in exchanges_info.items():
        base = exchange_name.split('_')[0].lower()
        
        if base == 'extended':
            extended_rate = loris.get_funding_rate(data, exchange_name, symbol)
            extended_exchange = exchange_name.split('_')[0].upper()
            if extended_rate is not None:
                print(f"   ✅ Extended (1h):    {extended_rate:+.6f}")
        
        elif base == 'variational':
            variational_rate = loris.get_funding_rate(data, exchange_name, symbol)
            variational_exchange = exchange_name.split('_')[0].upper()
            if variational_rate is not None:
                print(f"   ✅ Variational (8h): {variational_rate:+.6f}")
    
    if extended_rate is None or variational_rate is None:
        print(f"\n❌ Funding rates incomplets pour {symbol}")
        print(f"   Extended: {extended_rate}")
        print(f"   Variational: {variational_rate}")
        return
    
    # Déterminer le type
    if extended_rate < 0 and variational_rate < 0:
        position_type = "both_negative"
    elif extended_rate > 0 and variational_rate > 0:
        position_type = "both_positive"
    elif extended_rate < 0 and variational_rate > 0:
        position_type = "standard"
    else:
        position_type = "mixed"
    
    print("\n" + "="*100)
    print("🧮 CALCULS ÉTAPE PAR ÉTAPE")
    print("="*100 + "\n")
    
    print("📍 ÉTAPE 1: Calcul des paiements unitaires")
    print("-"*100 + "\n")
    
    # Paiement Extended
    extended_payment = abs(extended_rate) * position_size
    print(f"   Extended (1h):")
    print(f"   Payment = Position × |Rate|")
    print(f"   Payment = ${position_size:,} × {abs(extended_rate):.6f}")
    print(f"   Payment = ${extended_payment:.2f} par paiement")
    
    print()
    
    # Paiement Variational
    variational_payment = abs(variational_rate) * position_size
    print(f"   Variational (8h):")
    print(f"   Payment = Position × |Rate|")
    print(f"   Payment = ${position_size:,} × {abs(variational_rate):.6f}")
    print(f"   Payment = ${variational_payment:.2f} par paiement")
    
    print("\n📍 ÉTAPE 2: Nombre de paiements sur 8h")
    print("-"*100 + "\n")
    
    print(f"   Extended paie toutes les 1h")
    print(f"   Sur 8h → 8 paiements")
    print()
    print(f"   Variational paie toutes les 8h")
    print(f"   Sur 8h → 1 paiement")
    
    print("\n📍 ÉTAPE 3: Calcul selon la stratégie")
    print("-"*100 + "\n")
    
    print(f"   Type détecté: {position_type}\n")
    
    # Calcul selon le type
    if position_type == "both_negative":
        print("   🎯 STRATÉGIE: Both Negative")
        print("   " + "─"*96)
        print(f"   LONG {extended_exchange} @ {extended_rate:+.6f} (négatif → on REÇOIT)")
        print(f"   SHORT {variational_exchange} @ {variational_rate:+.6f} (négatif → on REÇOIT aussi)")
        print()
        
        # Full cycle
        extended_total = 8 * extended_payment
        variational_total = -variational_payment  # On reçoit mais on paie si on reste
        full_cycle = extended_total + variational_total
        full_cycle_per_hour = full_cycle / 8
        
        print(f"   ▶️  Option A: FULL CYCLE (rester 8h)")
        print(f"      Extended:     8 paiements × ${extended_payment:.2f} = +${extended_total:.2f}")
        print(f"      Variational:  1 paiement × ${variational_payment:.2f} = -${variational_payment:.2f}")
        print(f"      TOTAL:        ${full_cycle:.2f}")
        print(f"      Par heure:    ${full_cycle_per_hour:.2f}/h")
        print()
        
        # Early close
        early_close_payments = 7
        early_close_total = early_close_payments * extended_payment
        early_close_per_hour = early_close_total / 7
        
        print(f"   ▶️  Option B: EARLY CLOSE (fermer à 7h avant Variational) ⭐")
        print(f"      Extended:     {early_close_payments} paiements × ${extended_payment:.2f} = +${early_close_total:.2f}")
        print(f"      Variational:  0 paiement (fermé avant!) = $0.00")
        print(f"      TOTAL:        ${early_close_total:.2f}")
        print(f"      Par heure:    ${early_close_per_hour:.2f}/h ← MEILLEUR!")
        print()
        
        best_profit = early_close_total
        best_duration = 7
        best_per_hour = early_close_per_hour
        best_strategy = "early_close"
        
        print(f"   📊 COMPARAISON:")
        print(f"      Full cycle:   ${full_cycle_per_hour:.2f}/h")
        print(f"      Early close:  ${early_close_per_hour:.2f}/h ← Le bot choisit ça!")
    
    elif position_type == "both_positive":
        print("   🎯 STRATÉGIE: Both Positive")
        print("   " + "─"*96)
        print(f"   SHORT {extended_exchange} @ {extended_rate:+.6f} (positif → on REÇOIT)")
        print(f"   LONG {variational_exchange} @ {variational_rate:+.6f} (positif → on PAIE)")
        print()
        
        # Early close
        early_close_payments = 7
        early_close_total = early_close_payments * extended_payment
        early_close_per_hour = early_close_total / 7
        
        print(f"   ▶️  EARLY CLOSE (fermer à 7h avant Variational) ⭐")
        print(f"      Extended:     {early_close_payments} paiements × ${extended_payment:.2f} = +${early_close_total:.2f}")
        print(f"      Variational:  0 paiement (fermé avant!) = $0.00")
        print(f"      TOTAL:        ${early_close_total:.2f}")
        print(f"      Par heure:    ${early_close_per_hour:.2f}/h")
        
        best_profit = early_close_total
        best_duration = 7
        best_per_hour = early_close_per_hour
        best_strategy = "early_close"
    
    elif position_type == "standard":
        print("   🎯 STRATÉGIE: Standard (Extended négatif, Variational positif)")
        print("   " + "─"*96)
        print(f"   LONG {extended_exchange} @ {extended_rate:+.6f} (négatif → on REÇOIT)")
        print(f"   SHORT {variational_exchange} @ {variational_rate:+.6f} (positif → on REÇOIT)")
        print()
        
        # Full cycle
        extended_total = 8 * extended_payment
        variational_total = variational_payment
        full_cycle = extended_total + variational_total
        full_cycle_per_hour = full_cycle / 8
        
        print(f"   ▶️  FULL CYCLE (rester 8h) ⭐")
        print(f"      Extended:     8 paiements × ${extended_payment:.2f} = +${extended_total:.2f}")
        print(f"      Variational:  1 paiement × ${variational_payment:.2f} = +${variational_payment:.2f}")
        print(f"      TOTAL:        ${full_cycle:.2f}")
        print(f"      Par heure:    ${full_cycle_per_hour:.2f}/h")
        
        best_profit = full_cycle
        best_duration = 8
        best_per_hour = full_cycle_per_hour
        best_strategy = "full_cycle"
    
    else:  # mixed
        print("   🎯 STRATÉGIE: Mixed")
        print("   " + "─"*96)
        
        if extended_rate > 0:
            print(f"   SHORT {extended_exchange} @ {extended_rate:+.6f} (positif → on REÇOIT)")
            print(f"   LONG {variational_exchange} @ {variational_rate:+.6f} (négatif → on REÇOIT)")
        else:
            print(f"   LONG {extended_exchange} @ {extended_rate:+.6f} (négatif → on REÇOIT)")
            print(f"   SHORT {variational_exchange} @ {variational_rate:+.6f} (positif → on REÇOIT)")
        
        print()
        
        # Full cycle
        extended_total = 8 * extended_payment
        variational_total = variational_payment
        full_cycle = extended_total + variational_total
        full_cycle_per_hour = full_cycle / 8
        
        print(f"   ▶️  FULL CYCLE (rester 8h) ⭐")
        print(f"      Extended:     8 paiements × ${extended_payment:.2f} = +${extended_total:.2f}")
        print(f"      Variational:  1 paiement × ${variational_payment:.2f} = +${variational_payment:.2f}")
        print(f"      TOTAL:        ${full_cycle:.2f}")
        print(f"      Par heure:    ${full_cycle_per_hour:.2f}/h")
        
        best_profit = full_cycle
        best_duration = 8
        best_per_hour = full_cycle_per_hour
        best_strategy = "full_cycle"
    
    print("\n" + "="*100)
    print("💰 RÉSULTAT FINAL")
    print("="*100 + "\n")
    
    print(f"   Symbole:          {symbol}")
    print(f"   Position:         ${position_size:,}")
    print(f"   Type:             {position_type}")
    print(f"   Stratégie:        {best_strategy}")
    print(f"   Profit total:     ${best_profit:.2f}")
    print(f"   Durée:            {best_duration}h")
    print(f"   Profit/heure:     ${best_per_hour:.2f}/h")
    
    print("\n" + "="*100 + "\n")
    
    print("✅ Voilà comment le calcul est fait !")
    print("🔗 Données de https://api.loris.tools/funding")
    print("📊 Extended (1h) vs Variational (8h) uniquement")
    
    # Timeline
    show_timeline(symbol, extended_payment, variational_payment, extended_rate, variational_rate, best_strategy)


def show_timeline(symbol, ext_payment, var_payment, ext_rate, var_rate, strategy):
    """Affiche la timeline heure par heure"""
    
    print("\n" + "="*100)
    print(f"📅 TIMELINE {symbol} - Stratégie {strategy.replace('_', ' ').title()}")
    print("="*100 + "\n")
    
    print(f"   Heure    Extended    Variational    Cumul      Action")
    print("   " + "─"*94)
    
    cumul = 0
    
    for hour in range(8):
        ext_str = f"+$ {ext_payment:.2f}" if ext_rate < 0 else f"-$ {ext_payment:.2f}"
        var_str = "-"
        action = f"✅ {'Reçu' if ext_rate < 0 else 'Payé'} Extended"
        
        cumul += ext_payment if ext_rate < 0 else -ext_payment
        
        print(f"   {hour:02d}:00    {ext_str:12} {var_str:14} $ {cumul:7.2f}    {action}")
        
        if strategy == "early_close" and hour == 6:
            print("   " + "─"*94)
            print(f"   07:00    -            -              $ {cumul:7.2f}    🚪 FERMETURE")
            print("   " + "─"*94)
            
            var_str = f"-${var_payment:.2f}" if var_rate < 0 else f"+${var_payment:.2f}"
            print(f"   08:00    +$ {ext_payment:.2f}    {var_str:14} -          ❌ Évité (déjà fermé)")
            break
    
    if strategy == "full_cycle":
        var_str = f"-${var_payment:.2f}" if var_rate < 0 else f"+${var_payment:.2f}"
        var_impact = -var_payment if var_rate < 0 else var_payment
        cumul += var_impact
        action = "💰 Paiement Variational"
        
        print("   " + "─"*94)
        print(f"   08:00    -            {var_str:14} $ {cumul:7.2f}    {action}")
    
    print("\n   " + "─"*94)
    
    if strategy == "early_close":
        duration = 7
        per_hour = cumul / 7
    else:
        duration = 8
        per_hour = cumul / 8
    
    print(f"   TOTAL:   ${cumul:.2f} sur {duration}h = ${per_hour:.2f}/h")
    
    print("\n" + "="*100 + "\n")


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else "AVNT"
    
    explain_calculation(symbol)
    
    print("\n💡 Pour tester un autre symbole:")
    print("   py explain_calculs_v2.py BTC")
    print("   py explain_calculs_v2.py ETH")
    print("   py explain_calculs_v2.py BERA\n")

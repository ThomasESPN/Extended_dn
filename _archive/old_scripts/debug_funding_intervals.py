"""
Debug: Analyser les intervalles de funding réels de Loris Tools
Pour comprendre quels exchanges ont 1h vs 8h
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.data.loris_api import get_loris_api
import json


def main():
    print("\n" + "="*100)
    print("🔍 ANALYSE DES INTERVALLES DE FUNDING - LORIS TOOLS")
    print("="*100 + "\n")
    
    loris = get_loris_api()
    data = loris.fetch_all_funding_rates()
    
    if not data:
        print("❌ Erreur récupération données")
        return
    
    print("📊 Structure des données Loris:\n")
    print(f"Clés disponibles: {list(data.keys())}\n")
    
    # Analyser la structure des exchanges
    exchanges_data = data.get('exchanges', {})
    print(f"Exchanges data keys: {list(exchanges_data.keys())}\n")
    
    # Lister tous les exchanges
    exchange_names = exchanges_data.get('exchange_names', [])
    print(f"📡 Nombre d'exchanges: {len(exchange_names)}\n")
    
    # Grouper par type
    hourly_exchanges = []
    eight_hour_exchanges = []
    unknown_exchanges = []
    
    for ex in exchange_names:
        name = ex['name']
        display = ex['display']
        base = name.split('_')[0].lower()
        
        # Notes dans loris_api.py:
        # "Extended, Hyperliquid, Lighter, Vest utilisent des intervalles de 1h (rates multipliés par 8)"
        if base in ['extended', 'hyperliquid', 'lighter', 'vest']:
            hourly_exchanges.append(f"{display} ({name})")
        elif base == 'variational':
            # Variational peut avoir des intervalles variables par paire!
            unknown_exchanges.append(f"{display} ({name})")
        else:
            eight_hour_exchanges.append(f"{display} ({name})")
    
    print("⏰ EXCHANGES 1H (funding toutes les heures):")
    for ex in hourly_exchanges:
        print(f"   - {ex}")
    
    print(f"\n⏰ EXCHANGES 8H (funding toutes les 8 heures):")
    for ex in eight_hour_exchanges:
        print(f"   - {ex}")
    
    print(f"\n❓ EXCHANGES À VÉRIFIER (intervalle variable?):")
    for ex in unknown_exchanges:
        print(f"   - {ex}")
    
    # Analyser quelques symboles spécifiques
    print(f"\n\n{'='*100}")
    print("🎯 ANALYSE DÉTAILLÉE DE QUELQUES SYMBOLES")
    print(f"{'='*100}\n")
    
    test_symbols = ['RESOLV', 'DOOD', 'BTC', 'ETH', 'ZORA']
    funding_rates = data.get('funding_rates', {})
    
    for symbol in test_symbols:
        print(f"\n📊 {symbol}:")
        print(f"   {'Exchange':<20} {'Rate (raw)':<15} {'Rate (decimal)':<15}")
        print(f"   {'-'*50}")
        
        for exchange_info in exchange_names[:10]:  # Top 10 exchanges
            ex_name = exchange_info['name']
            ex_display = exchange_info['display']
            
            if ex_name in funding_rates:
                rate_raw = funding_rates[ex_name].get(symbol)
                if rate_raw is not None:
                    rate_decimal = rate_raw / 10000.0
                    print(f"   {ex_display:<20} {rate_raw:<15} {rate_decimal:<15.6f}")
    
    # Chercher si Loris donne l'info d'intervalle quelque part
    print(f"\n\n{'='*100}")
    print("🔍 ANALYSE DE 'funding_intervals' DANS LA RÉPONSE API")
    print(f"{'='*100}\n")
    
    funding_intervals = data.get('funding_intervals', {})
    print(f"Type: {type(funding_intervals)}")
    print(f"Nombre d'entrées: {len(funding_intervals)}")
    
    # Analyser la structure
    if isinstance(funding_intervals, dict):
        # Prendre quelques exemples
        print(f"\n📊 Exemples d'intervalles de funding:\n")
        for i, (key, value) in enumerate(list(funding_intervals.items())[:20]):
            print(f"   {key}: {value}")
            if i >= 19:
                break
        
        # Chercher les symboles qu'on teste
        print(f"\n🎯 Intervalles pour nos symboles test:")
        for symbol in ['RESOLV', 'DOOD', 'BTC', 'ETH', 'ZORA']:
            # Chercher les clés qui contiennent ce symbole
            matching_keys = [k for k in funding_intervals.keys() if symbol in k]
            if matching_keys:
                print(f"\n   {symbol}:")
                for key in matching_keys[:5]:  # Max 5
                    print(f"      {key}: {funding_intervals[key]}")
    
    # Analyser la structure des exchanges
    print(f"\n\n{'='*100}")
    print("🔍 ANALYSE DÉTAILLÉE DES EXCHANGES")
    print(f"{'='*100}\n")
    
    for ex_info in exchange_names[:10]:
        print(f"\n{ex_info['display']}:")
        print(f"   name: {ex_info['name']}")
        print(f"   interval: {ex_info.get('interval', 'N/A')} heures")
        
        # Vérifier si c'est 1 ou 8
        interval_hours = ex_info.get('interval', 0)
        if interval_hours == 1:
            print(f"   ✅ Funding TOUTES LES HEURES")
        elif interval_hours == 8:
            print(f"   ✅ Funding TOUTES LES 8 HEURES")
        else:
            print(f"   ⚠️  Intervalle inconnu: {interval_hours}")
    
    print(f"\n\n💡 CONCLUSION:")
    print(f"   L'API Loris ne semble PAS fournir l'intervalle de funding par paire.")
    print(f"   Les notes du code indiquent que :")
    print(f"   - Extended, Hyperliquid, Lighter, Vest = 1h (rates × 8)")
    print(f"   - Autres exchanges = 8h")
    print(f"   MAIS il faut VÉRIFIER si c'est toujours vrai pour TOUTES les paires!\n")


if __name__ == "__main__":
    main()

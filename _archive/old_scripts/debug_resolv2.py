#!/usr/bin/env python3
"""
Script de debug pour vérifier la structure des données Loris
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.data.loris_api import LorisAPI
from datetime import datetime
import json

def main():
    print("=" * 100)
    print("🔍 DEBUG STRUCTURE API LORIS")
    print("=" * 100)
    
    # Récupérer les données Loris
    loris = LorisAPI()
    data = loris.fetch_all_funding_rates()
    
    if not data:
        print("❌ Impossible de récupérer les données")
        return
    
    print(f"\n📊 STRUCTURE DES DONNÉES:")
    print("-" * 100)
    print(f"Type: {type(data)}")
    print(f"Clés principales: {list(data.keys())}")
    print()
    
    # Afficher la structure exchanges
    print("🔧 EXCHANGES:")
    exchanges_data = data.get('exchanges', {})
    print(f"   Type: {type(exchanges_data)}")
    print(f"   Clés: {list(exchanges_data.keys())}")
    
    exchange_names = exchanges_data.get('exchange_names', [])
    print(f"\n   📡 {len(exchange_names)} exchanges:")
    for ex in exchange_names[:5]:
        print(f"      {ex}")
    print()
    
    # Afficher la structure symbols
    print("📋 SYMBOLS:")
    symbols = data.get('symbols', [])
    print(f"   Type: {type(symbols)}")
    print(f"   Nombre: {len(symbols)}")
    print(f"   Premiers 10: {symbols[:10]}")
    print()
    
    # Afficher la structure funding_rates
    print("💰 FUNDING_RATES:")
    funding_rates = data.get('funding_rates', {})
    print(f"   Type: {type(funding_rates)}")
    print(f"   Exchanges disponibles: {list(funding_rates.keys())[:5]}")
    print()
    
    # Chercher RESOLV dans funding_rates
    print("🎯 RESOLV DANS FUNDING_RATES:")
    print("-" * 100)
    
    resolv_found = False
    for exchange_name, rates_dict in funding_rates.items():
        if 'RESOLV' in rates_dict:
            resolv_found = True
            rate_value = rates_dict['RESOLV']
            exchange_display = exchange_name.split('_')[0].upper()
            rate_decimal = rate_value / 10000.0  # Convertir de la notation Loris
            
            print(f"\n✅ {exchange_display:15s} ({exchange_name})")
            print(f"   Rate brut: {rate_value:10.2f}")
            print(f"   Rate converti: {rate_decimal:10.6f} ({rate_decimal*100:8.4f}%)")
    
    if not resolv_found:
        print("❌ RESOLV non trouvé!")
    
    print("\n" + "=" * 100)
    print("⏰ Timestamp: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 100)

if __name__ == "__main__":
    main()

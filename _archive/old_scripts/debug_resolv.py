#!/usr/bin/env python3
"""
Script de debug pour vérifier les données RESOLV sur Extended
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.data.loris_api import LorisAPI
from datetime import datetime

def main():
    print("=" * 100)
    print("🔍 DEBUG RESOLV SUR EXTENDED")
    print("=" * 100)
    
    # Récupérer les données Loris
    loris = LorisAPI()
    data = loris.fetch_all_funding_rates()
    
    if not data:
        print("❌ Impossible de récupérer les données")
        return
    
    print(f"\n✅ {len(data)} symboles disponibles\n")
    
    # Chercher RESOLV dans les données brutes
    print("📊 RECHERCHE DE RESOLV DANS LES DONNÉES:")
    print("-" * 100)
    
    resolv_found = False
    for symbol_data in data:
        symbol = symbol_data.get('symbol', '')
        if 'RESOLV' in symbol.upper():
            resolv_found = True
            print(f"\n✅ Trouvé: {symbol}")
            print(f"   Données complètes: {symbol_data}")
            print()
            
            # Afficher tous les exchanges pour ce symbole
            exchanges = symbol_data.get('exchanges', [])
            print(f"   📡 {len(exchanges)} exchanges disponibles:")
            for ex in exchanges:
                ex_name = ex.get('exchange', 'Unknown')
                rate = ex.get('rate', 0)
                interval = ex.get('interval', 0)
                print(f"      - {ex_name:20s} → Rate: {rate:10.6f} ({rate*100:8.4f}%) | Interval: {interval}h")
    
    if not resolv_found:
        print("❌ RESOLV non trouvé dans les données!")
        print("\n📋 Premiers 10 symboles disponibles:")
        for i, symbol_data in enumerate(data[:10]):
            print(f"   {i+1}. {symbol_data.get('symbol', 'Unknown')}")
    
    print("\n" + "=" * 100)
    print("🔍 VÉRIFICATION SPÉCIFIQUE EXTENDED")
    print("=" * 100)
    
    # Chercher extended_1_perp
    for symbol_data in data:
        symbol = symbol_data.get('symbol', '')
        if 'RESOLV' in symbol.upper():
            exchanges = symbol_data.get('exchanges', [])
            for ex in exchanges:
                ex_name = ex.get('exchange', '')
                if 'extended' in ex_name.lower():
                    print(f"\n🎯 EXTENDED trouvé pour {symbol}:")
                    print(f"   Exchange name: {ex_name}")
                    print(f"   Rate brut: {ex.get('rate', 0)}")
                    print(f"   Rate en %: {ex.get('rate', 0) * 100}%")
                    print(f"   Interval: {ex.get('interval', 0)}h")
                    print(f"   Timestamp: {ex.get('timestamp', 'N/A')}")
                    print(f"   Données complètes: {ex}")
    
    print("\n" + "=" * 100)
    print("⏰ Timestamp actuel: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 100)

if __name__ == "__main__":
    main()

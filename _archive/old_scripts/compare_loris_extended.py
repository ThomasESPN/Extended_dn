#!/usr/bin/env python3
"""
Comparer les données Loris API vs Loris Website vs Extended
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.data.loris_api import LorisAPI
from datetime import datetime

def main():
    print("=" * 120)
    print("🔍 COMPARAISON LORIS API vs LORIS WEBSITE vs EXTENDED")
    print("=" * 120)
    
    loris = LorisAPI()
    data = loris.fetch_all_funding_rates()
    
    if not data:
        print("❌ Erreur")
        return
    
    funding_rates = data.get('funding_rates', {})
    
    print("\n📊 RESOLV - COMPARAISON DES RATES:")
    print("-" * 120)
    
    # Extended
    extended_rate_raw = funding_rates.get('extended_1_perp', {}).get('RESOLV')
    extended_rate_decimal = extended_rate_raw / 10000.0 if extended_rate_raw else None
    
    # Hyperliquid
    hyperliquid_rate_raw = funding_rates.get('hyperliquid_1_perp', {}).get('RESOLV')
    hyperliquid_rate_decimal = hyperliquid_rate_raw / 10000.0 if hyperliquid_rate_raw else None
    
    print("\n🎯 EXTENDED:")
    print(f"   API Loris (brut):      {extended_rate_raw}")
    print(f"   API Loris (÷10000):    {extended_rate_decimal:.6f} = {extended_rate_decimal*100:.4f}%")
    print(f"   Website Loris affiche: -3.0")
    print(f"   Extended.exchange:     -0.9133% (à 15:00 UTC)")
    
    print("\n⚡ HYPERLIQUID:")
    print(f"   API Loris (brut):      {hyperliquid_rate_raw}")
    print(f"   API Loris (÷10000):    {hyperliquid_rate_decimal:.6f} = {hyperliquid_rate_decimal*100:.4f}%")
    print(f"   Website Loris affiche: -71.9")
    
    print("\n" + "=" * 120)
    print("💡 ANALYSE DES CONVERSIONS:")
    print("-" * 120)
    
    if extended_rate_raw and extended_rate_decimal:
        # Tester différentes conversions
        print("\n🔢 EXTENDED - Tests de conversion:")
        print(f"   Brut / 10:             {extended_rate_raw / 10:.2f} (Loris website affiche -3.0) ✅")
        print(f"   Brut / 100:            {extended_rate_raw / 100:.2f}")
        print(f"   Brut / 1000:           {extended_rate_raw / 1000:.2f}")
        print(f"   Décimal × 100:         {extended_rate_decimal * 100:.4f}%")
        
        # Comparaison avec Extended.exchange
        extended_real = -0.9133  # D'après screenshot Extended à 15:00
        print(f"\n   Extended.exchange (15:00): {extended_real}%")
        print(f"   Ratio vs Loris décimal:    {extended_real / (extended_rate_decimal*100):.2f}x")
        
    if hyperliquid_rate_raw and hyperliquid_rate_decimal:
        print("\n🔢 HYPERLIQUID - Tests de conversion:")
        print(f"   Brut / 10:             {hyperliquid_rate_raw / 10:.2f} (Loris website affiche -71.9) ✅")
        print(f"   Brut / 100:            {hyperliquid_rate_raw / 100:.2f}")
        print(f"   Décimal × 100:         {hyperliquid_rate_decimal * 100:.4f}%")
    
    # Calculer le spread comme Loris
    if extended_rate_raw and hyperliquid_rate_raw:
        print("\n" + "=" * 120)
        print("📈 SPREAD (comme Loris Tools):")
        print("-" * 120)
        
        # Méthode 1: Différence des rates bruts divisée par 10
        spread_method1 = abs(hyperliquid_rate_raw - extended_rate_raw) / 10
        print(f"   Méthode 1 (|hyp - ext| / 10):     {spread_method1:.1f} bps")
        print(f"   Website Loris affiche:            68.9 bps")
        print(f"   Match: {'✅' if abs(spread_method1 - 68.9) < 1 else '❌'}")
        
        # Méthode 2: Différence en décimal × 10000
        spread_method2 = abs(hyperliquid_rate_decimal - extended_rate_decimal) * 10000
        print(f"\n   Méthode 2 (|hyp - ext| × 10000):  {spread_method2:.1f} bps")
        print(f"   Website Loris affiche:            68.9 bps")
        print(f"   Match: {'✅' if abs(spread_method2 - 68.9) < 1 else '❌'}")
    
    print("\n" + "=" * 120)

if __name__ == "__main__":
    main()

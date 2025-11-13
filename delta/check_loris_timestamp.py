#!/usr/bin/env python3
"""
Vérifier le timestamp des données Loris
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.data.loris_api import LorisAPI
from datetime import datetime

def main():
    print("=" * 100)
    print("🕐 VÉRIFICATION TIMESTAMP LORIS TOOLS")
    print("=" * 100)
    
    loris = LorisAPI()
    data = loris.fetch_all_funding_rates()
    
    if not data:
        print("❌ Erreur")
        return
    
    # Timestamp de l'API
    api_timestamp = data.get('timestamp')
    current_time = datetime.now()
    
    print(f"\n⏰ Heure actuelle: {current_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📡 Timestamp API: {api_timestamp}")
    
    # Convertir le timestamp API en datetime si c'est un Unix timestamp
    if isinstance(api_timestamp, (int, float)):
        api_time = datetime.fromtimestamp(api_timestamp)
        print(f"   → {api_time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        age_seconds = (current_time - api_time).total_seconds()
        print(f"\n📊 Âge des données: {age_seconds:.0f} secondes ({age_seconds/60:.1f} minutes)")
        
        if age_seconds > 120:
            print("   ⚠️ Données potentiellement périmées (>2 minutes)")
        else:
            print("   ✅ Données récentes")
    
    # Vérifier funding_intervals pour RESOLV
    print("\n" + "=" * 100)
    print("📅 FUNDING INTERVALS POUR RESOLV")
    print("=" * 100)
    
    funding_intervals = data.get('funding_intervals', {})
    
    for exchange_name in ['extended_1_perp', 'hyperliquid_1_perp', 'variational_1_perp']:
        intervals = funding_intervals.get(exchange_name, {})
        if isinstance(intervals, dict) and 'RESOLV' in intervals:
            hours = intervals['RESOLV']
            print(f"{exchange_name:25s} → {hours}h")
    
    print("\n" + "=" * 100)

if __name__ == "__main__":
    main()

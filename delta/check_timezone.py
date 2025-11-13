#!/usr/bin/env python3
"""
Vérifier la timezone du timestamp Loris
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.data.loris_api import LorisAPI
from datetime import datetime, timezone
import time

def main():
    print("=" * 100)
    print("🌍 VÉRIFICATION TIMEZONE LORIS TOOLS")
    print("=" * 100)
    
    loris = LorisAPI()
    data = loris.fetch_all_funding_rates()
    
    if not data:
        print("❌ Erreur")
        return
    
    # Timestamps
    api_timestamp_str = data.get('timestamp')
    current_time_local = datetime.now()
    current_time_utc = datetime.now(timezone.utc)
    
    print(f"\n⏰ HEURES:")
    print("-" * 100)
    print(f"Heure locale:     {current_time_local.strftime('%Y-%m-%d %H:%M:%S')} (timezone système)")
    print(f"Heure UTC:        {current_time_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"API timestamp:    {api_timestamp_str}")
    
    # Essayer de parser le timestamp API
    try:
        # Si c'est une string au format ISO
        if isinstance(api_timestamp_str, str):
            # Parser avec différents formats
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f']:
                try:
                    api_time = datetime.strptime(api_timestamp_str.replace('Z', ''), fmt)
                    print(f"\n✅ Timestamp parsé: {api_time.strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    # Comparer avec UTC
                    diff_utc = (current_time_utc.replace(tzinfo=None) - api_time).total_seconds()
                    print(f"   Différence avec UTC actuel: {diff_utc:.0f} secondes ({diff_utc/60:.1f} minutes)")
                    
                    # Comparer avec local
                    diff_local = (current_time_local - api_time).total_seconds()
                    print(f"   Différence avec heure locale: {diff_local:.0f} secondes ({diff_local/60:.1f} minutes)")
                    
                    if abs(diff_utc) < 120:
                        print("\n🎯 Le timestamp est probablement en UTC! (différence <2min)")
                    elif abs(diff_local) < 120:
                        print("\n🎯 Le timestamp est probablement en heure locale! (différence <2min)")
                    
                    break
                except ValueError:
                    continue
        
        # Si c'est un Unix timestamp
        elif isinstance(api_timestamp_str, (int, float)):
            api_time = datetime.fromtimestamp(api_timestamp_str, tz=timezone.utc)
            print(f"\n✅ Unix timestamp converti: {api_time.strftime('%Y-%m-%d %H:%M:%S')} UTC")
            
            diff = (current_time_utc - api_time).total_seconds()
            print(f"   Âge des données: {diff:.0f} secondes ({diff/60:.1f} minutes)")
    
    except Exception as e:
        print(f"\n❌ Erreur de parsing: {e}")
    
    print("\n" + "=" * 100)
    print("🌍 INFO TIMEZONE SYSTÈME:")
    print("-" * 100)
    print(f"Offset UTC: {time.timezone / 3600:.0f} heures")
    print(f"DST actif: {time.daylight}")
    print("=" * 100)

if __name__ == "__main__":
    main()

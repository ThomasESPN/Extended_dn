#!/usr/bin/env python3
"""
Test Hyperliquid API directement
"""
import requests
import json

# Hyper liquid API publique
API_URL = "https://api.hyperliquid.xyz/info"

# Test 1: Meta and Asset Contexts
print("🔍 Test Hyperliquid API...")
print(f"URL: {API_URL}")

payload = {
    "type": "metaAndAssetCtxs"
}

try:
    response = requests.post(API_URL, json=payload, timeout=10)
    print(f"Status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ Réponse reçue!")
        print(f"Type: {type(data)}")
        print(f"Keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
        print(f"Length: {len(data) if isinstance(data, list) else 'N/A'}")
        
        # Afficher la structure
        print(f"\n📊 Structure:")
        print(json.dumps(data, indent=2)[:2000])  # Premiers 2000 caractères
        
except Exception as e:
    print(f"❌ Erreur: {e}")

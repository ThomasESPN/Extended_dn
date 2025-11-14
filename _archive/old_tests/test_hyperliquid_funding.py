#!/usr/bin/env python3
"""
Test Hyperliquid API - funding rates
"""
import requests
import json

API_URL = "https://api.hyperliquid.xyz/info"

payload = {
    "type": "metaAndAssetCtxs"
}

response = requests.post(API_URL, json=payload, timeout=10)
data = response.json()

print("📊 Structure complète:")
print(f"Nombre d'éléments: {len(data)}")

print("\n" + "=" * 80)
print("ÉLÉMENT [0] - Metadata:")
print("=" * 80)
print(f"Keys: {list(data[0].keys())}")
print(f"Universe length: {len(data[0]['universe'])}")
print(f"\nPremier symbol: {json.dumps(data[0]['universe'][0], indent=2)}")

if len(data) > 1:
    print("\n" + "=" * 80)
    print("ÉLÉMENT [1] - Asset Contexts (funding rates?):")
    print("=" * 80)
    print(f"Type: {type(data[1])}")
    if isinstance(data[1], list):
        print(f"Length: {len(data[1])}")
        if len(data[1]) > 0:
            print(f"\nPremier élément:")
            print(json.dumps(data[1][0], indent=2))
            
            # Chercher RESOLV
            for ctx in data[1]:
                if isinstance(ctx, dict):
                    # Trouver la clé qui contient le symbole
                    ctx_str = str(ctx)
                    if 'RESOLV' in ctx_str:
                        print(f"\n🎯 RESOLV trouvé:")
                        print(json.dumps(ctx, indent=2))
                        break

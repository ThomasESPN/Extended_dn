import requests
import json

API_URL = "https://api.hyperliquid.xyz/info"

payload = {"type": "metaAndAssetCtxs"}
response = requests.post(API_URL, json=payload, timeout=10)
data = response.json()

print(f"Type data: {type(data)}")
print(f"Len data: {len(data)}")
print()

# data[0]
print("=" * 80)
print("data[0] keys:", list(data[0].keys()) if isinstance(data[0], dict) else "Not a dict")
universe = data[0].get('universe', [])
print(f"Universe length: {len(universe)}")
print()
print("universe[0]:")
print(json.dumps(universe[0], indent=2))
print()

# data[1]
print("=" * 80)
print(f"data[1] type: {type(data[1])}")
print(f"data[1] length: {len(data[1])}")
print()
print("data[1][0]:")
print(json.dumps(data[1][0], indent=2))
print()

# Test match
print("=" * 80)
print("MATCHING TEST:")
print(f"Symbol from data[0][0]: {universe[0].get('name')}")
print(f"Funding from data[1][0]: {data[1][0].get('funding')}")

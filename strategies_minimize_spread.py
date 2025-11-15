#!/usr/bin/env python3
"""
Stratégies pour MINIMISER le spread dans le delta-neutral
"""

print("="*80)
print("STRATÉGIES POUR MINIMISER LE SPREAD")
print("="*80)

print("\n🎯 STRATÉGIE 1: ORDRES MAKER (au lieu de TAKER)")
print("-"*80)
print("ACTUELLEMENT (TAKER):")
print("  Extended BUY @ ASK:  $0.055655 (tu PAYES le spread)")
print("  Hyperliquid SELL @ BID: $0.055446 (tu PAYES le spread)")
print("  → Spread payé: $0.000209 (0.377%)")

print("\nAVEC MAKER:")
print("  Extended LIMIT BUY @ BID:  $0.055614 (tu REÇOIS le spread)")
print("  Hyperliquid LIMIT SELL @ ASK: $0.055464 (tu REÇOIS le spread)")
print("  → Spread GAGNÉ: -$0.000150 (-0.27%)")
print("\n  GAIN vs TAKER: $0.15 + $0.21 = $0.36 par position!")
print("  ⚠️ MAIS: risque de non-fill si marché bouge")

print("\n" + "="*80)
print("\n🎯 STRATÉGIE 2: LIMIT MID-PRICE (MAKER agressif)")
print("-"*80)

bid_ext = 0.055614
ask_ext = 0.055655
mid_ext = (bid_ext + ask_ext) / 2

bid_hyp = 0.055452
ask_hyp = 0.055464
mid_hyp = (bid_hyp + ask_hyp) / 2

print(f"Extended:")
print(f"  Bid: ${bid_ext:.6f}, Ask: ${ask_ext:.6f}")
print(f"  Mid: ${mid_ext:.6f}")
print(f"  LIMIT BUY @ mid - 0.01% = ${mid_ext * 0.9999:.6f}")
print(f"  → Tu payes ${abs(ask_ext - mid_ext * 0.9999):.6f} de moins que TAKER")

print(f"\nHyperliquid:")
print(f"  Bid: ${bid_hyp:.6f}, Ask: ${ask_hyp:.6f}")
print(f"  Mid: ${mid_hyp:.6f}")
print(f"  LIMIT SELL @ mid + 0.01% = ${mid_hyp * 1.0001:.6f}")
print(f"  → Tu gagnes ${abs(mid_hyp * 1.0001 - bid_hyp):.6f} de plus que TAKER")

spread_maker = abs((mid_ext * 0.9999) - (mid_hyp * 1.0001))
spread_taker = 0.000209
saving = (spread_taker - spread_maker) * 1000

print(f"\n💰 RÉSULTAT:")
print(f"  Spread TAKER:  ${spread_taker:.6f} → coût ${spread_taker * 1000:.2f}")
print(f"  Spread MAKER:  ${spread_maker:.6f} → coût ${spread_maker * 1000:.2f}")
print(f"  ÉCONOMIE:      ${saving:.2f} par trade!")

print("\n" + "="*80)
print("\n🎯 STRATÉGIE 3: SURVEILLER LE FUNDING AVANT D'ENTRER")
print("-"*80)
print("\nAVANT d'ouvrir la position, VÉRIFIER:")
print("  1. Funding rate Extended: doit être POSITIF et > 0.03%")
print("  2. Funding rate Hyperliquid: doit être < Extended")
print("  3. Différence: Extended - Hyperliquid > 0.04%")
print("\n✅ Si différence > 0.04%:")
print("   → Le spread de 0.377% sera récupéré en ~9 cycles (3 jours)")
print("\n❌ Si différence < 0.02%:")
print("   → Le spread prendra >18 cycles (6 jours) à récupérer")
print("   → PAS RENTABLE, ne pas trader!")

print("\n" + "="*80)
print("\n🎯 RECOMMANDATION FINALE")
print("="*80)

print("\n✅ POUR MINIMISER L'IMPACT DU SPREAD:")
print("\n  1. UTILISER ORDRES MAKER (limit @ mid-price)")
print("     → Économise $0.15-0.36 par trade")
print("     → Réduit le break-even de 9 cycles à ~5 cycles")
print("\n  2. VÉRIFIER FUNDING AVANT:")
print("     → Extended funding > +0.05%")
print("     → Différence Extended-Hyperliquid > 0.04%")
print("\n  3. SURVEILLER EN CONTINU:")
print("     → Fermer si funding devient défavorable")
print("     → Utiliser stop-loss sur funding rate")

print("\n❌ NE PAS TRADER SI:")
print("  - Spread > 0.5% (actuellement 0.377% = OK)")
print("  - Différence de funding < 0.02%")
print("  - Liquidité faible (slippage > 1%)")

print("\n" + "="*80)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CALCUL avec les VRAIS spreads du marché
Hyperliquid: 0.131% spread
ZORA: 0.10% spread
"""

# SETUP
total_notional = 10000  # $10k TOTAL
notional_per_side = 5000  # $5k par côté

# VRAIS SPREADS que tu vois
spread_hyperliquid_pct = 0.00131  # 0.131%
spread_zora_pct = 0.0010  # 0.10%

funding_profit = 12.0

print("="*70)
print("CALCUL avec VRAIS spreads: HL 0.131%, ZORA 0.10%")
print("="*70)

print(f"\nTotal notional: ${total_notional:,}")
print(f"  Extended:  ${notional_per_side:,}")
print(f"  Hyperliquid: ${notional_per_side:,}")
print(f"\nFunding profit: ${funding_profit:.2f}")

# PRIX ZORA (exemple à ~$0.055)
zora_price = 0.055288  # Prix que tu donnes
size = notional_per_side / zora_price

print(f"\nPrix ZORA: ${zora_price:.6f}")
print(f"Size par côté: {size:,.0f} ZORA")

# SCENARIO 1: TAKER (tu payes le spread)
print("\n" + "="*70)
print("SCENARIO 1: TAKER (tu PAYES le spread bid/ask)")
print("="*70)

# Sur Hyperliquid: spread 0.131%
# Sur Extended (ZORA): spread 0.10%

# Quand tu achètes Extended (LONG):
# - Tu achètes au ASK = mid + (spread/2)
# - Spread Extended: 0.10% → tu payes +0.05%

# Quand tu vends Hyperliquid (SHORT):
# - Tu vends au BID = mid - (spread/2)  
# - Spread Hyperliquid: 0.131% → tu payes -0.0655%

# TOTAL spread payé = 0.05% + 0.0655% = 0.1155%
total_spread_taker_pct = (spread_zora_pct / 2) + (spread_hyperliquid_pct / 2)
cost_taker = total_notional * total_spread_taker_pct

print(f"\nSpread Extended (ZORA):   {spread_zora_pct*100:.3f}%")
print(f"  Tu ACHETES au ASK: payes +{(spread_zora_pct/2)*100:.3f}%")
print(f"\nSpread Hyperliquid:       {spread_hyperliquid_pct*100:.3f}%")
print(f"  Tu VENDS au BID: payes -{(spread_hyperliquid_pct/2)*100:.3f}%")
print(f"\nTOTAL spread payé:        {total_spread_taker_pct*100:.3f}%")
print(f"Coût: ${total_notional:,} × {total_spread_taker_pct*100:.3f}% = ${cost_taker:.2f}")

profit_net_taker = funding_profit - cost_taker
print(f"\nProfit NET:")
print(f"  Funding:  +${funding_profit:.2f}")
print(f"  Spread:   -${cost_taker:.2f}")
print(f"  NET:      ${profit_net_taker:.2f}")

if profit_net_taker > 0:
    print(f"\n✅ RENTABLE! Tu gardes ${profit_net_taker:.2f} ({(profit_net_taker/funding_profit)*100:.1f}%)")
else:
    print(f"\n❌ PAS RENTABLE! Tu perds ${abs(profit_net_taker):.2f}")

# SCENARIO 2: MAKER (tu REÇOIS le spread)
print("\n" + "="*70)
print("SCENARIO 2: MAKER (tu REÇOIS le spread)")
print("="*70)

# Quand tu places LIMIT au mid (MAKER):
# - Extended: tu achètes au MID ou BID (tu REÇOIS +0.05%)
# - Hyperliquid: tu vends au MID ou ASK (tu REÇOIS +0.0655%)

# Tu GAGNES le spread au lieu de le payer!
total_spread_maker_pct = (spread_zora_pct / 2) + (spread_hyperliquid_pct / 2)
cost_maker = -total_notional * total_spread_maker_pct  # NÉGATIF = tu gagnes!

print(f"\nSpread Extended (ZORA):   {spread_zora_pct*100:.3f}%")
print(f"  LIMIT BUY au BID: reçois +{(spread_zora_pct/2)*100:.3f}%")
print(f"\nSpread Hyperliquid:       {spread_hyperliquid_pct*100:.3f}%")
print(f"  LIMIT SELL au ASK: reçois +{(spread_hyperliquid_pct/2)*100:.3f}%")
print(f"\nTOTAL spread GAGNÉ:       {total_spread_maker_pct*100:.3f}%")
print(f"Gain: ${total_notional:,} × {total_spread_maker_pct*100:.3f}% = ${abs(cost_maker):.2f}")

profit_net_maker = funding_profit - cost_maker  # - (-gain) = + gain!
print(f"\nProfit NET:")
print(f"  Funding:  +${funding_profit:.2f}")
print(f"  Spread:   +${abs(cost_maker):.2f}")
print(f"  NET:      ${profit_net_maker:.2f}")

print(f"\n✅ SUPER RENTABLE! Tu DOUBLES le profit!")
print(f"   ${funding_profit:.2f} funding + ${abs(cost_maker):.2f} spread = ${profit_net_maker:.2f}")

# SCENARIO 3: LIMIT proche du MID (compromis)
print("\n" + "="*70)
print("SCENARIO 3: LIMIT proche MID (±0.02% du mid)")
print("="*70)

# Tu places LIMIT légèrement agressif pour fill rapide
# Extended: mid - 0.02% (au lieu de BID)
# Hyperliquid: mid + 0.02% (au lieu de ASK)

offset_pct = 0.0002  # 0.02%

# Spread que tu payes
spread_limit_pct = offset_pct * 2  # 0.04% total
cost_limit = total_notional * spread_limit_pct

print(f"\nOffset: ±{offset_pct*100:.2f}%")
print(f"Spread total: {spread_limit_pct*100:.2f}%")
print(f"Coût: ${total_notional:,} × {spread_limit_pct*100:.2f}% = ${cost_limit:.2f}")

profit_net_limit = funding_profit - cost_limit
print(f"\nProfit NET:")
print(f"  Funding:  +${funding_profit:.2f}")
print(f"  Spread:   -${cost_limit:.2f}")
print(f"  NET:      ${profit_net_limit:.2f}")

print(f"\n✅ RENTABLE! Tu gardes ${profit_net_limit:.2f} ({(profit_net_limit/funding_profit)*100:.1f}%)")

# COMPARAISON
print("\n" + "="*70)
print("COMPARAISON")
print("="*70)

print(f"\nAvec 10k notional, funding $12:")
print(f"\n  TAKER (market):    ${profit_net_taker:+.2f} ({(profit_net_taker/funding_profit)*100:+.0f}%)")
print(f"  MAKER (limit BID/ASK): ${profit_net_maker:+.2f} ({(profit_net_maker/funding_profit)*100:+.0f}%)")
print(f"  LIMIT ±0.02%:      ${profit_net_limit:+.2f} ({(profit_net_limit/funding_profit)*100:+.0f}%)")

print(f"\n🎯 MEILLEURE STRATÉGIE: MAKER (limit au BID/ASK)")
print(f"   Tu GAGNES ${profit_net_maker:.2f} au lieu de $12!")
print(f"   Le spread AJOUTE au profit au lieu de le réduire!")

print("\n" + "="*70)
print("CONCLUSION")
print("="*70)

print(f"\nAvec ces spreads (0.10% ZORA, 0.131% HL):")
print(f"\n✅ TAKER est RENTABLE: +${profit_net_taker:.2f}")
print(f"   ({(profit_net_taker/funding_profit)*100:.0f}% du funding profit)")
print(f"\n🔥 MAKER est SUPER RENTABLE: +${profit_net_maker:.2f}")
print(f"   (2x le funding profit!)")
print(f"\n⚡ LIMIT ±0.02% est OPTIMAL: +${profit_net_limit:.2f}")
print(f"   (compromis entre fill rapide et profit max)")

print("\n" + "="*70)

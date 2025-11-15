#!/usr/bin/env python3
"""
Analyse de l'impact du spread sur le profit de funding arbitrage
"""

# TES DONNÉES RÉELLES
extended_fill = 0.055655
hyperliquid_fill = 0.055446
size = 1000  # ZORA
leverage = 3

# CALCUL DU SPREAD
spread_abs = abs(extended_fill - hyperliquid_fill)
spread_pct = (spread_abs / hyperliquid_fill) * 100

# Notional positions
extended_notional = size * extended_fill  # $55.66
hyperliquid_notional = size * hyperliquid_fill  # $55.45

print("="*80)
print("IMPACT DU SPREAD SUR LE PROFIT DE FUNDING")
print("="*80)

print(f"\n📊 POSITIONS:")
print(f"  Extended LONG:  1000 ZORA @ ${extended_fill:.6f} = ${extended_notional:.2f} notional")
print(f"  Hyperliquid SHORT: 1000 ZORA @ ${hyperliquid_fill:.6f} = ${hyperliquid_notional:.2f} notional")
print(f"  Spread d'entrée: ${spread_abs:.6f} ({spread_pct:.3f}%)")

# SCÉNARIO: Funding rate sur Extended
print("\n" + "="*80)
print("SCENARIO: FUNDING ARBITRAGE")
print("="*80)

# Exemple: Extended funding = +0.05% par 8h (tu REÇOIS car tu es LONG)
extended_funding_rate = 0.0005  # 0.05% par 8h (positif = tu reçois)
hyperliquid_funding_rate = 0.0001  # 0.01% par 8h (tu PAYES car tu es SHORT)

print(f"\nFunding rates (par 8h):")
print(f"  Extended:    +{extended_funding_rate*100:.3f}% (tu REÇOIS car LONG)")
print(f"  Hyperliquid: +{hyperliquid_funding_rate*100:.3f}% (tu PAYES car SHORT)")

# Calcul du profit de funding
extended_funding_profit = extended_notional * extended_funding_rate  # Tu REÇOIS
hyperliquid_funding_cost = hyperliquid_notional * hyperliquid_funding_rate  # Tu PAYES

net_funding_profit = extended_funding_profit - hyperliquid_funding_cost

print(f"\n💰 PROFIT DE FUNDING (par 8h):")
print(f"  Extended (tu reçois):  +${extended_funding_profit:.4f}")
print(f"  Hyperliquid (tu payes): -${hyperliquid_funding_cost:.4f}")
print(f"  PROFIT NET:            +${net_funding_profit:.4f}")

# Impact du spread
spread_cost = spread_abs * size  # $0.209 payé UNE FOIS à l'entrée

print(f"\n💸 COÛT DU SPREAD:")
print(f"  Spread d'entrée: ${spread_cost:.4f} (payé UNE FOIS)")

# Combien de cycles pour récupérer le spread?
cycles_to_breakeven = spread_cost / net_funding_profit if net_funding_profit > 0 else float('inf')

print(f"\n📈 RENTABILITÉ:")
print(f"  Cycles pour break-even: {cycles_to_breakeven:.1f} x 8h")
print(f"  Temps pour break-even:  {cycles_to_breakeven * 8 / 24:.1f} jours")

# Profit sur 30 jours
days = 30
cycles_per_day = 24 / 8  # 3 cycles par jour
total_cycles = days * cycles_per_day
total_funding_profit = net_funding_profit * total_cycles
total_profit_after_spread = total_funding_profit - spread_cost

print(f"\n📊 PROFIT SUR 30 JOURS:")
print(f"  Funding total (90 cycles): +${total_funding_profit:.2f}")
print(f"  Spread d'entrée:           -${spread_cost:.2f}")
print(f"  PROFIT NET:                +${total_profit_after_spread:.2f}")
print(f"  ROI sur margin $18:        {(total_profit_after_spread/18)*100:.1f}%")

print("\n" + "="*80)

# LE VRAI PROBLÈME: Si le spread EST LE DELTA
print("\n⚠️  ATTENTION: LE VRAI RISQUE!")
print("="*80)

print(f"\nTu as raison de poser la question!")
print(f"\nLe spread de ${spread_abs:.6f} par token signifie:")
print(f"  - Tu ACHÈTES Extended à ${extended_fill:.6f}")
print(f"  - Tu VENDS Hyperliquid à ${hyperliquid_fill:.6f}")
print(f"  - Tu es IMMÉDIATEMENT en perte de ${spread_cost:.4f}")
print(f"\nCette perte est RÉALISÉE à l'entrée!")
print(f"Tu dois gagner au moins ${spread_cost:.4f} en funding pour être profitable.")

print(f"\n✅ SI funding rate reste favorable > {cycles_to_breakeven:.0f} cycles:")
print(f"   → PROFITABLE après {cycles_to_breakeven * 8 / 24:.1f} jours")

print(f"\n❌ SI funding rate devient défavorable AVANT {cycles_to_breakeven:.0f} cycles:")
print(f"   → TU PERDS le spread + les funding costs!")

print("\n" + "="*80)
print("CONCLUSION:")
print("="*80)
print(f"\nLe spread de {spread_pct:.3f}% est un COÛT RÉEL.")
print(f"Mais il est ACCEPTABLE si:")
print(f"  1. Le funding rate reste positif > {cycles_to_breakeven:.0f} cycles ({cycles_to_breakeven * 8 / 24:.1f} jours)")
print(f"  2. La différence de funding entre Extended et Hyperliquid est stable")
print(f"  3. Tu surveilles et fermes si le funding devient défavorable")
print("\nLe delta-neutral te PROTÈGE du mouvement de prix,")
print("MAIS tu dois gagner assez en funding pour compenser le spread!")
print("="*80)

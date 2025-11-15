#!/usr/bin/env python3
"""Analyse du spread bid/ask entre Extended et Hyperliquid"""

# Tes résultats réels du test
extended_fill_price = 0.055655
hyperliquid_fill_price = 0.055446
size = 1000  # ZORA
leverage = 3

# Calculs
extended_notional = size * extended_fill_price
hyperliquid_notional = size * hyperliquid_fill_price

extended_margin = extended_notional / leverage
hyperliquid_margin = hyperliquid_notional / leverage

margin_diff = abs(extended_margin - hyperliquid_margin)
margin_diff_pct = (margin_diff / 18) * 100

spread_abs = abs(extended_fill_price - hyperliquid_fill_price)
spread_pct = (spread_abs / hyperliquid_fill_price) * 100

print("="*80)
print("ANALYSE DU SPREAD BID/ASK")
print("="*80)

print("\nPRIX:")
print(f"  Extended LONG @ ASK:    ${extended_fill_price:.6f}")
print(f"  Hyperliquid SHORT @ BID: ${hyperliquid_fill_price:.6f}")
print(f"  Spread:                  ${spread_abs:.6f} ({spread_pct:.3f}%)")

print("\nNOTIONAL (1000 ZORA):")
print(f"  Extended:    ${extended_notional:.2f}")
print(f"  Hyperliquid: ${hyperliquid_notional:.2f}")
print(f"  Difference:  ${abs(extended_notional - hyperliquid_notional):.2f}")

print("\nMARGIN (@3x leverage):")
print(f"  Extended:    ${extended_margin:.2f}")
print(f"  Hyperliquid: ${hyperliquid_margin:.2f}")
print(f"  Ecart:       ${margin_diff:.2f} ({margin_diff_pct:.1f}% du target $18)")

print("\nCOUT D'ENTREE DELTA-NEUTRAL:")
print(f"  Tu payes ${margin_diff:.2f} de spread pour entrer en position")
print(f"  C'est {margin_diff_pct:.1f}% de ton margin target de $18")

# Comparaison avec funding rate typique
typical_funding_8h = 0.0001  # 0.01% par 8h
funding_profit_8h = (extended_notional + hyperliquid_notional) / 2 * typical_funding_8h

print("\nRENTABILITE:")
print(f"  Funding rate typique:     0.01% par 8h")
print(f"  Profit funding par 8h:    ${funding_profit_8h:.4f}")
print(f"  Cycles pour break-even:   {margin_diff / funding_profit_8h:.1f} x 8h")
print(f"  Temps pour break-even:    ~{(margin_diff / funding_profit_8h * 8 / 24):.1f} jours")

print("\n" + "="*80)
if spread_pct < 0.3:
    print("VERDICT: EXCELLENT spread < 0.3%")
elif spread_pct < 0.5:
    print("VERDICT: BON spread < 0.5% - acceptable pour delta-neutral")
elif spread_pct < 1.0:
    print("VERDICT: SPREAD ELEVE (0.5-1%) - surveiller de pres!")
else:
    print("VERDICT: SPREAD TROP LARGE > 1% - NE PAS TRADER!")
print("="*80)

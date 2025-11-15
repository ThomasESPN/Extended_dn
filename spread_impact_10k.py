#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CALCUL CORRECT: FUNDING SUR NOTIONAL (pas leverage)
5k par wallet = 10k total notional
Funding profit = $12
Combien perdu au spread?
"""

# SETUP
total_notional = 10000  # $10k TOTAL
notional_per_side = 5000  # $5k Extended + $5k Hyperliquid

# PRIX ZORA
extended_ask = 0.055655
extended_bid = 0.055614
hyperliquid_bid = 0.055452
hyperliquid_ask = 0.055464

funding_profit = 12.0

print("="*70)
print("CALCUL: 5K par wallet (10K total) - Funding $12")
print("="*70)

# Combien de ZORA avec 5k par cote?
size_extended = notional_per_side / extended_ask
size_hyperliquid = notional_per_side / hyperliquid_bid
avg_size = (size_extended + size_hyperliquid) / 2

print(f"\nTotal notional: ${total_notional:,}")
print(f"  Extended:  ${notional_per_side:,} = {size_extended:,.0f} ZORA")
print(f"  Hyperliquid: ${notional_per_side:,} = {size_hyperliquid:,.0f} ZORA")
print(f"\nMEME SIZE: {avg_size:,.0f} ZORA sur les deux")
print(f"Funding profit: ${funding_profit:.2f}")

# SCENARIO 1: TAKER
print("\n" + "="*70)
print("SCENARIO 1: TAKER (market orders)")
print("="*70)

spread_taker = extended_ask - hyperliquid_bid
cost_taker = spread_taker * avg_size

print(f"\nSpread: ${spread_taker:.6f}")
print(f"  Extended BUY @ ASK:  ${extended_ask:.6f}")
print(f"  Hyperliquid SELL @ BID: ${hyperliquid_bid:.6f}")
print(f"\nCout du spread: ${cost_taker:.2f}")
print(f"\nProfit NET: ${funding_profit:.2f} - ${cost_taker:.2f} = ${funding_profit - cost_taker:.2f}")
print(f"Tu PERDS {(cost_taker/funding_profit)*100:.1f}% du profit!")

# SCENARIO 2: MAKER
print("\n" + "="*70)
print("SCENARIO 2: MAKER (limit @ mid-price)")
print("="*70)

extended_mid = (extended_bid + extended_ask) / 2
hyperliquid_mid = (hyperliquid_bid + hyperliquid_ask) / 2
spread_maker = extended_mid - hyperliquid_mid
cost_maker = spread_maker * avg_size

print(f"\nSpread: ${spread_maker:.6f}")
print(f"  Extended @ MID:  ${extended_mid:.6f}")
print(f"  Hyperliquid @ MID: ${hyperliquid_mid:.6f}")
print(f"\nCout du spread: ${cost_maker:.2f}")
print(f"\nProfit NET: ${funding_profit:.2f} - ${cost_maker:.2f} = ${funding_profit - cost_maker:.2f}")
print(f"Tu gardes {((funding_profit - cost_maker)/funding_profit)*100:.1f}% du profit!")

# SCENARIO 3: LIMIT 5 MIN AVANT
print("\n" + "="*70)
print("SCENARIO 3: LIMIT 5 MIN AVANT (+-0.01% mid)")
print("="*70)

offset = 0.0001
extended_limit = extended_mid * (1 - offset)
hyperliquid_limit = hyperliquid_mid * (1 + offset)
spread_limit = extended_limit - hyperliquid_limit
cost_limit = spread_limit * avg_size

print(f"\nSpread: ${spread_limit:.6f}")
print(f"  Extended:  ${extended_limit:.6f} (mid - 0.01%)")
print(f"  Hyperliquid: ${hyperliquid_limit:.6f} (mid + 0.01%)")
print(f"\nCout du spread: ${cost_limit:.2f}")
print(f"\nProfit NET: ${funding_profit:.2f} - ${cost_limit:.2f} = ${funding_profit - cost_limit:.2f}")
print(f"Tu gardes {((funding_profit - cost_limit)/funding_profit)*100:.1f}% du profit!")

# REPONSE
print("\n" + "="*70)
print("REPONSE FINALE")
print("="*70)

print(f"\nAvec 5k par wallet (10k total), funding $12:")
print(f"\n  TAKER:       perte ${cost_taker:.2f} ({(cost_taker/funding_profit)*100:.0f}%)")
print(f"  MAKER:       perte ${cost_maker:.2f} ({(cost_maker/funding_profit)*100:.0f}%)")
print(f"  LIMIT 5 MIN: perte ${cost_limit:.2f} ({(cost_limit/funding_profit)*100:.0f}%)")

print(f"\nMEILLEURE STRATEGIE: LIMIT orders 5 min avant")
print(f"  Tu perds seulement ${cost_limit:.2f}")
print(f"  Tu GARDES ${funding_profit - cost_limit:.2f} ({((funding_profit - cost_limit)/funding_profit)*100:.0f}% du profit)")

print("\n" + "="*70)

#!/usr/bin/env python3
"""
Analyse de l'impact du spread sur un trade de 10k USD
Funding profit = $12 USD, combien perdu au spread?
"""

print("="*80)
print("IMPACT DU SPREAD SUR 10K USD - FUNDING PROFIT $12")
print("="*80)

# DONNÉES DU BOT SNIPER
zora_funding_extended = -0.0015  # -0.0015% (tu PAYES car négatif)
zora_funding_hyperliquid = -0.0014  # -0.0014% (tu PAYES car négatif)
funding_profit = 15.31  # $15.31 selon bot_sniper

print(f"\n📊 FUNDING RATES (du bot_sniper):")
print(f"  Extended LONG:       {zora_funding_extended:.4f}%")
print(f"  Hyperliquid SHORT:   {zora_funding_hyperliquid:.4f}%")
print(f"  Différence:          {abs(zora_funding_extended - zora_funding_hyperliquid):.4f}%")
print(f"  Profit attendu:      ${funding_profit:.2f}")

# CAPITAL & LEVERAGE
capital = 10000  # $10k
leverage = 3
position_size = capital * leverage  # $30k par côté

print(f"\n💰 CAPITAL:")
print(f"  Margin:              ${capital:,.0f}")
print(f"  Leverage:            {leverage}x")
print(f"  Position size:       ${position_size:,.0f} par côté")

# PRIX ACTUELS ZORA (de tes tests précédents)
extended_ask = 0.055655  # Prix pour ACHETER Extended
extended_bid = 0.055614  # Prix pour VENDRE Extended
hyperliquid_ask = 0.055464  # Prix pour ACHETER Hyperliquid
hyperliquid_bid = 0.055452  # Prix pour VENDRE Hyperliquid

print(f"\n📈 PRIX ZORA:")
print(f"  Extended:    bid=${extended_bid:.6f}, ask=${extended_ask:.6f}")
print(f"  Hyperliquid: bid=${hyperliquid_bid:.6f}, ask=${hyperliquid_ask:.6f}")

# SCÉNARIO 1: ORDRES TAKER (exécution immédiate)
print("\n" + "="*80)
print("SCÉNARIO 1: ORDRES TAKER (MARKET ORDERS)")
print("="*80)

# Tu ACHÈTES Extended au ASK, tu VENDS Hyperliquid au BID
extended_entry_taker = extended_ask  # $0.055655
hyperliquid_entry_taker = hyperliquid_bid  # $0.055452

# Combien de ZORA avec 30k?
size_extended_taker = position_size / extended_entry_taker
size_hyperliquid_taker = position_size / hyperliquid_entry_taker

print(f"\n🔥 TAKER (exécution immédiate):")
print(f"  Extended LONG:  BUY @ ASK ${extended_entry_taker:.6f}")
print(f"  Size:           {size_extended_taker:,.0f} ZORA")
print(f"\n  Hyperliquid SHORT: SELL @ BID ${hyperliquid_entry_taker:.6f}")
print(f"  Size:           {size_hyperliquid_taker:,.0f} ZORA")

# DELTA NEUTRAL = même SIZE
avg_size_taker = (size_extended_taker + size_hyperliquid_taker) / 2
print(f"\n  ⚠️ PROBLÈME: sizes différentes!")
print(f"  Pour delta-neutral, on force la MÊME size: {avg_size_taker:,.0f} ZORA")

# Recalculer avec même size
same_size = avg_size_taker
extended_notional_taker = same_size * extended_entry_taker
hyperliquid_notional_taker = same_size * hyperliquid_entry_taker

spread_taker = abs(extended_entry_taker - hyperliquid_entry_taker)
spread_cost_taker = spread_taker * same_size

print(f"\n💸 COÛT DU SPREAD (TAKER):")
print(f"  Extended:    {same_size:,.0f} ZORA @ ${extended_entry_taker:.6f} = ${extended_notional_taker:,.2f}")
print(f"  Hyperliquid: {same_size:,.0f} ZORA @ ${hyperliquid_entry_taker:.6f} = ${hyperliquid_notional_taker:,.2f}")
print(f"  Spread:      ${spread_taker:.6f} × {same_size:,.0f} = ${spread_cost_taker:.2f}")

# SCÉNARIO 2: ORDRES MAKER (limit orders)
print("\n" + "="*80)
print("SCÉNARIO 2: ORDRES MAKER (LIMIT @ MID-PRICE)")
print("="*80)

# Tu places LIMIT au mid-price
extended_mid = (extended_bid + extended_ask) / 2  # $0.0556345
hyperliquid_mid = (hyperliquid_bid + hyperliquid_ask) / 2  # $0.055458

# Légèrement agressif pour fill rapide
extended_entry_maker = extended_mid - 0.00001  # Mid - $0.00001 (meilleur que mid)
hyperliquid_entry_maker = hyperliquid_mid + 0.00001  # Mid + $0.00001

print(f"\n🎯 MAKER (limit orders au mid-price):")
print(f"  Extended LONG:  LIMIT BUY @ ${extended_entry_maker:.6f}")
print(f"  Hyperliquid SHORT: LIMIT SELL @ ${hyperliquid_entry_maker:.6f}")

spread_maker = abs(extended_entry_maker - hyperliquid_entry_maker)
spread_cost_maker = spread_maker * same_size

print(f"\n💸 COÛT DU SPREAD (MAKER):")
print(f"  Spread:      ${spread_maker:.6f} × {same_size:,.0f} = ${spread_cost_maker:.2f}")

# COMPARAISON
print("\n" + "="*80)
print("COMPARAISON: TAKER vs MAKER")
print("="*80)

saving = spread_cost_taker - spread_cost_maker
saving_pct = (saving / funding_profit) * 100

print(f"\n💰 COÛT DU SPREAD:")
print(f"  TAKER:       ${spread_cost_taker:.2f}")
print(f"  MAKER:       ${spread_cost_maker:.2f}")
print(f"  ÉCONOMIE:    ${saving:.2f} ({saving_pct:.1f}% du profit funding)")

# PROFIT NET
profit_net_taker = funding_profit - spread_cost_taker
profit_net_maker = funding_profit - spread_cost_maker

print(f"\n📊 PROFIT NET (Funding $12 - Spread):")
print(f"  TAKER:       ${funding_profit:.2f} - ${spread_cost_taker:.2f} = ${profit_net_taker:.2f}")
print(f"  MAKER:       ${funding_profit:.2f} - ${spread_cost_maker:.2f} = ${profit_net_maker:.2f}")

print(f"\n⚠️ TAKER perd {abs(profit_net_taker / funding_profit) * 100:.1f}% du profit au spread!")
print(f"✅ MAKER garde {abs(profit_net_maker / funding_profit) * 100:.1f}% du profit!")

# SCÉNARIO 3: LIMIT ORDERS 5 MIN AVANT (même prix)
print("\n" + "="*80)
print("SCÉNARIO 3: LIMIT ORDERS 5 MIN AVANT LE FUNDING")
print("="*80)

print(f"\nSTRATÉGIE:")
print(f"  1. Placer LIMIT orders 5 min avant le funding")
print(f"  2. Prix très proche du mid (±0.005%)")
print(f"  3. Attendre le fill")
print(f"  4. Si pas fill en 3 min → annuler et passer TAKER")

# Avec ±0.005% du mid
offset_pct = 0.00005  # 0.005%
extended_entry_limit = extended_mid * (1 - offset_pct)
hyperliquid_entry_limit = hyperliquid_mid * (1 + offset_pct)

spread_limit = abs(extended_entry_limit - hyperliquid_entry_limit)
spread_cost_limit = spread_limit * same_size

print(f"\n🎯 LIMIT 5 MIN AVANT:")
print(f"  Extended:    LIMIT BUY @ ${extended_entry_limit:.6f} (mid - 0.005%)")
print(f"  Hyperliquid: LIMIT SELL @ ${hyperliquid_entry_limit:.6f} (mid + 0.005%)")
print(f"  Spread:      ${spread_limit:.6f} × {same_size:,.0f} = ${spread_cost_limit:.2f}")

profit_net_limit = funding_profit - spread_cost_limit

print(f"\n📊 PROFIT NET:")
print(f"  ${funding_profit:.2f} - ${spread_cost_limit:.2f} = ${profit_net_limit:.2f}")
print(f"  Tu gardes {abs(profit_net_limit / funding_profit) * 100:.1f}% du profit!")

# RÉPONSE À LA QUESTION
print("\n" + "="*80)
print("RÉPONSE: AVEC 10K USD, FUNDING PROFIT $12, COMBIEN PERDU AU SPREAD?")
print("="*80)

# Recalculer pour funding profit de $12 exactement
funding_profit_target = 12.0

# Ratio entre $15.31 et $12
ratio = funding_profit_target / funding_profit

# Ajuster les spreads
spread_cost_taker_12 = spread_cost_taker * ratio
spread_cost_maker_12 = spread_cost_maker * ratio
spread_cost_limit_12 = spread_cost_limit * ratio

profit_net_taker_12 = funding_profit_target - spread_cost_taker_12
profit_net_maker_12 = funding_profit_target - spread_cost_maker_12
profit_net_limit_12 = funding_profit_target - spread_cost_limit_12

print(f"\n💰 AVEC FUNDING PROFIT = ${funding_profit_target:.2f}:")
print(f"\n  TAKER (market orders):")
print(f"    Spread cost: ${spread_cost_taker_12:.2f}")
print(f"    Profit net:  ${profit_net_taker_12:.2f}")
print(f"    Tu PERDS:    {abs((spread_cost_taker_12 / funding_profit_target) * 100):.1f}% du profit!")
print(f"\n  MAKER (limit @ mid):")
print(f"    Spread cost: ${spread_cost_maker_12:.2f}")
print(f"    Profit net:  ${profit_net_maker_12:.2f}")
print(f"    Tu PERDS:    {abs((spread_cost_maker_12 / funding_profit_target) * 100):.1f}% du profit")
print(f"\n  LIMIT 5 MIN AVANT:")
print(f"    Spread cost: ${spread_cost_limit_12:.2f}")
print(f"    Profit net:  ${profit_net_limit_12:.2f}")
print(f"    Tu PERDS:    {abs((spread_cost_limit_12 / funding_profit_target) * 100):.1f}% du profit")

print("\n" + "="*80)
print("CONCLUSION")
print("="*80)

print(f"\n✅ AVEC LIMIT ORDERS 5 MIN AVANT:")
print(f"  - Tu PERDS ~${spread_cost_limit_12:.2f} au spread")
print(f"  - Sur un profit de $12, il te reste ${profit_net_limit_12:.2f}")
print(f"  - C'est {abs((profit_net_limit_12 / funding_profit_target) * 100):.1f}% du profit!")
print(f"\n❌ AVEC MARKET ORDERS (TAKER):")
print(f"  - Tu PERDS ~${spread_cost_taker_12:.2f} au spread")
print(f"  - Il ne reste que ${profit_net_taker_12:.2f}")
print(f"  - Tu perds {abs((spread_cost_taker_12 / funding_profit_target) * 100):.1f}% du profit!")

print(f"\n🎯 RECOMMANDATION:")
print(f"  TOUJOURS utiliser LIMIT orders au mid-price 5 min avant le funding!")
print(f"  L'écart sera MINIMAL et tu garderas ~{abs((profit_net_limit_12 / funding_profit_target) * 100):.0f}% du profit!")

print("\n" + "="*80)

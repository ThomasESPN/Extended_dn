"""
Test rapide du bot Extended vs Hyperliquid
"""
from main_extended_hyperliquid import ExtendedHyperliquidBot

# Créer le bot en dry-run
bot = ExtendedHyperliquidBot(dry_run=True)

# Faire UN cycle de test
print("\n" + "="*80)
print("TEST: UN CYCLE")
print("="*80 + "\n")

# 1. Récupérer funding rates
funding_data = bot.get_funding_rates()
print(f"✅ {len(funding_data)} symboles communs\n")

# 2. Trouver opportunités
opportunities = bot.find_opportunities(funding_data)

if opportunities:
    bot.display_opportunities(opportunities)
    
    # 3. Simuler ouverture de position sur RESOLV
    best = opportunities[0]
    print("\n" + "="*80)
    print("TEST: Simulation ouverture position")
    print("="*80)
    
    bot.open_position(
        symbol=best['symbol'],
        long_exchange=best['long_exchange'].lower(),
        short_exchange=best['short_exchange'].lower(),
        size_usd=100
    )
    
    # 4. Monitor
    print("\n" + "="*80)
    print("TEST: Monitor position")
    print("="*80)
    bot.monitor_positions(funding_data)
    
    # 5. Fermer
    print("\n" + "="*80)
    print("TEST: Fermeture position")
    print("="*80)
    bot.close_position(best['symbol'])
    
else:
    print("❌ Aucune opportunité trouvée")

print("\n✅ Test terminé\n")

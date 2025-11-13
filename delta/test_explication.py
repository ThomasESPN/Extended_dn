"""
Test rapide avec explication
"""
from main_extended_hyperliquid import ExtendedHyperliquidBot

print("\n" + "="*80)
print("📚 TEST DU BOT AVEC EXPLICATION")
print("="*80 + "\n")

# Créer le bot
bot = ExtendedHyperliquidBot(dry_run=True)

# Faire un cycle
funding_data = bot.get_funding_rates()
opportunities = bot.find_opportunities(funding_data)

if opportunities:
    bot.display_opportunities(opportunities)
    
    print("\n" + "="*80)
    print("💡 EXPLICATION DÉTAILLÉE (RESOLV)")
    print("="*80)
    
    # Trouver RESOLV
    resolv = next((o for o in opportunities if o['symbol'] == 'RESOLV'), None)
    
    if resolv:
        print(f"\n📊 Funding Rates:")
        print(f"   Extended:    {resolv['long_rate' if resolv['long_exchange'] == 'EXTENDED' else 'short_rate']*100:.4f}%")
        print(f"   Hyperliquid: {resolv['short_rate' if resolv['long_exchange'] == 'EXTENDED' else 'long_rate']*100:.4f}%")
        
        print(f"\n🎯 Stratégie:")
        print(f"   Position 1: LONG {resolv['long_exchange']} (taille $10,000)")
        print(f"   → Tu REÇOIS {abs(resolv['long_rate'])*100:.4f}% par heure")
        print(f"   → = ${abs(resolv['long_rate'])*10000:.2f}/h")
        
        print(f"\n   Position 2: SHORT {resolv['short_exchange']} (taille $10,000)")
        print(f"   → Tu PAIES {abs(resolv['short_rate'])*100:.4f}% par heure")
        print(f"   → = ${abs(resolv['short_rate'])*10000:.2f}/h")
        
        print(f"\n💰 Profit Net:")
        print(f"   {abs(resolv['long_rate'])*10000:.2f} - {abs(resolv['short_rate'])*10000:.2f} = ${resolv['profit_per_hour']:.2f}/h")
        
        print(f"\n⏱️  Sur 8 heures:")
        print(f"   ${resolv['profit_per_hour']:.2f} × 8 = ${resolv['profit_per_hour']*8:.2f}")
        
        print(f"\n🔒 Risque de prix: AUCUN (delta-neutral)")
        print(f"   Tu es LONG et SHORT en même temps sur le même actif")
        print(f"   → Si le prix monte/baisse, tu gagnes d'un côté et perds de l'autre")
        print(f"   → Seul le funding compte !\n")
    
    print("="*80 + "\n")

print("✅ Test terminé - Lis GUIDE_FUNDING_ARBITRAGE.md pour plus d'infos\n")

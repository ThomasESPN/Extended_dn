"""
Test du bot V2 avec la vraie stratégie
"""
from main_extended_hyperliquid_v2 import ExtendedHyperliquidBotV2
from datetime import datetime, timezone, timedelta

print("\n" + "="*80)
print("🧪 TEST BOT V2 - STRATÉGIE FINALE")
print("="*80 + "\n")

# Créer le bot
bot = ExtendedHyperliquidBotV2(dry_run=True)

print("\n📅 Heure actuelle UTC:", datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'))

# Prochain cycle HL
next_funding = bot.get_next_hl_funding_time()
print(f"⏰ Prochain cycle Hyperliquid: {next_funding.strftime('%H:%M UTC')}")
close_time = next_funding - timedelta(minutes=bot.close_before_hl_minutes)
print(f"🔒 Fermeture des positions à: {close_time.strftime('%H:%M UTC')}\n")

# Récupérer les rates
print("📊 Récupération des funding rates...\n")
funding_data = bot.get_funding_rates()

# Trouver opportunités
opportunities = bot.find_opportunities(funding_data)

if opportunities:
    bot.display_opportunities(opportunities, next_funding)
    
    print("\n" + "="*80)
    print("💡 DÉTAIL DU CALCUL (RESOLV)")
    print("="*80)
    
    # Trouver RESOLV si disponible
    resolv = next((o for o in opportunities if o['symbol'] == 'RESOLV'), None)
    
    if resolv:
        print(f"\n📊 Rates:")
        print(f"   Extended:    {resolv['ext_rate']*100:.4f}% par heure (payé CHAQUE HEURE)")
        print(f"   Hyperliquid: {resolv['hyp_rate']*100:.4f}% par 8h (payé à 00:00, 08:00, 16:00 UTC SEULEMENT)")
        print(f"                → ON IGNORE HL (on ferme toujours avant les cycles)")
        
        print(f"\n🎯 Position:")
        print(f"   LONG {resolv['long_exchange']}")
        print(f"   SHORT {resolv['short_exchange']}")
        
        print(f"\n💰 Calcul (Extended SEULEMENT) :")
        if resolv['short_exchange'] == 'EXTENDED':
            if resolv['ext_rate'] > 0:
                print(f"   Extended POSITIF → Les SHORTS REÇOIVENT")
                print(f"   → On reçoit {resolv['ext_rate']*100:.4f}% × $10,000 = ${resolv['ext_rate']*10000:.2f} CHAQUE HEURE")
            else:
                print(f"   Extended NÉGATIF → Les SHORTS PAIENT")
                print(f"   → On paie {abs(resolv['ext_rate'])*100:.4f}% × $10,000 = ${abs(resolv['ext_rate'])*10000:.2f} CHAQUE HEURE")
        else:
            if resolv['ext_rate'] < 0:
                print(f"   Extended NÉGATIF → Les LONGS REÇOIVENT")
                print(f"   → On reçoit {abs(resolv['ext_rate'])*100:.4f}% × $10,000 = ${abs(resolv['ext_rate'])*10000:.2f} CHAQUE HEURE")
            else:
                print(f"   Extended POSITIF → Les LONGS PAIENT")
                print(f"   → On paie {resolv['ext_rate']*100:.4f}% × $10,000 = ${resolv['ext_rate']*10000:.2f} CHAQUE HEURE")
        
        print(f"\n   Hyperliquid → ON NE PAIE/REÇOIT RIEN (on ferme avant les cycles 8h)")
        print(f"                  Si on restait ouvert:")
        if resolv['short_exchange'] == 'HYPERLIQUID':
            print(f"                  → On PAIERAIT {abs(resolv['hyp_rate'])*100:.4f}% × $10,000 = ${abs(resolv['hyp_rate'])*10000:.2f} toutes les 8h")
            print(f"                  → Mais on FERME AVANT pour éviter ça !")
        else:
            print(f"                  → On RECEVRAIT {abs(resolv['hyp_rate'])*100:.4f}% × $10,000 = ${abs(resolv['hyp_rate'])*10000:.2f} toutes les 8h")
            print(f"                  → Mais on FERME AVANT (on préfère éviter le risque)")
        
        print(f"\n✅ Profit net: ${resolv['profit_per_hour']:.2f} par heure (Extended CHAQUE HEURE)")
        print(f"✅ Sur 21h (évitant 3 cycles HL): ${resolv['profit_per_hour']*21:.2f} par 24h")
        print(f"✅ Profit avant {next_funding.strftime('%H:%M UTC')}: ${resolv['profit_until_next_cycle']:.2f}\n")

else:
    print("❌ Aucune opportunité trouvée")

print("="*80 + "\n")
print("✅ Test terminé\n")

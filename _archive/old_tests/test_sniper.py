"""
Test du Bot Sniper
"""
from bot_sniper import SniperBot
from datetime import datetime, timezone, timedelta

print("\n" + "="*80)
print("🧪 TEST BOT SNIPER")
print("="*80 + "\n")

# Créer le bot
bot = SniperBot(dry_run=True)

now = datetime.now(timezone.utc)
print(f"📅 Heure actuelle UTC: {now.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"   Heure: {now.hour}")
print(f"   Minute: {now.minute}\n")

# Vérifier si on doit ouvrir
should_open, next_hour = bot.should_open_position()

print("="*80)
print("TIMING D'OUVERTURE:")
print("="*80)
print(f"\n⏰ Minute actuelle: {now.minute}")
print(f"   Fenêtre d'ouverture: minute 58")
print(f"   Prochain funding: {next_hour.strftime('%H:%M UTC')}")
print(f"   Est-ce un cycle HL ? {'OUI ❌' if bot.is_hl_funding_hour(next_hour.hour) else 'NON ✅'}")
print(f"\n   → {'✅ ON OUVRE' if should_open else '❌ On attend minute 58'}\n")

# Vérifier si on doit fermer
should_close = bot.should_close_position()

print("="*80)
print("TIMING DE FERMETURE:")
print("="*80)
print(f"\n⏰ Minute actuelle: {now.minute}")
print(f"   Fenêtre de fermeture: minute 01")
print(f"\n   → {'✅ ON FERME' if should_close else '❌ On attend minute 01'}\n")

# Récupérer les rates
print("="*80)
print("MEILLEURES OPPORTUNITÉS:")
print("="*80 + "\n")

funding_data = bot.get_funding_rates()
best = bot.find_best_opportunity(funding_data)

if best:
    print(f"🏆 BEST SNIPER:")
    print(f"   Symbole: {best['symbol']}")
    print(f"   LONG {best['long_exchange']} + SHORT {best['short_exchange']}")
    print(f"   Funding Extended: {best['ext_rate']*100:.4f}%")
    print(f"   Profit par snipe: ${best['profit_per_hour']:.2f}")
    print(f"\n💰 Sur 24h (21 snipes):")
    print(f"   Profit: 21 × ${best['profit_per_hour']:.2f} = ${best['profit_per_hour']*21:.2f}")
    print(f"   Risque: 21 × 3 min = 63 minutes")
    print(f"\n   VS ancienne stratégie (hold 21h):")
    print(f"   Même profit, 20x MOINS de risque ! 🚀\n")
else:
    print("❌ Aucune opportunité profitable\n")

print("="*80)
print("CYCLE SUIVANT:")
print("="*80)

if should_open:
    print(f"\n✅ Le bot VA ouvrir maintenant (minute 58)")
    print(f"   1. Ouvrir LONG + SHORT (delta-neutral)")
    print(f"   2. Attendre jusqu'à {next_hour.strftime('%H:%M')} (recevoir funding)")
    print(f"   3. Fermer à {next_hour.strftime('%H:01')} (1 min après)")
    print(f"   4. Risque total: 3 minutes seulement !")
elif should_close:
    print(f"\n✅ Le bot VA fermer maintenant (minute 01)")
    print(f"   Funding reçu, on ferme pour minimiser le risque !")
else:
    minutes_until_58 = (58 - now.minute) % 60
    next_open_time = (now + timedelta(minutes=minutes_until_58)).replace(second=0)
    print(f"\n⏳ Prochain snipe:")
    print(f"   À {next_open_time.strftime('%H:58 UTC')}")
    print(f"   Dans {minutes_until_58} minutes")
    print(f"   Funding: {(next_open_time + timedelta(minutes=2)).strftime('%H:00 UTC')}")
    print(f"   Fermeture: {(next_open_time + timedelta(minutes=3)).strftime('%H:01 UTC')}")

print("\n" + "="*80 + "\n")
print("✅ Test terminé - Lis STRATEGIE_SNIPER.md pour plus d'infos\n")

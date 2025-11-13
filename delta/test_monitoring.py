"""
Test du monitoring intelligent (check 5 min avant chaque heure)
"""
from main_extended_hyperliquid_v2 import ExtendedHyperliquidBotV2
from datetime import datetime, timezone

print("\n" + "="*80)
print("🧪 TEST MONITORING INTELLIGENT")
print("="*80 + "\n")

# Créer le bot
bot = ExtendedHyperliquidBotV2(dry_run=True)

# Heure actuelle
now = datetime.now(timezone.utc)
print(f"📅 Heure actuelle UTC: {now.strftime('%Y-%m-%d %H:%M:%S')}")
print(f"   Minutes: {now.minute}\n")

# Vérifier si on doit checker le profit
should_check = bot.should_check_profit()

print("="*80)
print("LOGIQUE DU CHECK PROFIT:")
print("="*80)
print(f"\n⏰ Check profit 5 min avant chaque heure (minute >= 55)")
print(f"   Minute actuelle: {now.minute}")
print(f"   Fenêtre de check: {now.minute >= 55}")
print(f"   → {'✅ ON VÉRIFIE LE PROFIT' if should_check else '❌ On attend (pas encore X:55)'}\n")

if should_check:
    print("💡 On est dans la fenêtre X:55-X:59 :")
    print("   → Le bot VA vérifier si le profit est toujours positif")
    print("   → Si profit > 0 : On GARDE jusqu'à l'heure (on encaisse le funding)")
    print("   → Si profit < 0 : On FERME maintenant (on évite de payer)")
else:
    print("💡 On n'est PAS dans la fenêtre X:55-X:59 :")
    print(f"   → Le bot N'VA PAS vérifier le profit maintenant")
    print(f"   → Il attendra {now.minute}:55 pour checker")
    print(f"   → Comme ça on ne ferme pas pour rien en milieu d'heure !")

print("\n" + "="*80)
print("EXEMPLE SCÉNARIO:")
print("="*80)

print("\n📊 14:30 - Le funding rate change, profit devient négatif")
print("   → Bot: 'Pas encore 14:55, on GARDE la position'")
print("   → On continue de perdre un peu pendant 25 min...")

print("\n📊 14:55 - Vérification automatique du profit")
print("   → Bot: 'On est à 14:55, je vérifie le profit...'")
print("   → Profit toujours négatif → FERMETURE")
print("   → On évite de payer le funding de 15:00 !")

print("\n📊 14:56 - Le funding redevient positif")
print("   → Trop tard, on a fermé à 14:55")
print("   → Mais on a évité de payer à 15:00 !")
print("   → On peut réouvrir après 15:00 si toujours profitable")

print("\n" + "="*80)
print("AVANTAGES:")
print("="*80)
print("\n✅ On ne ferme pas pour rien si le rate fluctue en milieu d'heure")
print("✅ On vérifie juste avant l'heure pour décider si on encaisse ou pas")
print("✅ On maximise les encaissements même si le rate fluctue")
print("\n" + "="*80 + "\n")

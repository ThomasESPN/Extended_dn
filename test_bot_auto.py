"""
Test du bot avec mode auto (1 cycle uniquement)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.main import ArbitrageBot
from config import get_config

# Forcer le mode auto
config = get_config()
config.config['arbitrage']['mode'] = 'auto'
config.config['arbitrage']['check_interval'] = 10  # Court pour le test

print("\n" + "="*80)
print("🧪 TEST DU BOT EN MODE AUTO")
print("="*80)
print("Mode: AUTO - Scan automatique de toutes les paires Loris Tools")
print("1 cycle seulement (pas de loop infinie)")
print("="*80 + "\n")

# Créer et lancer le bot pour 1 cycle
bot = ArbitrageBot()
bot.mode = 'auto'
bot.max_pairs = 5
bot.min_profit_per_hour = 1.0

print("\n▶️  Lancement du cycle AUTO...\n")

try:
    bot.run_auto_cycle()
    print("\n✅ Cycle terminé avec succès!\n")
except Exception as e:
    print(f"\n❌ Erreur: {e}\n")

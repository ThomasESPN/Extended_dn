"""
Bot Sniper - Stratégie Ultra-Optimisée Extended vs Hyperliquid
Ouvre 2 min avant chaque heure, ferme 1 min après
Risque minimal, profit maximal !
"""
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone
from loguru import logger
from tabulate import tabulate

# Ajouter le répertoire src au path
sys.path.insert(0, str(Path(__file__).parent))

from src.exchanges.extended_api import ExtendedAPI
from src.exchanges.hyperliquid_api import HyperliquidAPI


class SniperBot:
    """
    Bot Sniper - Stratégie de timing parfait
    
    Logique:
    - X:58 → Ouvrir LONG Extended + SHORT Hyperliquid (delta-neutral, même size)
    - X:00 → Recevoir funding Extended
    - X:01 → Fermer tout
    
    Risque: 3 minutes par heure au lieu de 60 !
    """
    
    def __init__(self, config_path="config/config.json", dry_run=True):
        """Initialise le bot"""
        # Charger la config
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Paramètres
        self.dry_run = dry_run
        self.wallet_address = self.config['wallet']['address']
        self.private_key = self.config['wallet']['private_key']
        
        # Timing optimisé
        self.open_before_minutes = 58  # Ouvrir à X:58 (2 min avant funding)
        self.close_after_minutes = 1   # Fermer à X:01 (1 min après funding)
        self.close_before_hl_minutes = 5  # Éviter les cycles HL (X:55)
        
        # Cycles Hyperliquid à éviter (UTC)
        self.hl_funding_hours = [0, 8, 16]
        
        # Position tracking
        self.active_positions = {}
        
        # APIs
        logger.info("Initialisation des APIs...")
        
        # Extended API avec tous les credentials
        extended_config = self.config.get('extended', {})
        self.extended = ExtendedAPI(
            wallet_address=self.wallet_address,
            private_key=self.private_key,
            api_key=extended_config.get('api_key'),
            stark_public_key=extended_config.get('stark_public_key'),
            stark_private_key=extended_config.get('stark_private_key'),
            vault_id=extended_config.get('vault_id'),
            client_id=extended_config.get('client_id')
        )
        
        # Hyperliquid API
        self.hyperliquid = HyperliquidAPI(self.wallet_address, self.private_key)
        
        # Logger
        logger.remove()
        logger.add(
            sys.stderr,
            level="INFO",
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
        )
        
        logger.info("✅ Bot Sniper initialisé")
        if self.dry_run:
            logger.warning("⚠️  MODE DRY-RUN")
    
    def is_hl_funding_hour(self, hour):
        """Vérifie si c'est une heure de funding HL"""
        return hour in self.hl_funding_hours
    
    def should_open_position(self):
        """
        Vérifie si on doit ouvrir une position (X:58)
        Et si ce n'est PAS une heure de funding HL
        
        Returns:
            (bool, datetime): (doit_ouvrir, prochaine_heure)
        """
        now_utc = datetime.now(timezone.utc)
        current_minute = now_utc.minute
        next_hour = (now_utc + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        
        # Ouvrir 2 min avant (minute 58)
        should_open = current_minute == (60 - self.open_before_minutes)
        
        # Vérifier que la prochaine heure n'est PAS un cycle HL
        if should_open and self.is_hl_funding_hour(next_hour.hour):
            logger.warning(f"⚠️  {next_hour.strftime('%H:00')} est un cycle HL - ON SKIP")
            return False, next_hour
        
        return should_open, next_hour
    
    def should_close_position(self):
        """
        Vérifie si on doit fermer les positions (X:01)
        
        Returns:
            bool: True si on doit fermer
        """
        now_utc = datetime.now(timezone.utc)
        current_minute = now_utc.minute
        
        # Fermer 1 min après (minute 01)
        return current_minute == self.close_after_minutes
    
    def get_next_snipe_time(self):
        """Retourne l'heure du prochain snipe (X:58)"""
        now_utc = datetime.now(timezone.utc)
        current_minute = now_utc.minute
        
        # Si on est avant X:58, le prochain snipe est cette heure
        if current_minute < self.open_before_minutes:
            next_snipe = now_utc.replace(minute=self.open_before_minutes, second=0, microsecond=0)
            funding_hour = (next_snipe + timedelta(minutes=2)).hour
            if not self.is_hl_funding_hour(funding_hour):
                return next_snipe
        
        # Sinon, chercher la prochaine heure valide
        for i in range(1, 25):
            future = now_utc + timedelta(hours=i)
            next_snipe = future.replace(minute=self.open_before_minutes, second=0, microsecond=0)
            funding_hour = (next_snipe + timedelta(minutes=2)).hour
            if not self.is_hl_funding_hour(funding_hour):
                return next_snipe
        
        return None
    
    def get_funding_rates(self):
        """Récupère les funding rates"""
        logger.debug("Récupération funding rates...")
        
        ext_rates = self.extended.get_all_funding_rates()
        hyp_rates = self.hyperliquid.get_all_funding_rates()
        
        comparison = {}
        
        for symbol in ext_rates.keys():
            if symbol in hyp_rates:
                ext_rate = ext_rates[symbol]['rate']
                hyp_rate = hyp_rates[symbol]['rate']
                
                comparison[symbol] = {
                    'extended': ext_rate,
                    'hyperliquid': hyp_rate,
                    'long_exchange': 'extended' if ext_rate < 0 else 'hyperliquid',
                    'short_exchange': 'hyperliquid' if ext_rate < 0 else 'extended'
                }
        
        return comparison
    
    def calculate_profit_per_hour(self, ext_rate, long_exchange):
        """Calcule le profit par heure (Extended seulement)"""
        position_size = 10000
        
        if long_exchange == 'extended':
            # LONG Extended
            if ext_rate < 0:
                profit = abs(ext_rate) * position_size
            else:
                profit = -abs(ext_rate) * position_size
        else:
            # SHORT Extended
            if ext_rate > 0:
                profit = abs(ext_rate) * position_size
            else:
                profit = -abs(ext_rate) * position_size
        
        return profit
    
    def find_best_opportunity(self, funding_data, show_table=False):
        """Trouve la meilleure opportunité"""
        opportunities = []
        
        for symbol, data in funding_data.items():
            profit = self.calculate_profit_per_hour(
                data['extended'],
                data['long_exchange']
            )
            
            if profit > 0:
                opportunities.append({
                    'symbol': symbol,
                    'long_exchange': data['long_exchange'].upper(),
                    'short_exchange': data['short_exchange'].upper(),
                    'ext_rate': data['extended'],
                    'hyp_rate': data['hyperliquid'],
                    'profit_per_hour': profit
                })
        
        opportunities.sort(key=lambda x: x['profit_per_hour'], reverse=True)
        
        # Afficher le tableau si demandé
        if show_table and opportunities:
            from tabulate import tabulate
            
            logger.info(f"\n✅ {len(opportunities)} opportunités trouvées\n")
            
            table_data = []
            for i, opp in enumerate(opportunities[:20], 1):
                table_data.append([
                    i,
                    opp['symbol'],
                    opp['long_exchange'],
                    f"{opp['ext_rate']:.4f}%" if opp['long_exchange'] == 'EXTENDED' else f"{opp['hyp_rate']:.4f}%",
                    opp['short_exchange'],
                    f"{opp['hyp_rate']:.4f}%" if opp['short_exchange'] == 'HYPERLIQUID' else f"{opp['ext_rate']:.4f}%",
                    f"${opp['profit_per_hour']:.2f}"
                ])
            
            headers = ["#", "Symbole", "LONG", "Rate LONG", "SHORT", "Rate SHORT", "$/snipe"]
            logger.info(tabulate(table_data, headers=headers, tablefmt="grid"))
            logger.info("")
        
        return opportunities[0] if opportunities else None
    
    def open_sniper_position(self, symbol, long_exchange, short_exchange, size_usd=100):
        """
        Ouvre une position sniper (delta-neutral, MÊME SIZE exacte)
        
        IMPORTANT: Les deux ordres doivent être en LIMIT pour être fill à la même size
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"🎯 SNIPER - OUVERTURE: {symbol}")
        logger.info(f"{'='*80}")
        logger.info(f"   📈 LONG {long_exchange.upper()}")
        logger.info(f"   📉 SHORT {short_exchange.upper()}")
        logger.info(f"   💰 Size: ${size_usd} (EXACTEMENT la même sur les deux)")
        logger.info(f"   ⏰ Fermeture dans ~3 minutes")
        
        if self.dry_run:
            logger.warning("   ⚠️  DRY-RUN: Position simulée")
        else:
            try:
                # TODO: Utiliser des ordres LIMIT pour garantir la même size exacte
                # Si market orders, risque de légère différence de fill
                
                # LONG
                if long_exchange == 'extended':
                    self.extended.place_order(symbol, size_usd, is_long=True)
                else:
                    self.hyperliquid.place_order(symbol, size_usd, is_long=True)
                
                # SHORT
                if short_exchange == 'extended':
                    self.extended.place_order(symbol, size_usd, is_long=False)
                else:
                    self.hyperliquid.place_order(symbol, size_usd, is_long=False)
                
                logger.success(f"   ✅ Positions ouvertes (delta-neutral)")
            except Exception as e:
                logger.error(f"   ❌ Erreur: {e}")
                return False
        
        self.active_positions[symbol] = {
            'long_exchange': long_exchange,
            'short_exchange': short_exchange,
            'size_usd': size_usd,
            'opened_at': datetime.now(timezone.utc)
        }
        
        logger.info(f"{'='*80}\n")
        return True
    
    def close_sniper_position(self, symbol):
        """Ferme la position sniper"""
        if symbol not in self.active_positions:
            return False
        
        pos = self.active_positions[symbol]
        duration = datetime.now(timezone.utc) - pos['opened_at']
        
        logger.info(f"\n{'='*80}")
        logger.info(f"💰 SNIPER - FERMETURE: {symbol}")
        logger.info(f"{'='*80}")
        logger.info(f"   Durée: {duration}")
        logger.info(f"   Risque: {duration.total_seconds():.0f} secondes seulement !")
        
        if self.dry_run:
            logger.warning("   ⚠️  DRY-RUN: Fermeture simulée")
        else:
            try:
                # Fermer long
                if pos['long_exchange'] == 'extended':
                    self.extended.close_position(symbol)
                else:
                    self.hyperliquid.close_position(symbol)
                
                # Fermer short
                if pos['short_exchange'] == 'extended':
                    self.extended.close_position(symbol)
                else:
                    self.hyperliquid.close_position(symbol)
                
                logger.success(f"   ✅ Positions fermées")
            except Exception as e:
                logger.error(f"   ❌ Erreur: {e}")
                return False
        
        del self.active_positions[symbol]
        logger.info(f"{'='*80}\n")
        return True
    
    def run(self):
        """Boucle principale"""
        logger.info("\n" + "="*80)
        logger.info("🎯 BOT SNIPER - STRATÉGIE ULTRA-OPTIMISÉE")
        logger.info("="*80)
        logger.info(f"Wallet: {self.wallet_address}")
        logger.info(f"Ouverture: X:58 (2 min avant funding)")
        logger.info(f"Fermeture: X:01 (1 min après funding)")
        logger.info(f"Skip heures HL: {', '.join([f'{h:02d}:00' for h in self.hl_funding_hours])}")
        logger.info(f"Skip heures HL: {', '.join([f'{h:02d}:00' for h in self.hl_funding_hours])}")
        logger.info(f"Mode: {'DRY-RUN' if self.dry_run else 'LIVE'}")
        logger.info("="*80)
        logger.info("")
        logger.info("🚀 STRATÉGIE SNIPER:")
        logger.info("   • X:58 → Ouvrir LONG Extended + SHORT Hyperliquid (delta-neutral)")
        logger.info("   • X:00 → Recevoir funding Extended")
        logger.info("   • X:01 → Fermer tout")
        logger.info("   • Risque: 3 MINUTES au lieu de 60 MINUTES !")
        logger.info("   • Sur 24h: 21 snipers (évitant 00:00, 08:00, 16:00)")
        logger.info("")
        logger.info("⚠️  IMPORTANT:")
        logger.info("   • Les deux positions doivent avoir EXACTEMENT la même size")
        logger.info("   • Utiliser des ordres LIMIT pour garantir le fill identique")
        logger.info("   • Delta-neutral = Pas de risque de prix !")
        logger.info("")
        logger.info("="*80 + "\n")
        
        try:
            last_log_minute = -1
            last_table_minute = -1
            cycle_count = 0
            first_run = True
            
            while True:
                now_utc = datetime.now(timezone.utc)
                
                # Afficher l'heure actuelle toutes les minutes
                if now_utc.minute != last_log_minute:
                    last_log_minute = now_utc.minute
                    cycle_count += 1
                    
                    logger.info("")
                    logger.info("─" * 80)
                    logger.info(f"🔄 CYCLE #{cycle_count} - {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                    logger.info("─" * 80)
                    
                    next_snipe = self.get_next_snipe_time()
                    if next_snipe:
                        minutes_left = int((next_snipe - now_utc).total_seconds() / 60)
                        funding_time = next_snipe + timedelta(minutes=2)
                        logger.info(f"⏰ Prochain snipe: {next_snipe.strftime('%H:%M')} UTC (dans {minutes_left} min)")
                        logger.info(f"💰 Funding reçu à: {funding_time.strftime('%H:%M')} UTC")
                    
                    # Afficher le tableau toutes les 5 minutes OU au premier run
                    if first_run or now_utc.minute % 5 == 0:
                        if first_run:
                            logger.info("\n📊 SCAN INITIAL DES OPPORTUNITÉS\n")
                            first_run = False
                        else:
                            logger.info("\n📊 SCAN DES OPPORTUNITÉS (toutes les 5 min)\n")
                        
                        funding_data = self.get_funding_rates()
                        self.find_best_opportunity(funding_data, show_table=True)
                
                # Vérifier si on doit ouvrir
                should_open, next_hour = self.should_open_position()
                
                if should_open and not self.active_positions:
                    logger.info(f"\n{'═'*80}")
                    logger.info(f"🎯 SNIPER ACTIVATION - {now_utc.strftime('%H:%M:%S UTC')}")
                    logger.info(f"{'═'*80}\n")
                    
                    # Récupérer les rates et afficher le tableau
                    funding_data = self.get_funding_rates()
                    
                    # Trouver la meilleure opportunité (avec tableau)
                    best = self.find_best_opportunity(funding_data, show_table=True)
                    
                    if best:
                        logger.success(
                            f"\n🏆 SÉLECTION: {best['symbol']} - "
                            f"${best['profit_per_hour']:.2f}/snipe - "
                            f"LONG {best['long_exchange']} + SHORT {best['short_exchange']}\n"
                        )
                        
                        # Ouvrir la position
                        self.open_sniper_position(
                            best['symbol'],
                            best['long_exchange'].lower(),
                            best['short_exchange'].lower(),
                            size_usd=100
                        )
                    else:
                        logger.warning("❌ Aucune opportunité profitable - SKIP ce cycle")
                
                # Vérifier si on doit fermer
                should_close = self.should_close_position()
                
                if should_close and self.active_positions:
                    logger.info(f"\n⏰ {now_utc.strftime('%H:%M')} - Fermeture des positions...\n")
                    for symbol in list(self.active_positions.keys()):
                        self.close_sniper_position(symbol)
                
                # Attendre 30 secondes
                time.sleep(30)
                
        except KeyboardInterrupt:
            logger.info("\n\n⚠️  Arrêt demandé...")
            
            if self.active_positions:
                logger.warning(f"Fermeture de {len(self.active_positions)} positions...")
                for symbol in list(self.active_positions.keys()):
                    self.close_sniper_position(symbol)
            
            logger.info("✅ Bot arrêté\n")


def main():
    """Point d'entrée"""
    print("\n" + "="*80)
    print("🎯 BOT SNIPER - STRATÉGIE ULTRA-OPTIMISÉE")
    print("="*80)
    print("Ouvre 2 min avant, ferme 1 min après")
    print("Risque: 3 minutes au lieu de 60 !")
    print("="*80 + "\n")
    
    print("Mode:")
    print("  1. DRY-RUN (simulation)")
    print("  2. LIVE (vraies positions)")
    print()
    
    choice = input("Votre choix (1/2) [1]: ").strip() or "1"
    dry_run = choice == "1"
    
    if not dry_run:
        confirm = input("\n⚠️  MODE LIVE - Confirmer? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("Annulé.")
            return
    
    print()
    
    bot = SniperBot(dry_run=dry_run)
    bot.run()


if __name__ == "__main__":
    main()

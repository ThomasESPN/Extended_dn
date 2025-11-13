"""
Bot Principal - Extended vs Hyperliquid Arbitrage V2
Timing optimisé : Ferme AVANT les cycles Hyperliquid (8h) pour ne jamais payer
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


class ExtendedHyperliquidBotV2:
    """
    Bot de timing funding arbitrage Extended vs Hyperliquid V2
    
    Logique optimisée:
    - Extended = funding 1h (on REÇOIT chaque heure)
    - Hyperliquid = funding 8h (on PAIE toutes les 8h si SHORT)
    - Stratégie: FERMER 5min AVANT le cycle HL, RÉOUVRIR APRÈS
    """
    
    def __init__(self, config_path="config/config.json", dry_run=True):
        """
        Initialise le bot
        
        Args:
            config_path: Chemin vers config.json
            dry_run: Si True, n'ouvre pas vraiment de positions (logs seulement)
        """
        # Charger la config
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Paramètres
        self.dry_run = dry_run
        self.wallet_address = self.config['wallet']['address']
        self.private_key = self.config['wallet']['private_key']
        
        # Seuils
        self.min_spread_bps = 5.0  # Spread minimum pour ouvrir (5 bps = 0.05%)
        self.close_before_hl_minutes = 5  # Fermer 5 minutes AVANT le funding HL
        self.close_before_ext_minutes = 5  # Vérifier profit 5 minutes AVANT chaque heure Extended
        self.reopen_after_hl_minutes = 1  # Réouvrir 1 minute APRÈS le funding HL
        self.check_interval = 30  # Vérifier toutes les 30 secondes
        
        # Cycles Hyperliquid (UTC)
        self.hl_funding_hours = [0, 8, 16]  # 00:00, 08:00, 16:00 UTC
        
        # Position tracking
        self.active_positions = {}  # {symbol: {long_exchange, short_exchange, entry_spread, opened_at}}
        
        # APIs
        logger.info("Initialisation des APIs...")
        self.extended = ExtendedAPI(self.wallet_address, self.private_key)
        self.hyperliquid = HyperliquidAPI(self.wallet_address, self.private_key)
        
        # Logger
        logger.remove()
        logger.add(
            sys.stderr,
            level="INFO",
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
        )
        
        logger.info("✅ Bot Extended vs Hyperliquid V2 initialisé")
        if self.dry_run:
            logger.warning("⚠️  MODE DRY-RUN (pas de vraies positions)")
    
    def get_next_hl_funding_time(self):
        """
        Calcule le prochain cycle de funding Hyperliquid
        
        Returns:
            datetime du prochain funding HL (UTC)
        """
        now_utc = datetime.now(timezone.utc)
        current_hour = now_utc.hour
        
        # Trouver la prochaine heure de funding
        next_funding_hour = None
        for hour in self.hl_funding_hours:
            if hour > current_hour:
                next_funding_hour = hour
                break
        
        # Si aucune heure trouvée aujourd'hui, prendre la première demain
        if next_funding_hour is None:
            next_funding_hour = self.hl_funding_hours[0]
            next_funding_time = now_utc.replace(hour=next_funding_hour, minute=0, second=0, microsecond=0) + timedelta(days=1)
        else:
            next_funding_time = now_utc.replace(hour=next_funding_hour, minute=0, second=0, microsecond=0)
        
        return next_funding_time
    
    def should_check_profit(self):
        """
        Vérifie si on est dans la fenêtre pour vérifier le profit (5 min avant chaque heure)
        
        Returns:
            bool: True si on doit vérifier le profit maintenant
        """
        now_utc = datetime.now(timezone.utc)
        minutes = now_utc.minute
        
        # Vérifier 5 min avant chaque heure (55, 56, 57, 58, 59)
        return minutes >= (60 - self.close_before_ext_minutes)
    
    def should_close_before_hl_funding(self):
        """
        Vérifie si on doit fermer les positions AVANT le funding HL
        
        Returns:
            (bool, datetime): (doit_fermer, prochain_funding_time)
        """
        now_utc = datetime.now(timezone.utc)
        next_funding = self.get_next_hl_funding_time()
        
        # Calculer le temps restant
        time_until_funding = (next_funding - now_utc).total_seconds() / 60  # en minutes
        
        # Fermer si on est dans la fenêtre (5 minutes avant)
        should_close = 0 < time_until_funding <= self.close_before_hl_minutes
        
        return should_close, next_funding
    
    def should_reopen_after_hl_funding(self):
        """
        Vérifie si on peut réouvrir APRÈS le funding HL
        
        Returns:
            bool: True si on peut réouvrir
        """
        now_utc = datetime.now(timezone.utc)
        next_funding = self.get_next_hl_funding_time()
        
        # Calculer le temps depuis le dernier funding
        last_funding = next_funding - timedelta(hours=8)
        minutes_since_funding = (now_utc - last_funding).total_seconds() / 60
        
        # Réouvrir si ça fait plus de X minutes depuis le funding
        can_reopen = minutes_since_funding >= self.reopen_after_hl_minutes
        
        return can_reopen
    
    def get_funding_rates(self):
        """
        Récupère les funding rates de Extended et Hyperliquid
        
        Returns:
            Dict {symbol: {extended: rate, hyperliquid: rate, spread_bps}}
        """
        logger.debug("Récupération funding rates...")
        
        # Extended
        ext_rates = self.extended.get_all_funding_rates()
        logger.debug(f"Extended: {len(ext_rates)} symboles")
        
        # Hyperliquid
        hyp_rates = self.hyperliquid.get_all_funding_rates()
        logger.debug(f"Hyperliquid: {len(hyp_rates)} symboles")
        
        # Matcher les symboles communs
        comparison = {}
        
        for symbol in ext_rates.keys():
            if symbol in hyp_rates:
                ext_rate = ext_rates[symbol]['rate']
                hyp_rate = hyp_rates[symbol]['rate']
                
                # Extended = 1h, Hyperliquid = 8h
                # Normaliser Hyperliquid par heure
                hyp_rate_per_hour = hyp_rate / 8
                
                # Spread en bps (basis points)
                spread_bps = abs(ext_rate - hyp_rate_per_hour) * 10000
                
                comparison[symbol] = {
                    'extended': ext_rate,
                    'hyperliquid': hyp_rate,
                    'hyperliquid_per_hour': hyp_rate_per_hour,
                    'spread_bps': spread_bps,
                    'long_exchange': 'extended' if ext_rate < hyp_rate_per_hour else 'hyperliquid',
                    'short_exchange': 'hyperliquid' if ext_rate < hyp_rate_per_hour else 'extended'
                }
        
        logger.debug(f"Symboles communs: {len(comparison)}")
        return comparison
    
    def calculate_profit_per_hour(self, ext_rate, hyp_rate, long_exchange):
        """
        Calcule le profit PAR HEURE (Extended paie chaque heure, HL on ignore car on ferme avant)
        
        Args:
            ext_rate: Rate Extended (par heure)
            hyp_rate: Rate Hyperliquid (par 8h) - IGNORÉ car on ferme avant les cycles
            long_exchange: 'extended' ou 'hyperliquid'
            
        Returns:
            float: Profit par heure en $
        """
        position_size = 10000
        
        # Extended paie CHAQUE HEURE - c'est notre seule source de profit
        # On ignore HL car on ferme TOUJOURS avant les cycles
        
        if long_exchange == 'extended':
            # LONG Extended
            if ext_rate < 0:
                # Négatif = longs reçoivent
                profit_per_hour = abs(ext_rate) * position_size
            else:
                # Positif = longs paient
                profit_per_hour = -abs(ext_rate) * position_size
        else:
            # SHORT Extended
            if ext_rate > 0:
                # Positif = shorts reçoivent
                profit_per_hour = abs(ext_rate) * position_size
            else:
                # Négatif = shorts paient
                profit_per_hour = -abs(ext_rate) * position_size
        
        return profit_per_hour
    
    def calculate_profit_until_next_hl_cycle(self, ext_rate, hyp_rate, long_exchange):
        """
        Calcule le profit TOTAL jusqu'au prochain cycle HL
        
        Returns:
            float: Profit estimé en $ jusqu'au prochain cycle
        """
        now_utc = datetime.now(timezone.utc)
        next_funding = self.get_next_hl_funding_time()
        hours_until_funding = (next_funding - now_utc).total_seconds() / 3600
        
        # Ne compter que les heures complètes Extended qu'on va encaisser
        hours_until_funding = max(0, hours_until_funding - (self.close_before_hl_minutes / 60))
        
        profit_per_hour = self.calculate_profit_per_hour(ext_rate, hyp_rate, long_exchange)
        
        return profit_per_hour * hours_until_funding
    
    def find_opportunities(self, funding_data):
        """
        Trouve les opportunités d'arbitrage optimisées
        On ne garde que les positions avec profit_per_hour > 0 via Extended
        
        Args:
            funding_data: Dict des funding rates comparés
            
        Returns:
            Liste [{symbol, spread_bps, long_exchange, short_exchange, profit_per_hour, profit_until_next_cycle}]
        """
        opportunities = []
        
        for symbol, data in funding_data.items():
            # Calculer profit par heure (Extended seulement)
            profit_per_hour = self.calculate_profit_per_hour(
                data['extended'],
                data['hyperliquid'],
                data['long_exchange']
            )
            
            # Ne garder que si profitable PAR HEURE
            if profit_per_hour > 0:
                # Calculer profit total jusqu'au prochain cycle HL
                profit_until_cycle = self.calculate_profit_until_next_hl_cycle(
                    data['extended'],
                    data['hyperliquid'],
                    data['long_exchange']
                )
                
                opportunities.append({
                    'symbol': symbol,
                    'spread_bps': data['spread_bps'],
                    'long_exchange': data['long_exchange'].upper(),
                    'short_exchange': data['short_exchange'].upper(),
                    'ext_rate': data['extended'],
                    'hyp_rate': data['hyperliquid'],
                    'hyp_rate_per_hour': data['hyperliquid_per_hour'],
                    'profit_per_hour': profit_per_hour,
                    'profit_until_next_cycle': profit_until_cycle
                })
        
        # Trier par profit par heure
        opportunities.sort(key=lambda x: x['profit_per_hour'], reverse=True)
        
        return opportunities
    
    def display_opportunities(self, opportunities, next_funding_time):
        """Affiche les opportunités avec timing"""
        if not opportunities:
            logger.info("❌ Aucune opportunité trouvée")
            return
        
        now_utc = datetime.now(timezone.utc)
        hours_until = (next_funding_time - now_utc).total_seconds() / 3600
        
        logger.info(f"\n✅ {len(opportunities)} opportunités trouvées")
        logger.info(f"⏰ Prochain cycle HL: {next_funding_time.strftime('%H:%M UTC')} (dans {hours_until:.1f}h)")
        logger.info(f"🔒 On FERME à: {(next_funding_time - timedelta(minutes=self.close_before_hl_minutes)).strftime('%H:%M UTC')}\n")
        
        table_data = []
        for i, opp in enumerate(opportunities[:20], 1):
            # Déterminer les rates pour l'affichage
            if opp['long_exchange'] == 'EXTENDED':
                long_rate = opp['ext_rate']
                short_rate = opp['hyp_rate_per_hour']
            else:
                long_rate = opp['hyp_rate_per_hour']
                short_rate = opp['ext_rate']
            
            table_data.append([
                i,
                opp['symbol'],
                opp['long_exchange'],
                f"{long_rate*100:.4f}%",
                opp['short_exchange'],
                f"{short_rate*100:.4f}%",
                f"${opp['profit_per_hour']:.2f}",
                f"${opp['profit_until_next_cycle']:.2f}"
            ])
        
        headers = ["#", "Symbole", "LONG", "Rate LONG", "SHORT", "Rate SHORT", "$/h (Ext)", f"$ avant {next_funding_time.strftime('%H:%M')}"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        
        # Best
        best = opportunities[0]
        logger.success(
            f"\n🏆 BEST: {best['symbol']}\n"
            f"   📈 LONG {best['long_exchange']}\n"
            f"   📉 SHORT {best['short_exchange']}\n"
            f"   � Profit: ${best['profit_per_hour']:.2f}/h (Extended seulement)\n"
            f"   � Total avant {next_funding_time.strftime('%H:%M UTC')}: ${best['profit_until_next_cycle']:.2f}\n"
            f"   ⏰ On FERME à {(next_funding_time - timedelta(minutes=self.close_before_hl_minutes)).strftime('%H:%M UTC')} (avant cycle HL)"
        )
    
    def open_position(self, symbol, long_exchange, short_exchange, size_usd=100):
        """Ouvre une position d'arbitrage"""
        logger.info(f"\n{'='*80}")
        logger.info(f"🔓 OUVERTURE POSITION: {symbol}")
        logger.info(f"{'='*80}")
        logger.info(f"   📈 LONG {long_exchange.upper()}")
        logger.info(f"   📉 SHORT {short_exchange.upper()}")
        logger.info(f"   💰 Size: ${size_usd}")
        
        if self.dry_run:
            logger.warning("   ⚠️  DRY-RUN: Position simulée")
        else:
            try:
                # Ouvrir long
                if long_exchange == 'extended':
                    self.extended.place_order(symbol, size_usd, is_long=True)
                else:
                    self.hyperliquid.place_order(symbol, size_usd, is_long=True)
                
                # Ouvrir short
                if short_exchange == 'extended':
                    self.extended.place_order(symbol, size_usd, is_long=False)
                else:
                    self.hyperliquid.place_order(symbol, size_usd, is_long=False)
                
                logger.success(f"   ✅ Positions ouvertes")
            except Exception as e:
                logger.error(f"   ❌ Erreur: {e}")
                return False
        
        # Tracker la position
        self.active_positions[symbol] = {
            'long_exchange': long_exchange,
            'short_exchange': short_exchange,
            'size_usd': size_usd,
            'opened_at': datetime.now(timezone.utc)
        }
        
        logger.info(f"{'='*80}\n")
        return True
    
    def close_position(self, symbol, reason=""):
        """Ferme une position d'arbitrage"""
        if symbol not in self.active_positions:
            logger.warning(f"Position {symbol} introuvable")
            return False
        
        pos = self.active_positions[symbol]
        
        logger.info(f"\n{'='*80}")
        logger.info(f"🔒 FERMETURE POSITION: {symbol}")
        if reason:
            logger.info(f"   Raison: {reason}")
        logger.info(f"{'='*80}")
        logger.info(f"   Durée: {datetime.now(timezone.utc) - pos['opened_at']}")
        
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
        
        # Retirer du tracking
        del self.active_positions[symbol]
        
        logger.info(f"{'='*80}\n")
        return True
    
    def run(self):
        """Boucle principale du bot"""
        logger.info("\n" + "="*80)
        logger.info("🚀 BOT EXTENDED vs HYPERLIQUID V2 - TIMING OPTIMISÉ")
        logger.info("="*80)
        logger.info(f"Wallet: {self.wallet_address}")
        logger.info(f"Spread minimum: {self.min_spread_bps} bps")
        logger.info(f"Fermeture avant HL: {self.close_before_hl_minutes} min")
        logger.info(f"Check profit avant Extended: {self.close_before_ext_minutes} min avant chaque heure")
        logger.info(f"Réouverture après HL: {self.reopen_after_hl_minutes} min")
        logger.info(f"Check interval: {self.check_interval}s")
        logger.info(f"Mode: {'DRY-RUN' if self.dry_run else 'LIVE'}")
        logger.info("="*80)
        logger.info("")
        logger.info("💡 STRATÉGIE OPTIMISÉE:")
        logger.info("   • Notre profit vient d'EXTENDED qui paie CHAQUE HEURE")
        logger.info("   • Hyperliquid paie toutes les 8H (00:00, 08:00, 16:00 UTC)")
        logger.info("   • On FERME TOUJOURS 5min AVANT le cycle HL (peu importe LONG ou SHORT)")
        logger.info("   • On RÉOUVRE juste APRÈS le cycle HL si toujours profitable")
        logger.info("")
        logger.info("💰 MONITORING INTELLIGENT:")
        logger.info("   • On vérifie le profit 5 MIN AVANT chaque heure Extended (X:55)")
        logger.info("   • Si profit > 0 à X:55 → On GARDE jusqu'à X:00 (on encaisse)")
        logger.info("   • Si profit < 0 à X:55 → On FERME (on évite de payer)")
        logger.info("   • Comme ça on ne ferme pas pour rien en milieu d'heure !")
        logger.info("")
        logger.info("="*80 + "\n")
        
        try:
            cycle = 0
            while True:
                cycle += 1
                logger.info(f"\n{'─'*80}")
                logger.info(f"🔄 CYCLE #{cycle} - {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
                logger.info(f"{'─'*80}\n")
                
                # Vérifier si on doit fermer avant le funding HL
                should_close, next_funding = self.should_close_before_hl_funding()
                
                if should_close and self.active_positions:
                    logger.warning(f"⚠️  FERMETURE AVANT FUNDING HL ({next_funding.strftime('%H:%M UTC')})")
                    for symbol in list(self.active_positions.keys()):
                        self.close_position(symbol, reason="Avant funding Hyperliquid")
                
                # Vérifier si on peut réouvrir
                can_reopen = self.should_reopen_after_hl_funding()
                
                if not can_reopen:
                    logger.info("⏳ Attente après funding HL avant de réouvrir...")
                    time.sleep(self.check_interval)
                    continue
                
                # 1. Récupérer funding rates
                funding_data = self.get_funding_rates()
                
                # 2. Trouver opportunités
                opportunities = self.find_opportunities(funding_data)
                
                if opportunities:
                    self.display_opportunities(opportunities, next_funding)
                else:
                    logger.info("❌ Aucune opportunité trouvée\n")
                
                # 3. Monitor positions actives - FERMER si profit devient négatif
                # MAIS seulement 5 min avant chaque heure Extended (pour ne pas fermer pour rien)
                if self.active_positions and self.should_check_profit():
                    logger.debug("Vérification profit (5 min avant l'heure)...")
                    for symbol in list(self.active_positions.keys()):
                        pos = self.active_positions[symbol]
                        
                        # Récupérer les rates actuels pour ce symbole
                        if symbol in funding_data:
                            data = funding_data[symbol]
                            
                            # Calculer le profit actuel par heure
                            current_profit_per_hour = self.calculate_profit_per_hour(
                                data['extended'],
                                data['hyperliquid'],
                                pos['long_exchange']
                            )
                            
                            # Si le profit devient négatif ou trop faible, fermer
                            if current_profit_per_hour <= 0:
                                logger.warning(
                                    f"⚠️  {symbol}: Profit devenu négatif "
                                    f"(${current_profit_per_hour:.2f}/h) → FERMETURE AVANT HEURE"
                                )
                                self.close_position(symbol, reason="Profit négatif (check avant heure)")
                            else:
                                logger.debug(
                                    f"   {symbol}: Profit ${current_profit_per_hour:.2f}/h - OK (on garde)"
                                )
                
                # 4. Afficher positions actives
                if self.active_positions:
                    logger.info(f"\n📊 Positions actives: {len(self.active_positions)}")
                    for sym, pos in self.active_positions.items():
                        age = datetime.now(timezone.utc) - pos['opened_at']
                        logger.info(
                            f"   {sym}: LONG {pos['long_exchange'].upper()} + "
                            f"SHORT {pos['short_exchange'].upper()} "
                            f"(depuis {age})"
                        )
                    logger.info("")
                
                # 4. Attendre avant prochain cycle
                logger.debug(f"Attente {self.check_interval}s...\n")
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            logger.info("\n\n⚠️  Arrêt demandé par l'utilisateur...")
            
            # Fermer toutes les positions
            if self.active_positions:
                logger.warning(f"Fermeture de {len(self.active_positions)} positions...")
                for symbol in list(self.active_positions.keys()):
                    self.close_position(symbol, reason="Arrêt du bot")
            
            logger.info("✅ Bot arrêté proprement\n")


def main():
    """Point d'entrée"""
    print("\n" + "="*80)
    print("🎯 BOT ARBITRAGE EXTENDED vs HYPERLIQUID V2")
    print("="*80)
    print("Timing optimisé: Ferme AVANT les cycles Hyperliquid")
    print("="*80 + "\n")
    
    # Demander le mode
    print("Mode:")
    print("  1. DRY-RUN (simulation, pas de vraies positions)")
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
    
    # Lancer le bot
    bot = ExtendedHyperliquidBotV2(dry_run=dry_run)
    bot.run()


if __name__ == "__main__":
    main()

"""
Bot Principal - Extended vs Hyperliquid Arbitrage
Monitor en temps réel et fermeture automatique des positions
"""
import sys
import time
import json
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger
from tabulate import tabulate

# Ajouter le répertoire src au path
sys.path.insert(0, str(Path(__file__).parent))

from src.exchanges.extended_api import ExtendedAPI
from src.exchanges.hyperliquid_api import HyperliquidAPI


class ExtendedHyperliquidBot:
    """
    Bot de timing funding arbitrage Extended vs Hyperliquid
    
    Logique:
    - Monitor les funding rates en temps réel
    - Ouvre positions quand spread > seuil
    - Ferme automatiquement quand spread disparaît
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
        self.close_spread_bps = 2.0  # Spread pour fermer (2 bps = 0.02%)
        self.check_interval = 60  # Vérifier toutes les 60 secondes
        
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
        
        logger.info("✅ Bot Extended vs Hyperliquid initialisé")
        if self.dry_run:
            logger.warning("⚠️  MODE DRY-RUN (pas de vraies positions)")
    
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
                
                # Spread en bps (basis points)
                spread_bps = abs(ext_rate - hyp_rate) * 10000
                
                comparison[symbol] = {
                    'extended': ext_rate,
                    'hyperliquid': hyp_rate,
                    'spread_bps': spread_bps,
                    'long_exchange': 'extended' if ext_rate < hyp_rate else 'hyperliquid',
                    'short_exchange': 'hyperliquid' if ext_rate < hyp_rate else 'extended'
                }
        
        logger.debug(f"Symboles communs: {len(comparison)}")
        return comparison
    
    def find_opportunities(self, funding_data):
        """
        Trouve les opportunités d'arbitrage
        
        Args:
            funding_data: Dict des funding rates comparés
            
        Returns:
            Liste [{symbol, spread_bps, long_exchange, short_exchange, profit_per_hour}]
        """
        opportunities = []
        
        for symbol, data in funding_data.items():
            if data['spread_bps'] >= self.min_spread_bps:
                # Calculer profit par heure (sur $10,000)
                ext_rate = data['extended']
                hyp_rate = data['hyperliquid']
                
                # Le long reçoit le funding (négatif), le short paie
                if data['long_exchange'] == 'extended':
                    long_profit = abs(ext_rate) * 10000  # Reçoit
                    short_cost = abs(hyp_rate) * 10000  # Paie
                else:
                    long_profit = abs(hyp_rate) * 10000
                    short_cost = abs(ext_rate) * 10000
                
                profit_per_hour = long_profit - short_cost
                
                opportunities.append({
                    'symbol': symbol,
                    'spread_bps': data['spread_bps'],
                    'long_exchange': data['long_exchange'].upper(),
                    'short_exchange': data['short_exchange'].upper(),
                    'long_rate': ext_rate if data['long_exchange'] == 'extended' else hyp_rate,
                    'short_rate': hyp_rate if data['long_exchange'] == 'extended' else ext_rate,
                    'profit_per_hour': profit_per_hour
                })
        
        # Trier par spread
        opportunities.sort(key=lambda x: x['spread_bps'], reverse=True)
        
        return opportunities
    
    def display_opportunities(self, opportunities):
        """Affiche les opportunités"""
        if not opportunities:
            logger.info("❌ Aucune opportunité trouvée")
            return
        
        logger.info(f"\n✅ {len(opportunities)} opportunités trouvées\n")
        
        table_data = []
        for i, opp in enumerate(opportunities[:20], 1):
            table_data.append([
                i,
                opp['symbol'],
                f"{opp['spread_bps']:.1f}",
                opp['long_exchange'],
                f"{opp['long_rate']*100:.4f}%",
                opp['short_exchange'],
                f"{opp['short_rate']*100:.4f}%",
                f"${opp['profit_per_hour']:.2f}"
            ])
        
        headers = ["#", "Symbole", "Spread(bps)", "LONG", "Rate LONG", "SHORT", "Rate SHORT", "$/h"]
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        
        # Best avec explication
        best = opportunities[0]
        logger.success(
            f"\n🏆 BEST: {best['symbol']} - "
            f"Spread {best['spread_bps']:.1f} bps - "
            f"${best['profit_per_hour']:.2f}/h\n"
            f"   📈 LONG {best['long_exchange']} @ {best['long_rate']*100:.4f}% (TU REÇOIS funding)\n"
            f"   📉 SHORT {best['short_exchange']} @ {best['short_rate']*100:.4f}% (TU PAIES funding)\n"
            f"   💰 Profit = {abs(best['long_rate'])*100:.4f}% - {abs(best['short_rate'])*100:.4f}% = {best['spread_bps']/100:.4f}%/h"
        )
    
    def open_position(self, symbol, long_exchange, short_exchange, size_usd=100):
        """
        Ouvre une position d'arbitrage
        
        Args:
            symbol: Symbole (ex: 'RESOLV')
            long_exchange: 'extended' ou 'hyperliquid'
            short_exchange: 'extended' ou 'hyperliquid'
            size_usd: Taille en USD
        """
        logger.info(f"\n{'='*80}")
        logger.info(f"🔓 OUVERTURE POSITION: {symbol}")
        logger.info(f"{'='*80}")
        logger.info(f"   📈 LONG {long_exchange.upper()}")
        logger.info(f"   📉 SHORT {short_exchange.upper()}")
        logger.info(f"   💰 Size: ${size_usd}")
        
        if self.dry_run:
            logger.warning("   ⚠️  DRY-RUN: Position simulée (pas de vrai trade)")
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
            'opened_at': datetime.now(),
            'entry_spread': None  # Sera mis à jour
        }
        
        logger.info(f"{'='*80}\n")
        return True
    
    def close_position(self, symbol):
        """
        Ferme une position d'arbitrage
        
        Args:
            symbol: Symbole à fermer
        """
        if symbol not in self.active_positions:
            logger.warning(f"Position {symbol} introuvable")
            return False
        
        pos = self.active_positions[symbol]
        
        logger.info(f"\n{'='*80}")
        logger.info(f"🔒 FERMETURE POSITION: {symbol}")
        logger.info(f"{'='*80}")
        logger.info(f"   Durée: {datetime.now() - pos['opened_at']}")
        
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
    
    def monitor_positions(self, funding_data):
        """
        Monitor les positions actives et ferme si spread disparaît
        
        Args:
            funding_data: Dict des funding rates actuels
        """
        if not self.active_positions:
            return
        
        logger.debug(f"Monitoring {len(self.active_positions)} positions actives...")
        
        for symbol in list(self.active_positions.keys()):
            if symbol not in funding_data:
                logger.warning(f"⚠️  {symbol}: Funding rate non disponible")
                continue
            
            data = funding_data[symbol]
            current_spread = data['spread_bps']
            
            # Vérifier si on doit fermer
            if current_spread < self.close_spread_bps:
                logger.warning(
                    f"⚠️  {symbol}: Spread tombé à {current_spread:.1f} bps "
                    f"(seuil: {self.close_spread_bps} bps) → FERMETURE"
                )
                self.close_position(symbol)
            else:
                logger.debug(
                    f"   {symbol}: Spread {current_spread:.1f} bps - OK"
                )
    
    def run(self):
        """
        Boucle principale du bot
        """
        logger.info("\n" + "="*80)
        logger.info("🚀 BOT EXTENDED vs HYPERLIQUID - DÉMARRÉ")
        logger.info("="*80)
        logger.info(f"Wallet: {self.wallet_address}")
        logger.info(f"Spread minimum: {self.min_spread_bps} bps")
        logger.info(f"Spread fermeture: {self.close_spread_bps} bps")
        logger.info(f"Check interval: {self.check_interval}s")
        logger.info(f"Mode: {'DRY-RUN' if self.dry_run else 'LIVE'}")
        logger.info("="*80)
        logger.info("")
        logger.info("💡 LOGIQUE DU BOT:")
        logger.info("   • Funding rate NÉGATIF = Les LONGS REÇOIVENT de l'argent")
        logger.info("   • Funding rate POSITIF = Les SHORTS REÇOIVENT de l'argent")
        logger.info("")
        logger.info("   Exemple: RESOLV @ -0.9155% (Extended) vs -0.6579% (Hyperliquid)")
        logger.info("   → LONG Extended (reçois 0.9155%/h) + SHORT Hyperliquid (paies 0.6579%/h)")
        logger.info("   → Profit = 0.9155% - 0.6579% = 0.2576%/h = $25.76/h sur $10k")
        logger.info("")
        logger.info("="*80 + "\n")
        
        try:
            cycle = 0
            while True:
                cycle += 1
                logger.info(f"\n{'─'*80}")
                logger.info(f"🔄 CYCLE #{cycle} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                logger.info(f"{'─'*80}\n")
                
                # 1. Récupérer funding rates
                funding_data = self.get_funding_rates()
                
                # 2. Trouver opportunités
                opportunities = self.find_opportunities(funding_data)
                
                if opportunities:
                    self.display_opportunities(opportunities)
                else:
                    logger.info("❌ Aucune opportunité trouvée\n")
                
                # 3. Monitor positions actives
                self.monitor_positions(funding_data)
                
                # 4. Afficher positions actives
                if self.active_positions:
                    logger.info(f"\n📊 Positions actives: {len(self.active_positions)}")
                    for sym, pos in self.active_positions.items():
                        age = datetime.now() - pos['opened_at']
                        logger.info(
                            f"   {sym}: LONG {pos['long_exchange'].upper()} + "
                            f"SHORT {pos['short_exchange'].upper()} "
                            f"(depuis {age})"
                        )
                    logger.info("")
                
                # 5. Attendre avant prochain cycle
                logger.debug(f"Attente {self.check_interval}s...\n")
                time.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            logger.info("\n\n⚠️  Arrêt demandé par l'utilisateur...")
            
            # Fermer toutes les positions
            if self.active_positions:
                logger.warning(f"Fermeture de {len(self.active_positions)} positions...")
                for symbol in list(self.active_positions.keys()):
                    self.close_position(symbol)
            
            logger.info("✅ Bot arrêté proprement\n")


def main():
    """Point d'entrée"""
    print("\n" + "="*80)
    print("🎯 BOT ARBITRAGE EXTENDED vs HYPERLIQUID")
    print("="*80)
    print("Monitor en temps réel + Fermeture automatique")
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
    bot = ExtendedHyperliquidBot(dry_run=dry_run)
    bot.run()


if __name__ == "__main__":
    main()

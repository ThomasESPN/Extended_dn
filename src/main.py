"""
Main Bot Script
Bot principal de timing funding arbitrage avec intégration Loris Tools API
"""
import sys
import time
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger
from tabulate import tabulate

# Ajouter le répertoire parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config
from src.data import FundingCollector
from src.data.loris_api import get_loris_api
from src.data.funding_collector import FundingRate
from src.strategies import ArbitrageCalculator
from src.execution import TradeExecutor, RebalancingManager


class ArbitrageBot:
    """Bot principal de timing funding arbitrage"""
    
    def __init__(self):
        """Initialise le bot"""
        # Configuration
        self.config = get_config()
        
        # Configurer les logs
        log_level = self.config.get('monitoring', 'log_level', default='INFO')
        logger.remove()
        logger.add(
            sys.stderr,
            level=log_level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
        )
        logger.add(
            "logs/bot_{time:YYYY-MM-DD}.log",
            rotation="00:00",
            retention="30 days",
            level=log_level
        )
        
        # Composants
        self.collector = FundingCollector(self.config)
        self.loris = get_loris_api()  # API Loris Tools
        self.calculator = ArbitrageCalculator(self.config)
        self.executor = TradeExecutor(self.config)
        self.rebalancer = RebalancingManager(self.config)
        
        # État
        self.running = False
        self.mode = self.config.get('arbitrage', 'mode', default='manual')  # manual, auto, smart
        
        # Mode manual: utilise les paires configurées
        # Mode auto: scan automatique des meilleures opportunités
        # Mode smart: combine les deux avec allocation dynamique
        
        if self.mode == 'manual':
            self.pairs = self.config.get_pairs()
        else:
            self.pairs = []  # Sera rempli dynamiquement
            self.max_pairs = self.config.get('arbitrage', 'max_concurrent_pairs', default=5)
            self.min_profit_per_hour = self.config.get('arbitrage', 'min_profit_per_hour', default=1.0)
        
        logger.info("Arbitrage Bot initialized")
        logger.info(f"Mode: {self.mode}")
    
    def start(self):
        """Démarre le bot"""
        self.running = True
        
        logger.info("="*80)
        logger.info("🚀 TIMING FUNDING ARBITRAGE BOT - STARTED")
        logger.info("="*80)
        logger.info(f"Mode: {self.mode}")
        
        if self.mode == 'manual':
            logger.info(f"Pairs: {', '.join(self.pairs)}")
        else:
            logger.info(f"Max concurrent pairs: {self.max_pairs}")
            logger.info(f"Min profit/hour: ${self.min_profit_per_hour}")
        
        logger.info(f"Check interval: {self.config.get('arbitrage', 'check_interval')}s")
        logger.info("="*80)
        
        try:
            while self.running:
                if self.mode == 'manual':
                    self.run_manual_cycle()
                elif self.mode == 'auto':
                    self.run_auto_cycle()
                elif self.mode == 'smart':
                    self.run_smart_cycle()
                
                # Attendre avant le prochain cycle
                interval = self.config.get('arbitrage', 'check_interval', default=60)
                time.sleep(interval)
                
        except KeyboardInterrupt:
            logger.info("Stopping bot...")
            self.stop()
    
    def run_manual_cycle(self):
        """Exécute un cycle en mode manuel (paires configurées)"""
        try:
            logger.info("Starting manual cycle")
            
            # 1. Collecter les funding rates
            funding_data = self.collector.get_all_funding_rates(self.pairs)
            
            # 2. Analyser les opportunités
            opportunities = self.calculator.find_best_opportunities(funding_data)
            
            if opportunities:
                logger.info(f"Found {len(opportunities)} opportunities")
                
                # Afficher les opportunités
                self.display_opportunities(opportunities)
            else:
                logger.info("No profitable opportunities found")
            
            # 3. Gérer les positions existantes
            self.manage_existing_positions()
            
            # 4. Rebalancing si nécessaire
            if self.config.get('arbitrage', 'auto_rebalance'):
                self.rebalancer.auto_rebalance_if_needed()
            
        except Exception as e:
            logger.error(f"Error in manual cycle: {e}")
    
    def run_auto_cycle(self):
        """Exécute un cycle en mode automatique (scan toutes les paires Loris)"""
        try:
            logger.info("Starting auto cycle - scanning all symbols")
            
            # 1. Récupérer toutes les données Loris
            data = self.loris.fetch_all_funding_rates()
            if not data:
                logger.error("Failed to fetch Loris data")
                return
            
            symbols = data.get('symbols', [])
            logger.info(f"Scanning {len(symbols)} symbols from Loris Tools")
            
            # 2. Trouver les meilleures opportunités
            opportunities = self.find_all_opportunities(data)
            
            if opportunities:
                logger.success(f"Found {len(opportunities)} opportunities")
                
                # Trier par profit/heure
                opportunities.sort(key=lambda x: x['opportunity'].profit_per_hour, reverse=True)
                
                # Afficher le top
                self.display_top_opportunities(opportunities[:10])
                
                # 3. Gérer les positions existantes
                self.manage_existing_positions()
                
                # 4. Ouvrir de nouvelles positions si on est en dessous du max
                active_count = len(self.executor.get_active_pairs())
                
                if active_count < self.max_pairs:
                    logger.info(f"Active pairs: {active_count}/{self.max_pairs}")
                    
                    # Ouvrir les meilleures opportunités disponibles
                    for opp_data in opportunities[:self.max_pairs - active_count]:
                        opp = opp_data['opportunity']
                        long_exchange = opp_data.get('long_exchange', 'Extended')
                        
                        # Vérifier le seuil de profit minimum
                        if opp.profit_per_hour >= self.min_profit_per_hour:
                            logger.info(
                                f"Opening position for {opp.symbol} "
                                f"(${opp.profit_per_hour:.2f}/h) - "
                                f"LONG {long_exchange} + SHORT Variational"
                            )
                            
                            # TODO: Implémenter l'ouverture automatique sécurisée
                            # self.executor.open_arbitrage_pair(
                            #     symbol=opp.symbol,
                            #     long_exchange=long_exchange.lower(),
                            #     short_exchange='variational',
                            #     size=self.config.get('trading', 'max_position_size')
                            # )
                        else:
                            logger.debug(f"Skipping {opp.symbol} - profit too low")
                            break
                else:
                    logger.info(f"Max pairs reached ({active_count}/{self.max_pairs})")
            else:
                logger.info("No profitable opportunities found")
            
            # 5. Rebalancing si nécessaire
            if self.config.get('arbitrage', 'auto_rebalance'):
                self.rebalancer.auto_rebalance_if_needed()
                
        except Exception as e:
            logger.error(f"Error in auto cycle: {e}")
    
    def run_smart_cycle(self):
        """
        Exécute un cycle en mode smart (combine manuel + auto)
        - Priorité aux paires configurées
        - Complète avec les meilleures opportunités Loris si de la capacité
        """
        try:
            logger.info("Starting smart cycle")
            
            all_opportunities = []
            
            # 1. Analyser les paires configurées (prioritaires)
            if self.config.get_pairs():
                funding_data = self.collector.get_all_funding_rates(self.config.get_pairs())
                manual_opps = self.calculator.find_best_opportunities(funding_data)
                
                for opp in manual_opps:
                    all_opportunities.append({
                        'symbol': opp.symbol.split('/')[0],
                        'opportunity': opp,
                        'priority': 'high'
                    })
            
            # 2. Scanner les autres paires Loris
            data = self.loris.fetch_all_funding_rates()
            if data:
                auto_opps = self.find_all_opportunities(data)
                
                for opp_data in auto_opps:
                    # Éviter les doublons
                    symbol = opp_data['symbol']
                    if not any(o['symbol'] == symbol for o in all_opportunities):
                        opp_data['priority'] = 'normal'
                        all_opportunities.append(opp_data)
            
            # 3. Trier: priorité haute d'abord, puis par profit
            all_opportunities.sort(
                key=lambda x: (
                    0 if x['priority'] == 'high' else 1,
                    -x['opportunity'].profit_per_hour
                )
            )
            
            if all_opportunities:
                logger.success(f"Found {len(all_opportunities)} total opportunities")
                self.display_top_opportunities(all_opportunities[:15])
                
                # 4. Gérer les positions et en ouvrir de nouvelles si besoin
                self.manage_existing_positions()
                
                active_count = len(self.executor.get_active_pairs())
                if active_count < self.max_pairs:
                    logger.info(f"Could open {self.max_pairs - active_count} more positions")
            
            # 5. Rebalancing
            if self.config.get('arbitrage', 'auto_rebalance'):
                self.rebalancer.auto_rebalance_if_needed()
                
        except Exception as e:
            logger.error(f"Error in smart cycle: {e}")
    
    def find_all_opportunities(self, loris_data):
        """
        Analyse toutes les paires disponibles sur Loris et trouve les opportunités
        UTILISE LA MÊME LOGIQUE QUE find_best_opportunity.py:
        - Cherche le MEILLEUR rate 1h entre Extended ET Hyperliquid
        - Compare avec Variational (8h)
        
        Args:
            loris_data: Données de l'API Loris
            
        Returns:
            Liste de dictionnaires {symbol, opportunity, ...}
        """
        opportunities = []
        symbols = loris_data.get('symbols', [])
        
        # 🎯 Récupérer les infos d'exchanges via get_exchange_info()
        exchanges_info = self.loris.get_exchange_info(loris_data)
        
        # 🎯 Identifier les exchanges 1h (Extended, Hyperliquid) et Variational
        exchanges_1h = []
        variational_exchange = None
        
        for exchange_name in exchanges_info.keys():
            base = exchange_name.split('_')[0].lower()
            if base in ['extended', 'hyperliquid']:
                exchanges_1h.append(exchange_name)
            elif base == 'variational':
                variational_exchange = exchange_name
        
        if not exchanges_1h or not variational_exchange:
            logger.error(f"Missing exchanges - 1h: {exchanges_1h}, 8h: {variational_exchange}")
            return []
        
        logger.debug(f"Using exchanges - 1h: {exchanges_1h}, 8h: {variational_exchange}")
        
        for symbol in symbols:  # Scan TOUS les symboles (1429)
            try:
                # Trouver le MEILLEUR rate 1h (Extended OU Hyperliquid, le plus négatif)
                best_1h_rate = None
                best_1h_exchange_full = None
                
                for exchange in exchanges_1h:
                    rate = self.loris.get_funding_rate(loris_data, exchange, symbol)
                    if rate is not None:
                        # On veut le plus négatif (meilleur pour recevoir)
                        if best_1h_rate is None or rate < best_1h_rate:
                            best_1h_rate = rate
                            best_1h_exchange_full = exchange
                
                # Trouver le rate Variational (8h)
                best_8h_rate = self.loris.get_funding_rate(loris_data, variational_exchange, symbol)
                
                # Si on a les deux rates
                if best_1h_rate is not None and best_8h_rate is not None:
                    # Nom court de l'exchange (Extended ou Hyperliquid)
                    best_1h_exchange_name = best_1h_exchange_full.split('_')[0].capitalize()
                    
                    # Debug: Log pour DOOD spécifiquement
                    if symbol == "DOOD":
                        logger.debug(f"DOOD found: 1h={best_1h_rate} ({best_1h_exchange_name}), 8h={best_8h_rate}")
                    
                    # Créer les FundingRate objects
                    funding_data = {
                        f"{symbol}/USDT": {
                            'extended': FundingRate(
                                exchange=best_1h_exchange_name,  # "Extended" ou "Hyperliquid"
                                symbol=f"{symbol}/USDT",
                                rate=best_1h_rate,
                                timestamp=datetime.now(),
                                funding_interval=3600  # 1h
                            ),
                            'variational': FundingRate(
                                exchange="Variational",
                                symbol=f"{symbol}/USDT",
                                rate=best_8h_rate,
                                timestamp=datetime.now(),
                                funding_interval=28800  # 8h
                            )
                        }
                    }
                    
                    # Calculer l'opportunité
                    opps = self.calculator.find_best_opportunities(funding_data)
                    
                    if opps:
                        # Debug DOOD
                        if symbol == "DOOD":
                            logger.debug(f"DOOD opportunity: ${opps[0].profit_per_hour:.2f}/h")
                        
                        opportunities.append({
                            'symbol': symbol,
                            'opportunity': opps[0],
                            'long_exchange': best_1h_exchange_name,
                            'rate_1h': best_1h_rate,
                            'rate_8h': best_8h_rate
                        })
                    elif symbol == "DOOD":
                        logger.debug(f"DOOD rejected by calculator")
                        
            except Exception as e:
                # Continuer si erreur sur un symbole spécifique
                if symbol == "DOOD":
                    logger.error(f"Error processing DOOD: {e}")
                continue
        
        logger.debug(f"Total opportunities found: {len(opportunities)}")
        return opportunities
    
    def display_opportunities(self, opportunities):
        """Affiche les opportunités de manière formatée"""
        if not opportunities:
            return
        
        table_data = []
        for i, opp in enumerate(opportunities[:5], 1):
            table_data.append([
                i,
                opp.symbol,
                f"{opp.extended_rate:.6f}",
                f"{opp.variational_rate:.6f}",
                f"${opp.profit_per_hour:.2f}",
                opp.position_type
            ])
        
        headers = ["#", "Paire", "Rate 1h", "Rate 8h", "$/heure", "Type"]
        
        logger.info("\n" + tabulate(table_data, headers=headers, tablefmt="simple"))
    
    def display_top_opportunities(self, opportunities_data):
        """Affiche le top des opportunités avec l'exchange utilisé"""
        if not opportunities_data:
            return
        
        table_data = []
        for i, item in enumerate(opportunities_data[:10], 1):
            opp = item['opportunity']
            priority = item.get('priority', 'normal')
            
            # Afficher quel exchange 1h est utilisé (Extended ou Hyperliquid)
            exchange_1h = item.get('long_exchange', 'Extended')
            
            table_data.append([
                i,
                item['symbol'],
                f"{item.get('rate_1h', opp.extended_rate):.5f}",
                f"{item.get('rate_8h', opp.variational_rate):.5f}",
                f"${opp.profit_per_hour:.2f}",
                opp.position_type,
                exchange_1h[:3].upper(),  # "EXT" ou "HYP"
                "⭐" if priority == 'high' else ""
            ])
        
        headers = ["#", "Symbole", "Rate 1h", "Rate 8h", "$/h", "Type", "DEX", "Prio"]
        
        logger.info("\n" + tabulate(table_data, headers=headers, tablefmt="simple"))
        
        # Afficher la meilleure avec l'exchange
        best = opportunities_data[0]
        best_exchange = best.get('long_exchange', 'Extended')
        logger.success(
            f"🏆 Best: {best['symbol']} ({best_exchange}) - "
            f"${best['opportunity'].profit_per_hour:.2f}/h "
            f"(${best['opportunity'].estimated_profit_full_cycle:.2f} per 8h cycle)"
        )
    
    def manage_existing_positions(self):
        """Gère les positions existantes"""
        active_pairs = self.executor.get_active_pairs()
        
        if not active_pairs:
            return
        
        logger.debug(f"Managing {len(active_pairs)} active pairs")
        
        for pair_id, pair in list(active_pairs.items()):
            # Vérifier si on doit fermer
            if pair.target_close_time and datetime.now() >= pair.target_close_time:
                logger.info(f"Target close time reached for {pair_id}")
                self.executor.close_arbitrage_pair(pair_id)
            
            # Vérifier le changement de polarité des funding
            if self.config.get('arbitrage', 'watch_polarity_change'):
                self.check_funding_polarity(pair)
    
    def check_funding_polarity(self, pair):
        """
        Vérifie si les funding rates ont changé de polarité
        
        Args:
            pair: ArbitragePair à surveiller
        """
        # Récupérer les funding actuels
        ext_funding = self.collector.get_extended_funding(pair.symbol)
        var_funding = self.collector.get_variational_funding(pair.symbol)
        
        if not ext_funding or not var_funding:
            return
        
        # Comparer avec les rates d'ouverture
        ext_changed = (ext_funding.rate * pair.long_position.entry_funding) < 0
        var_changed = (var_funding.rate * pair.short_position.entry_funding) < 0
        
        if ext_changed or var_changed:
            logger.warning(f"⚠️  Funding polarity changed for {pair.symbol}!")
            logger.warning(f"   Consider closing position early")
    
    def stop(self):
        """Arrête le bot"""
        self.running = False
        
        # Fermer toutes les positions actives
        active_pairs = self.executor.get_active_pairs()
        if active_pairs:
            logger.warning(f"Closing {len(active_pairs)} active pairs...")
            for pair_id in list(active_pairs.keys()):
                self.executor.close_arbitrage_pair(pair_id)
        
        logger.info("Bot stopped")


def main():
    """Point d'entrée principal"""
    
    print("\n" + "="*80)
    print("🚀 TIMING FUNDING ARBITRAGE BOT")
    print("="*80)
    print("Intégration Loris Tools API - Données en temps réel")
    print("https://loris.tools")
    print("="*80 + "\n")
    
    # Demander le mode si non configuré
    config = get_config()
    mode = config.get('arbitrage', 'mode', default=None)
    
    if not mode or mode not in ['manual', 'auto', 'smart']:
        print("Sélectionnez le mode de trading:")
        print("  1. MANUAL  - Surveille uniquement les paires configurées (BTC/USDT, ETH/USDT...)")
        print("  2. AUTO    - Scan automatique de toutes les paires Loris (1430+ symboles)")
        print("  3. SMART   - Combine manuel + auto (paires configurées + scan Loris)")
        print()
        
        choice = input("Votre choix (1/2/3): ").strip()
        
        mode_map = {'1': 'manual', '2': 'auto', '3': 'smart'}
        mode = mode_map.get(choice, 'manual')
        
        print(f"\n✅ Mode sélectionné: {mode.upper()}\n")
        
        # Mettre à jour la config temporairement
        config.config['arbitrage']['mode'] = mode
    
    # Démarrer le bot
    bot = ArbitrageBot()
    bot.start()


if __name__ == "__main__":
    main()

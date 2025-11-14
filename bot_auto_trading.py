"""
Bot Auto Trading - Exécution Réelle Delta-Neutral
Stratégie: LONG Extended + SHORT Hyperliquid
Timing: 5 min avant -> Funding -> 5 min après
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


class AutoTradingBot:
    """
    Bot de Trading Automatique Delta-Neutral
    
    Stratégie:
    1. Scan toutes les 5 min pour trouver le TOP 1
    2. 5 min AVANT funding Extended (X:55) → Ouvrir positions
       - LONG Extended (ordre LIMIT)
       - SHORT Hyperliquid (ordre LIMIT)
       - MÊME SIZE exacte pour delta-neutral parfait
    3. X:00 → Recevoir funding Extended
    4. 5 min APRÈS funding (X:05) → Fermer tout
    
    Évite les cycles 8h de Hyperliquid (00:00, 08:00, 16:00 UTC)
    """
    
    def __init__(self, config_path="config/config.json", dry_run=True):
        """Initialise le bot"""
        # Charger la config
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Paramètres de trading
        self.dry_run = dry_run
        self.wallet_address = self.config['wallet']['address']
        self.private_key = self.config['wallet']['private_key']
        
        # Paramètres auto-trading
        auto_config = self.config.get('auto_trading', {})
        self.enabled = auto_config.get('enabled', False)
        self.position_size_usd = auto_config.get('position_size_usd', 100)
        self.max_positions = auto_config.get('max_concurrent_positions', 1)
        self.min_profit_per_snipe = auto_config.get('min_profit_per_snipe', 5.0)
        
        # Timing
        self.open_before_minutes = 5   # Ouvrir 5 min avant funding (X:55)
        self.close_after_minutes = 5   # Fermer 5 min après funding (X:05)
        
        # Cycles Hyperliquid à éviter (UTC)
        self.hl_funding_hours = [0, 8, 16]
        
        # Position tracking
        self.active_positions = {}
        self.last_scan_time = None
        
        # Extended credentials
        extended_config = self.config.get('extended', {})
        
        # APIs
        logger.info("🔌 Initialisation des APIs...")
        self.extended = ExtendedAPI(
            wallet_address=self.wallet_address,
            private_key=self.private_key,
            api_key=extended_config.get('api_key'),
            stark_public_key=extended_config.get('stark_public_key'),
            stark_private_key=extended_config.get('stark_private_key'),
            vault_id=extended_config.get('vault_id'),
            client_id=extended_config.get('client_id')
        )
        self.hyperliquid = HyperliquidAPI(
            wallet_address=self.wallet_address,
            private_key=self.private_key
        )
        
        # Logger
        logger.remove()
        logger.add(
            sys.stderr,
            level="INFO",
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
        )
        logger.add(
            "logs/bot_auto_{time:YYYY-MM-DD}.log",
            rotation="00:00",
            retention="7 days",
            level="DEBUG"
        )
        
        logger.info("✅ Bot Auto-Trading initialisé")
        if self.dry_run:
            logger.warning("⚠️  MODE DRY-RUN (simulation)")
        else:
            logger.success("🚀 MODE LIVE (TRADING RÉEL)")
        
        if not self.enabled:
            logger.warning("⚠️  Auto-trading désactivé dans config")
    
    def is_hl_funding_hour(self, hour):
        """Vérifie si c'est une heure de funding HL (8h)"""
        return hour in self.hl_funding_hours
    
    def get_next_funding_time(self):
        """
        Retourne la prochaine heure de funding Extended
        
        Returns:
            datetime: Prochaine heure UTC (toujours à l'heure pile)
        """
        now_utc = datetime.now(timezone.utc)
        next_hour = (now_utc + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
        
        # Si c'est une heure HL, passer à la suivante
        while self.is_hl_funding_hour(next_hour.hour):
            next_hour += timedelta(hours=1)
        
        return next_hour
    
    def should_open_position(self):
        """
        Vérifie si c'est le moment d'ouvrir (X:55)
        
        Returns:
            (bool, datetime): (doit_ouvrir, heure_funding)
        """
        now_utc = datetime.now(timezone.utc)
        next_funding = self.get_next_funding_time()
        
        # Temps avant le funding
        time_to_funding = (next_funding - now_utc).total_seconds() / 60
        
        # Ouvrir si on est entre 5 et 6 min avant (fenêtre de 1 min)
        should_open = 5 <= time_to_funding <= 6
        
        return should_open, next_funding
    
    def should_close_position(self):
        """
        Vérifie si c'est le moment de fermer (X:05)
        
        Returns:
            bool: True si on doit fermer
        """
        now_utc = datetime.now(timezone.utc)
        current_minute = now_utc.minute
        
        # Fermer 5 min après chaque heure (X:05)
        return current_minute == 5
    
    def scan_opportunities(self):
        """
        Scanne toutes les paires et trouve la meilleure opportunité
        
        Returns:
            dict: Meilleure opportunité ou None
        """
        logger.info("📊 SCAN DES OPPORTUNITÉS...")
        
        opportunities = []
        
        try:
            # 1. Récupérer les funding rates Extended
            ext_rates = self.extended.get_all_funding_rates()
            logger.info(f"   Extended: {len(ext_rates)} symboles")
            
            # 2. Récupérer les funding rates Hyperliquid
            hyp_rates = self.hyperliquid.get_all_funding_rates()
            logger.info(f"   Hyperliquid: {len(hyp_rates)} symboles")
            
            # 3. Trouver les symboles communs
            common_symbols = set(ext_rates.keys()) & set(hyp_rates.keys())
            logger.info(f"   Symboles communs: {len(common_symbols)}")
            
            # 4. Calculer les opportunités
            for symbol in common_symbols:
                ext_rate = ext_rates[symbol]['rate']
                hyp_rate = hyp_rates[symbol]['rate']
                
                # 🎯 NOUVEAU: Vérifier la compatibilité des leviers
                ext_max_lev = self.extended.get_max_leverage(symbol)
                hyp_max_lev = self.hyperliquid.get_max_leverage(symbol)
                
                # Prendre le MINIMUM des deux, avec un max de 10x
                compatible_leverage = min(ext_max_lev, hyp_max_lev, 10)
                
                logger.info(f"   {symbol}: Extended max {ext_max_lev}x, Hyperliquid max {hyp_max_lev}x → Using {compatible_leverage}x")
                
                # Calculer le profit par snipe (3 min de risque)
                # On reçoit le funding Extended sur 1h
                # Profit = (ext_rate payé par heure) - frais
                
                # Si Extended est négatif, on est payé pour le LONG
                # Si Hyperliquid est aussi négatif, on est payé pour le SHORT
                profit_per_hour = abs(ext_rate) + abs(hyp_rate) if ext_rate < 0 and hyp_rate < 0 else abs(ext_rate - hyp_rate)
                
                # Conversion en $ sur position de $100
                profit_per_snipe = (profit_per_hour / 100) * self.position_size_usd
                
                opportunities.append({
                    'symbol': symbol,
                    'ext_rate': ext_rate,
                    'hyp_rate': hyp_rate,
                    'profit_per_snipe': profit_per_snipe,
                    'long_exchange': 'EXTENDED' if ext_rate < hyp_rate else 'HYPERLIQUID',
                    'short_exchange': 'HYPERLIQUID' if ext_rate < hyp_rate else 'EXTENDED',
                    'leverage': compatible_leverage  # 🎯 AJOUTÉ
                })
            
            # 5. Trier par profit
            opportunities.sort(key=lambda x: x['profit_per_snipe'], reverse=True)
            
            # 6. Afficher le top 10
            if opportunities:
                logger.info(f"\n✅ {len(opportunities)} opportunités trouvées\n")
                
                table_data = []
                for i, opp in enumerate(opportunities[:10], 1):
                    table_data.append([
                        i,
                        opp['symbol'],
                        f"{opp['leverage']}x",  # 🎯 AJOUTÉ
                        opp['long_exchange'],
                        f"{opp['ext_rate']:.4f}%" if opp['long_exchange'] == 'EXTENDED' else f"{opp['hyp_rate']:.4f}%",
                        opp['short_exchange'],
                        f"{opp['hyp_rate']:.4f}%" if opp['short_exchange'] == 'HYPERLIQUID' else f"{opp['ext_rate']:.4f}%",
                        f"${opp['profit_per_snipe']:.2f}"
                    ])
                
                headers = ["#", "Symbole", "Leverage", "LONG", "Rate LONG", "SHORT", "Rate SHORT", "$/snipe"]  # 🎯 MODIFIÉ
                logger.info(tabulate(table_data, headers=headers, tablefmt="grid"))
                logger.info("")
                
                # Retourner le TOP 1
                best = opportunities[0]
                logger.success(f"🏆 TOP 1: {best['symbol']} - ${best['profit_per_snipe']:.2f}/snipe")
                return best
            else:
                logger.warning("❌ Aucune opportunité trouvée")
                return None
                
        except Exception as e:
            logger.error(f"Erreur lors du scan: {e}")
            return None
    
    def get_market_price(self, exchange, symbol):
        """
        Récupère le prix market actuel
        
        Args:
            exchange: 'extended' ou 'hyperliquid'
            symbol: Symbole (ex: 'IP')
            
        Returns:
            float: Prix actuel
        """
        try:
            if exchange == 'extended':
                return self.extended.get_market_price(symbol)
            else:
                return self.hyperliquid.get_market_price(symbol)
        except Exception as e:
            logger.error(f"Erreur récupération prix {symbol} sur {exchange}: {e}")
            return None
    
    def open_delta_neutral_position(self, opportunity):
        """
        Ouvre une position DELTA-NEUTRAL avec ordres LIMIT
        
        CRITIQUE: Les deux ordres doivent avoir EXACTEMENT la même size
        
        Args:
            opportunity: Dict avec symbol, long_exchange, short_exchange, leverage, etc.
        """
        symbol = opportunity['symbol']
        long_ex = opportunity['long_exchange'].lower()
        short_ex = opportunity['short_exchange'].lower()
        leverage = opportunity['leverage']  # 🎯 AJOUTÉ
        
        logger.info(f"\n{'='*80}")
        logger.info(f"🎯 OUVERTURE POSITION DELTA-NEUTRAL: {symbol}")
        logger.info(f"{'='*80}")
        logger.info(f"   📈 LONG  {long_ex.upper()}")
        logger.info(f"   📉 SHORT {short_ex.upper()}")
        logger.info(f"   ⚡ Leverage: {leverage}x (minimum des deux exchanges)")  # 🎯 AJOUTÉ
        logger.info(f"   💰 Size: ${self.position_size_usd} (identique des deux côtés)")
        logger.info(f"   📊 Profit estimé: ${opportunity['profit_per_snipe']:.2f}")
        logger.info(f"   ⏰ Fermeture dans ~10 min (5 min après funding)")
        
        if self.dry_run:
            logger.warning("   ⚠️  DRY-RUN: Position simulée")
            success_long = True
            success_short = True
        else:
            try:
                # 1. Récupérer les prix actuels
                logger.info("   📡 Récupération des prix market...")
                long_price = self.get_market_price(long_ex, symbol)
                short_price = self.get_market_price(short_ex, symbol)
                
                if not long_price or not short_price:
                    logger.error("   ❌ Impossible de récupérer les prix")
                    return False
                
                logger.info(f"   Prix {long_ex.upper()}: ${long_price:.4f}")
                logger.info(f"   Prix {short_ex.upper()}: ${short_price:.4f}")
                
                # 2. Calculer la MÊME SIZE pour delta-neutral
                # IMPORTANT: Utiliser la même size sur les deux exchanges !
                avg_price = (long_price + short_price) / 2
                target_size = self.position_size_usd / avg_price
                
                # Respecter les minimums Extended (plus restrictif)
                min_sizes = {"BTC": 0.001, "ETH": 0.01, "SOL": 0.1}
                min_size_extended = min_sizes.get(symbol, 0.01)
                
                if target_size < min_size_extended:
                    logger.warning(f"   ⚠️ Size {target_size:.4f} < min {min_size_extended}, using minimum")
                    target_size = min_size_extended
                else:
                    target_size = round(target_size, 4)
                
                # MÊME SIZE sur les deux exchanges (vrai delta-neutral)
                long_size = target_size
                short_size = target_size
                
                logger.info(f"   Size identique: {target_size} {symbol}")
                logger.info(f"   LONG value: ${long_size * long_price:.2f}")
                logger.info(f"   SHORT value: ${short_size * short_price:.2f}")
                logger.info(f"   Delta: ${abs(long_size * long_price - short_size * short_price):.2f}")
                
                # 3. Placer les ordres LIMIT simultanément
                logger.info("   📝 Placement des ordres LIMIT...")
                
                # LONG
                if long_ex == 'extended':
                    result_long = self.extended.place_order(
                        symbol=symbol,
                        side="buy",
                        size=long_size,
                        price=long_price * 1.0005,  # +0.05% pour fill rapide
                        order_type="limit"
                    )
                else:
                    result_long = self.hyperliquid.place_order(
                        symbol=symbol,
                        side="buy",
                        size=long_size,
                        price=long_price * 1.0005,
                        order_type="limit"
                    )
                
                # SHORT
                if short_ex == 'extended':
                    result_short = self.extended.place_order(
                        symbol=symbol,
                        side="sell",
                        size=short_size,
                        price=short_price * 0.9995,  # -0.05% pour fill rapide
                        order_type="limit"
                    )
                else:
                    result_short = self.hyperliquid.place_order(
                        symbol=symbol,
                        side="sell",
                        size=short_size,
                        price=short_price * 0.9995,
                        order_type="limit"
                    )
                
                success_long = result_long and result_long.get('order_id') is not None
                success_short = result_short and result_short.get('status') in ['ok', 'OK']
                
                if success_long and success_short:
                    logger.success("   ✅ Positions ouvertes (DELTA-NEUTRAL)")
                else:
                    logger.error(f"   ❌ Échec: LONG={success_long}, SHORT={success_short}")
                    return False
                    
            except Exception as e:
                logger.error(f"   ❌ Erreur: {e}")
                return False
        
        # Sauvegarder la position
        self.active_positions[symbol] = {
            'long_exchange': long_ex,
            'short_exchange': short_ex,
            'size_usd': self.position_size_usd,
            'expected_profit': opportunity['profit_per_snipe'],
            'opened_at': datetime.now(timezone.utc),
            'funding_time': self.get_next_funding_time()
        }
        
        logger.info(f"{'='*80}\n")
        return True
    
    def close_delta_neutral_position(self, symbol):
        """
        Ferme une position delta-neutral
        
        Args:
            symbol: Symbole de la position à fermer
        """
        if symbol not in self.active_positions:
            logger.warning(f"Position {symbol} non trouvée")
            return False
        
        pos = self.active_positions[symbol]
        duration = datetime.now(timezone.utc) - pos['opened_at']
        
        logger.info(f"\n{'='*80}")
        logger.info(f"💰 FERMETURE POSITION: {symbol}")
        logger.info(f"{'='*80}")
        logger.info(f"   Durée totale: {duration}")
        logger.info(f"   Profit estimé: ${pos['expected_profit']:.2f}")
        logger.info(f"   Risque: {duration.total_seconds():.0f} secondes seulement !")
        
        if self.dry_run:
            logger.warning("   ⚠️  DRY-RUN: Fermeture simulée")
            success = True
        else:
            try:
                # Fermer les deux positions
                long_ex = pos['long_exchange']
                short_ex = pos['short_exchange']
                
                logger.info(f"   Fermeture LONG {long_ex.upper()}...")
                if long_ex == 'extended':
                    self.extended.close_position(symbol)
                else:
                    self.hyperliquid.close_position(symbol)
                
                logger.info(f"   Fermeture SHORT {short_ex.upper()}...")
                if short_ex == 'extended':
                    self.extended.close_position(symbol)
                else:
                    self.hyperliquid.close_position(symbol)
                
                logger.success("   ✅ Positions fermées")
                success = True
                
            except Exception as e:
                logger.error(f"   ❌ Erreur: {e}")
                success = False
        
        if success:
            del self.active_positions[symbol]
        
        logger.info(f"{'='*80}\n")
        return success
    
    def run(self):
        """Boucle principale du bot"""
        logger.info("\n" + "="*80)
        logger.info("🤖 BOT AUTO-TRADING DELTA-NEUTRAL")
        logger.info("="*80)
        logger.info(f"Wallet: {self.wallet_address}")
        logger.info(f"Position size: ${self.position_size_usd}")
        logger.info(f"Min profit/snipe: ${self.min_profit_per_snipe}")
        logger.info(f"Max positions: {self.max_positions}")
        logger.info(f"Mode: {'DRY-RUN' if self.dry_run else '🔴 LIVE'}")
        logger.info(f"Auto-trading: {'✅ ENABLED' if self.enabled else '❌ DISABLED'}")
        logger.info("="*80)
        logger.info("")
        logger.info("📋 STRATÉGIE:")
        logger.info("   1. Scan toutes les 5 min → Trouve TOP 1")
        logger.info("   2. X:55 → Ouvre LONG Extended + SHORT Hyperliquid")
        logger.info("   3. X:00 → Reçoit funding Extended")
        logger.info("   4. X:05 → Ferme tout")
        logger.info("   5. Évite cycles HL 8h (00:00, 08:00, 16:00)")
        logger.info("")
        logger.info("⚠️  SÉCURITÉ:")
        logger.info("   • Delta-neutral = Pas de risque de prix")
        logger.info("   • Ordres LIMIT = Size identique garantie")
        logger.info("   • Risque: 10 min par cycle seulement")
        logger.info("")
        logger.info("="*80 + "\n")
        
        if not self.enabled:
            logger.error("❌ Auto-trading désactivé dans config.json")
            logger.info("   Pour activer: config.json → auto_trading.enabled = true")
            return
        
        try:
            cycle_count = 0
            
            while True:
                cycle_count += 1
                now_utc = datetime.now(timezone.utc)
                
                logger.info("─" * 80)
                logger.info(f"🔄 CYCLE #{cycle_count} - {now_utc.strftime('%Y-%m-%d %H:%M:%S')} UTC")
                logger.info("─" * 80)
                
                # Afficher le prochain funding
                next_funding = self.get_next_funding_time()
                time_to_funding = (next_funding - now_utc).total_seconds() / 60
                logger.info(f"⏰ Prochain funding: {next_funding.strftime('%H:%M')} UTC (dans {time_to_funding:.0f} min)")
                logger.info(f"💼 Positions actives: {len(self.active_positions)}/{self.max_positions}")
                logger.info("")
                
                # 1. Fermer les positions existantes si c'est le moment
                if self.should_close_position() and self.active_positions:
                    logger.info("💰 Fermeture des positions...")
                    for symbol in list(self.active_positions.keys()):
                        self.close_delta_neutral_position(symbol)
                
                # 2. Ouvrir une nouvelle position si nécessaire
                should_open, funding_time = self.should_open_position()
                
                if should_open and len(self.active_positions) < self.max_positions:
                    logger.info("🎯 Fenêtre d'ouverture détectée !")
                    
                    # Scanner les opportunités
                    best_opp = self.scan_opportunities()
                    
                    if best_opp:
                        # Vérifier le profit minimum
                        if best_opp['profit_per_snipe'] >= self.min_profit_per_snipe:
                            logger.success(f"✅ Opportunité valide: {best_opp['symbol']} (${best_opp['profit_per_snipe']:.2f})")
                            self.open_delta_neutral_position(best_opp)
                        else:
                            logger.warning(f"⚠️  Profit trop faible: ${best_opp['profit_per_snipe']:.2f} < ${self.min_profit_per_snipe}")
                    else:
                        logger.warning("❌ Aucune opportunité trouvée")
                
                # 3. Attendre 60 secondes avant le prochain cycle
                logger.info("⏳ Attente 60s...\n")
                time.sleep(60)
                
        except KeyboardInterrupt:
            logger.info("\n⚠️  Arrêt demandé...")
            
            # Fermer toutes les positions avant de quitter
            if self.active_positions:
                logger.warning(f"⚠️  {len(self.active_positions)} positions actives")
                logger.info("💰 Fermeture de toutes les positions...")
                
                for symbol in list(self.active_positions.keys()):
                    self.close_delta_neutral_position(symbol)
            
            logger.info("✅ Bot arrêté\n")


def main():
    """Point d'entrée"""
    print("\n" + "="*80)
    print("🤖 BOT AUTO-TRADING DELTA-NEUTRAL")
    print("="*80)
    print("Stratégie: LONG Extended + SHORT Hyperliquid")
    print("Timing: 5 min avant → Funding → 5 min après")
    print("="*80 + "\n")
    
    # Demander le mode
    print("Mode de trading:")
    print("  1. DRY-RUN (simulation, RECOMMANDÉ pour débuter)")
    print("  2. LIVE (TRADING RÉEL avec argent réel)")
    print()
    
    choice = input("Votre choix (1/2) [1]: ").strip() or "1"
    dry_run = choice == "1"
    
    if not dry_run:
        print("\n⚠️  ⚠️  ⚠️  ATTENTION ⚠️  ⚠️  ⚠️")
        print("Vous allez activer le trading RÉEL !")
        print("Vérifiez que:")
        print("  - Votre wallet est configuré correctement")
        print("  - Vous avez suffisamment de fonds")
        print("  - La taille des positions est adaptée")
        print()
        confirm = input("Taper 'CONFIRM' pour continuer: ")
        if confirm != "CONFIRM":
            print("❌ Annulé")
            return
    
    print()
    
    # Lancer le bot
    bot = AutoTradingBot(dry_run=dry_run)
    bot.run()


if __name__ == "__main__":
    main()

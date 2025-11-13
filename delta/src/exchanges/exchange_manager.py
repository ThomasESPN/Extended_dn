"""
Exchange Manager
Centralise l'initialisation des APIs avec le wallet global
"""
from typing import Dict, Optional
from loguru import logger
from .hyperliquid_api import HyperliquidAPI
from .variational_api import VariationalAPI
import json
import os


class ExchangeManager:
    """Gestionnaire centralisé pour tous les exchanges"""
    
    def __init__(self, config_path: str = None):
        """
        Initialise le manager avec le wallet global
        
        Args:
            config_path: Chemin vers config.json
        """
        if config_path is None:
            # Chemin par défaut
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                'config',
                'config.json'
            )
        
        # Charger la config
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        # Récupérer le wallet global (même wallet pour tous les DEX)
        self.wallet_address = self.config['wallet']['address']
        self.private_key = self.config['wallet']['private_key']
        
        # Initialiser les APIs
        self.hyperliquid = None
        self.variational = None
        self.extended = None
        
        self._init_exchanges()
    
    def _init_exchanges(self):
        """Initialise tous les exchanges activés"""
        
        # Hyperliquid
        if self.config['exchanges']['hyperliquid'].get('enabled', True):
            try:
                self.hyperliquid = HyperliquidAPI(
                    wallet_address=self.wallet_address,
                    private_key=self.private_key,
                    testnet=False  # Change to True pour tester
                )
                logger.success("✅ Hyperliquid API initialisée")
            except Exception as e:
                logger.error(f"❌ Erreur Hyperliquid: {e}")
        
        # Variational
        if self.config['exchanges']['variational'].get('enabled', True):
            try:
                self.variational = VariationalAPI(
                    wallet_address=self.wallet_address,
                    private_key=self.private_key
                )
                logger.success("✅ Variational API initialisée")
            except Exception as e:
                logger.error(f"❌ Erreur Variational: {e}")
        
        # Extended (TODO: créer extended_api.py)
        # if self.config['exchanges']['extended'].get('enabled', True):
        #     try:
        #         self.extended = ExtendedAPI(
        #             wallet_address=self.wallet_address,
        #             private_key=self.private_key
        #         )
        #         logger.success("✅ Extended API initialisée")
        #     except Exception as e:
        #         logger.error(f"❌ Erreur Extended: {e}")
    
    def get_total_balance(self) -> float:
        """
        Récupère le total des balances sur tous les exchanges
        
        Returns:
            Balance totale en USD
        """
        total = 0.0
        
        if self.hyperliquid:
            try:
                balance = self.hyperliquid.get_balance()
                total += balance
                logger.info(f"Hyperliquid: ${balance:,.2f}")
            except Exception as e:
                logger.error(f"Erreur balance Hyperliquid: {e}")
        
        if self.variational:
            try:
                balance = self.variational.get_balance()
                total += balance
                logger.info(f"Variational: ${balance:,.2f}")
            except Exception as e:
                logger.error(f"Erreur balance Variational: {e}")
        
        return total
    
    def get_all_positions(self) -> Dict:
        """
        Récupère toutes les positions sur tous les exchanges
        
        Returns:
            Dict avec positions par exchange
        """
        positions = {
            'hyperliquid': [],
            'variational': [],
            'extended': []
        }
        
        if self.hyperliquid:
            try:
                positions['hyperliquid'] = self.hyperliquid.get_open_positions()
            except Exception as e:
                logger.error(f"Erreur positions Hyperliquid: {e}")
        
        if self.variational:
            try:
                positions['variational'] = self.variational.get_open_positions()
            except Exception as e:
                logger.error(f"Erreur positions Variational: {e}")
        
        return positions
    
    def open_delta_neutral_position(
        self,
        symbol: str,
        size: float,
        long_exchange: str,
        short_exchange: str
    ) -> Dict:
        """
        Ouvre une position delta-neutral
        
        Args:
            symbol: Paire (ex: "ARK/USDT")
            size: Taille en USD
            long_exchange: 'hyperliquid', 'variational' ou 'extended'
            short_exchange: 'hyperliquid', 'variational' ou 'extended'
        
        Returns:
            Dict avec résultats des 2 ordres
        """
        results = {
            'long': None,
            'short': None,
            'success': False
        }
        
        try:
            # LONG sur exchange A
            long_api = self._get_exchange_api(long_exchange)
            if long_api:
                logger.info(f"📈 LONG {symbol} sur {long_exchange} (${size:,.2f})")
                results['long'] = long_api.place_order(
                    symbol=symbol,
                    side='buy',
                    size=size,
                    order_type='market'
                )
            
            # SHORT sur exchange B
            short_api = self._get_exchange_api(short_exchange)
            if short_api:
                logger.info(f"📉 SHORT {symbol} sur {short_exchange} (${size:,.2f})")
                results['short'] = short_api.place_order(
                    symbol=symbol,
                    side='sell',
                    size=size,
                    order_type='market'
                )
            
            # Vérifier que les 2 ordres ont réussi
            if results['long'] and results['short']:
                results['success'] = True
                logger.success(f"✅ Position delta-neutral ouverte: {symbol}")
            else:
                logger.error("❌ Échec ouverture position delta-neutral")
        
        except Exception as e:
            logger.error(f"❌ Erreur ouverture position: {e}")
        
        return results
    
    def _get_exchange_api(self, exchange_name: str):
        """Récupère l'API pour un exchange donné"""
        if exchange_name.lower() == 'hyperliquid':
            return self.hyperliquid
        elif exchange_name.lower() == 'variational':
            return self.variational
        elif exchange_name.lower() == 'extended':
            return self.extended
        return None


if __name__ == "__main__":
    """Test du manager"""
    manager = ExchangeManager()
    
    print("\n" + "="*50)
    print("💼 BALANCES")
    print("="*50)
    total = manager.get_total_balance()
    print(f"\n💰 Total: ${total:,.2f}")
    
    print("\n" + "="*50)
    print("📊 POSITIONS OUVERTES")
    print("="*50)
    positions = manager.get_all_positions()
    for exchange, pos in positions.items():
        if pos:
            print(f"\n{exchange.upper()}:")
            for p in pos:
                print(f"  - {p}")

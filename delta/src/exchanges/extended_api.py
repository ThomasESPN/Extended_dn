"""
Extended Exchange API Integration
Documentation: https://api-docs.extended.exchange/
"""
from typing import Optional, Dict, List
import requests
import json
from datetime import datetime

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

try:
    from eth_account import Account
    from eth_account.signers.local import LocalAccount
    HAS_ETH_ACCOUNT = True
except ImportError:
    HAS_ETH_ACCOUNT = False
    logger.warning("eth-account not installed, signing features disabled")


class ExtendedAPI:
    """Client API pour Extended Exchange avec wallet signing"""
    
    # API publique Extended (Starknet mainnet)
    API_URL = "https://api.starknet.extended.exchange"
    
    def __init__(self, wallet_address: str, private_key: str = None):
        """
        Initialise le client Extended
        
        Args:
            wallet_address: Adresse publique du wallet (0x...)
            private_key: Clé privée du wallet (optionnel pour endpoints publics)
        """
        self.wallet_address = wallet_address
        self.account = None
        
        if private_key and HAS_ETH_ACCOUNT:
            self.account = Account.from_key(private_key)
        
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        
        logger.info(f"Extended API initialized for {wallet_address}")
    
    def get_funding_rate(self, symbol: str) -> Optional[Dict]:
        """
        Récupère le funding rate actuel pour un symbole
        
        Args:
            symbol: Symbole (ex: "RESOLV", "BTC")
            
        Returns:
            Dict avec {
                'symbol': str,
                'rate': float (décimal, ex: -0.009953 = -0.9953%),
                'next_funding': timestamp,
                'interval_hours': int
            }
        """
        try:
            # Endpoint public pour les funding rates
            # Format: /perp/{symbol}/funding ou /markets/{symbol}/funding
            url = f"{self.API_URL}/perp/{symbol}-USD/funding"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Parser la réponse Extended
            # TODO: Ajuster selon le format réel de leur API
            return {
                'symbol': symbol,
                'rate': float(data.get('fundingRate', 0)),
                'next_funding': data.get('nextFundingTime'),
                'interval_hours': 1  # Extended utilise 1h
            }
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching funding rate for {symbol}: {e}")
            return None
    
    def get_all_funding_rates(self) -> Dict[str, Dict]:
        """
        Récupère tous les funding rates disponibles sur Extended
        
        Returns:
            Dict {symbol: funding_info}
        """
        try:
            # Endpoint pour tous les markets
            url = f"{self.API_URL}/api/v1/info/markets"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            response_data = response.json()
            
            if response_data.get('status') != 'OK':
                logger.error(f"Extended API error: {response_data}")
                return {}
            
            markets = response_data.get('data', [])
            
            funding_rates = {}
            
            # Pour chaque market, extraire le funding rate
            for market in markets:
                # Le market est au format "BTC-USD", extraire le symbole
                name = market.get('name', '')
                symbol = name.replace('-USD', '').replace('-USDT', '')
                
                if not symbol:
                    continue
                
                market_stats = market.get('marketStats', {})
                funding_rate_str = market_stats.get('fundingRate')
                
                if funding_rate_str is not None:
                    funding_rates[symbol] = {
                        'symbol': symbol,
                        'rate': float(funding_rate_str),
                        'next_funding': market_stats.get('nextFundingRate'),
                        'interval_hours': 1  # Extended utilise 1h
                    }
            
            logger.info(f"Fetched {len(funding_rates)} funding rates from Extended")
            return funding_rates
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching all funding rates: {e}")
            return {}
    
    def get_balance(self) -> float:
        """
        Récupère le balance USDC disponible
        
        Returns:
            Balance en USDC
        """
        try:
            # TODO: Endpoint authentifié pour le balance
            # Nécessite signature avec self.account
            url = f"{self.API_URL}/account/balance"
            
            # TODO: Ajouter signature headers
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            return float(data.get('availableBalance', 0))
            
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return 0.0
    
    def get_open_positions(self) -> List[Dict]:
        """
        Récupère les positions ouvertes
        
        Returns:
            Liste des positions
        """
        try:
            # TODO: Endpoint authentifié pour les positions
            url = f"{self.API_URL}/account/positions"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []
    
    def place_order(
        self,
        symbol: str,
        is_buy: bool,
        size: float,
        price: Optional[float] = None,
        reduce_only: bool = False
    ) -> Optional[Dict]:
        """
        Place un ordre sur Extended
        
        Args:
            symbol: Symbole (ex: "BTC")
            is_buy: True pour LONG, False pour SHORT
            size: Taille en USD
            price: Prix limite (None pour market order)
            reduce_only: True pour fermeture uniquement
            
        Returns:
            Réponse de l'exchange ou None
        """
        try:
            # TODO: Implémenter la signature avec eth_account
            logger.warning("place_order not fully implemented - signature needed")
            logger.info(f"Would place order: {symbol} {'BUY' if is_buy else 'SELL'} {size} @ {price or 'MARKET'}")
            
            order_data = {
                "symbol": f"{symbol}-USD",
                "side": "BUY" if is_buy else "SELL",
                "size": str(size),
                "price": str(price) if price else None,
                "type": "LIMIT" if price else "MARKET",
                "reduceOnly": reduce_only
            }
            
            # TODO: Signer et envoyer
            return {
                "status": "simulation",
                "order": order_data
            }
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None
    
    def close_position(self, symbol: str, size: float = None) -> bool:
        """
        Ferme une position
        
        Args:
            symbol: Symbole de la position
            size: Taille à fermer (None = tout)
            
        Returns:
            True si succès
        """
        try:
            positions = self.get_open_positions()
            
            for pos in positions:
                if pos.get('symbol') == symbol:
                    pos_size = float(pos.get('size', 0))
                    
                    # Fermer avec un ordre inverse
                    is_buy = pos_size < 0  # Si short, acheter pour fermer
                    close_size = abs(pos_size) if size is None else size
                    
                    return self.place_order(
                        symbol=symbol,
                        is_buy=is_buy,
                        size=close_size,
                        reduce_only=True
                    ) is not None
            
            logger.warning(f"No position found for {symbol}")
            return False
            
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False


def test_extended_connection():
    """Test de connexion à Extended"""
    import sys
    import os
    sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    
    from config import get_config
    
    config = get_config()
    wallet = config.get('wallet', 'address')
    pkey = config.get('wallet', 'private_key')
    
    if wallet == "0xYOUR_WALLET_ADDRESS":
        print("⚠️  Configure your wallet in config.json first!")
        return
    
    print(f"\n🔗 Testing Extended connection...")
    print(f"   Wallet: {wallet}\n")
    
    api = ExtendedAPI(wallet, pkey)
    
    # Test 1: Funding rate RESOLV
    print("📊 Fetching RESOLV funding rate...")
    resolv = api.get_funding_rate("RESOLV")
    if resolv:
        print(f"✅ RESOLV rate: {resolv['rate']*100:.4f}%")
    else:
        print("❌ Failed to fetch RESOLV rate")
    
    # Test 2: Tous les funding rates
    print("\n📊 Fetching all funding rates...")
    all_rates = api.get_all_funding_rates()
    print(f"✅ Total symbols: {len(all_rates)}")
    
    # Afficher les top 5
    if all_rates:
        print("\n🔝 Top 5 symbols:")
        for i, (symbol, info) in enumerate(list(all_rates.items())[:5]):
            print(f"   {i+1}. {symbol}: {info['rate']*100:.4f}%")


if __name__ == "__main__":
    test_extended_connection()

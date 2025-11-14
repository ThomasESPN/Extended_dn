"""
Hyperliquid API Integration
Utilise le SDK officiel Hyperliquid avec wallet signing
"""
from typing import Optional, Dict
import requests
import json
import sys
import os

# Ajouter le SDK Hyperliquid au path
SDK_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'hyperliquid-python-sdk-master')
if SDK_PATH not in sys.path:
    sys.path.insert(0, SDK_PATH)

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

try:
    from eth_account import Account
    from eth_account.signers.local import LocalAccount
    from hyperliquid.exchange import Exchange
    from hyperliquid.info import Info
    HAS_ETH_ACCOUNT = True
    HAS_HYPERLIQUID_SDK = True
except ImportError as e:
    HAS_ETH_ACCOUNT = False
    HAS_HYPERLIQUID_SDK = False
    logger.warning(f"Hyperliquid SDK not fully available: {e}")


class HyperliquidAPI:
    """Client API pour Hyperliquid avec wallet signing"""
    
    def __init__(self, wallet_address: str, private_key: str = None, testnet: bool = False):
        """
        Initialise le client Hyperliquid
        
        Args:
            wallet_address: Adresse publique du wallet (0x...)
            private_key: Clé privée du wallet (optionnel pour endpoints publics)
            testnet: True pour testnet, False pour mainnet
        """
        self.wallet_address = wallet_address
        self.account = None
        self.exchange = None
        self.info_client = None
        
        if private_key and HAS_ETH_ACCOUNT and HAS_HYPERLIQUID_SDK:
            # Initialiser le compte eth_account
            self.account = Account.from_key(private_key)
            
            # Initialiser le SDK Hyperliquid
            base_url = "https://api.hyperliquid-testnet.xyz" if testnet else "https://api.hyperliquid.xyz"
            
            # Exchange pour les ordres
            self.exchange = Exchange(
                wallet=self.account,
                base_url=base_url,
                account_address=wallet_address
            )
            
            # Info pour les données publiques
            self.info_client = Info(base_url=base_url, skip_ws=True)
        
        # API endpoints (fallback si SDK non disponible)
        if testnet:
            self.api_url = "https://api.hyperliquid-testnet.xyz"
        else:
            self.api_url = "https://api.hyperliquid.xyz"
        
        self.info_url = f"{self.api_url}/info"
        self.exchange_url = f"{self.api_url}/exchange"
        
        # Cache pour les métadonnées (leverage max, etc.)
        self.meta_cache = None
        
        logger.info(f"Hyperliquid API initialized for {wallet_address}")
    
    def get_max_leverage(self, symbol: str) -> int:
        """
        Récupère le levier maximum pour un symbole sur Hyperliquid
        
        Args:
            symbol: Symbole (ex: "ETH", "BTC")
            
        Returns:
            Max leverage (int), ex: 50, 20, 10
        """
        try:
            # Charger les métadonnées si pas déjà fait
            if not self.meta_cache:
                if self.info_client:
                    # Utiliser le SDK
                    self.meta_cache = self.info_client.meta()
                else:
                    # Fallback API REST
                    payload = {"type": "meta"}
                    response = requests.post(self.info_url, json=payload, timeout=10)
                    response.raise_for_status()
                    self.meta_cache = response.json()
            
            # Chercher le symbole dans l'universe
            universe = self.meta_cache.get("universe", [])
            for coin_info in universe:
                if coin_info.get("name") == symbol.upper():
                    max_lev = coin_info.get("maxLeverage", 50)
                    logger.info(f"   Hyperliquid {symbol}: max leverage {max_lev}x")
                    return int(max_lev)
            
            logger.warning(f"Symbol {symbol} not found on Hyperliquid, using default 50x")
            return 50  # Défaut Hyperliquid
            
        except Exception as e:
            logger.error(f"Error getting Hyperliquid max leverage for {symbol}: {e}")
            return 50  # Défaut Hyperliquid
    
    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """
        Récupère les prix bid/ask/last pour un symbole
        
        Args:
            symbol: Symbole (ex: "ETH", "BTC")
            
        Returns:
            Dict avec {'bid': float, 'ask': float, 'last': float}
        """
        try:
            payload = {
                "type": "allMids"
            }
            
            response = requests.post(self.info_url, json=payload, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # data est un dict {symbol: price_mid}
            if symbol in data:
                mid_price = float(data[symbol])
                # Approximation bid/ask avec 0.01% de spread
                spread = mid_price * 0.0001
                
                return {
                    'bid': mid_price - spread,
                    'ask': mid_price + spread,
                    'last': mid_price
                }
            
            logger.warning(f"Symbol {symbol} not found in Hyperliquid tickers")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            return None
    
    def get_user_state(self) -> Optional[Dict]:
        """
        Récupère l'état du compte utilisateur
        
        Returns:
            Dict avec positions, balances, etc.
        """
        try:
            payload = {
                "type": "clearinghouseState",
                "user": self.wallet_address
            }
            
            response = requests.post(self.info_url, json=payload, timeout=10)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Error fetching user state: {e}")
            return None
    
    def get_balance(self) -> float:
        """
        Récupère le balance USDC disponible
        
        Returns:
            Balance en USDC
        """
        try:
            state = self.get_user_state()
            if state and 'marginSummary' in state:
                return float(state['marginSummary']['accountValue'])
            return 0.0
            
        except Exception as e:
            logger.error(f"Error fetching balance: {e}")
            return 0.0
    
    def place_order(
        self,
        symbol: str,
        side: str,
        size: float,
        order_type: str = 'market',
        price: Optional[float] = None,
        reduce_only: bool = False,
        post_only: bool = False
    ) -> Optional[Dict]:
        """
        Place un ordre sur Hyperliquid en utilisant le SDK officiel
        
        Args:
            symbol: Symbole (ex: "BTC", "ETH")
            side: 'buy' ou 'sell'
            size: Taille en contracts (pas en USD!)
            order_type: 'market' ou 'limit'
            price: Prix limite (requis si order_type='limit')
            reduce_only: True pour fermeture uniquement
            post_only: True pour maker only (ALO)
            
        Returns:
            Réponse de l'exchange ou None
        """
        try:
            if not self.exchange:
                logger.error("Exchange SDK not initialized - cannot place orders")
                return None
            
            is_buy = side.lower() == 'buy'
            
            # Déterminer le type d'ordre Hyperliquid
            if order_type.lower() == 'limit':
                if post_only:
                    hl_order_type = {"limit": {"tif": "Alo"}}  # Add Liquidity Only (maker only)
                    logger.info(f"   📗 MAKER order (Alo)")
                else:
                    hl_order_type = {"limit": {"tif": "Gtc"}}  # Good Till Cancel
                    logger.info(f"   📙 LIMIT order (Gtc)")
                    
                # 🎯 STRATÉGIE MAKER: mid price ±0.005% pour fill rapide en restant maker
                # D'après le bot Next.js: prix proche du mid, ajusté de ±0.005%
                # Si pas de fill → retry avec offset plus grand (géré par le bot)
                if not price and post_only:
                    ticker = self.get_ticker(symbol)
                    bid = ticker['bid']
                    ask = ticker['ask']
                    mid = (bid + ask) / 2
                    
                    if is_buy:
                        # BUY = mid - 0.005% (légèrement en dessous pour MAKER)
                        price = mid * 0.99995
                        logger.info(f"   Limit MAKER BUY: mid - 0.005% = ${price:.2f} (bid: ${bid:.2f}, ask: ${ask:.2f})")
                    else:
                        # SELL = mid + 0.005% (légèrement au-dessus pour MAKER)
                        price = mid * 1.00005
                        logger.info(f"   Limit MAKER SELL: mid + 0.005% = ${price:.2f} (bid: ${bid:.2f}, ask: ${ask:.2f})")
            else:
                # Market order = limit avec slippage
                hl_order_type = {"limit": {"tif": "Ioc"}}  # Immediate or Cancel
                logger.info(f"   📕 TAKER order (Ioc)")
                if not price:
                    # Calculer le prix avec slippage pour market order
                    price = self.exchange._slippage_price(symbol, is_buy, 0.01)  # 1% slippage
            
            if not price:
                logger.error("Price is required for Hyperliquid orders")
                return None
            
            # Arrondir le prix à 5 chiffres significatifs (requis par Hyperliquid)
            price = round(float(f"{price:.5g}"), 6)
            
            logger.info(f"Placing order: {symbol} {side.upper()} {size} @ {price}")
            
            # Placer l'ordre via le SDK
            result = self.exchange.order(
                name=symbol,
                is_buy=is_buy,
                sz=size,
                limit_px=price,
                order_type=hl_order_type,
                reduce_only=reduce_only
            )
            
            logger.success(f"✅ Order placed successfully: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def cancel_order(self, order_id: int) -> bool:
        """
        Annule un ordre
        
        Args:
            order_id: ID de l'ordre à annuler
            
        Returns:
            True si succès
        """
        try:
            # TODO: Implémenter la signature et l'annulation
            logger.warning("cancel_order not fully implemented")
            return False
            
        except Exception as e:
            logger.error(f"Error canceling order: {e}")
            return False
    
    def get_funding_rate(self, symbol: str) -> Optional[Dict]:
        """
        Récupère le funding rate actuel pour un symbole
        
        Args:
            symbol: Symbole (ex: "BTC", "ETH")
            
        Returns:
            Dict avec {
                'symbol': str,
                'rate': float (décimal, ex: -0.00571 = -0.571%),
                'next_funding': timestamp,
                'interval_hours': int
            }
        """
        try:
            payload = {
                "type": "metaAndAssetCtxs"
            }
            
            response = requests.post(self.info_url, json=payload, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # Chercher le symbole dans les contexts
            for ctx in data[0].get('universe', []):
                if ctx.get('name') == symbol:
                    # Le funding rate est dans ctx
                    funding = ctx.get('funding')
                    
                    return {
                        'symbol': symbol,
                        'rate': float(funding) if funding else 0.0,
                        'next_funding': None,  # TODO: parser timestamp
                        'interval_hours': 1  # Hyperliquid utilise 1h pour la plupart
                    }
            
            logger.warning(f"Symbol {symbol} not found on Hyperliquid")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching funding rate for {symbol}: {e}")
            return None
    
    def get_all_funding_rates(self) -> Dict[str, Dict]:
        """
        Récupère tous les funding rates disponibles sur Hyperliquid
        
        Returns:
            Dict {symbol: funding_info}
        """
        try:
            payload = {
                "type": "metaAndAssetCtxs"
            }
            
            response = requests.post(self.info_url, json=payload, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            funding_rates = {}
            
            # data[0] = metadata avec symbols, data[1] = contexts avec funding rates
            # Ils sont matchés par index
            universe = data[0].get('universe', [])
            contexts = data[1] if len(data) > 1 else []
            
            for i, meta in enumerate(universe):
                if i < len(contexts):
                    symbol = meta.get('name')
                    funding = contexts[i].get('funding')
                    
                    if symbol and funding is not None:
                        funding_rates[symbol] = {
                            'symbol': symbol,
                            'rate': float(funding),
                            'next_funding': None,
                            'interval_hours': 1
                        }
            
            logger.info(f"Fetched {len(funding_rates)} funding rates from Hyperliquid")
            return funding_rates
            
        except Exception as e:
            logger.error(f"Error fetching all funding rates: {e}")
            return {}
    
    def get_open_positions(self) -> list:
        """
        Récupère les positions ouvertes
        
        Returns:
            Liste des positions
        """
        try:
            state = self.get_user_state()
            if state and 'assetPositions' in state:
                return state['assetPositions']
            return []
            
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []
    
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
                if pos.get('position', {}).get('coin') == symbol:
                    pos_size = float(pos['position']['szi'])
                    
                    # Fermer la position avec un ordre inverse
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


def test_hyperliquid_connection():
    """Test de connexion à Hyperliquid"""
    from config import get_config
    
    config = get_config()
    wallet = config.get('exchanges', 'hyperliquid', 'wallet_address')
    pkey = config.get('exchanges', 'hyperliquid', 'private_key')
    
    if wallet == "0xYOUR_HYPERLIQUID_WALLET_ADDRESS":
        print("⚠️  Configure your Hyperliquid wallet in config.json first!")
        return
    
    print(f"\n🔗 Testing Hyperliquid connection...")
    print(f"   Wallet: {wallet}\n")
    
    api = HyperliquidAPI(wallet, pkey, testnet=False)
    
    # Test 1: Balance
    balance = api.get_balance()
    print(f"✅ Balance: ${balance:.2f} USDC")
    
    # Test 2: Positions
    positions = api.get_open_positions()
    print(f"✅ Open positions: {len(positions)}")
    
    if positions:
        for pos in positions:
            print(f"   - {pos['position']['coin']}: {pos['position']['szi']}")


if __name__ == "__main__":
    test_hyperliquid_connection()

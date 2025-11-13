"""
Hyperliquid API Integration
Utilise le SDK officiel Hyperliquid avec wallet signing
"""
from typing import Optional, Dict
import requests
import json

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
        
        if private_key and HAS_ETH_ACCOUNT:
            self.account = Account.from_key(private_key)
        
        # API endpoints
        if testnet:
            self.api_url = "https://api.hyperliquid-testnet.xyz"
        else:
            self.api_url = "https://api.hyperliquid.xyz"
        
        self.info_url = f"{self.api_url}/info"
        self.exchange_url = f"{self.api_url}/exchange"
        
        logger.info(f"Hyperliquid API initialized for {wallet_address}")
    
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
        is_buy: bool,
        size: float,
        price: Optional[float] = None,
        reduce_only: bool = False,
        post_only: bool = False
    ) -> Optional[Dict]:
        """
        Place un ordre sur Hyperliquid
        
        Args:
            symbol: Symbole (ex: "BTC")
            is_buy: True pour LONG, False pour SHORT
            size: Taille en USD
            price: Prix limite (None pour market order)
            reduce_only: True pour fermeture uniquement
            post_only: True pour maker only (ALO)
            
        Returns:
            Réponse de l'exchange ou None
        """
        try:
            # TODO: Implémenter la signature avec eth_account
            # Voir: https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint
            
            logger.warning("place_order not fully implemented - signature needed")
            logger.info(f"Would place order: {symbol} {'BUY' if is_buy else 'SELL'} {size} @ {price or 'MARKET'}")
            
            # Placeholder pour la structure
            order_spec = {
                "asset": symbol,
                "isBuy": is_buy,
                "limitPx": str(price) if price else "0",
                "sz": str(size),
                "reduceOnly": reduce_only,
                "orderType": {"limit": {"tif": "Alo" if post_only else "Gtc"}}
            }
            
            # TODO: Signer l'ordre avec self.account
            # TODO: Envoyer à self.exchange_url
            
            return {
                "status": "simulation",
                "order": order_spec
            }
            
        except Exception as e:
            logger.error(f"Error placing order: {e}")
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

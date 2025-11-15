"""
Hyperliquid API Integration
Utilise le SDK officiel Hyperliquid avec wallet signing
"""
from typing import Optional, Dict
import requests
import json
import websocket
import threading
import time

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
        
        # WebSocket pour orderbook en temps réel
        self.ws_app = None  # Instance WebSocketApp
        self.ws_thread = None
        self.orderbook_cache = {}  # {coin: {"bid": float, "ask": float, "last_update": float}}
        self.ws_connected = False
        self.ws_coin = None  # Coin actuellement connecté
        
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
    
    def ws_orderbook(self, ticker: str):
        """
        Se connecte au WebSocket orderbook pour un ticker donné
        
        Args:
            ticker: Symbole du ticker (ex: "ZORA", "BTC", "ETH")
            
        Returns:
            True si la connexion est établie, False sinon
        """
        try:
            # Le ticker est utilisé tel quel pour Hyperliquid (ex: "BTC", "ETH", "ZORA")
            coin = ticker.upper()
            
            # Si déjà connecté au même coin, ne rien faire
            if self.ws_connected and self.ws_coin == coin and self.ws_app:
                logger.info(f"WebSocket déjà connecté au coin {coin}")
                return True
            
            # Fermer la connexion précédente si différente
            if self.ws_app and self.ws_coin != coin:
                try:
                    self.ws_app.close()
                except:
                    pass
                self.ws_connected = False
                self.ws_app = None
            
            # URL WebSocket Hyperliquid
            ws_url = f"{self.api_url.replace('https', 'wss').replace('http', 'ws')}/ws"
            
            logger.info(f"🔌 Connexion WebSocket orderbook pour {coin}...")
            
            def on_message(ws, message):
                try:
                    if message == "Websocket connection established.":
                        return
                    
                    data = json.loads(message)
                    channel = data.get('channel')
                    
                    if channel == 'l2Book':
                        orderbook_data = data.get('data', {})
                        msg_coin = orderbook_data.get('coin')
                        levels = orderbook_data.get('levels', [[], []])
                        
                        if msg_coin and len(levels) >= 2:
                            bids = levels[0]  # Premier tableau = bids
                            asks = levels[1]  # Deuxième tableau = asks
                            
                            if bids and asks:
                                # Format: [{"px": "25670", "sz": "0.1", "n": 1}, ...]
                                best_bid = float(bids[0]['px']) if bids else None
                                best_ask = float(asks[0]['px']) if asks else None
                                
                                if best_bid and best_ask:
                                    self.orderbook_cache[msg_coin] = {
                                        "bid": best_bid,
                                        "ask": best_ask,
                                        "last_update": time.time()
                                    }
                except Exception as e:
                    logger.error(f"Erreur traitement message WebSocket: {e}")
            
            def on_error(ws, error):
                error_str = str(error)
                logger.error(f"WebSocket error: {error}")
                self.ws_connected = False
            
            def on_close(ws, close_status_code, close_msg):
                if close_status_code != 1000:
                    logger.warning(f"WebSocket fermé: {close_status_code} - {close_msg}")
                self.ws_connected = False
                self.ws_coin = None
            
            def on_open(ws):
                logger.success(f"✅ WebSocket orderbook connecté pour {coin}")
                self.ws_connected = True
                self.ws_coin = coin
                
                # Souscrire au l2Book pour ce coin
                subscription = {
                    "method": "subscribe",
                    "subscription": {
                        "type": "l2Book",
                        "coin": coin
                    }
                }
                ws.send(json.dumps(subscription))
                logger.info(f"   📡 Souscription l2Book envoyée pour {coin}")
            
            def run_websocket():
                self.ws_app = websocket.WebSocketApp(
                    ws_url,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close,
                    on_open=on_open
                )
                self.ws_app.run_forever()
            
            # Démarrer le websocket dans un thread séparé
            self.ws_thread = threading.Thread(target=run_websocket, daemon=True)
            self.ws_thread.start()
            
            # Attendre que la connexion s'établisse (jusqu'à 5 secondes)
            max_wait = 5
            waited = 0
            while not self.ws_connected and waited < max_wait:
                time.sleep(0.5)
                waited += 0.5
            
            if self.ws_connected:
                logger.success(f"✅ WebSocket orderbook démarré pour {coin}")
                return True
            else:
                logger.error(f"❌ Échec connexion WebSocket pour {coin}")
                return False
                
        except Exception as e:
            logger.error(f"Erreur lors de la connexion WebSocket pour {ticker}: {e}")
            return False
    
    def get_orderbook_data(self, ticker: str) -> Optional[Dict]:
        """
        Récupère les données de l'orderbook depuis le cache WebSocket
        
        Args:
            ticker: Symbole du ticker (ex: "ZORA", "BTC", "ETH")
            
        Returns:
            Dict avec {"bid": float, "ask": float} ou None si pas disponible
        """
        coin = ticker.upper()
        
        if coin in self.orderbook_cache:
            cache_data = self.orderbook_cache[coin]
            # Vérifier que les données sont récentes (< 10 secondes)
            if time.time() - cache_data['last_update'] < 10:
                return {
                    "bid": cache_data['bid'],
                    "ask": cache_data['ask']
                }
        
        return None


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

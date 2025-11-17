"""
Extended Exchange API Integration
Documentation: https://api-docs.extended.exchange/
"""
from typing import Optional, Dict, List
import requests
import json
import websocket
import threading
import time
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
        
        # WebSocket pour orderbook en temps réel
        self.ws_app = None  # Instance WebSocketApp (renommé pour éviter conflit avec méthode)
        self.ws_thread = None
        self.orderbook_cache = {}  # {market_name: {"bid": float, "ask": float, "last_update": float}}
        self.ws_connected = False
        self.ws_market = None  # Market actuellement connecté
        
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
    
    def ws_orderbook(self, ticker: str):
        """
        Se connecte au WebSocket orderbook pour un ticker donné
        
        Args:
            ticker: Symbole du ticker (ex: "ZORA") qui sera converti en "ZORA-USD"
            
        Returns:
            True si la connexion est établie, False sinon
        """
        try:
            # Convertir le ticker en nom de marché (ex: "ZORA" -> "ZORA-USD")
            market_name = f"{ticker.upper()}-USD"
            
            # Si déjà connecté au même marché, ne rien faire
            if self.ws_connected and self.ws_market == market_name and self.ws_app:
                logger.info(f"WebSocket déjà connecté au marché {market_name}")
                return True
            
            # Fermer la connexion précédente si différente
            if self.ws_app and self.ws_market != market_name:
                try:
                    self.ws_app.close()
                except:
                    pass
                self.ws_connected = False
                self.ws_app = None
            
            # URL WebSocket Extended
            ws_url = f"wss://api.starknet.extended.exchange/stream.extended.exchange/v1/orderbooks/{market_name}?depth=1"
            
            logger.info(f"🔌 Connexion WebSocket orderbook pour {market_name}...")
            
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    msg_type = data.get('type')
                    orderbook_data = data.get('data', {})
                    
                    if msg_type in ['SNAPSHOT', 'DELTA']:
                        market = orderbook_data.get('m')
                        bids = orderbook_data.get('b', [])
                        asks = orderbook_data.get('a', [])
                        
                        if market and bids and asks:
                            # Extraire le meilleur bid et ask
                            best_bid = float(bids[0]['p']) if bids else None
                            best_ask = float(asks[0]['p']) if asks else None
                            
                            if best_bid and best_ask:
                                self.orderbook_cache[market] = {
                                    "bid": best_bid,
                                    "ask": best_ask,
                                    "last_update": time.time()
                                }
                except Exception as e:
                    logger.error(f"Erreur traitement message WebSocket: {e}")
            
            def on_error(ws, error):
                error_str = str(error)
                if '403' in error_str or 'Forbidden' in error_str:
                    logger.warning(f"WebSocket 403 Forbidden pour {market_name}")
                    self.ws_connected = False
                else:
                    logger.error(f"WebSocket error: {error}")
                    self.ws_connected = False
            
            def on_close(ws, close_status_code, close_msg):
                if close_status_code != 1000:
                    logger.warning(f"WebSocket fermé: {close_status_code} - {close_msg}")
                self.ws_connected = False
                self.ws_market = None
            
            def on_open(ws):
                logger.success(f"✅ WebSocket orderbook connecté pour {market_name}")
                self.ws_connected = True
                self.ws_market = market_name
            
            def run_websocket():
                # Headers comme le SDK
                headers = [
                    "User-Agent: X10PythonTradingClient/0.0.17"
                ]
                
                self.ws_app = websocket.WebSocketApp(
                    ws_url,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close,
                    on_open=on_open,
                    header=headers
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
                logger.success(f"✅ WebSocket orderbook démarré pour {market_name}")
                return True
            else:
                logger.error(f"❌ Échec connexion WebSocket pour {market_name}")
                return False
                
        except Exception as e:
            logger.error(f"Erreur lors de la connexion WebSocket pour {ticker}: {e}")
            return False
    
    def get_orderbook_data(self, ticker: str) -> Optional[Dict]:
        """
        Récupère les données de l'orderbook depuis le cache WebSocket
        
        Args:
            ticker: Symbole du ticker (ex: "ZORA")
            
        Returns:
            Dict avec {"bid": float, "ask": float} ou None si pas disponible
        """
        market_name = f"{ticker.upper()}-USD"
        
        if market_name in self.orderbook_cache:
            cache_data = self.orderbook_cache[market_name]
            # Vérifier que les données sont récentes (< 10 secondes)
            if time.time() - cache_data['last_update'] < 10:
                return {
                    "bid": cache_data['bid'],
                    "ask": cache_data['ask']
                }
        
        return None


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

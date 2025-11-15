"""
Hyperliquid API Integration
Utilise le SDK officiel Hyperliquid avec wallet signing
"""
from typing import Optional, Dict, List
import requests
import json
import sys
import os
import time
import websocket
import threading

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
        
        # WebSocket pour orderbook en temps réel
        self.ws_app = None  # Instance WebSocketApp
        self.ws_thread = None
        self.orderbook_cache = {}  # {coin: {"bid": float, "ask": float, "last_update": float}}
        self.ws_connected = False
        self.ws_coin = None  # Coin actuellement connecté
        
        logger.info(f"Hyperliquid API initialized for {wallet_address}")
    
    def get_size_decimals(self, symbol: str) -> int:
        """
        Récupère le nombre de décimales pour la taille (sz_decimals) d'un symbole
        
        Args:
            symbol: Symbole (ex: "ETH", "BTC", "ZORA")
            
        Returns:
            Nombre de décimales (int), ex: 5 pour ZORA, 3 pour ETH
        """
        try:
            # Charger les métadonnées si pas déjà fait
            if not self.meta_cache:
                if self.info_client:
                    self.meta_cache = self.info_client.meta()
                else:
                    payload = {"type": "meta"}
                    response = requests.post(self.info_url, json=payload, timeout=10)
                    response.raise_for_status()
                    self.meta_cache = response.json()
            
            # Chercher le symbole dans l'universe
            universe = self.meta_cache.get("universe", [])
            for coin_info in universe:
                if coin_info.get("name") == symbol.upper():
                    sz_dec = coin_info.get("szDecimals", 4)
                    logger.info(f"   Hyperliquid {symbol}: {sz_dec} decimals")
                    return int(sz_dec)
            
            logger.warning(f"Symbol {symbol} not found on Hyperliquid, using default 4 decimals")
            return 4
            
        except Exception as e:
            logger.error(f"Error getting Hyperliquid decimals for {symbol}: {e}")
            return 4

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
    
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """
        Configure le levier pour un symbole sur Hyperliquid
        
        Args:
            symbol: Symbole (ex: "ETH", "BTC")
            leverage: Levier désiré (ex: 3, 5, 10)
            
        Returns:
            True si succès, False sinon
        """
        try:
            if not self.exchange:
                logger.error("Exchange client not available - cannot set leverage")
                return False
            
            # Trouver l'asset index
            if not self.meta_cache:
                self.get_max_leverage(symbol)  # Charger le meta_cache
            
            universe = self.meta_cache.get("universe", [])
            asset_index = None
            for idx, coin_info in enumerate(universe):
                if coin_info.get("name") == symbol.upper():
                    asset_index = idx
                    break
            
            if asset_index is None:
                logger.error(f"Symbol {symbol} not found for set_leverage")
                return False
            
            # Set leverage via SDK
            result = self.exchange.update_leverage(leverage, symbol, is_cross=True)
            
            if result and result.get('status') == 'ok':
                logger.info(f"✅ Hyperliquid leverage set to {leverage}x for {symbol}")
                return True
            else:
                logger.error(f"Failed to set leverage: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error setting Hyperliquid leverage for {symbol}: {e}")
            return False
    
    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """
        Récupère les prix bid/ask/last pour un symbole via l'orderbook L2
        
        Args:
            symbol: Symbole (ex: "ETH", "BTC")
            
        Returns:
            Dict avec {'bid': float, 'ask': float, 'last': float}
        """
        try:
            # Utiliser l2Book pour obtenir les vrais bid/ask (top 10)
            payload = {
                "type": "l2Book",
                "coin": symbol.upper()
            }
            
            response = requests.post(self.info_url, json=payload, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            # data est un array [bids, asks]
            # bids et asks sont des arrays de {px: str, sz: str, n: int}
            if isinstance(data, list) and len(data) >= 2:
                bids = data[0]  # Premier élément = bids
                asks = data[1]  # Deuxième élément = asks
                
                if bids and asks:
                    # Meilleur bid = premier élément (prix le plus élevé)
                    best_bid = float(bids[0]['px'])
                    # Meilleur ask = premier élément (prix le plus bas)
                    best_ask = float(asks[0]['px'])
                    mid_price = (best_bid + best_ask) / 2
                    
                    return {
                        'bid': best_bid,
                        'ask': best_ask,
                        'last': mid_price
                    }
            
            # Fallback sur allMids si l2Book échoue
            logger.debug(f"l2Book failed for {symbol}, falling back to allMids")
            payload = {
                "type": "allMids"
            }
            
            response = requests.post(self.info_url, json=payload, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
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
            order_id: ID de l'ordre à annuler (OID)
            
        Returns:
            True si succès
        """
        try:
            if not self.exchange:
                logger.error("Hyperliquid SDK not initialized")
                return False
            
            # Get coin index from open orders
            open_orders = self.get_open_orders()
            order = next((o for o in open_orders if o['oid'] == order_id), None)
            
            if not order:
                logger.warning(f"Order {order_id} not found in open orders")
                return False
            
            symbol = order['symbol']
            
            # Get coin index from meta (universe)
            coin_index = None
            if not self.meta_cache:
                if self.info_client:
                    self.meta_cache = self.info_client.meta()
                else:
                    payload = {"type": "meta"}
                    response = requests.post(self.info_url, json=payload, timeout=10)
                    response.raise_for_status()
                    self.meta_cache = response.json()
            
            universe = self.meta_cache.get('universe', [])
            for i, meta in enumerate(universe):
                if meta.get('name') == symbol:
                    coin_index = i
                    break
            
            if coin_index is None:
                logger.error(f"Can't find coin index for {symbol} in meta")
                return False
            
            # Use SDK to cancel
            result = self.exchange.cancel(symbol, order_id)
            
            if result and result.get('status') == 'ok':
                logger.success(f"✅ Order {order_id} cancelled")
                return True
            else:
                logger.error(f"Cancel failed: {result}")
                return False
            
        except Exception as e:
            logger.error(f"Error canceling order {order_id}: {e}")
            import traceback
            logger.error(traceback.format_exc())
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
    
    def get_user_fills(self, limit: int = 100) -> List[Dict]:
        """
        Récupère les fills récents de l'utilisateur
        https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint#retrieve-a-users-fills
        
        Args:
            limit: Nombre maximum de fills à récupérer
            
        Returns:
            Liste des fills récents
        """
        try:
            payload = {
                "type": "userFills",
                "user": self.wallet_address
            }
            
            response = requests.post(self.info_url, json=payload, timeout=10)
            response.raise_for_status()
            
            fills = response.json()
            
            # Convertir en format standardisé
            result = []
            for fill in fills[:limit]:
                result.append({
                    'symbol': fill.get('coin', ''),
                    'side': 'BUY' if fill.get('side', '') == 'B' else 'SELL',
                    'price': float(fill.get('px', 0)),
                    'size': float(fill.get('sz', 0)),
                    'timestamp': int(fill.get('time', 0)),
                    'fee': float(fill.get('fee', 0)),
                    'oid': fill.get('oid', 0),
                    'tid': fill.get('tid', 0),
                    'crossed': fill.get('crossed', False)
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching user fills: {e}")
            return []
    
    def get_open_orders(self) -> List[Dict]:
        """
        Récupère les ordres ouverts (resting)
        https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint#retrieve-a-users-open-orders
        
        Returns:
            Liste des ordres ouverts
        """
        try:
            payload = {
                "type": "openOrders",
                "user": self.wallet_address
            }
            
            response = requests.post(self.info_url, json=payload, timeout=10)
            response.raise_for_status()
            
            orders = response.json()
            
            # Convertir en format standardisé
            result = []
            for order in orders:
                result.append({
                    'oid': order.get('oid', 0),
                    'symbol': order.get('coin', ''),
                    'side': 'BUY' if order.get('side', '') == 'B' else 'SELL',
                    'price': float(order.get('limitPx', 0)),
                    'size': float(order.get('sz', 0)),
                    'filled_size': float(order.get('szFilled', 0)),
                    'timestamp': int(order.get('timestamp', 0)),
                    'order_type': order.get('orderType', ''),
                    'reduce_only': order.get('reduceOnly', False)
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching open orders: {e}")
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

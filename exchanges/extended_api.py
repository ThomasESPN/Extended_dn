"""
Extended Exchange API Integration - Using Official SDK x10-python-trading-starknet
Based on: python_sdk-extended/examples/
"""
from typing import Optional, Dict, List
from decimal import Decimal
import asyncio
import requests
import websocket
import json
import threading
import time

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# Import du SDK officiel Extended
try:
    from x10.perpetual.accounts import StarkPerpetualAccount
    from x10.perpetual.configuration import MAINNET_CONFIG
    from x10.perpetual.trading_client import PerpetualTradingClient
    from x10.perpetual.order_object import create_order_object
    from x10.perpetual.orders import OrderSide, TimeInForce
    HAS_EXTENDED_SDK = True
    logger.info("✅ Extended SDK (x10-python-trading-starknet) loaded")
except ImportError as e:
    HAS_EXTENDED_SDK = False
    logger.warning(f"Extended SDK not available: {e}")


class ExtendedAPI:
    """Client API pour Extended Exchange avec SDK officiel x10"""
    
    # Event loop partagé pour éviter "Event loop is closed"
    _event_loop = None
    
    @classmethod
    def get_event_loop(cls):
        """Récupère ou crée un event loop réutilisable"""
        if cls._event_loop is None or cls._event_loop.is_closed():
            try:
                cls._event_loop = asyncio.get_event_loop()
                if cls._event_loop.is_closed():
                    raise RuntimeError("Loop is closed")
            except RuntimeError:
                cls._event_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(cls._event_loop)
        return cls._event_loop
    
    def __init__(self, wallet_address: str, private_key: str = None, 
                 api_key: str = None, stark_public_key: str = None,
                 stark_private_key: str = None, vault_id: int = None, 
                 client_id: int = None):
        """
        Initialise le client Extended avec le SDK officiel
        
        Args:
            wallet_address: Adresse publique du wallet (0x...)
            private_key: Clé privée EVM (non utilisée pour Extended)
            api_key: API Key Extended
            stark_public_key: Clé publique Starknet
            stark_private_key: Clé privée Starknet
            vault_id: ID du vault Starknet
            client_id: ID du client (facultatif)
        """
        # Ne pas appeler super().__init__() si pas de parent qui l'attend
        # super().__init__(wallet_address, private_key)
        
        self.wallet_address = wallet_address
        self.api_key = api_key
        self.stark_public_key = stark_public_key
        self.stark_private_key = stark_private_key
        self.vault_id = vault_id
        self.client_id = client_id
        
        self.wallet_address = wallet_address
        self.trading_client = None
        self.stark_account = None
        self.markets_cache = None
        
        # WebSocket pour orderbook en temps réel
        self.ws_app = None  # Instance WebSocketApp (renommé pour éviter conflit avec méthode)
        self.ws_thread = None
        self.orderbook_cache = {}  # {market_name: {"bid": float, "ask": float, "last_update": float}}
        self.orderbook_state = {}  # {market: {"bids": {price: qty}, "asks": {price: qty}}} pour gérer DELTA
        self.ws_connected = False
        self.ws_market = None  # Market actuellement connecté
        
        # WebSocket pour mark price en temps réel
        self.ws_mark_price_app = None
        self.ws_mark_price_thread = None
        self.mark_price_cache = {}  # {market_name: {"mark_price": float, "last_update": float}}
        self.ws_mark_price_connected = False
        self.ws_mark_price_symbols = set()  # Symboles déjà abonnés
        
        # WebSocket pour positions en temps réel
        self.ws_account_app = None
        self.ws_account_thread = None
        self.positions_cache = {}  # {market: Position}
        self.orders_cache = []  # Liste des mises à jour d'ordres depuis WebSocket account
        self.ws_account_connected = False
        
        if not HAS_EXTENDED_SDK:
            logger.warning("⚠️ Extended SDK not installed - orders will be simulated")
            return
        
        if not all([api_key, stark_public_key, stark_private_key, vault_id]):
            logger.warning("⚠️ Missing Extended credentials - orders will be simulated")
            return
        
        try:
            # Vérifier format des clés
            if not stark_public_key.startswith("0x"):
                stark_public_key = "0x" + stark_public_key
            if not stark_private_key.startswith("0x"):
                stark_private_key = "0x" + stark_private_key
            
            # Créer le StarkPerpetualAccount
            stark_account = StarkPerpetualAccount(
                api_key=api_key,
                public_key=stark_public_key,
                private_key=stark_private_key,
                vault=vault_id
            )
            
            # Créer le PerpetualTradingClient (utilisation directe sans BlockingClient)
            logger.info("Initializing Extended SDK client...")
            self.trading_client = PerpetualTradingClient(
                endpoint_config=MAINNET_CONFIG,
                stark_account=stark_account
            )
            self.stark_account = stark_account
            
            logger.success(f"✅ Extended SDK initialized (vault {vault_id})")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Extended SDK: {type(e).__name__}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            self.trading_client = None
        
        logger.info(f"Extended API initialized for {wallet_address}")
    
    def _start_orderbook_websocket(self, market_name: str):
        """
        Démarre la connexion WebSocket pour l'orderbook d'un marché
        Utilise depth=1 pour obtenir seulement best bid/ask (fréquence 10ms)
        """
        if self.ws_connected and self.ws_orderbook:
            return  # Déjà connecté
        
        # URL WebSocket avec depth=5 pour s'assurer d'avoir toujours les deux côtés
        # depth=1 peut parfois ne retourner qu'un seul côté lors des DELTA, ce qui fausse le calcul du mid_price
        ws_url = f"wss://api.starknet.extended.exchange/stream.extended.exchange/v1/orderbooks/{market_name}?depth=5"
        
        def on_message(ws, message):
            try:
                # Le message peut contenir plusieurs objets JSON séparés par des virgules ou être un tableau
                # Essayer de parser comme JSON d'abord
                try:
                    # Essayer comme un seul objet JSON
                    data = json.loads(message)
                    messages = [data] if isinstance(data, dict) else data
                except:
                    # Si ça échoue, essayer de split par lignes (chaque ligne = un JSON)
                    messages = []
                    for line in message.strip().split('\n'):
                        if line.strip():
                            try:
                                messages.append(json.loads(line))
                            except:
                                pass
                
                # Traiter chaque message
                for data in messages:
                    if not isinstance(data, dict):
                        continue
                    
                    msg_type = data.get('type')
                    orderbook_data = data.get('data', {})
                    
                    # Ignorer les messages sans type ou sans data
                    if not msg_type or not orderbook_data:
                        continue
                    
                    if msg_type in ['SNAPSHOT', 'DELTA']:
                        market = orderbook_data.get('m')
                        if not market:
                            continue
                        
                        # Initialiser l'état si nécessaire
                        if market not in self.orderbook_state:
                            self.orderbook_state[market] = {"bids": {}, "asks": {}}
                        
                        state = self.orderbook_state[market]
                        
                        # Traiter les bids
                        bids = orderbook_data.get('b', [])
                        for bid in bids:
                            price = float(bid['p'])
                            qty = float(bid['q'])
                            
                            if msg_type == 'SNAPSHOT':
                                # SNAPSHOT: quantité absolue
                                if qty > 0:
                                    state['bids'][price] = qty
                                else:
                                    state['bids'].pop(price, None)
                            else:  # DELTA
                                # DELTA: quantité négative = suppression, positive = ajout/modification
                                if qty <= 0:
                                    state['bids'].pop(price, None)
                                else:
                                    state['bids'][price] = qty
                        
                        # Traiter les asks
                        asks = orderbook_data.get('a', [])
                        for ask in asks:
                            price = float(ask['p'])
                            qty = float(ask['q'])
                            
                            if msg_type == 'SNAPSHOT':
                                # SNAPSHOT: quantité absolue
                                if qty > 0:
                                    state['asks'][price] = qty
                                else:
                                    state['asks'].pop(price, None)
                            else:  # DELTA
                                # DELTA: quantité négative = suppression, positive = ajout/modification
                                if qty <= 0:
                                    state['asks'].pop(price, None)
                                else:
                                    state['asks'][price] = qty
                        
                        # Extraire le meilleur bid (prix le plus élevé) et ask (prix le plus bas)
                        if state['bids'] and state['asks']:
                            best_bid = max(state['bids'].keys())
                            best_ask = min(state['asks'].keys())
                            
                            self.orderbook_cache[market] = {
                                "bid": best_bid,
                                "ask": best_ask,
                                "last_update": time.time()
                            }
            except Exception as e:
                logger.error(f"Error processing websocket message: {e}")
                import traceback
                logger.debug(traceback.format_exc())
        
        def on_error(ws, error):
            error_str = str(error)
            # Si 403, essayer l'autre URL
            if '403' in error_str or 'Forbidden' in error_str:
                logger.warning(f"WebSocket 403 Forbidden, le WebSocket orderbook n'est peut-être pas accessible")
                logger.warning(f"   → Fallback sur l'API REST pour les prix")
                self.ws_connected = False
            else:
                logger.error(f"WebSocket error: {error}")
                self.ws_connected = False
        
        def on_close(ws, close_status_code, close_msg):
            if close_status_code != 1000:  # 1000 = normal closure
                logger.warning(f"WebSocket closed: {close_status_code} - {close_msg}")
            self.ws_connected = False
        
        def on_open(ws):
            logger.success(f"✅ WebSocket orderbook connected for {market_name}")
            self.ws_connected = True
        
        def run_websocket():
            # Ajouter les headers comme le SDK (User-Agent)
            # websocket-client utilise header (liste de strings au format "Key: Value")
            headers = [
                "User-Agent: X10PythonTradingClient/0.0.17"
            ]
            
            self.ws_orderbook = websocket.WebSocketApp(
                ws_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open,
                header=headers
            )
            self.ws_orderbook.run_forever()
        
        # Démarrer le websocket dans un thread séparé
        self.ws_thread = threading.Thread(target=run_websocket, daemon=True)
        self.ws_thread.start()
        
        # Attendre un peu pour que la connexion s'établisse
        time.sleep(1)
    
    def _stop_orderbook_websocket(self):
        """Ferme la connexion WebSocket"""
        if self.ws_orderbook:
            self.ws_orderbook.close()
            self.ws_connected = False
            logger.info("WebSocket orderbook closed")

    def get_markets(self) -> List[Dict]:
        """Récupère la liste des marchés disponibles"""
        if not self.trading_client:
            return self._get_markets_fallback()
        
        try:
            if not self.markets_cache:
                # get_markets() retourne Dict[str, MarketModel]
                markets_dict = self.get_event_loop().run_until_complete(self.trading_client.markets_info.get_markets_dict())
                self.markets_cache = markets_dict
            
            return [
                {
                    "symbol": name.replace("-USD", "").replace("_", ""),
                    "name": market.name,
                    "min_size": float(market.trading_config.min_order_size)
                }
                for name, market in self.markets_cache.items()
            ]
        except Exception as e:
            logger.error(f"Error fetching Extended markets: {e}")
            return self._get_markets_fallback()
    
    def _get_markets_fallback(self) -> List[Dict]:
        """Marchés par défaut si SDK pas dispo"""
        return [
            {"symbol": "BTC", "name": "BTC-USD", "min_size": 0.001},
            {"symbol": "ETH", "name": "ETH-USD", "min_size": 0.01},
            {"symbol": "SOL", "name": "SOL-USD", "min_size": 0.1}
        ]
    
    def get_size_decimals(self, symbol: str) -> int:
        """
        Récupère le nombre de décimales pour la taille d'un symbole sur Extended
        
        Args:
            symbol: Symbole (ex: "ETH", "BTC", "ZORA")
            
        Returns:
            Nombre de décimales (int), ex: 5 pour ZORA, 3 pour ETH
        """
        if not self.trading_client:
            return 4  # Défaut
        
        try:
            # Charger les marchés si pas déjà fait
            if not self.markets_cache:
                self.get_markets()
            
            # Trouver le marché
            market_name = None
            for name in self.markets_cache.keys():
                if symbol.upper() in name:
                    market_name = name
                    break
            
            if not market_name:
                logger.warning(f"Market {symbol} not found on Extended, using default 4 decimals")
                return 4
            
            market = self.markets_cache[market_name]
            # Extended a step_size dans trading_config
            # Par exemple step_size = 0.001 → 3 decimals, 0.00001 → 5 decimals
            step_size = float(market.trading_config.step_size)
            decimals = len(str(step_size).split('.')[-1].rstrip('0'))
            
            logger.info(f"   Extended {symbol}: {decimals} decimals (step_size={step_size})")
            return decimals
            
        except Exception as e:
            logger.error(f"Error getting Extended decimals for {symbol}: {e}")
            return 4  # Défaut

    def get_max_leverage(self, symbol: str) -> int:
        """
        Récupère le levier maximum pour un symbole sur Extended
        
        Args:
            symbol: Symbole (ex: "ETH", "BTC")
            
        Returns:
            Max leverage (int), ex: 10, 3, 20
        """
        if not self.trading_client:
            return 10  # Défaut conservateur
        
        try:
            # Charger les marchés si pas déjà fait
            if not self.markets_cache:
                self.get_markets()
            
            # Trouver le marché
            market_name = None
            for name in self.markets_cache.keys():
                if symbol.upper() in name:
                    market_name = name
                    break
            
            if not market_name:
                logger.warning(f"Market {symbol} not found on Extended, using default leverage 10x")
                return 10
            
            market = self.markets_cache[market_name]
            max_lev = float(market.trading_config.max_leverage)
            
            logger.info(f"   Extended {symbol}: max leverage {max_lev}x")
            return int(max_lev)
            
        except Exception as e:
            logger.error(f"Error getting Extended max leverage for {symbol}: {e}")
            return 10  # Défaut conservateur
    
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """
        Configure le levier pour un symbole sur Extended
        
        Args:
            symbol: Symbole (ex: "ETH", "BTC", "ZORA")
            leverage: Levier désiré (ex: 3, 5, 10)
            
        Returns:
            True si succès, False sinon
        """
        if not self.trading_client:
            logger.error("Trading client not available - cannot set leverage")
            return False
        
        try:
            from decimal import Decimal
            
            # Charger les marchés si pas déjà fait
            if not self.markets_cache:
                self.get_markets()
            
            # Trouver le nom du marché
            market_name = None
            for name in self.markets_cache.keys():
                if symbol.upper() in name:
                    market_name = name
                    break
            
            if not market_name:
                logger.error(f"Market {symbol} not found for set_leverage")
                return False
            
            # Update leverage via SDK (async)
            async def update_lev_async():
                result = await self.trading_client.account.update_leverage(
                    market_name=market_name,
                    leverage=Decimal(str(leverage))
                )
                return result
            
            loop = self.get_event_loop()
            result = loop.run_until_complete(update_lev_async())
            
            if result and result.status == "OK":
                logger.success(f"✅ Extended leverage set to {leverage}x for {symbol}")
                return True
            else:
                logger.error(f"Failed to set Extended leverage: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error setting Extended leverage for {symbol}: {e}")
            return False

    def round_price(self, symbol: str, price: float) -> float:
        """
        Arrondit un prix selon les règles du marché Extended (tick size)
        
        Args:
            symbol: Symbole (ex: "ETH", "BTC", "ZORA")
            price: Prix à arrondir
            
        Returns:
            Prix arrondi selon le tick_size du marché
        """
        if not self.trading_client:
            return round(price, 2)  # Fallback: 2 decimals
        
        try:
            # Charger les marchés si pas déjà fait
            if not self.markets_cache:
                self.get_markets()
            
            # Trouver le marché
            market_name = None
            for name in self.markets_cache.keys():
                if symbol.upper() in name:
                    market_name = name
                    break
            
            if not market_name:
                logger.warning(f"Market {symbol} not found, using default rounding")
                return round(price, 2)
            
            market = self.markets_cache[market_name]
            rounded = market.trading_config.round_price(Decimal(str(price)))
            return float(rounded)
            
        except Exception as e:
            logger.error(f"Error rounding price for {symbol}: {e}")
            return round(price, 2)

    def get_min_order_size(self, symbol: str) -> float:
        """
        Récupère la taille minimale d'ordre pour un symbole sur Extended
        
        Args:
            symbol: Symbole (ex: "ETH", "BTC", "ZORA")
            
        Returns:
            Taille minimale (float)
        """
        if not self.trading_client:
            return 0.01  # Fallback
        
        try:
            # Charger les marchés si pas déjà fait
            if not self.markets_cache:
                self.get_markets()
            
            # Trouver le marché
            market_name = None
            for name in self.markets_cache.keys():
                if symbol.upper() in name:
                    market_name = name
                    break
            
            if not market_name:
                logger.warning(f"Market {symbol} not found, using default min size")
                return 0.01
            
            market = self.markets_cache[market_name]
            min_size = float(market.trading_config.min_order_size)
            
            logger.info(f"   Extended {symbol}: min order size = {min_size}")
            return min_size
            
        except Exception as e:
            logger.error(f"Error getting min order size for {symbol}: {e}")
            return 0.01

    def get_ticker(self, symbol: str) -> Dict:
        """
        Récupère les prix bid/ask pour un symbole en temps réel via WebSocket orderbook
        
        Returns:
            {"bid": float, "ask": float, "last": float}
        """
        if not self.trading_client:
            return self._simulate_ticker(symbol)
        
        try:
            # Charger les marchés si pas déjà fait (pour trouver le nom du marché)
            if not self.markets_cache:
                self.get_markets()
            
            # Trouver le nom du marché
            market_name = None
            for name in self.markets_cache.keys():
                if symbol.upper() in name:
                    market_name = name
                    break
            
            if not market_name:
                logger.warning(f"Market {symbol} not found, using simulation")
                return self._simulate_ticker(symbol)
            
            # Démarrer le WebSocket si pas déjà connecté
            if not self.ws_connected:
                self._start_orderbook_websocket(market_name)
                # Attendre un peu pour recevoir le premier SNAPSHOT
                time.sleep(1)
            
            # Attendre jusqu'à recevoir des données du WebSocket (max 5 secondes)
            max_wait = 5
            wait_start = time.time()
            while not (market_name in self.orderbook_cache and 
                      time.time() - self.orderbook_cache[market_name]['last_update'] < 10):
                if time.time() - wait_start > max_wait:
                    break
                time.sleep(0.1)
            
            # Vérifier si on a des données du WebSocket
            if market_name in self.orderbook_cache:
                cache_data = self.orderbook_cache[market_name]
                if time.time() - cache_data['last_update'] < 10:  # Données récentes (< 10s)
                    mid_price = (cache_data['bid'] + cache_data['ask']) / 2
                    return {
                        "bid": cache_data['bid'],
                        "ask": cache_data['ask'],
                        "last": mid_price
                    }
            
            # Fallback sur le cache des marchés si WebSocket pas encore prêt
            if market_name in self.markets_cache:
                market = self.markets_cache[market_name]
                return {
                    "bid": float(market.market_stats.bid_price),
                    "ask": float(market.market_stats.ask_price),
                    "last": float(market.market_stats.last_price)
                }
            
            return self._simulate_ticker(symbol)
        except Exception as e:
            logger.error(f"Error fetching Extended ticker {symbol}: {e}")
            # Fallback sur le cache en cas d'erreur
            try:
                if self.markets_cache and market_name:
                    market = self.markets_cache[market_name]
                    return {
                        "bid": float(market.market_stats.bid_price),
                        "ask": float(market.market_stats.ask_price),
                        "last": float(market.market_stats.last_price)
                    }
            except:
                pass
            return self._simulate_ticker(symbol)
    
    def get_orderbook(self, symbol: str, depth: int = 20) -> Dict:
        """
        Récupère l'orderbook real-time pour un symbole
        
        Args:
            symbol: Symbole (ex: "ZORA", "ETH")
            depth: Nombre de niveaux de prix (default 20)
            
        Returns:
            {"bids": [[price, size], ...], "asks": [[price, size], ...]}
        """
        if not self.trading_client:
            # Simulation
            ticker = self._simulate_ticker(symbol)
            return {
                "bids": [[ticker['bid'], 1000.0]],
                "asks": [[ticker['ask'], 1000.0]]
            }
        
        try:
            # Charger les marchés si pas déjà fait
            if not self.markets_cache:
                self.get_markets()
            
            # Trouver le nom du marché
            market_name = None
            for name in self.markets_cache.keys():
                if symbol.upper() in name:
                    market_name = name
                    break
            
            if not market_name:
                logger.warning(f"Market {symbol} not found for orderbook")
                return {"bids": [], "asks": []}
            
            # Récupérer l'orderbook via le SDK
            from x10.perpetual.orders import OrderSide
            
            orderbook = self.trading_client.get_orderbook(market_name, depth=depth)
            
            # Parser les bids et asks
            bids = []
            asks = []
            
            if hasattr(orderbook, 'bids'):
                for level in orderbook.bids:
                    bids.append([float(level.price), float(level.size)])
            
            if hasattr(orderbook, 'asks'):
                for level in orderbook.asks:
                    asks.append([float(level.price), float(level.size)])
            
            return {
                "bids": bids,  # Sorted descending (highest bid first)
                "asks": asks   # Sorted ascending (lowest ask first)
            }
            
        except Exception as e:
            logger.error(f"Error fetching Extended orderbook {symbol}: {e}")
            # Fallback sur ticker
            ticker = self.get_ticker(symbol)
            return {
                "bids": [[ticker['bid'], 1000.0]],
                "asks": [[ticker['ask'], 1000.0]]
            }
    
    def _simulate_ticker(self, symbol: str) -> Dict:
        """Simulation de ticker pour tests"""
        prices = {
            "BTC": 43000.0,
            "ETH": 3130.0,
            "SOL": 110.0
        }
        mid = prices.get(symbol, 100.0)
        spread = mid * 0.001
        
        return {
            "bid": mid - spread/2,
            "ask": mid + spread/2,
            "last": mid
        }

    def place_order(self, symbol: str, side: str, size: float, price: float = None,
                   order_type: str = "limit", reduce_only: bool = False, post_only: bool = False) -> Dict:
        """
        Place un ordre sur Extended avec le SDK officiel
        
        Args:
            symbol: Symbole (BTC, ETH, SOL...)
            side: "buy" ou "sell"
            size: Taille en unités de l'asset
            price: Prix limite (None pour market order)
            order_type: "limit" ou "market"
            reduce_only: True pour close only
            post_only: True pour ordres maker uniquement (rejette si taker)
        
        Returns:
            Dict avec order_id et status
        """
        if not self.trading_client:
            logger.warning(f"⚠️ Extended SDK not available - simulating order")
            return {
                "order_id": None,
                "status": "simulated",
                "symbol": symbol,
                "side": side,
                "size": size,
                "price": price
            }
        
        try:
            # Charger les marchés si pas déjà fait
            if not self.markets_cache:
                self.get_markets()
            
            # Trouver le nom du marché
            market_name = None
            for name, market in self.markets_cache.items():
                if symbol.upper() in name:
                    market_name = name
                    break
            
            if not market_name:
                logger.error(f"Market {symbol} not found on Extended")
                return {
                    "order_id": None,
                    "status": "error",
                    "error": f"Market {symbol} not found",
                    "symbol": symbol
                }
            
            market = self.markets_cache[market_name]
            
            # Pour MARKET order, récupérer le prix du ticker si non fourni
            if order_type == "market" and price is None:
                # Récupérer le mark price pour rester proche (Extended calcule le coût en fonction de l'écart au mark)
                # Extended rejette les ordres si order_cost dépasse la balance
                # order_cost augmente avec l'écart entre order_price et mark_price
                mark_price_data = self.get_mark_price(symbol)
                mark_price = float(mark_price_data) if mark_price_data else None
                
                ticker = self.get_ticker(symbol)
                
                # Utiliser mark price ± 0.5% pour minimiser l'order cost tout en garantissant l'exécution
                # ⚠️ Plus on s'éloigne du mark, plus l'order cost augmente (peut doubler!)
                # Réduction de 1% à 0.5% pour avoir un order cost plus bas
                if side == "buy":
                    if mark_price:
                        price = mark_price * 1.005  # +0.5% du mark price (réduit de 1%)
                        logger.info(f"   Market BUY: using mark + 0.5% = ${price:.2f} (mark=${mark_price:.2f})")
                    elif ticker and ticker.get('ask'):
                        price = ticker['ask'] * 1.005  # Fallback: ask + 0.5%
                        logger.info(f"   Market BUY: using ask + 0.5% = ${price:.2f}")
                    else:
                        logger.error(f"   Cannot get price for MARKET BUY order - mark_price={mark_price}, ticker={ticker}")
                        return {
                            "order_id": None,
                            "status": "error",
                            "error": "Cannot determine market price for BUY order",
                            "symbol": symbol,
                            "side": side,
                            "size": size
                        }
                else:
                    if mark_price:
                        price = mark_price * 0.995  # -0.5% du mark price (réduit de 1%)
                        logger.info(f"   Market SELL: using mark - 0.5% = ${price:.2f} (mark=${mark_price:.2f})")
                    elif ticker and ticker.get('bid'):
                        price = ticker['bid'] * 0.995  # Fallback: bid - 0.5%
                        logger.info(f"   Market SELL: using bid - 0.5% = ${price:.2f}")
                    else:
                        logger.error(f"   Cannot get price for MARKET SELL order - mark_price={mark_price}, ticker={ticker}")
                        return {
                            "order_id": None,
                            "status": "error",
                            "error": "Cannot determine market price for SELL order",
                            "symbol": symbol,
                            "side": side,
                            "size": size
                        }
            elif order_type == "limit" and price is None:
                # Pour LIMIT MAKER, utiliser le prix du côté MAKER
                # 🎯 STRATÉGIE MAKER: mid price ±0.005% pour fill rapide en restant maker
                # D'après le bot Next.js: prix proche du mid, ajusté de ±0.005%
                # Si pas de fill → retry avec offset plus grand (géré par le bot)
                ticker = self.get_ticker(symbol)
                if not ticker or 'bid' not in ticker or 'ask' not in ticker:
                    logger.error(f"Cannot get ticker for LIMIT order on {symbol} - ticker={ticker}")
                    return {
                        "order_id": None,
                        "status": "error",
                        "error": "Cannot get ticker for LIMIT order",
                        "symbol": symbol,
                        "side": side,
                        "size": size
                    }
                
                bid = ticker['bid']
                ask = ticker['ask']
                mid = (bid + ask) / 2
                
                if side == "buy":
                    # LONG = mid - 0.005% (légèrement en dessous pour MAKER)
                    price = mid * 0.99995
                    logger.info(f"   Limit MAKER BUY: mid - 0.005% = ${price:.2f} (bid: ${bid:.2f}, ask: ${ask:.2f})")
                else:
                    # SHORT = mid + 0.005% (légèrement au-dessus pour MAKER)
                    price = mid * 1.00005
                    logger.info(f"   Limit MAKER SELL: mid + 0.005% = ${price:.2f} (bid: ${bid:.2f}, ask: ${ask:.2f})")
            
            # Convertir side en OrderSide
            order_side = OrderSide.BUY if side.upper() == "BUY" else OrderSide.SELL
            
            # Arrondir la taille selon les règles du marché (IMPORTANT !)
            rounded_size = market.trading_config.round_order_size(Decimal(str(size)))
            
            # Vérifier que la taille est >= min_order_size
            # ⚠️ NE PAS forcer le minimum si insuffisant, laisser l'API rejeter
            if rounded_size < market.trading_config.min_order_size:
                logger.error(f"Size {rounded_size} < min {market.trading_config.min_order_size} - insuffisant pour trader")
                return {
                    "order_id": None,
                    "status": "error",
                    "error": f"Size {rounded_size} below minimum {market.trading_config.min_order_size}",
                    "symbol": symbol,
                    "side": side,
                    "size": size,
                    "price": price
                }
            
            # Arrondir le prix selon les règles du marché
            # Vérifier que price n'est pas None avant conversion
            if price is None:
                logger.error(f"Price is None for {order_type} order on {symbol}")
                return {
                    "order_id": None,
                    "status": "error",
                    "error": "Price is None",
                    "symbol": symbol,
                    "side": side,
                    "size": size,
                    "order_type": order_type
                }
            
            try:
                rounded_price = market.trading_config.round_price(Decimal(str(price)))
            except (ValueError, decimal.InvalidOperation) as e:
                logger.error(f"Invalid price value: {price} (type: {type(price)}) - {e}")
                return {
                    "order_id": None,
                    "status": "error",
                    "error": f"Invalid price value: {price}",
                    "symbol": symbol,
                    "side": side,
                    "size": size,
                    "price": price
                }
            
            # 🎯 MAKER vs TAKER
            # LIMIT avec post_only=True = MAKER (ajoute liquidité, frais réduits)
            # MARKET avec IOC = TAKER (prend liquidité, frais plus élevés)
            if order_type.lower() == "limit":
                time_in_force = TimeInForce.GTT
                # Utiliser le paramètre post_only passé à la fonction
                # (par défaut False, mais peut être forcé à True pour maker)
                if not post_only:
                    logger.info(f"   📗 LIMIT order")
                else:
                    logger.info(f"   📗 MAKER order (post_only=True)")
            else:  # market
                time_in_force = TimeInForce.IOC
                post_only = False  # TAKER - exécution immédiate
                logger.info(f"   📕 TAKER order (IOC)")
            
            logger.info(f"Placing order: {market_name} {side.upper()} {rounded_size} @ {rounded_price}")
            
            # Créer l'objet order avec signature Starknet
            async def place_order_async():
                order_obj = create_order_object(
                    account=self.stark_account,
                    starknet_domain=MAINNET_CONFIG.starknet_domain,
                    market=market,
                    side=order_side,
                    amount_of_synthetic=rounded_size,
                    price=rounded_price,
                    time_in_force=time_in_force,
                    reduce_only=reduce_only,
                    post_only=post_only  # 🔥 Utiliser la variable
                )
                
                # Placer l'ordre (sans attendre la confirmation WebSocket)
                result = await self.trading_client.orders.place_order(order=order_obj)
                return result
            
            # Exécuter avec loop réutilisable
            loop = self.get_event_loop()
            result = loop.run_until_complete(place_order_async())
            
            logger.success(f"✅ Order placed: {result.to_pretty_json()}")
            
            return {
                "order_id": result.data.id if result.data else None,
                "status": result.status if isinstance(result.status, str) else result.status.value,
                "symbol": symbol,
                "side": side,
                "size": float(rounded_size),
                "price": float(rounded_price),
                "raw": result
            }
            
        except TimeoutError:
            logger.warning(f"⚠️ Extended order timeout - order likely placed: {symbol} {side} {size}")
            # L'ordre est probablement placé même avec timeout
            return {
                "order_id": "pending",
                "status": "timeout",
                "symbol": symbol,
                "side": side,
                "size": float(rounded_size) if 'rounded_size' in locals() else size,
                "price": float(rounded_price) if 'rounded_price' in locals() else price,
                "note": "Order placed but confirmation timeout - check Extended UI"
            }
        except ValueError as e:
            # Erreur HTTP de l'API (comme "same side" 1138)
            error_str = str(e)
            # Ne pas logger l'erreur complète si c'est une erreur "same side" qui sera gérée
            if '1138' in error_str or 'same side' in error_str.lower():
                logger.debug(f"Extended order error (will be handled): {error_str}")
            else:
                logger.error(f"Extended order failed: {error_str}")
            return {
                "order_id": None,
                "status": "error",
                "error": error_str,
                "symbol": symbol,
                "side": side,
                "size": size,
                "price": price
            }
        except Exception as e:
            logger.error(f"Extended order failed: {type(e).__name__}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "order_id": None,
                "status": "error",
                "error": str(e),
                "symbol": symbol,
                "side": side,
                "size": size,
                "price": price
            }

    def get_positions(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Récupère les positions ouvertes
        Utilise d'abord le cache WebSocket, puis l'API REST en fallback
        
        Args:
            symbol: Optionnel, filtre par symbole (ex: "BTC")
        """
        # Essayer d'abord le cache WebSocket (plus rapide et temps réel)
        # Mais si les données sont trop anciennes (> 2 secondes), utiliser l'API REST pour des données plus fraîches
        # Le PnL change en temps réel avec le prix, donc on a besoin de données très fraîches
        if self.ws_account_connected and self.positions_cache:
            positions = []
            cache_too_old = False
            for market, pos_data in self.positions_cache.items():
                # Filtrer par symbole si spécifié
                if symbol and pos_data.get('symbol') != symbol.upper():
                    continue
                    
                last_update = pos_data.get('last_update', 0)
                # Vérifier que les données sont récentes (< 60 secondes pour existence, < 2 secondes pour fraîcheur)
                if time.time() - last_update < 60:
                    positions.append(pos_data.copy())
                    # Si une position est trop ancienne (> 2 secondes), on va utiliser l'API REST pour PnL frais
                    if time.time() - last_update > 2:
                        cache_too_old = True
            
            if positions and not cache_too_old:
                logger.debug(f"Positions Extended depuis cache WebSocket: {len(positions)} positions")
                return positions
            elif cache_too_old:
                logger.debug("Cache WebSocket Extended trop ancien (>2s), utilisation de l'API REST pour PnL frais")
        
        # Fallback sur API REST
        if not self.trading_client:
            return []
        
        try:
            positions = self.get_event_loop().run_until_complete(self.trading_client.account.get_positions())
            result = []
            for pos in positions.data:
                if float(pos.size) != 0:
                    # pos.market est le nom complet (ex: "ETH-USD")
                    pos_symbol = pos.market.replace("-USD", "")
                    
                    # Filtrer par symbole si spécifié
                    if symbol and pos_symbol != symbol.upper():
                        continue
                    
                    result.append({
                        "symbol": pos_symbol,
                        "market": pos.market,
                        "side": "LONG" if float(pos.size) > 0 else "SHORT",
                        "size": abs(float(pos.size)),
                        "size_signed": float(pos.size),
                        "entry_price": float(pos.open_price),
                        "unrealized_pnl": float(pos.unrealised_pnl)
                    })
            return result
        except Exception as e:
            logger.error(f"Error fetching Extended positions: {e}")
            return []

    # DEPRECATED: Méthode cassée - utiliser get_order_by_id() à la place
    # def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
    #     """
    #     ⚠️ CASSÉ: trading_client._client n'existe pas
    #     Utiliser get_order_by_id() pour vérifier un ordre spécifique à la place
    #     """
    #     logger.warning("get_open_orders() est cassée - utiliser get_order_by_id() à la place")
    #     return []
    
    def get_order_by_id(self, order_id: int) -> Optional[Dict]:
        """
        Récupère un ordre par son ID Extended
        GET /api/v1/user/orders/{id}
        
        Args:
            order_id: L'ID numérique de l'ordre (assigné par Extended)
            
        Returns:
            Dict avec {status: 'OK', data: {id, status, type, side, price, filledQty, ...}}
            Status possible: NEW, PARTIALLY_FILLED, FILLED, REJECTED, CANCELLED, UNTRIGGERED, EXPIRED
        """
        if not self.trading_client:
            return None
        
        try:
            # Utiliser requests directement au lieu du SDK
            import requests
            
            response = requests.get(
                f"{self.rest_url}/v1/user/orders/{order_id}",
                headers=self.headers,
                timeout=5
            )
            response.raise_for_status()
            result = response.json()
            
            if not result or result.get('status') != 'OK':
                logger.debug(f"Order {order_id} not found or error: {result}")
                return None
            
            return result
            
        except Exception as e:
            logger.debug(f"Error fetching order {order_id}: {e}")
            return None
    
    def get_order_status(self, order_id: int) -> Optional[Dict]:
        """
        Check le statut d'un ordre spécifique par ID (legacy method)
        
        Args:
            order_id: L'ID de l'ordre
            
        Returns:
            Dict avec {status, filled_size, ...} ou None si erreur
        """
        order_data = self.get_order_by_id(order_id)
        if not order_data:
            return None
        
        try:
            data = order_data.get('data', {})
            return {
                'status': data.get('status'),
                'filled_size': float(data.get('filledQty', 0)),
                'total_size': float(data.get('qty', 0)),
                'average_price': float(data.get('averagePrice', 0)) if data.get('averagePrice') else None
            }
        except Exception as e:
            logger.debug(f"Error parsing order status: {e}")
            return None

    def get_balance(self) -> Dict:
        """Récupère le solde du compte"""
        if not self.trading_client:
            return {"total": 0, "available": 0}
        
        try:
            balance = self.get_event_loop().run_until_complete(self.trading_client.account.get_balance())
            
            if not balance or not balance.data:
                return {"total": 0, "available": 0}
            
            balance_data = balance.data
            
            # Essayer différents attributs possibles selon la version du SDK
            # Equity (valeur totale du compte)
            equity = 0.0
            if hasattr(balance_data, 'equity'):
                equity = float(balance_data.equity)
            elif hasattr(balance_data, 'total'):
                equity = float(balance_data.total)
            elif hasattr(balance_data, 'total_equity'):
                equity = float(balance_data.total_equity)
            
            # Available balance (solde disponible pour trading)
            available = 0.0
            if hasattr(balance_data, 'available_for_withdrawal'):
                available = float(balance_data.available_for_withdrawal)
            elif hasattr(balance_data, 'available_balance'):
                available = float(balance_data.available_balance)
            elif hasattr(balance_data, 'available_for_trade'):
                available = float(balance_data.available_for_trade)
            elif hasattr(balance_data, 'available'):
                available = float(balance_data.available)
            elif hasattr(balance_data, 'balance'):
                available = float(balance_data.balance)
            elif hasattr(balance_data, 'collateral_balance'):
                available = float(balance_data.collateral_balance)
            
            # Si equity est 0 mais available existe, utiliser available comme total
            if equity == 0 and available > 0:
                equity = available
            
            # Si tout est 0, essayer d'utiliser directement les valeurs brutes
            if equity == 0 and available == 0:
                # Essayer de convertir l'objet en dict ou accéder aux valeurs directement
                try:
                    if hasattr(balance_data, '__dict__'):
                        data_dict = balance_data.__dict__
                        logger.debug(f"BalanceModel __dict__: {data_dict}")
                        if 'equity' in data_dict:
                            equity = float(data_dict['equity'])
                        if 'available_for_withdrawal' in data_dict:
                            available = float(data_dict['available_for_withdrawal'])
                        elif 'available_balance' in data_dict:
                            available = float(data_dict['available_balance'])
                except Exception as e:
                    logger.debug(f"Error accessing __dict__: {e}")
            
            return {
                "total": equity,
                "available": available,
                "currency": "USDC"
            }
        except AttributeError as e:
            # Erreur spécifique pour les attributs manquants
            logger.error(f"Error fetching Extended balance - attribut manquant: {e}")
            # Essayer de récupérer l'objet pour afficher les attributs disponibles
            try:
                balance = self.get_event_loop().run_until_complete(self.trading_client.account.get_balance())
                if balance and balance.data:
                    attrs = [attr for attr in dir(balance.data) if not attr.startswith('_')]
                    logger.error(f"BalanceModel attributes disponibles: {attrs}")
                    # Essayer d'afficher __dict__ si disponible
                    if hasattr(balance.data, '__dict__'):
                        logger.error(f"BalanceModel __dict__: {balance.data.__dict__}")
                    # Essayer d'afficher via vars() aussi
                    try:
                        logger.error(f"BalanceModel vars(): {vars(balance.data)}")
                    except:
                        pass
            except Exception as e2:
                logger.debug(f"Impossible d'afficher les attributs: {e2}")
            import traceback
            logger.debug(traceback.format_exc())
            return {"total": 0, "available": 0}
        except Exception as e:
            logger.error(f"Error fetching Extended balance: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return {"total": 0, "available": 0}

    def cancel_order(self, order_id: str) -> bool:
        """
        Annule un ordre par son ID Extended (numérique)
        
        Args:
            order_id: ID numérique assigné par Extended (pas external_id)
        """
        if not self.trading_client:
            return False
        
        try:
            # Convertir l'ID en int si c'est une string
            if isinstance(order_id, str):
                try:
                    order_id_int = int(order_id)
                except ValueError:
                    logger.error(f"Invalid order_id format: {order_id}")
                    return False
            else:
                order_id_int = order_id
            
            # Le SDK utilise cancel_order avec l'ID numérique
            result = self.get_event_loop().run_until_complete(
                self.trading_client.orders.cancel_order(order_id=order_id_int)
            )
            
            # result.status peut être un string ou un enum
            if isinstance(result.status, str):
                success = result.status == "OK"
            else:
                success = result.status.value == "OK"
            
            if success:
                logger.success(f"✅ Ordre Extended {order_id_int} annulé")
            else:
                logger.warning(f"⚠️  Annulation Extended {order_id_int} échouée: {result.status}")
            
            return success
                
        except Exception as e:
            logger.error(f"Error cancelling Extended order: {e}")
            return False

    def get_funding_rate(self, symbol: str) -> float:
        """Récupère le taux de funding actuel"""
        if not self.trading_client:
            return 0.0
        
        try:
            # Charger les marchés si pas déjà fait
            if not self.markets_cache:
                self.get_markets()
            
            # Trouver le nom du marché
            market_name = None
            for name in self.markets_cache.keys():
                if symbol.upper() in name:
                    market_name = name
                    break
            
            if not market_name:
                return 0.0
            
            market = self.markets_cache[market_name]
            return float(market.market_stats.funding_rate)
        except Exception as e:
            logger.error(f"Error fetching Extended funding rate: {e}")
            return 0.0
    
    def get_mark_price(self, symbol: str) -> Optional[float]:
        """
        Récupère le mark price pour un symbole depuis l'API REST
        
        Args:
            symbol: Symbole (ex: "BTC")
            
        Returns:
            Mark price ou None si non disponible
        """
        if not self.trading_client:
            return None
        
        try:
            # Forcer le rechargement des marchés pour avoir le mark_price le plus récent
            markets_dict = self.get_event_loop().run_until_complete(self.trading_client.markets_info.get_markets_dict())
            self.markets_cache = markets_dict
            
            # Trouver le nom du marché
            market_name = None
            for name in self.markets_cache.keys():
                if symbol.upper() in name:
                    market_name = name
                    break
            
            if not market_name:
                logger.warning(f"Market {symbol} not found on Extended")
                return None
            
            market = self.markets_cache[market_name]
            mark_price = float(market.market_stats.mark_price)
            logger.debug(f"Extended mark price for {symbol}: ${mark_price:.2f}")
            return mark_price
        except Exception as e:
            logger.error(f"Error fetching Extended mark price: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def get_all_funding_rates(self) -> Dict[str, Dict]:
        """Récupère tous les funding rates"""
        if not self.trading_client:
            return {}
        
        try:
            # Charger les marchés si pas déjà fait
            if not self.markets_cache:
                self.get_markets()
            
            rates = {}
            for market_name, market in self.markets_cache.items():
                # Extraire le symbole (ex: "ETH-USD" -> "ETH")
                symbol = market_name.split('-')[0]
                rates[symbol] = {
                    'rate': float(market.market_stats.funding_rate),
                    'next_funding': None  # Extended n'a pas de next_funding timestamp
                }
            
            return rates
        except Exception as e:
            logger.error(f"Error fetching all Extended funding rates: {e}")
            return {}
    
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
            ws_url = f"wss://api.starknet.extended.exchange/stream.extended.exchange/v1/orderbooks/{market_name}"
            
            logger.info(f"🔌 Connexion WebSocket orderbook pour {market_name}...")
            
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    msg_type = data.get('type')
                    orderbook_data = data.get('data', {})
                    
                    if msg_type in ['SNAPSHOT', 'DELTA']:
                        market = orderbook_data.get('m')
                        if not market:
                            return
                        
                        # Initialiser l'état de l'orderbook si nécessaire
                        if market not in self.orderbook_state:
                            self.orderbook_state[market] = {"bids": {}, "asks": {}}
                        
                        state = self.orderbook_state[market]
                        
                        # Traiter les bids
                        bids = orderbook_data.get('b', [])
                        for bid in bids:
                            try:
                                price = float(bid['p'])
                                qty = float(bid['q'])
                                
                                if msg_type == 'SNAPSHOT':
                                    # SNAPSHOT: quantité absolue
                                    if qty > 0:
                                        state['bids'][price] = qty
                                    else:
                                        state['bids'].pop(price, None)
                                else:  # DELTA
                                    # DELTA: quantité négative = suppression, positive = ajout/modification
                                    if qty <= 0:
                                        state['bids'].pop(price, None)
                                    else:
                                        state['bids'][price] = qty
                            except (KeyError, ValueError) as e:
                                logger.debug(f"Erreur traitement bid: {e}")
                                continue
                        
                        # Traiter les asks
                        asks = orderbook_data.get('a', [])
                        for ask in asks:
                            try:
                                price = float(ask['p'])
                                qty = float(ask['q'])
                                
                                if msg_type == 'SNAPSHOT':
                                    # SNAPSHOT: quantité absolue
                                    if qty > 0:
                                        state['asks'][price] = qty
                                    else:
                                        state['asks'].pop(price, None)
                                else:  # DELTA
                                    # DELTA: quantité négative = suppression, positive = ajout/modification
                                    if qty <= 0:
                                        state['asks'].pop(price, None)
                                    else:
                                        state['asks'][price] = qty
                            except (KeyError, ValueError) as e:
                                logger.debug(f"Erreur traitement ask: {e}")
                                continue
                        
                        # Extraire le meilleur bid (prix le plus élevé) et ask (prix le plus bas)
                        if state['bids'] and state['asks']:
                            best_bid = max(state['bids'].keys())
                            best_ask = min(state['asks'].keys())
                            
                            # VALIDATION CRITIQUE: Vérifier que bid < ask
                            if best_bid >= best_ask:
                                logger.warning(f"⚠️  Orderbook Extended {market} INVALIDE: bid={best_bid:.2f} >= ask={best_ask:.2f}")
                                logger.warning(f"   État: {len(state['bids'])} bids, {len(state['asks'])} asks")
                            else:
                                # Orderbook valide, mettre à jour le cache
                                self.orderbook_cache[market] = {
                                    "bid": best_bid,
                                    "ask": best_ask,
                                    "last_update": time.time()
                                }
                                # Log retiré pour réduire la verbosité
                                # logger.debug(f"✅ Orderbook Extended {market}: bid={best_bid:.2f}, ask={best_ask:.2f}")
                except Exception as e:
                    logger.error(f"Erreur traitement message WebSocket: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
            
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
    
    def ws_account(self) -> bool:
        """
        Se connecte au WebSocket account pour récupérer les positions en temps réel
        Documentation: https://api-docs.extended.exchange/websocket#account-updates-stream
        
        Returns:
            True si la connexion est établie
        """
        if not self.api_key:
            logger.error("API key required for Extended account WebSocket")
            return False
        
        if self.ws_account_connected:
            logger.info("WebSocket account Extended déjà connecté")
            return True
        
        try:
            ws_url = "wss://api.starknet.extended.exchange/stream.extended.exchange/v1/account"
            
            logger.info("🔌 Connexion WebSocket account Extended pour les positions...")
            
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    msg_type = data.get('type')
                    
                    # Gérer les pings du serveur (toutes les 15 secondes)
                    if msg_type == 'ping':
                        ws.send(json.dumps({"type": "pong"}))
                        return
                    
                    # Gérer les positions
                    if msg_type == 'POSITION':
                        positions_data = data.get('data', {}).get('positions', [])
                        
                        # S'assurer que positions_cache est initialisé (peut être None temporairement)
                        if self.positions_cache is None:
                            self.positions_cache = {}
                        
                        for pos in positions_data:
                            market = pos.get('market', '')
                            size = float(pos.get('size', '0'))
                            
                            # Si size = 0, retirer du cache
                            if abs(size) < 0.0001:
                                if self.positions_cache and market in self.positions_cache:
                                    del self.positions_cache[market]
                                continue
                            
                            # Extraire le symbole (ex: "BTC-USD" -> "BTC")
                            symbol = market.replace("-USD", "")
                            
                            side = pos.get('side', 'UNKNOWN')
                            # Calculer size_signed: positif pour LONG, négatif pour SHORT
                            size_signed = size if side == 'LONG' else -size
                            
                            self.positions_cache[market] = {
                                'symbol': symbol,
                                'market': market,
                                'side': side,
                                'size': abs(size),
                                'size_signed': size_signed,
                                'entry_price': float(pos.get('openPrice', '0')),  # Harmoniser avec REST API
                                'open_price': float(pos.get('openPrice', '0')),  # Garder pour compatibilité
                                'mark_price': float(pos.get('markPrice', '0')),
                                'unrealized_pnl': float(pos.get('unrealisedPnl', '0')),  # Harmoniser avec REST API
                                'unrealised_pnl': float(pos.get('unrealisedPnl', '0')),  # Garder pour compatibilité
                                'realised_pnl': float(pos.get('realisedPnl', '0')),
                                'leverage': float(pos.get('leverage', '0')),
                                'margin': float(pos.get('margin', '0')),
                                'liquidation_price': float(pos.get('liquidationPrice', '0')),
                                'last_update': time.time()
                            }
                            logger.debug(f"Position Extended mise à jour: {symbol} {side} {abs(size)}")
                    
                    # Gérer les mises à jour d'ordres
                    if msg_type == 'ORDER':
                        orders_data = data.get('data', {}).get('orders', [])
                        # Stocker les mises à jour d'ordres
                        if orders_data:
                            self.orders_cache = orders_data
                            for order in orders_data:
                                logger.debug(f"Ordre Extended mis à jour: ID={order.get('id')}, Status={order.get('status')}")
                    
                except Exception as e:
                    logger.error(f"Error processing Extended account WebSocket message: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
            
            def on_error(ws, error):
                error_str = str(error)
                if '403' in error_str or 'Forbidden' in error_str:
                    logger.warning(f"WebSocket account Extended 403 Forbidden - vérifier l'API key")
                else:
                    logger.error(f"WebSocket account Extended error: {error}")
                self.ws_account_connected = False
            
            def on_close(ws, close_status_code, close_msg):
                if close_status_code != 1000:
                    logger.warning(f"WebSocket account Extended fermé: {close_status_code} - {close_msg}")
                self.ws_account_connected = False
                # Tentative de reconnexion automatique après 5 secondes
                if close_status_code != 1000:  # Pas une fermeture normale
                    logger.info("Tentative de reconnexion automatique dans 5 secondes...")
                    time.sleep(5)
                    try:
                        self.ws_account()
                    except:
                        pass
            
            def on_open(ws):
                logger.success("✅ WebSocket account Extended connecté")
                self.ws_account_connected = True
            
            def run_websocket():
                headers = [
                    f"X-Api-Key: {self.api_key}",
                    "User-Agent: X10PythonTradingClient/0.0.17"
                ]
                
                self.ws_account_app = websocket.WebSocketApp(
                    ws_url,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close,
                    on_open=on_open,
                    header=headers
                )
                
                # Le serveur envoie des pings toutes les 15s, on répond avec pong dans on_message
                # Pas besoin d'envoyer des pings nous-mêmes
                
                self.ws_account_app.run_forever()
            
            self.ws_account_thread = threading.Thread(target=run_websocket, daemon=True)
            self.ws_account_thread.start()
            
            # Attendre la connexion
            time.sleep(2)
            
            if self.ws_account_connected:
                logger.success("✅ WebSocket account Extended démarré")
                return True
            else:
                logger.warning("WebSocket account Extended: connexion en cours...")
                return False
            
        except Exception as e:
            logger.error(f"Erreur connexion WebSocket account Extended: {e}")
            import traceback
            logger.error(traceback.format_exc())
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
        
        cache_data = self.orderbook_cache.get(market_name)
        if cache_data:
            # Vérifier que les données sont récentes (< 10 secondes)
            if time.time() - cache_data.get('last_update', 0) < 10:
                bid = cache_data.get('bid')
                ask = cache_data.get('ask')
                
                # S'assurer que bid et ask sont valides
                if bid and ask and bid > 0 and ask > 0:
                    result = {
                        "bid": bid,
                        "ask": ask
                    }
                    # Ajouter les 2èmes niveaux si disponibles
                    if 'second_bid' in cache_data:
                        result['second_bid'] = cache_data['second_bid']
                    if 'second_ask' in cache_data:
                        result['second_ask'] = cache_data['second_ask']
                    return result
                else:
                    logger.warning(f"⚠️  Orderbook Extended {ticker}: bid={bid} ou ask={ask} invalide, ignoring cache")
            else:
                # Données trop anciennes, forcer une reconnexion
                logger.warning(f"Données orderbook Extended trop anciennes pour {ticker}, reconnexion...")
                self.ws_connected = False
                self.ws_orderbook(ticker)
                time.sleep(1)
                # Réessayer après reconnexion
                cache_data = self.orderbook_cache.get(market_name)
                if cache_data and time.time() - cache_data.get('last_update', 0) < 10:
                    bid = cache_data.get('bid')
                    ask = cache_data.get('ask')
                    
                    # S'assurer que bid et ask sont valides
                    if bid and ask and bid > 0 and ask > 0:
                        result = {
                            "bid": bid,
                            "ask": ask
                        }
                        if 'second_bid' in cache_data:
                            result['second_bid'] = cache_data['second_bid']
                        if 'second_ask' in cache_data:
                            result['second_ask'] = cache_data['second_ask']
                        return result
        
        # Si pas de cache ou WebSocket déconnecté, essayer de reconnecter
        if not self.ws_connected:
            logger.info(f"Reconnexion WebSocket orderbook Extended pour {ticker}...")
            self.ws_orderbook(ticker)
            time.sleep(2)
            cache_data = self.orderbook_cache.get(market_name)
            if cache_data:
                bid = cache_data.get('bid')
                ask = cache_data.get('ask')
                
                # S'assurer que bid et ask sont valides
                if bid and ask and bid > 0 and ask > 0:
                    result = {
                        "bid": bid,
                        "ask": ask
                    }
                    if 'second_bid' in cache_data:
                        result['second_bid'] = cache_data['second_bid']
                    if 'second_ask' in cache_data:
                        result['second_ask'] = cache_data['second_ask']
                    return result
        
        logger.warning(f"⚠️  Impossible de récupérer l'orderbook Extended pour {ticker}")
        return None
    
    def ws_mark_price(self, ticker: str) -> bool:
        """
        Se connecte au WebSocket mark price pour un ticker donné
        Le mark price est utilisé pour calculer l'unrealized P&L et les liquidations
        
        Args:
            ticker: Symbole du ticker (ex: "BTC", "ETH")
            
        Returns:
            True si la connexion est établie
        """
        try:
            import websocket
            
            market_name = f"{ticker.upper()}-USD"
            
            # Si déjà abonné à ce symbole, ne rien faire
            if ticker in self.ws_mark_price_symbols:
                logger.debug(f"WebSocket mark price déjà abonné à {ticker}")
                return True
            
            # Initialiser le WebSocket si pas encore fait
            if not self.ws_mark_price_connected:
                # URL WebSocket Extended
                # D'après la doc, on peut recevoir tous les markets sans spécifier de market
                # Mais si ça ne marche pas, Extended pourrait requérir /{market_name}
                # Pour l'instant, essayons avec tous les markets (sans market dans l'URL)
                ws_url = f"wss://api.starknet.extended.exchange/stream.extended.exchange/v1/prices/mark"
                
                logger.info(f"🔌 Initialisation WebSocket mark price Extended...")
                
                def on_message(ws, message):
                    try:
                        data = json.loads(message)
                        msg_type = data.get('type')
                        
                        if msg_type == 'MP':  # Mark Price message
                            data_obj = data.get('data', {})
                            market = data_obj.get('m')  # Market name (ex: "BTC-USD")
                            mark_price_str = data_obj.get('p')  # Mark price
                            timestamp = data_obj.get('ts')  # Timestamp
                            
                            if market and mark_price_str:
                                mark_price = float(mark_price_str)
                                
                                # Stocker dans le cache
                                self.mark_price_cache[market] = {
                                    "mark_price": mark_price,
                                    "last_update": time.time(),
                                    "timestamp": timestamp
                                }
                                
                                logger.debug(f"✅ Mark price mis à jour pour {market}: {mark_price}")
                        
                        elif msg_type == 'ping':
                            # Répondre au ping avec pong
                            ws.send(json.dumps({"type": "pong"}))
                        
                        else:
                            # Log des messages inconnus pour debug
                            logger.debug(f"Message WebSocket mark price reçu (type: {msg_type}): {message[:200] if len(message) > 200 else message}")
                    
                    except Exception as e:
                        logger.warning(f"⚠️  Erreur traitement message WebSocket mark price: {e}")
                        logger.debug(f"Message brut: {message[:500] if len(message) > 500 else message}")
                
                def on_error(ws, error):
                    logger.warning(f"⚠️  WebSocket mark price error: {error}")
                
                def on_close(ws, close_status_code, close_msg):
                    logger.warning(f"⚠️  WebSocket mark price fermé (code: {close_status_code}, msg: {close_msg})")
                    self.ws_mark_price_connected = False
                
                def on_open(ws):
                    logger.info("✅ WebSocket mark price ouvert et connecté")
                    self.ws_mark_price_connected = True
                
                # Créer le client WebSocket
                self.ws_mark_price_app = websocket.WebSocketApp(
                    ws_url,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close,
                    on_open=on_open
                )
                
                # Démarrer dans un thread
                def run_websocket():
                    try:
                        # Activer le ping/pong automatique pour garder la connexion vivante
                        self.ws_mark_price_app.run_forever(ping_interval=30, ping_timeout=10)
                    except Exception as e:
                        logger.error(f"❌ Erreur thread WebSocket mark price: {e}")
                        import traceback
                        logger.debug(traceback.format_exc())
                
                self.ws_mark_price_thread = threading.Thread(target=run_websocket, daemon=True)
                self.ws_mark_price_thread.start()
                
                # Attendre la connexion
                time.sleep(2)
            
            # Marquer le symbole comme abonné
            self.ws_mark_price_symbols.add(ticker)
            
            # Attendre un peu pour recevoir les premières données
            time.sleep(0.5)
            
            logger.info(f"✅ WebSocket mark price abonné à {ticker}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur connexion WebSocket mark price Extended: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    def get_mark_price_data(self, ticker: str) -> Optional[Dict[str, float]]:
        """
        Récupère le mark price depuis le cache WebSocket
        
        Args:
            ticker: Symbole du ticker (ex: "BTC", "ETH")
            
        Returns:
            Dict avec {"mark_price": float} ou None si indisponible
        """
        try:
            market_name = f"{ticker.upper()}-USD"
            
            # Vérifier le cache
            cache_data = self.mark_price_cache.get(market_name)
            
            if cache_data:
                # Vérifier que les données ne sont pas trop anciennes (< 5 secondes)
                if time.time() - cache_data.get('last_update', 0) < 5:
                    return {
                        'mark_price': cache_data.get('mark_price', 0)
                    }
                else:
                    # Données trop anciennes, reconnecter
                    logger.warning(f"⚠️  Cache mark price Extended trop ancien pour {ticker}, reconnexion...")
                    self.ws_mark_price_symbols.discard(ticker)
                    self.ws_mark_price(ticker)
            
            return None
            
        except Exception as e:
            logger.debug(f"Erreur récupération mark price depuis cache: {e}")
        return None
    
    def get_account_updates(self) -> Dict:
        """
        Retourne les dernières mises à jour depuis le WebSocket account
        Inclut les ordres (ORDER type) et positions (POSITION type)
        
        Returns:
            Dict avec {orders: [], positions: {}}
        """
        return {
            'orders': self.orders_cache if hasattr(self, 'orders_cache') else [],
            'positions': self.positions_cache if hasattr(self, 'positions_cache') else {}
        }
    
    def withdraw(self, amount: float, destination_address: str = None) -> Dict:
        """
        Effectue un retrait d'USDC depuis Extended vers Arbitrum via le bridge Rhino.fi
        
        Args:
            amount: Montant à retirer en USDC
            destination_address: Adresse Arbitrum de destination (optionnel, utilise wallet_address si non fourni)
            
        Returns:
            Dict avec status='success' ou 'error'
        """
        if not HAS_EXTENDED_SDK:
            logger.error("Extended SDK not available")
            return {"status": "error", "message": "SDK not available"}
        
        if not self.stark_account:
            logger.error("Extended account not initialized")
            return {"status": "error", "message": "Extended account not initialized"}
        
        if amount <= 0:
            logger.error(f"Invalid withdrawal amount: ${amount:.2f}")
            return {"status": "error", "message": "Amount must be positive"}
        
        try:
            logger.info(f"📤 Retrait de ${amount:.2f} depuis Extended vers Arbitrum...")
            
            # Fonction asynchrone pour gérer le retrait
            async def _async_withdraw():
                trading_client = PerpetualTradingClient(
                    endpoint_config=MAINNET_CONFIG,
                    stark_account=self.stark_account,
                )
                try:
                    # Étape 1: Récupérer la config du bridge
                    logger.debug("Étape 1: Récupération de la config du bridge...")
                    bridge_config_response = await trading_client.account.get_bridge_config()
                    
                    if not bridge_config_response or not bridge_config_response.data:
                        raise ValueError("Failed to get bridge config")
                    
                    bridge_config = bridge_config_response.data
                    
                    # Trouver la chaîne Arbitrum
                    arb_chain = None
                    for chain in bridge_config.chains:
                        if chain.chain == "ARB":
                            arb_chain = chain
                            break
                    
                    if not arb_chain:
                        raise ValueError("Arbitrum chain not found in bridge config")
                    
                    logger.info(f"Bridge Arbitrum trouvé: {arb_chain.contractAddress}")
                    
                    # Étape 2: Demander un devis pour le retrait
                    logger.debug("Étape 2: Demande de devis bridge...")
                    amount_rounded = round(float(amount), 2)
                    amount_decimal = Decimal(str(amount_rounded))
                    quote_response = await trading_client.account.get_bridge_quote(
                        chain_in="STRK",
                        chain_out="ARB",
                        amount=amount_decimal
                    )
                    
                    if not quote_response or not quote_response.data:
                        raise ValueError("Failed to get bridge quote")
                    
                    quote = quote_response.data
                    logger.info(f"Devis bridge reçu: ID={quote.id}, Frais=${quote.fee}")
                    logger.info(f"  Montant retrait: ${amount:.2f}")
                    logger.info(f"  Frais bridge: ${quote.fee}")
                    logger.info(f"  Montant après frais: ${amount - float(quote.fee):.2f}")
                    
                    # Étape 3: Confirmer le devis (avec retry et nouveau devis si nécessaire)
                    logger.debug("Étape 3: Confirmation du devis...")
                    max_commit_retries = 2  # Réduire à 2 tentatives
                    commit_success = False
                    current_quote = quote
                    
                    for commit_attempt in range(max_commit_retries):
                        try:
                            commit_response = await trading_client.account.commit_bridge_quote(current_quote.id)
                            if commit_response and commit_response.status != "OK":
                                logger.warning(f"Bridge quote commit response: {commit_response.status}")
                            commit_success = True
                            logger.info(f"Devis bridge confirmé: {current_quote.id}")
                            break
                        except Exception as commit_err:
                            error_str = str(commit_err)
                            if '500' in error_str or '1006' in error_str or 'Internal Server Error' in error_str:
                                if commit_attempt < max_commit_retries - 1:
                                    wait_time = 3  # Attendre 3 secondes
                                    logger.warning(f"⚠️  Erreur serveur Extended (500) lors de la confirmation (tentative {commit_attempt + 1}/{max_commit_retries})")
                                    logger.warning(f"   Demande d'un nouveau devis...")
                                    await asyncio.sleep(wait_time)
                                    
                                    # Demander un nouveau devis si le commit échoue
                                    logger.info("   Demande d'un nouveau devis bridge...")
                                    new_quote_response = await trading_client.account.get_bridge_quote(
                                        chain_in="STRK",
                                        chain_out="ARB",
                                        amount=amount_decimal
                                    )
                                    
                                    if new_quote_response and new_quote_response.data:
                                        current_quote = new_quote_response.data
                                        logger.info(f"   Nouveau devis reçu: ID={current_quote.id}, Frais=${current_quote.fee}")
                                    else:
                                        logger.warning("   Impossible d'obtenir un nouveau devis, réessai avec l'ancien...")
                                else:
                                    raise ValueError(f"Erreur serveur Extended (500) après {max_commit_retries} tentatives: {error_str}")
                            else:
                                raise
                    
                    if not commit_success:
                        raise ValueError("Failed to commit bridge quote after retries")
                    
                    # Utiliser le quote final (peut être différent si on a demandé un nouveau devis)
                    quote = current_quote
                    
                    # Attendre plus longtemps pour s'assurer que le commit est bien traité (éviter erreurs 500)
                    await asyncio.sleep(3)
                    
                    # Étape 4: Effectuer le retrait (avec retry en cas d'erreur 500)
                    logger.debug("Étape 4: Soumission du retrait...")
                    if hasattr(quote, 'amount') and quote.amount:
                        amount_for_withdrawal = Decimal(str(quote.amount))
                    else:
                        amount_for_withdrawal = Decimal(str(round(float(amount_decimal), 2)))
                    
                    max_withdraw_retries = 3
                    withdrawal_success = False
                    
                    for withdraw_attempt in range(max_withdraw_retries):
                        try:
                            withdrawal_response = await trading_client.account.withdraw(
                                amount=amount_for_withdrawal,
                                chain_id="ARB",
                                quote_id=quote.id
                            )
                            
                            if not withdrawal_response or withdrawal_response.data is None:
                                raise ValueError("Failed to submit withdrawal - no data returned")
                            
                            withdrawal_success = True
                            break
                            
                        except Exception as withdraw_err:
                            error_str = str(withdraw_err)
                            if '500' in error_str or '1006' in error_str or 'Internal Server Error' in error_str:
                                if withdraw_attempt < max_withdraw_retries - 1:
                                    wait_time = (withdraw_attempt + 1) * 3  # 3s, 6s, 9s
                                    logger.warning(f"⚠️  Erreur serveur Extended (500) lors du retrait (tentative {withdraw_attempt + 1}/{max_withdraw_retries})")
                                    logger.warning(f"   Attente de {wait_time}s avant réessai...")
                                    await asyncio.sleep(wait_time)
                                else:
                                    logger.error(f"❌ Erreur serveur Extended (500) après {max_withdraw_retries} tentatives")
                                    logger.error("   Causes possibles:")
                                    logger.error("   - Problème temporaire du serveur Extended")
                                    logger.error("   - Quote ID expiré ou invalide")
                                    logger.error("   - Bridge Extended temporairement indisponible")
                                    raise ValueError(f"Erreur serveur Extended (500) après {max_withdraw_retries} tentatives: {error_str}")
                            else:
                                raise
                    
                    if not withdrawal_success:
                        raise ValueError("Failed to submit withdrawal after retries")
                    
                    withdrawal_id = withdrawal_response.data
                    logger.success(f"✅ Retrait Extended soumis: ID={withdrawal_id}")
                    
                    return {
                        "status": "success",
                        "withdrawal_id": withdrawal_id,
                        "quote_id": quote.id,
                        "bridge_fee": float(quote.fee),
                        "amount_after_fee": amount - float(quote.fee)
                    }
                    
                finally:
                    await trading_client.close()
            
            # Exécuter la fonction asynchrone
            loop = self.get_event_loop()
            result = loop.run_until_complete(_async_withdraw())
            return result
            
        except Exception as e:
            logger.error(f"Erreur lors du retrait Extended: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"status": "error", "message": str(e)}
    
    def deposit(self, amount: float, from_address: str = None, private_key: str = None) -> Dict:
        """
        Effectue un dépôt d'USDC depuis Arbitrum vers Extended via le bridge Rhino.fi
        
        Args:
            amount: Montant à déposer en USDC
            from_address: Adresse Arbitrum source (optionnel, utilise wallet_address si non fourni)
            private_key: Clé privée Arbitrum pour signer la transaction (requis)
            
        Returns:
            Dict avec status='success' ou 'error'
        """
        if not HAS_EXTENDED_SDK:
            logger.error("Extended SDK not available")
            return {"status": "error", "message": "SDK not available"}
        
        try:
            from web3 import Web3
            try:
                from web3.middleware import geth_poa_middleware
            except ImportError:
                try:
                    from web3.middleware import ExtraDataToPOAMiddleware as geth_poa_middleware
                except ImportError:
                    geth_poa_middleware = None
            from eth_account import Account
        except ImportError:
            logger.error("web3 not available. Install it with: pip install web3")
            return {"status": "error", "message": "web3 not available"}
        
        if not self.stark_account:
            logger.error("Extended account not initialized")
            return {"status": "error", "message": "Extended account not initialized"}
        
        if amount <= 0:
            logger.error(f"Invalid deposit amount: ${amount:.2f}")
            return {"status": "error", "message": "Amount must be positive"}
        
        try:
            logger.info(f"📥 Dépôt de ${amount:.2f} depuis Arbitrum vers Extended...")
            
            # Fonction asynchrone pour gérer les étapes API
            async def _async_get_bridge_info():
                trading_client = PerpetualTradingClient(
                    endpoint_config=MAINNET_CONFIG,
                    stark_account=self.stark_account,
                )
                try:
                    # Étape 1: Récupérer la config du bridge
                    logger.debug("Étape 1: Récupération de la config du bridge...")
                    bridge_config_response = await trading_client.account.get_bridge_config()
                    
                    if not bridge_config_response or not bridge_config_response.data:
                        raise ValueError("Failed to get bridge config")
                    
                    bridge_config = bridge_config_response.data
                    
                    # Trouver la chaîne Arbitrum
                    arb_chain = None
                    for chain in bridge_config.chains:
                        if chain.chain == "ARB":
                            arb_chain = chain
                            break
                    
                    if not arb_chain:
                        raise ValueError("Arbitrum chain not found in bridge config")
                    
                    logger.info(f"Bridge Arbitrum trouvé: {arb_chain.contractAddress}")
                    
                    # Étape 2: Demander un devis pour le dépôt
                    logger.debug("Étape 2: Demande de devis bridge...")
                    amount_decimal = Decimal(str(amount))
                    quote_response = await trading_client.account.get_bridge_quote(
                        chain_in="ARB",
                        chain_out="STRK",
                        amount=amount_decimal
                    )
                    
                    if not quote_response or not quote_response.data:
                        raise ValueError("Failed to get bridge quote")
                    
                    quote = quote_response.data
                    logger.info(f"Devis bridge reçu: ID={quote.id}, Frais=${quote.fee}")
                    
                    # Étape 3: Confirmer le devis
                    logger.debug("Étape 3: Confirmation du devis...")
                    await trading_client.account.commit_bridge_quote(quote.id)
                    logger.info(f"Devis bridge confirmé: {quote.id}")
                    
                    return {
                        "bridge_address": arb_chain.contractAddress,
                        "quote_id": quote.id,
                        "bridge_fee": float(quote.fee)
                    }
                    
                finally:
                    await trading_client.close()
            
            # Exécuter les étapes API
            loop = self.get_event_loop()
            bridge_info = loop.run_until_complete(_async_get_bridge_info())
            bridge_address = bridge_info["bridge_address"]
            quote_id = bridge_info["quote_id"]
            bridge_fee = bridge_info["bridge_fee"]
            
            # Étape 4: Appeler depositWithId sur le contrat bridge sur Arbitrum
            logger.debug("Étape 4: Appel depositWithId sur le contrat bridge Arbitrum...")
            
            # Connecter à Arbitrum
            arbitrum_rpc_url = "https://arb1.arbitrum.io/rpc"
            w3 = Web3(Web3.HTTPProvider(arbitrum_rpc_url))
            if geth_poa_middleware is not None:
                try:
                    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
                except Exception:
                    pass
            
            if not w3.is_connected():
                logger.error("Failed to connect to Arbitrum RPC")
                return {"status": "error", "message": "Failed to connect to Arbitrum"}
            
            # ABI pour le contrat bridge
            bridge_abi = [{
                "constant": False,
                "inputs": [
                    {"name": "token", "type": "address"},
                    {"name": "amount", "type": "uint256"},
                    {"name": "commitmentId", "type": "uint256"}
                ],
                "name": "depositWithId",
                "outputs": [],
                "type": "function"
            }]
            
            # ABI pour USDC (approve)
            erc20_abi = [{
                "constant": False,
                "inputs": [
                    {"name": "_spender", "type": "address"},
                    {"name": "_value", "type": "uint256"}
                ],
                "name": "approve",
                "outputs": [{"name": "", "type": "bool"}],
                "type": "function"
            }]
            
            # Adresses
            usdc_address = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"  # USDC sur Arbitrum
            bridge_contract = w3.eth.contract(
                address=Web3.to_checksum_address(bridge_address),
                abi=bridge_abi
            )
            usdc_contract = w3.eth.contract(
                address=Web3.to_checksum_address(usdc_address),
                abi=erc20_abi
            )
            
            # Utiliser from_address ou wallet_address
            deposit_address = from_address if from_address else self.wallet_address
            if not deposit_address:
                return {"status": "error", "message": "No deposit address provided"}
            
            if not private_key:
                return {"status": "error", "message": "Arbitrum private key required for deposit"}
            
            # Créer le wallet avec la clé privée
            from eth_account import Account
            wallet = Account.from_key(private_key)
            
            if wallet.address.lower() != deposit_address.lower():
                logger.warning(f"⚠️  Adresse wallet ({wallet.address}) ne correspond pas à from_address ({deposit_address})")
            
            # Vérifier le solde USDC
            usdc_address = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
            usdc_balance_abi = [{
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function"
            }]
            
            usdc_balance_contract = w3.eth.contract(
                address=Web3.to_checksum_address(usdc_address),
                abi=usdc_balance_abi
            )
            
            balance = usdc_balance_contract.functions.balanceOf(
                Web3.to_checksum_address(wallet.address)
            ).call()
            balance_usd = balance / 1e6
            
            logger.info(f"Solde USDC sur Arbitrum: ${balance_usd:,.2f}")
            
            if balance_usd < amount:
                return {
                    "status": "error",
                    "message": f"Solde insuffisant: ${balance_usd:,.2f} < ${amount:,.2f}"
                }
            
            # Convertir le montant en wei (USDC a 6 décimales)
            amount_wei = int(amount * 1e6)
            
            # Vérifier et approuver si nécessaire
            allowance_abi = [{
                "constant": True,
                "inputs": [
                    {"name": "_owner", "type": "address"},
                    {"name": "_spender", "type": "address"}
                ],
                "name": "allowance",
                "outputs": [{"name": "", "type": "uint256"}],
                "type": "function"
            }]
            
            usdc_allowance_contract = w3.eth.contract(
                address=Web3.to_checksum_address(usdc_address),
                abi=allowance_abi + erc20_abi
            )
            
            allowance = usdc_allowance_contract.functions.allowance(
                Web3.to_checksum_address(wallet.address),
                Web3.to_checksum_address(bridge_address)
            ).call()
            
            if allowance < amount_wei:
                logger.info(f"Approbation du bridge pour ${amount:.2f} USDC...")
                nonce = w3.eth.get_transaction_count(wallet.address)
                
                approve_txn = usdc_allowance_contract.functions.approve(
                    Web3.to_checksum_address(bridge_address),
                    amount_wei
                ).build_transaction({
                    'from': wallet.address,
                    'nonce': nonce,
                    'gas': 100000,
                    'chainId': 42161,
                    'gasPrice': w3.eth.gas_price
                })
                
                signed_approve = w3.eth.account.sign_transaction(approve_txn, private_key)
                approve_hash = w3.eth.send_raw_transaction(signed_approve.rawTransaction)
                logger.info(f"Transaction d'approbation envoyée: {approve_hash.hex()}")
                approve_receipt = w3.eth.wait_for_transaction_receipt(approve_hash, timeout=120)
                
                if approve_receipt.status != 1:
                    return {"status": "error", "message": "Approval transaction failed"}
                
                logger.success("✅ Approbation confirmée")
            
            # Convertir quote_id en uint256
            if isinstance(quote_id, str):
                quote_id_clean = quote_id.replace('0x', '').replace('-', '')
                commitment_id = int(quote_id_clean, 16)
            else:
                commitment_id = int(quote_id)
            
            # Appeler depositWithId
            logger.info(f"Appel depositWithId avec commitmentId={commitment_id}...")
            nonce = w3.eth.get_transaction_count(wallet.address)
            
            deposit_txn = bridge_contract.functions.depositWithId(
                Web3.to_checksum_address(usdc_address),
                amount_wei,
                commitment_id
            ).build_transaction({
                'from': wallet.address,
                'nonce': nonce,
                'gas': 200000,
                'chainId': 42161,
                'gasPrice': w3.eth.gas_price
            })
            
            signed_deposit = w3.eth.account.sign_transaction(deposit_txn, private_key)
            deposit_hash = w3.eth.send_raw_transaction(signed_deposit.rawTransaction)
            logger.info(f"Transaction de dépôt envoyée: {deposit_hash.hex()}")
            
            deposit_receipt = w3.eth.wait_for_transaction_receipt(deposit_hash, timeout=120)
            
            if deposit_receipt.status != 1:
                return {"status": "error", "message": "Deposit transaction failed"}
            
            logger.success(f"✅ Dépôt Extended réussi: {deposit_hash.hex()}")
            
            return {
                "status": "success",
                "transaction_hash": deposit_hash.hex(),
                "amount": amount,
                "bridge_fee": bridge_fee
            }
            
        except Exception as e:
            logger.error(f"Erreur lors du dépôt Extended: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {"status": "error", "message": str(e)}
    
    def close(self):
        """Ferme les connexions WebSocket"""
        try:
            if self.ws_app:
                self.ws_app.close()
            if self.ws_account_app:
                self.ws_account_app.close()
            if self.ws_mark_price_app:
                self.ws_mark_price_app.close()
        except:
            pass
    
    def __del__(self):
        """Cleanup du client"""
        self.close()
        if self.trading_client:
            try:
                self.get_event_loop().run_until_complete(self.trading_client.close())
            except:
                pass

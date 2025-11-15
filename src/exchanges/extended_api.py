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
            stark_public_key: Clé publique Starknet (0x...)
            stark_private_key: Clé privée Starknet (0x...)
            vault_id: Vault ID Extended
            client_id: Client ID Extended (non utilisé par le SDK)
        """
        self.wallet_address = wallet_address
        self.api_key = api_key
        self.vault_id = vault_id
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
        
        # URL WebSocket selon l'utilisateur (fonctionne)
        # Ajouter depth=1 pour best bid/ask seulement (fréquence 10ms)
        ws_url = f"wss://api.starknet.extended.exchange/stream.extended.exchange/v1/orderbooks/{market_name}?depth=1"
        
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
                   order_type: str = "limit", reduce_only: bool = False) -> Dict:
        """
        Place un ordre sur Extended avec le SDK officiel
        
        Args:
            symbol: Symbole (BTC, ETH, SOL...)
            side: "buy" ou "sell"
            size: Taille en unités de l'asset
            price: Prix limite (None pour market order)
            order_type: "limit" ou "market"
            reduce_only: True pour close only
        
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
                ticker = self.get_ticker(symbol)
                # Pour MARKET order, utiliser un prix TRÈS agressif avec slippage pour garantir l'exécution
                # BUY = ask + 1% (accepter de payer plus cher)
                # SELL = bid - 1% (accepter de vendre moins cher)
                if side == "buy":
                    price = ticker['ask'] * 1.01  # +1% slippage
                    logger.info(f"   Market BUY: using ask + 1% = ${price:.2f}")
                else:
                    price = ticker['bid'] * 0.99  # -1% slippage
                    logger.info(f"   Market SELL: using bid - 1% = ${price:.2f}")
            elif order_type == "limit" and price is None:
                # Pour LIMIT MAKER, utiliser le prix du côté MAKER
                # 🎯 STRATÉGIE MAKER: mid price ±0.005% pour fill rapide en restant maker
                # D'après le bot Next.js: prix proche du mid, ajusté de ±0.005%
                # Si pas de fill → retry avec offset plus grand (géré par le bot)
                ticker = self.get_ticker(symbol)
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
            rounded_price = market.trading_config.round_price(Decimal(str(price)))
            
            # 🎯 MAKER vs TAKER
            # LIMIT avec post_only=True = MAKER (ajoute liquidité, frais réduits)
            # MARKET avec IOC = TAKER (prend liquidité, frais plus élevés)
            if order_type.lower() == "limit":
                time_in_force = TimeInForce.GTT
                post_only = True  # 🔥 MAKER - ordre dans l'orderbook
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

    def get_positions(self) -> List[Dict]:
        """Récupère les positions ouvertes"""
        if not self.trading_client:
            return []
        
        try:
            positions = self.get_event_loop().run_until_complete(self.trading_client.account.get_positions())
            result = []
            for pos in positions.data:
                if float(pos.size) != 0:
                    # pos.market est le nom complet (ex: "ETH-USD")
                    symbol = pos.market.replace("-USD", "")
                    result.append({
                        "symbol": symbol,
                        "side": "LONG" if float(pos.size) > 0 else "SHORT",
                        "size": abs(float(pos.size)),
                        "entry_price": float(pos.open_price),
                        "unrealized_pnl": float(pos.unrealised_pnl)
                    })
            return result
        except Exception as e:
            logger.error(f"Error fetching Extended positions: {e}")
            return []

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Récupère les ordres ouverts (pending/resting)
        
        Args:
            symbol: Optionnel, filtre par symbole
            
        Returns:
            Liste d'ordres avec {order_id, symbol, side, size, price, status}
        """
        if not self.trading_client:
            return []
        
        try:
            # 🔥 Extended SDK n'a pas de get_orders(), on doit utiliser get_orders_history avec filter
            # Pour l'instant, on retourne une liste vide et on checke via get_order_by_id() dans le bot
            logger.warning("Extended SDK doesn't support listing all open orders - using order_by_id instead")
            return []
            
        except Exception as e:
            logger.error(f"Error fetching Extended open orders: {e}")
            return []
    
    def get_order_status(self, order_id: int) -> Optional[Dict]:
        """
        Check le statut d'un ordre spécifique par ID
        
        Args:
            order_id: L'ID de l'ordre
            
        Returns:
            Dict avec {status, filled_size, ...} ou None si erreur
        """
        if not self.trading_client:
            return None
        
        try:
            result = self.get_event_loop().run_until_complete(
                self.trading_client.account.get_order_by_id(order_id)
            )
            
            if not result or not hasattr(result, 'data'):
                return None
            
            order = result.data
            return {
                "order_id": str(order.id),
                "status": str(order.status).lower(),
                "symbol": order.market.replace("-USD", ""),
                "side": str(order.side).lower(),
                "size": float(order.qty),  # 🔥 qty pas size!
                "price": float(order.price) if hasattr(order, 'price') else None,
                "filled_size": float(order.filled_qty) if order.filled_qty else 0  # 🔥 filled_qty!
            }
            
        except Exception as e:
            logger.error(f"Error fetching order {order_id} status: {e}")
            return None

    def get_balance(self) -> Dict:
        """Récupère le solde du compte"""
        if not self.trading_client:
            return {"total": 0, "available": 0}
        
        try:
            balance = self.get_event_loop().run_until_complete(self.trading_client.account.get_balance())
            return {
                "total": float(balance.data.equity),
                "available": float(balance.data.available_balance),
                "currency": "USDC"
            }
        except Exception as e:
            logger.error(f"Error fetching Extended balance: {e}")
            return {"total": 0, "available": 0}

    def cancel_order(self, order_id: str) -> bool:
        """Annule un ordre"""
        if not self.trading_client:
            return False
        
        try:
            # Le SDK utilise cancel_order_by_id
            result = self.get_event_loop().run_until_complete(self.trading_client.orders.cancel_order(order_id=order_id))
            
            # result.status peut être un string ou un enum
            if isinstance(result.status, str):
                return result.status == "OK"
            else:
                return result.status.value == "OK"
                
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
                        bids = orderbook_data.get('b', [])
                        asks = orderbook_data.get('a', [])
                        
                        if market and bids and asks:
                            # Extraire le meilleur bid/ask et le 2ème niveau
                            best_bid = float(bids[0]['p']) if len(bids) > 0 else None
                            best_ask = float(asks[0]['p']) if len(asks) > 0 else None
                            second_bid = float(bids[1]['p']) if len(bids) > 1 else best_bid
                            second_ask = float(asks[1]['p']) if len(asks) > 1 else best_ask
                            
                            if best_bid and best_ask:
                                self.orderbook_cache[market] = {
                                    "bid": best_bid,
                                    "ask": best_ask,
                                    "second_bid": second_bid,
                                    "second_ask": second_ask,
                                    "last_update": time.time()
                                }
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
                result = {
                    "bid": cache_data['bid'],
                    "ask": cache_data['ask']
                }
                # Ajouter les 2èmes niveaux si disponibles
                if 'second_bid' in cache_data:
                    result['second_bid'] = cache_data['second_bid']
                if 'second_ask' in cache_data:
                    result['second_ask'] = cache_data['second_ask']
                return result
        
        return None
    
    def __del__(self):
        """Cleanup du client"""
        if self.trading_client:
            try:
                self.get_event_loop().run_until_complete(self.trading_client.close())
            except:
                pass

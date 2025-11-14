"""
Extended Exchange API Integration - Using Official SDK x10-python-trading-starknet
Based on: python_sdk-extended/examples/
"""
from typing import Optional, Dict, List
from decimal import Decimal
import asyncio

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

    def get_ticker(self, symbol: str) -> Dict:
        """
        Récupère les prix bid/ask pour un symbole
        
        Returns:
            {"bid": float, "ask": float, "last": float}
        """
        if not self.trading_client:
            return self._simulate_ticker(symbol)
        
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
                logger.warning(f"Market {symbol} not found, using simulation")
                return self._simulate_ticker(symbol)
            
            # Récupérer le market pour avoir les stats
            market = self.markets_cache[market_name]
            
            return {
                "bid": float(market.market_stats.bid_price),
                "ask": float(market.market_stats.ask_price),
                "last": float(market.market_stats.last_price)
            }
        except Exception as e:
            logger.error(f"Error fetching Extended ticker {symbol}: {e}")
            return self._simulate_ticker(symbol)
    
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
            if rounded_size < market.trading_config.min_order_size:
                logger.warning(f"Size {rounded_size} < min {market.trading_config.min_order_size}, using minimum")
                rounded_size = market.trading_config.min_order_size
            
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
    
    def __del__(self):
        """Cleanup du client"""
        if self.trading_client:
            try:
                self.get_event_loop().run_until_complete(self.trading_client.close())
            except:
                pass

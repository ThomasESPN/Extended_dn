"""
Extended Exchange API Integration - Using Official SDK
SDK: x10-python-trading-starknet
"""
from typing import Optional, Dict, List
import asyncio

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# Import du SDK officiel Extended
try:
    from x10.perpetual.configuration import MAINNET_CONFIG
    from x10.perpetual.accounts import StarkPerpetualAccount
    from x10.perpetual.trading_client import PerpetualTradingClient
    from x10.perpetual.order_object import create_order_object
    from x10.perpetual.orders import OrderSide, TimeInForce
    HAS_EXTENDED_SDK = True
    logger.info("✅ Extended SDK (x10-python-trading-starknet) loaded")
except ImportError as e:
    HAS_EXTENDED_SDK = False
    logger.warning(f"Extended SDK not available: {e}")


class ExtendedAPI:
    """Client API pour Extended Exchange avec SDK officiel (async)"""
    
    def __init__(self, wallet_address: str, private_key: str = None, 
                 api_key: str = None, stark_public_key: str = None,
                 stark_private_key: str = None, vault_id: int = None, 
                 client_id: int = None):
        """
        Initialise le client Extended avec le SDK officiel
        
        Args:
            wallet_address: Adresse publique du wallet (0x...)
            private_key: Clé privée EVM (non utilisée)
            api_key: API Key Extended
            stark_public_key: Clé publique Starknet (0x...)
            stark_private_key: Clé privée Starknet (0x...)
            vault_id: Vault ID Extended
            client_id: Client ID Extended (non utilisé dans SDK)
        """
        self.wallet_address = wallet_address
        self.api_key = api_key
        self.vault_id = vault_id
        self.client_id = client_id
        self.stark_account = None
        self.trading_client = None
        self.markets_dict = None
        
        if not HAS_EXTENDED_SDK:
            logger.warning("⚠️ Extended SDK not installed - orders will be simulated")
            return
        
        if not all([api_key, stark_public_key, stark_private_key, vault_id]):
            logger.warning("⚠️ Missing Extended credentials - orders will be simulated")
            return
        
        try:
            # Créer le StarkPerpetualAccount
            self.stark_account = StarkPerpetualAccount(
                api_key=api_key,
                public_key=stark_public_key,  # Format: "0x..."
                private_key=stark_private_key,  # Format: "0x..."
                vault=vault_id
            )
            
            # Créer le trading client (async)
            self.trading_client = PerpetualTradingClient(
                config=MAINNET_CONFIG,
                account=self.stark_account
            )
            
            logger.success(f"✅ Extended SDK initialized (vault {vault_id})")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Extended SDK: {type(e).__name__}: {e}")
            self.trading_client = None
        
        logger.info(f"Extended API initialized for {wallet_address}")

    async def _init_markets(self):
        """Initialise la liste des marchés (appelé une seule fois)"""
        if self.markets_dict or not self.trading_client:
            return
        
        try:
            self.markets_dict = await self.trading_client.markets_info.get_markets_dict()
            logger.debug(f"Loaded {len(self.markets_dict)} Extended markets")
        except Exception as e:
            logger.error(f"Error loading Extended markets: {e}")
            self.markets_dict = {}

    def get_markets(self) -> List[Dict]:
        """Récupère la liste des marchés disponibles (sync wrapper)"""
        if not self.trading_client:
            return self._get_markets_fallback()
        
        try:
            # Run async in sync context
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Si déjà dans un event loop, créer un nouveau thread
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self._init_markets())
                    future.result()
            else:
                loop.run_until_complete(self._init_markets())
            
            if not self.markets_dict:
                return self._get_markets_fallback()
            
            return [
                {
                    "symbol": name.replace("_", "").replace("USD", ""),
                    "name": market.name,
                    "min_size": float(market.trading_config.min_order_size)
                }
                for name, market in self.markets_dict.items()
            ]
        except Exception as e:
            logger.error(f"Error fetching Extended markets: {e}")
            return self._get_markets_fallback()
    
    def _get_markets_fallback(self) -> List[Dict]:
        """Marchés par défaut si SDK pas dispo"""
        return [
            {"symbol": "BTC", "name": "Bitcoin", "min_size": 0.001},
            {"symbol": "ETH", "name": "Ethereum", "min_size": 0.01},
            {"symbol": "SOL", "name": "Solana", "min_size": 0.1}
        ]

    def get_ticker(self, symbol: str) -> Dict:
        """
        Récupère les prix bid/ask pour un symbole
        
        Returns:
            {"bid": float, "ask": float, "last": float}
        """
        if not self.api_client:
            return self._simulate_ticker(symbol)
        
        try:
            ticker = self.api_client.get_ticker(symbol)
            return {
                "bid": float(ticker.get("bid", 0)),
                "ask": float(ticker.get("ask", 0)),
                "last": float(ticker.get("last", 0))
            }
        except Exception as e:
            logger.error(f"Error fetching Extended ticker {symbol}: {e}")
            return self._simulate_ticker(symbol)
    
    def _simulate_ticker(self, symbol: str) -> Dict:
        """Simulation de ticker pour tests"""
        # Prix fictifs basiques
        prices = {
            "BTC": 43000.0,
            "ETH": 3080.0,
            "SOL": 110.0
        }
        mid = prices.get(symbol, 100.0)
        spread = mid * 0.001  # 0.1% spread
        
        return {
            "bid": mid - spread/2,
            "ask": mid + spread/2,
            "last": mid
        }

    def place_order(self, symbol: str, side: str, size: float, price: float,
                   order_type: str = "limit", reduce_only: bool = False) -> Dict:
        """
        Place un ordre sur Extended
        
        Args:
            symbol: Symbole (BTC, ETH, SOL...)
            side: "buy" ou "sell"
            size: Taille en unités de l'asset
            price: Prix limite
            order_type: "limit" ou "market"
            reduce_only: True pour close only
        
        Returns:
            Dict avec order_id et status
        """
        if not self.api_client:
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
            logger.info(f"Placing order: {symbol} {side.upper()} {size} @ {price}")
            
            # Placer l'ordre avec le SDK
            result = self.api_client.place_order(
                symbol=symbol,
                side=side.lower(),
                order_type=order_type,
                size=str(size),
                price=str(price),
                reduce_only=reduce_only
            )
            
            logger.success(f"✅ Order placed: {result}")
            
            return {
                "order_id": result.get("order_id"),
                "status": result.get("status", "pending"),
                "symbol": symbol,
                "side": side,
                "size": size,
                "price": price,
                "raw": result
            }
            
        except Exception as e:
            logger.error(f"Extended order failed: {type(e).__name__}: {e}")
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
        if not self.api_client:
            return []
        
        try:
            positions = self.api_client.get_positions()
            return positions
        except Exception as e:
            logger.error(f"Error fetching Extended positions: {e}")
            return []

    def get_balance(self) -> Dict:
        """Récupère le solde du compte"""
        if not self.api_client:
            return {"total": 0, "available": 0}
        
        try:
            balance = self.api_client.get_balance()
            return {
                "total": float(balance.get("total", 0)),
                "available": float(balance.get("available", 0)),
                "currency": "USDC"
            }
        except Exception as e:
            logger.error(f"Error fetching Extended balance: {e}")
            return {"total": 0, "available": 0}

    def cancel_order(self, order_id: str) -> bool:
        """Annule un ordre"""
        if not self.api_client:
            return False
        
        try:
            result = self.api_client.cancel_order(order_id)
            return result.get("status") == "cancelled"
        except Exception as e:
            logger.error(f"Error cancelling Extended order: {e}")
            return False

    def get_funding_rate(self, symbol: str) -> float:
        """Récupère le taux de funding actuel"""
        if not self.api_client:
            return 0.0
        
        try:
            funding = self.api_client.get_funding_rate(symbol)
            return float(funding.get("rate", 0))
        except Exception as e:
            logger.error(f"Error fetching Extended funding rate: {e}")
            return 0.0

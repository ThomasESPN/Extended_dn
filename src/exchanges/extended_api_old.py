"""
Extended Exchange API Integration
Documentation: https://api-docs.extended.exchange/

Méthode basée sur le projet DroidHL qui fonctionne :
- Utilise starknet_py pour les signatures au lieu de fast_stark_crypto
- Auth headers: X-Api-Key, X-Starknet-PubKey, X-Starknet-Signature
"""
from typing import Optional, Dict, List
import requests
import json
from datetime import datetime
import hashlib

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

# Import starknet_py pour signing (comme dans DroidHL)
try:
    from starkware.crypto.signature.signature import private_to_stark_key, sign, pedersen_hash
    HAS_STARKNET = True
    logger.info("✅ Starkware crypto loaded successfully")
except ImportError as e:
    HAS_STARKNET = False
    logger.warning(f"starknet_py not available - Extended orders will be simulated: {e}")


class ExtendedAPI:
    """Client API pour Extended Exchange avec Starknet signing (méthode DroidHL)"""
    
    # API publique Extended (Starknet mainnet)
    API_URL = "https://api.starknet.extended.exchange"
    
    def __init__(self, wallet_address: str, private_key: str = None, 
                 api_key: str = None, stark_public_key: str = None,
                 stark_private_key: str = None, vault_id: int = None):
        """
        Initialise le client Extended
        
        Args:
            wallet_address: Adresse publique du wallet (0x...)
            private_key: Clé privée du wallet EVM (non utilisée pour Extended)
            api_key: API Key Extended
            stark_public_key: Clé publique Starknet
            stark_private_key: Clé privée Starknet
            vault_id: Vault ID Extended
        """
        self.wallet_address = wallet_address
        self.api_key = api_key
        self.stark_private_key = stark_private_key
        self.stark_public_key = stark_public_key
        self.vault_id = vault_id
        
        # Vérifier les credentials
        if api_key and stark_private_key and HAS_STARKNET:
            try:
                # Nettoyer la clé privée
                if stark_private_key.startswith("0x"):
                    stark_private_key = stark_private_key[2:]
                
                # Dériver la clé publique depuis la privée
                self.stark_private_key_int = int(stark_private_key, 16)
                self.derived_public_key = hex(private_to_stark_key(self.stark_private_key_int))
                
                logger.success(f"✅ Extended initialized with Starknet signing (vault {vault_id})")
                logger.debug(f"Public key derived: {self.derived_public_key[:20]}...")
                
            except Exception as e:
                logger.error(f"❌ Failed to initialize Starknet signing: {type(e).__name__}: {e}")
        elif not HAS_STARKNET:
            logger.warning("⚠️ starkware.crypto not available")
        else:
            logger.warning(f"⚠️ Missing Extended credentials")
        
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json',
            'Content-Type': 'application/json',
            'User-Agent': 'DeltaFund/1.0'
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
    
    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """
        Récupère les prix bid/ask/last pour un symbole
        
        Args:
            symbol: Symbole (ex: "ETH", "BTC")
            
        Returns:
            Dict avec {'bid': float, 'ask': float, 'last': float}
        """
        try:
            # Extended n'a pas d'endpoint ticker dédié, on utilise les markets
            market = f"{symbol}-USD"
            url = f"{self.API_URL}/api/v1/info/markets"
            
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('status') != 'OK':
                logger.error(f"Extended markets error: {data}")
                return None
            
            markets = data.get('data', [])
            
            # Chercher le market
            for mkt in markets:
                if mkt.get('name') == market:
                    # Récupérer les stats du market
                    stats = mkt.get('marketStats', {})
                    last = float(stats.get('lastPrice', 0))
                    
                    # Approximer bid/ask avec spread de 0.05%
                    spread = last * 0.0005
                    
                    return {
                        'bid': last - spread,
                        'ask': last + spread,
                        'last': last
                    }
            
            logger.warning(f"Symbol {market} not found on Extended")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching ticker for {symbol}: {e}")
            return None
    
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
        side: str,
        size: float,
        order_type: str = 'market',
        price: Optional[float] = None,
        reduce_only: bool = False
    ) -> Optional[Dict]:
        """
        Place un ordre sur Extended en utilisant le SDK officiel
        
        Args:
            symbol: Symbole (ex: "BTC", "ETH")
            side: 'buy' ou 'sell'
            size: Taille en contracts (pas en USD!)
            order_type: 'market' ou 'limit'
            price: Prix limite (requis si order_type='limit')
            reduce_only: True pour fermeture uniquement
            
        Returns:
            Reponse de l'exchange ou None
        """
        # Vieille methode SDK supprimee - voir _create_auth_headers et place_order ci-dessous
        pass
    
    def _create_auth_headers(self, endpoint: str, method: str = "GET", payload: dict = None) -> dict:
        """
        Create Extended auth headers with Starknet signing (DroidHL method)
        
        Uses X-Api-Key, X-Starknet-PubKey, X-Starknet-Signature
        """
        if not self.api_key or not HAS_STARKNET:
            return {
                "Content-Type": "application/json",
                "User-Agent": "DeltaFund/1.0",
                "X-Api-Key": self.api_key if self.api_key else ""
            }
        
        try:
            # Create message to sign (like DroidHL: hash of user, endpoint, method, payload)
            def keccak_hash(text: str) -> int:
                """Starknet keccak hash (simplified with SHA256)"""
                import hashlib
                h = hashlib.sha256(text.encode()).digest()
                return int.from_bytes(h[:31], 'big')  # 31 bytes to stay in field
            
            user_hash = keccak_hash("user")
            endpoint_hash = keccak_hash(endpoint)
            method_hash = keccak_hash(method.upper())
            payload_hash = keccak_hash(json.dumps(payload) if payload else "")
            
            # Pedersen hash of full payload
            msg_hash = pedersen_hash(pedersen_hash(pedersen_hash(user_hash, endpoint_hash), method_hash), payload_hash)
            
            # Sign with Starknet private key
            r, s = sign(msg_hash, self.stark_private_key_int)
            
            return {
                "Content-Type": "application/json",
                "User-Agent": "DeltaFund/1.0",
                "X-Api-Key": self.api_key,
                "X-Starknet-PubKey": self.derived_public_key,
                "X-Starknet-Signature": f"{hex(r)},{hex(s)}"
            }
            
        except Exception as e:
            logger.error(f"Error creating auth headers: {e}")
            # Fallback: API key only
            return {
                "Content-Type": "application/json",
                "User-Agent": "DeltaFund/1.0",
                "X-Api-Key": self.api_key if self.api_key else ""
            }
    
    def place_order(self, symbol: str, side: str, size: float, price: float = None,
                    order_type: str = 'LIMIT', reduce_only: bool = False, **kwargs) -> Optional[Dict]:
        """
        Place order on Extended (REST API + signing like DroidHL)
        
        Args:
            symbol: Symbol (ex: "ETH")
            side: "BUY" or "SELL"
            size: Order size
            price: Limit price (required for Extended)
            order_type: Order type ("LIMIT" by default)
            reduce_only: If True, only reduce position
            
        Returns:
            Dict with status and order_id, or None if error
        """
        try:
            if not self.api_key or not HAS_STARKNET:
                logger.warning("Extended signing not available - order will be simulated")
                logger.info(f"Would place order: {symbol} {side.upper()} {size} @ {price or 'MARKET'}")
                
                return {
                    "status": "simulation",
                    "order": {
                        "market": f"{symbol}-USD",
                        "side": side.upper(),
                        "size": str(size),
                        "type": order_type.upper(),
                        "price": str(price) if price else None
                    }
                }
            
            # Build order (Extended API format)
            order_payload = {
                "asset": symbol,
                "is_buy": side.upper() == "BUY",
                "limit_price": str(price) if price else "0",
                "size": str(size),
                "reduce_only": reduce_only,
                "time_in_force": "GTT" if order_type.lower() == 'limit' else "IOC"
            }
            
            logger.info(f"Placing order: {symbol} {side.upper()} {size} @ {price}")
            
            # Create authenticated headers
            headers = self._create_auth_headers("order", "POST", order_payload)
            
            # Send request
            url = f"{self.API_URL}/api/v1/user/order"
            response = self.session.post(url, headers=headers, json=order_payload, timeout=10)
            
            if not response.ok:
                error_text = response.text
                logger.error(f"Extended API error {response.status_code}: {error_text}")
                logger.error(f"Request URL: {url}")
                logger.error(f"Request headers: {headers}")
                logger.error(f"Request payload: {order_payload}")
                return None
            
            data = response.json()
            logger.success(f"✅ Order placed successfully: {data}")
            
            return {
                "status": "ok",
                "response": data
            }
            
        except Exception as e:
            logger.error(f"Error placing order on Extended: {e}")
            import traceback
            traceback.print_exc()
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

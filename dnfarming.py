"""
DN Farming Bot
Ouvre des trades opposés (long/short) sur deux comptes Extended avec rebalancing automatique
"""
import os
import sys
import time
import random
import json
import threading
import websocket
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from decimal import Decimal

from dotenv import load_dotenv
from loguru import logger

# Import pour les transactions Arbitrum
try:
    from web3 import Web3
    try:
        from web3.middleware import geth_poa_middleware
    except ImportError:
        try:
            from web3.middleware import ExtraDataToPOAMiddleware as geth_poa_middleware
        except ImportError:
            geth_poa_middleware = None
    import eth_account
    from eth_account.signers.local import LocalAccount
    HAS_WEB3 = True
except ImportError:
    HAS_WEB3 = False
    logger.warning("web3 not found. Install it with: pip install web3")

# Ajouter le chemin src pour les imports
src_path = os.path.join(os.path.dirname(__file__), 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from exchanges.extended_api import ExtendedAPI
from exchanges.hyperliquid_api import HyperliquidAPI
from exchanges.lighter_api import LighterAPI
from exchanges.rebalancing import RebalancingManager


class PnLWebSocketManager:
    """Gestionnaire de WebSocket pour récupérer les PnL en temps réel"""
    
    def __init__(self, extended_api_key: str, hyperliquid_wallet: str, symbol: str, 
                 extended_client=None, mode: int = 2, lighter_client=None):
        """
        Args:
            extended_api_key: API Key Extended pour l'authentification
            hyperliquid_wallet: Adresse wallet Hyperliquid (mode 2)
            symbol: Symbole à surveiller (ex: "BTC")
            extended_client: Client Extended pour fallback REST (optionnel)
            mode: Mode de trading (2 = Hyperliquid, 3 = Lighter)
            lighter_client: Client Lighter (mode 3)
        """
        self.extended_api_key = extended_api_key
        self.hyperliquid_wallet = hyperliquid_wallet
        self.symbol = symbol
        self.extended_client = extended_client  # Pour fallback REST si WebSocket échoue
        self.mode = mode
        self.lighter_client = lighter_client  # Pour le mode 3
        
        # Nom du second exchange
        self.second_exchange_name = "Hyperliquid" if mode == 2 else "Lighter"
        
        # Cache des PnL
        self.extended_pnl = 0.0
        self.second_pnl = 0.0  # PnL du second exchange (Hyperliquid ou Lighter)
        # Alias pour compatibilité
        self.hyperliquid_pnl = 0.0
        self.extended_position = None  # Position Extended complète
        self.second_position = None  # Position du second exchange
        self.hyperliquid_position = None  # Alias pour compatibilité
        
        # WebSocket instances
        self.extended_ws = None
        self.second_ws = None  # WS du second exchange
        self.hyperliquid_ws = None  # Alias pour compatibilité
        self.extended_ws_thread = None
        self.second_ws_thread = None
        self.hyperliquid_ws_thread = None  # Alias
        
        # État de connexion
        self.extended_connected = False
        self.second_connected = False
        self.hyperliquid_connected = False  # Alias
        
        # Dernière mise à jour
        self.extended_last_update = 0
        self.second_last_update = 0
        self.hyperliquid_last_update = 0  # Alias
    
    def start(self) -> bool:
        """Démarre les WebSocket pour les deux exchanges"""
        logger.info(f"🔌 Démarrage des WebSocket PnL pour {self.symbol}...")
        
        # Démarrer WebSocket Extended
        self._start_extended_ws()
        
        # Démarrer WebSocket du second exchange (Hyperliquid ou Lighter)
        if self.mode == 2:
            self._start_hyperliquid_ws()
        else:
            self._start_lighter_ws()
        
        # Attendre que les connexions soient établies (max 10 secondes)
        max_wait = 10
        waited = 0
        while waited < max_wait:
            second_connected = self.hyperliquid_connected if self.mode == 2 else self.second_connected
            if self.extended_connected and second_connected:
                logger.success(f"✅ WebSocket PnL connectés pour les deux exchanges")
                return True
            time.sleep(0.5)
            waited += 0.5
        
        if not self.extended_connected:
            logger.warning("⚠️  WebSocket Extended non connecté")
        second_connected = self.hyperliquid_connected if self.mode == 2 else self.second_connected
        if not second_connected:
            logger.warning(f"⚠️  WebSocket {self.second_exchange_name} non connecté")
        
        return self.extended_connected or second_connected
    
    def _start_extended_ws(self):
        """Démarre le WebSocket Extended pour les positions (authentifié)"""
        # URL WebSocket privé Extended
        ws_url = "wss://api.starknet.extended.exchange/stream.extended.exchange/v1/account"
        
        def on_message(ws, message):
            try:
                data = json.loads(message)
                msg_type = data.get('type')
                
                if msg_type == 'POSITION':
                    positions = data.get('data', {}).get('positions', [])
                    for pos in positions:
                        market = pos.get('market', '')
                        if self.symbol.upper() in market:
                            self.extended_pnl = float(pos.get('unrealisedPnl', 0))
                            self.extended_position = pos
                            self.extended_last_update = time.time()
                            logger.debug(f"Extended PnL update: ${self.extended_pnl:.2f}")
                
                elif msg_type == 'BALANCE':
                    # Mise à jour du balance si nécessaire
                    balance_data = data.get('data', {}).get('balance', {})
                    logger.debug(f"Extended balance update: {balance_data}")
                    
            except Exception as e:
                logger.debug(f"Extended WS message error: {e}")
        
        def on_error(ws, error):
            error_str = str(error)
            if '403' in error_str:
                logger.error(f"Extended WebSocket 403 Forbidden - Vérifiez l'API Key")
            else:
                logger.error(f"Extended WebSocket error: {error}")
            self.extended_connected = False
        
        def on_close(ws, close_status_code, close_msg):
            if close_status_code and close_status_code != 1000:
                logger.warning(f"Extended WebSocket fermé: {close_status_code} - {close_msg}")
            self.extended_connected = False
        
        def on_open(ws):
            logger.success(f"✅ Extended WebSocket PnL connecté")
            self.extended_connected = True
        
        def run_ws():
            # Headers requis pour Extended WebSocket privé:
            # - X-Api-Key: API key pour l'authentification
            # - User-Agent: Obligatoire (utiliser le même que le SDK Extended)
            headers = {
                "X-Api-Key": self.extended_api_key,
                "User-Agent": "X10PythonTradingClient/0.0.17"
            }
            
            # Convertir en liste pour websocket-client
            header_list = [f"{k}: {v}" for k, v in headers.items()]
            
            logger.info(f"Extended WS connecting with API key: {self.extended_api_key[:8]}...")
            
            self.extended_ws = websocket.WebSocketApp(
                ws_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open,
                header=header_list
            )
            self.extended_ws.run_forever(ping_interval=15, ping_timeout=10)
        
        self.extended_ws_thread = threading.Thread(target=run_ws, daemon=True)
        self.extended_ws_thread.start()
    
    def _start_hyperliquid_ws(self):
        """Démarre le WebSocket Hyperliquid pour les positions (webData2)"""
        ws_url = "wss://api.hyperliquid.xyz/ws"
        
        def on_message(ws, message):
            try:
                if message == "Websocket connection established.":
                    return
                
                data = json.loads(message)
                channel = data.get('channel')
                
                if channel == 'webData2':
                    web_data = data.get('data', {})
                    
                    # Récupérer les positions
                    clearinghouse = web_data.get('clearinghouseState', {})
                    asset_positions = clearinghouse.get('assetPositions', [])
                    
                    for pos_wrapper in asset_positions:
                        pos = pos_wrapper.get('position', {})
                        coin = pos.get('coin', '')
                        
                        if coin == self.symbol.upper():
                            # Calculer le PnL: unrealizedPnl est directement fourni
                            self.hyperliquid_pnl = float(pos.get('unrealizedPnl', 0))
                            self.hyperliquid_position = pos
                            self.hyperliquid_last_update = time.time()
                            logger.debug(f"Hyperliquid PnL update: ${self.hyperliquid_pnl:.2f}")
                            break
                            
            except Exception as e:
                logger.debug(f"Hyperliquid WS message error: {e}")
        
        def on_error(ws, error):
            logger.error(f"Hyperliquid WebSocket error: {error}")
            self.hyperliquid_connected = False
        
        def on_close(ws, close_status_code, close_msg):
            logger.warning(f"Hyperliquid WebSocket fermé: {close_status_code}")
            self.hyperliquid_connected = False
        
        def on_open(ws):
            logger.success(f"✅ Hyperliquid WebSocket PnL connecté")
            self.hyperliquid_connected = True
            
            # S'abonner à webData2 pour cet utilisateur
            subscription = {
                "method": "subscribe",
                "subscription": {
                    "type": "webData2",
                    "user": self.hyperliquid_wallet
                }
            }
            ws.send(json.dumps(subscription))
            logger.info(f"   📡 Souscription webData2 envoyée pour {self.hyperliquid_wallet[:10]}...")
        
        def run_ws():
            self.hyperliquid_ws = websocket.WebSocketApp(
                ws_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )
            self.hyperliquid_ws.run_forever()
        
        self.hyperliquid_ws_thread = threading.Thread(target=run_ws, daemon=True)
        self.hyperliquid_ws_thread.start()
    
    def _start_lighter_ws(self):
        """Démarre le WebSocket Lighter pour les positions"""
        # Pour Lighter, on utilise le client API pour récupérer les positions
        # car Lighter utilise un système différent de WebSocket
        # On simule un WebSocket avec un thread de polling
        
        def poll_lighter_positions():
            while True:
                try:
                    if not self.lighter_client:
                        break
                    
                    # Récupérer les positions via l'API
                    positions = self.lighter_client.get_positions()
                    
                    for pos in positions:
                        if pos.get('symbol', '').upper() == self.symbol.upper():
                            self.second_pnl = float(pos.get('unrealized_pnl', 0))
                            self.second_position = pos
                            self.second_last_update = time.time()
                            logger.debug(f"Lighter PnL update: ${self.second_pnl:.2f}")
                            break
                    
                    time.sleep(5)  # Polling toutes les 5 secondes
                    
                except Exception as e:
                    logger.debug(f"Lighter polling error: {e}")
                    time.sleep(5)
        
        # Marquer comme connecté
        self.second_connected = True
        logger.success(f"✅ Lighter PnL polling démarré")
        
        # Démarrer le thread de polling
        self.second_ws_thread = threading.Thread(target=poll_lighter_positions, daemon=True)
        self.second_ws_thread.start()
    
    def get_combined_pnl(self) -> Tuple[float, float, float]:
        """
        Récupère le PnL combiné en temps réel
        - Second exchange (Hyperliquid/Lighter): depuis WebSocket ou polling (temps réel)
        - Extended: Calcul manuel avec MID PRICE (moyenne bid/ask)
        
        Returns:
            Tuple (extended_pnl, second_pnl, total_pnl)
        """
        # PnL Extended: Calcul manuel avec MID PRICE
        ext_pnl = self.extended_pnl
        if self.extended_client:
            try:
                positions = self.extended_client.get_positions()
                for pos in positions:
                    if pos['symbol'] == self.symbol:
                        # Récupérer le MID PRICE (moyenne bid/ask)
                        ticker = self.extended_client.get_ticker(self.symbol)
                        if ticker:
                            bid = ticker.get('bid', 0)
                            ask = ticker.get('ask', 0)
                            mid_price = (bid + ask) / 2 if bid and ask else ticker.get('last', 0)
                            
                            entry_price = pos.get('entry_price', 0)
                            size = pos.get('size', 0)
                            side = pos.get('side', 'LONG')
                            
                            # Calculer le PnL avec MID PRICE
                            # LONG: profit si mid > entry
                            # SHORT: profit si mid < entry
                            if side == 'LONG':
                                ext_pnl = (mid_price - entry_price) * size
                            else:  # SHORT
                                ext_pnl = (entry_price - mid_price) * size
                            
                            self.extended_pnl = ext_pnl
                        break
            except Exception as e:
                logger.debug(f"Extended PnL calculation error: {e}")
        
        # PnL du second exchange: depuis WebSocket/polling (mis à jour en temps réel)
        if self.mode == 2:
            second_pnl = self.hyperliquid_pnl
        else:
            second_pnl = self.second_pnl
        
        total_pnl = ext_pnl + second_pnl
        return ext_pnl, second_pnl, total_pnl
    
    def is_data_fresh(self, max_age_seconds: float = 5.0) -> bool:
        """Vérifie si les données sont récentes"""
        now = time.time()
        ext_fresh = (now - self.extended_last_update) < max_age_seconds if self.extended_last_update > 0 else False
        
        if self.mode == 2:
            second_fresh = (now - self.hyperliquid_last_update) < max_age_seconds if self.hyperliquid_last_update > 0 else False
        else:
            second_fresh = (now - self.second_last_update) < max_age_seconds if self.second_last_update > 0 else False
        
        return ext_fresh and second_fresh
    
    def stop(self):
        """Arrête les WebSocket et threads de polling"""
        if self.extended_ws:
            try:
                self.extended_ws.close()
            except:
                pass
        if self.hyperliquid_ws:
            try:
                self.hyperliquid_ws.close()
            except:
                pass
        # Pour Lighter (mode 3), le thread s'arrêtera automatiquement (daemon=True)
        self.extended_connected = False
        self.hyperliquid_connected = False
        self.second_connected = False
        logger.info("WebSocket PnL fermés")


class PriceComparator:
    """Comparateur de prix en temps réel entre deux exchanges via WebSocket"""
    
    def __init__(self, extended_client, second_client, symbol: str, mode: int = 2):
        """
        Args:
            extended_client: Client Extended API
            second_client: Client Hyperliquid API (mode 2) ou Lighter API (mode 3)
            symbol: Symbole à comparer (ex: "BTC", "ETH")
            mode: Mode de trading (2 = Extended<->Hyperliquid, 3 = Extended<->Lighter)
        """
        self.extended_client = extended_client
        self.second_client = second_client
        # Aliases pour compatibilité
        self.hyperliquid_client = second_client if mode == 2 else None
        self.lighter_client = second_client if mode == 3 else None
        self.symbol = symbol
        self.mode = mode
        self.ws_connected = False
        
        # Nom de l'exchange secondaire pour les logs
        self.second_exchange_name = "Hyperliquid" if mode == 2 else "Lighter"
        
    def start_websockets(self) -> bool:
        """
        Démarre les WebSocket sur les deux exchanges (optionnel)
        Note: La comparaison utilise maintenant get_ticker() directement pour des prix fiables
        """
        logger.info(f"🔌 Démarrage des WebSocket pour {self.symbol}...")
        
        # Démarrer le WebSocket Extended
        ext_ok = self.extended_client.ws_orderbook(self.symbol)
        if ext_ok:
            logger.success(f"   ✅ Extended WebSocket connecté pour {self.symbol}")
        else:
            logger.warning(f"   ⚠️  WebSocket Extended non disponible, utilisation de l'API REST")
        
        # Démarrer le WebSocket du second exchange (Hyperliquid ou Lighter)
        second_ok = self.second_client.ws_orderbook(self.symbol)
        if second_ok:
            logger.success(f"   ✅ {self.second_exchange_name} WebSocket connecté pour {self.symbol}")
        else:
            logger.warning(f"   ⚠️  WebSocket {self.second_exchange_name} non disponible, utilisation de l'API REST")
        
        self.ws_connected = ext_ok and second_ok
        
        # Attendre un peu pour recevoir les premières données
        if self.ws_connected:
            time.sleep(2)
        
        return True  # Toujours retourner True car get_ticker() fonctionne en fallback
    
    def get_prices(self) -> Tuple[Optional[float], Optional[float]]:
        """
        Récupère les prix mid actuels des deux exchanges
        Utilise TOUJOURS get_ticker pour avoir des prix fiables et synchronisés
        
        Returns:
            Tuple (extended_mid_price, second_exchange_mid_price)
        """
        # Prix Extended - utiliser get_ticker directement pour avoir des prix frais
        ext_ticker = self.extended_client.get_ticker(self.symbol)
        ext_price = None
        if ext_ticker:
            # Utiliser le mid price (moyenne bid/ask)
            ext_bid = ext_ticker.get('bid', 0)
            ext_ask = ext_ticker.get('ask', 0)
            if ext_bid and ext_ask:
                ext_price = (ext_bid + ext_ask) / 2
            else:
                ext_price = ext_ticker.get('last', 0)
            logger.debug(f"Extended ticker: bid=${ext_bid:,.2f}, ask=${ext_ask:,.2f}, mid=${ext_price:,.2f}")
        
        # Prix du second exchange (Hyperliquid ou Lighter) - utiliser get_ticker directement
        second_ticker = self.second_client.get_ticker(self.symbol)
        second_price = None
        if second_ticker:
            # Utiliser le mid price (moyenne bid/ask)
            second_bid = second_ticker.get('bid', 0)
            second_ask = second_ticker.get('ask', 0)
            if second_bid and second_ask:
                second_price = (second_bid + second_ask) / 2
            else:
                second_price = second_ticker.get('last', 0)
            logger.debug(f"{self.second_exchange_name} ticker: bid=${second_bid:,.2f}, ask=${second_ask:,.2f}, mid=${second_price:,.2f}")
        
        return ext_price, second_price
    
    def compare_and_decide(self) -> Tuple[str, str, float, float, float]:
        """
        Compare les prix et décide quel côté trader sur chaque exchange
        
        Returns:
            Tuple (extended_side, second_side, price_diff_percent, ext_price, second_price)
            - extended_side: "buy" (long) ou "sell" (short) pour Extended
            - second_side: "buy" (long) ou "sell" (short) pour le second exchange
            - price_diff_percent: différence de prix en pourcentage
            - ext_price: prix Extended utilisé pour la décision
            - second_price: prix du second exchange utilisé pour la décision
        """
        ext_price, second_price = self.get_prices()
        
        if not ext_price or not second_price:
            logger.error("❌ Impossible de récupérer les prix des deux exchanges")
            return None, None, 0, 0, 0
        
        # Calculer la différence de prix
        avg_price = (ext_price + second_price) / 2
        price_diff = abs(ext_price - second_price)
        price_diff_percent = (price_diff / avg_price) * 100
        
        logger.info(f"\n{'='*50}")
        logger.info(f"📊 COMPARAISON DES PRIX {self.symbol}")
        logger.info(f"{'='*50}")
        logger.info(f"   Extended:    ${ext_price:,.2f}")
        logger.info(f"   {self.second_exchange_name}: ${second_price:,.2f}")
        logger.info(f"   Différence:  ${price_diff:,.2f} ({price_diff_percent:.4f}%)")
        
        # Règle: SHORT le plus haut, LONG le plus bas
        if ext_price > second_price:
            # Extended plus haut → SHORT Extended, LONG second exchange
            extended_side = "sell"  # SHORT Extended (prix plus haut)
            second_side = "buy"   # LONG second exchange (prix plus bas)
            logger.info(f"{'='*50}")
            logger.success(f"   Extended (${ext_price:,.2f}) > {self.second_exchange_name} (${second_price:,.2f})")
            logger.success(f"   → SHORT Extended, LONG {self.second_exchange_name}")
            logger.info(f"{'='*50}\n")
        else:
            # Second exchange plus haut ou égal → SHORT second exchange, LONG Extended
            extended_side = "buy"   # LONG Extended (prix plus bas ou égal)
            second_side = "sell"  # SHORT second exchange (prix plus haut)
            logger.info(f"{'='*50}")
            logger.success(f"   {self.second_exchange_name} (${second_price:,.2f}) >= Extended (${ext_price:,.2f})")
            logger.success(f"   → SHORT {self.second_exchange_name}, LONG Extended")
            logger.info(f"{'='*50}\n")
        
        return extended_side, second_side, price_diff_percent, ext_price, second_price


class DNFarmingBot:
    """Bot pour farming de delta neutre avec rebalancing automatique"""
    
    def __init__(self, mode: int = 1):
        """
        Initialise le bot avec les credentials depuis .env
        
        Args:
            mode: Mode de trading (1 = Extended <-> Extended, 2 = Extended <-> Hyperliquid)
        """
        load_dotenv()
        
        self.mode = mode
        
        # Variables pour stocker les infos de l'ordre Lighter (pour fermeture si position non détectée)
        self.last_lighter_order_size = None
        self.last_lighter_order_side = None
        self.last_lighter_order_symbol = None
        
        if mode == 1:
            # Mode 1: Deux comptes Extended
            logger.info("🔵 Mode 1: Trading delta neutre entre deux comptes Extended")
            
            # Charger les credentials pour le compte 1
            self.account1 = self._load_account_config(1)
            # Charger les credentials pour le compte 2
            self.account2 = self._load_account_config(2)
            
            # Initialiser les clients Extended
            logger.info("Initialisation des clients Extended...")
            logger.info(f"Compte 1: {self.account1.get('name', 'Account 1')}")
            logger.info(f"Compte 2: {self.account2.get('name', 'Account 2')}")
            
            self.client1 = ExtendedAPI(
                wallet_address=self.account1['wallet_address'] or self.account1['arbitrum_address'],
                api_key=self.account1['api_key'],
                stark_public_key=self.account1['stark_public_key'],
                stark_private_key=self.account1['stark_private_key'],
                vault_id=self.account1['vault_id']
            )
            
            self.client2 = ExtendedAPI(
                wallet_address=self.account2['wallet_address'] or self.account2['arbitrum_address'],
                api_key=self.account2['api_key'],
                stark_public_key=self.account2['stark_public_key'],
                stark_private_key=self.account2['stark_private_key'],
                vault_id=self.account2['vault_id']
            )
            
            # Initialiser les rebalancing managers pour chaque compte
            self.rebalance_manager1 = self._create_rebalance_manager(self.account1)
            self.rebalance_manager2 = self._create_rebalance_manager(self.account2)
            
            # client2 est aussi Extended en mode 1
            self.hyperliquid_client = None
            
        elif mode == 2:
            # Mode 2: Extended <-> Hyperliquid
            logger.info("🟢 Mode 2: Trading delta neutre entre Extended et Hyperliquid")
            
            # Charger les credentials pour Extended (compte 1)
            self.account1 = self._load_account_config(1)
            
            # Charger les credentials pour Hyperliquid depuis les variables HYPERLIQUID_*
            self.account2 = self._load_hyperliquid_config()
            
            # Initialiser le client Extended
            logger.info("Initialisation du client Extended...")
            logger.info(f"Extended: {self.account1.get('name', 'Extended Account')}")
            
            self.client1 = ExtendedAPI(
                wallet_address=self.account1['wallet_address'] or self.account1['arbitrum_address'],
                api_key=self.account1['api_key'],
                stark_public_key=self.account1['stark_public_key'],
                stark_private_key=self.account1['stark_private_key'],
                vault_id=self.account1['vault_id']
            )
            
            # Initialiser le client Hyperliquid
            logger.info("Initialisation du client Hyperliquid...")
            hyperliquid_wallet = self.account2.get('arbitrum_address')
            hyperliquid_private_key = self.account2.get('arbitrum_private_key')
            
            if not hyperliquid_wallet or not hyperliquid_private_key:
                raise ValueError("HYPERLIQUID_ARBITRUM_ADDRESS et HYPERLIQUID_ARBITRUM_PRIVATE_KEY requis pour le mode 2")
            
            logger.info(f"Hyperliquid: {hyperliquid_wallet}")
            
            self.hyperliquid_client = HyperliquidAPI(
                wallet_address=hyperliquid_wallet,
                private_key=hyperliquid_private_key,
                testnet=False
            )
            
            # client2 pointe vers Hyperliquid en mode 2
            self.client2 = self.hyperliquid_client
            
            # Lighter client non utilisé en mode 2
            self.lighter_client = None
            
            # Initialiser les rebalancing managers
            self.rebalance_manager1 = self._create_rebalance_manager(self.account1)
            # Pour Hyperliquid, on crée un RebalancingManager avec une config minimale depuis les comptes
            from exchanges.rebalancing import RebalancingManager
            rebalance_config = self._create_rebalance_config_for_mode2()
            self.rebalance_manager2 = RebalancingManager(rebalance_config)
            
        elif mode == 3:
            # Mode 3: Extended <-> Lighter
            logger.info("🟣 Mode 3: Trading delta neutre entre Extended et Lighter")
            
            # Charger les credentials pour Extended (compte 1)
            self.account1 = self._load_account_config(1)
            
            # Charger les credentials pour Lighter
            self.account2 = self._load_lighter_config()
            
            # Initialiser le client Extended
            logger.info("Initialisation du client Extended...")
            logger.info(f"Extended: {self.account1.get('name', 'Extended Account')}")
            
            self.client1 = ExtendedAPI(
                wallet_address=self.account1['wallet_address'] or self.account1['arbitrum_address'],
                api_key=self.account1['api_key'],
                stark_public_key=self.account1['stark_public_key'],
                stark_private_key=self.account1['stark_private_key'],
                vault_id=self.account1['vault_id']
            )
            
            # Initialiser le client Lighter
            logger.info("Initialisation du client Lighter...")
            lighter_account_index = self.account2.get('account_index', 0)
            lighter_api_keys = self.account2.get('api_private_keys', {})
            lighter_l1_address = self.account2.get('l1_address')
            
            if not lighter_api_keys:
                raise ValueError("LIGHTER_API_KEY_0 ou LIGHTER_API_KEY requis pour le mode 3")
            
            logger.info(f"Lighter: Account Index {lighter_account_index}")
            
            # Récupérer la clé privée L1 pour fast withdraw
            lighter_l1_private_key = self.account2.get('l1_private_key')
            
            self.lighter_client = LighterAPI(
                account_index=lighter_account_index,
                api_private_keys=lighter_api_keys,
                l1_address=lighter_l1_address,
                l1_private_key=lighter_l1_private_key,
                testnet=False
            )
            
            # client2 pointe vers Lighter en mode 3
            self.client2 = self.lighter_client
            
            # Hyperliquid client non utilisé en mode 3
            self.hyperliquid_client = None
            
            # Initialiser les rebalancing managers
            self.rebalance_manager1 = self._create_rebalance_manager(self.account1)
            # Pour Lighter, on crée un RebalancingManager avec une config minimale
            from exchanges.rebalancing import RebalancingManager
            rebalance_config = self._create_rebalance_config_for_mode3()
            self.rebalance_manager2 = RebalancingManager(rebalance_config)
            
        else:
            raise ValueError(f"Mode invalide: {mode}. Utilisez 1, 2 ou 3")
        
        # Configuration Arbitrum pour les transferts
        self.arbitrum_rpc_url = "https://arb1.arbitrum.io/rpc"
        self.arbitrum_usdc_address = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"  # USDC on Arbitrum
        self.arbitrum_chain_id = 42161
        
        logger.success("✅ Bot initialisé avec succès")
    
    def _get_gas_params(self, w3):
        """
        Récupère les paramètres de gas pour une transaction EIP-1559
        
        Args:
            w3: Instance Web3 connectée
            
        Returns:
            Dict avec maxFeePerGas et maxPriorityFeePerGas
        """
        try:
            latest_block = w3.eth.get_block('latest')
            base_fee = latest_block.get('baseFeePerGas', 0)
            
            max_priority_fee = w3.to_wei(0.1, 'gwei')  # 0.1 gwei pour Arbitrum
            
            if base_fee > 0:
                max_fee = int(base_fee * 1.2) + max_priority_fee
            else:
                gas_price = w3.eth.gas_price
                max_fee = gas_price
                max_priority_fee = w3.to_wei(0.1, 'gwei')
            
            return {
                'maxFeePerGas': max_fee,
                'maxPriorityFeePerGas': max_priority_fee
            }
        except Exception as e:
            logger.warning(f"Error getting EIP-1559 gas params, using legacy gasPrice: {e}")
            gas_price = w3.eth.gas_price
            return {
                'gasPrice': gas_price
            }
    
    def transfer_usdc_on_arbitrum(self, from_private_key: str, to_address: str, amount: float) -> Dict:
        """
        Transfère des USDC sur Arbitrum d'une adresse à une autre
        
        Args:
            from_private_key: Clé privée EVM du compte source (0x...)
            to_address: Adresse de destination (0x...)
            amount: Montant en USDC
        
        Returns:
            Dict avec le résultat de la transaction
        """
        if not HAS_WEB3:
            return {"status": "error", "message": "web3 not available"}
        
        try:
            logger.info(f"Transfert de ${amount:.2f} USDC sur Arbitrum vers {to_address}...")
            
            # Connecter à Arbitrum
            w3 = Web3(Web3.HTTPProvider(self.arbitrum_rpc_url))
            if geth_poa_middleware is not None:
                try:
                    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
                except Exception:
                    pass
            
            if not w3.is_connected():
                return {"status": "error", "message": "Failed to connect to Arbitrum RPC"}
            
            # Créer le wallet depuis la clé privée
            if not from_private_key.startswith("0x"):
                from_private_key = "0x" + from_private_key
            
            wallet = eth_account.Account.from_key(from_private_key)
            from_address = wallet.address
            
            # ABI pour USDC (transfer et balanceOf)
            erc20_abi = [
                {
                    "constant": False,
                    "inputs": [
                        {"name": "_to", "type": "address"},
                        {"name": "_value", "type": "uint256"}
                    ],
                    "name": "transfer",
                    "outputs": [{"name": "", "type": "bool"}],
                    "type": "function"
                },
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function"
                }
            ]
            
            # Créer le contrat USDC
            usdc_contract = w3.eth.contract(
                address=Web3.to_checksum_address(self.arbitrum_usdc_address),
                abi=erc20_abi
            )
            
            # Vérifier le solde USDC disponible
            balance = usdc_contract.functions.balanceOf(
                Web3.to_checksum_address(from_address)
            ).call()
            balance_usd = balance / 1e6  # USDC a 6 décimales
            
            logger.info(f"Solde USDC sur Arbitrum: ${balance_usd:,.2f}")
            
            if balance_usd < amount:
                return {
                    "status": "error",
                    "message": f"Insufficient balance. Available: ${balance_usd:,.2f}, Required: ${amount:,.2f}"
                }
            
            # Convertir le montant en wei (USDC a 6 décimales)
            amount_wei = int(amount * 1e6)
            
            # Obtenir le nonce
            nonce = w3.eth.get_transaction_count(from_address)
            
            # Obtenir les paramètres de gas
            gas_params = self._get_gas_params(w3)
            
            # Construire la transaction transfer
            transaction = usdc_contract.functions.transfer(
                Web3.to_checksum_address(to_address),
                amount_wei
            ).build_transaction({
                'from': from_address,
                'nonce': nonce,
                'gas': 100000,  # Gas limit pour un transfer ERC20
                'chainId': self.arbitrum_chain_id,
                **gas_params
            })
            
            # Signer la transaction
            signed_txn = w3.eth.account.sign_transaction(transaction, wallet.key)
            
            # Envoyer la transaction
            logger.info("Envoi de la transaction sur Arbitrum...")
            raw_tx = signed_txn.raw_transaction if hasattr(signed_txn, 'raw_transaction') else signed_txn.rawTransaction
            tx_hash = w3.eth.send_raw_transaction(raw_tx)
            
            logger.info(f"Transaction envoyée: {tx_hash.hex()}")
            logger.info("Attente de la confirmation...")
            
            # Attendre la confirmation
            tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if tx_receipt.status == 1:
                logger.success(f"✅ Transfert réussi! Transaction: {tx_hash.hex()}")
                return {
                    "status": "success",
                    "amount": amount,
                    "transaction_hash": tx_hash.hex(),
                    "receipt": {
                        "blockNumber": tx_receipt.blockNumber,
                        "gasUsed": tx_receipt.gasUsed
                    }
                }
            else:
                logger.error(f"Transaction échouée: {tx_hash.hex()}")
                return {
                    "status": "error",
                    "message": "Transaction failed",
                    "transaction_hash": tx_hash.hex()
                }
            
        except Exception as e:
            logger.error(f"Erreur lors du transfert Arbitrum: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                "status": "error",
                "message": str(e)
            }
    
    def _get_arbitrum_balance(self, address: str) -> float:
        """
        Récupère le solde USDC actuel sur Arbitrum pour une adresse
        
        Args:
            address: Adresse à vérifier
        
        Returns:
            Solde en USDC, 0.0 en cas d'erreur
        """
        if not HAS_WEB3:
            return 0.0
        
        try:
            w3 = Web3(Web3.HTTPProvider(self.arbitrum_rpc_url))
            if not w3.is_connected():
                return 0.0
            
            # ABI pour balanceOf
            erc20_abi = [
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function"
                }
            ]
            
            usdc_contract = w3.eth.contract(
                address=Web3.to_checksum_address(self.arbitrum_usdc_address),
                abi=erc20_abi
            )
            
            balance = usdc_contract.functions.balanceOf(
                Web3.to_checksum_address(address)
            ).call()
            balance_usd = balance / 1e6  # USDC a 6 décimales
            
            return balance_usd
            
        except Exception as e:
            logger.debug(f"Erreur lors de la récupération du solde Arbitrum: {e}")
            return 0.0
    
    def wait_for_arbitrum_balance(self, address: str, min_balance: float, max_wait_seconds: int = 600) -> bool:
        """
        Attend qu'un solde USDC soit disponible sur Arbitrum
        
        Args:
            address: Adresse à vérifier
            min_balance: Solde minimum requis en USDC
            max_wait_seconds: Temps maximum d'attente en secondes
        
        Returns:
            True si le solde est disponible, False sinon
        """
        if not HAS_WEB3:
            return False
        
        try:
            w3 = Web3(Web3.HTTPProvider(self.arbitrum_rpc_url))
            if not w3.is_connected():
                return False
            
            # ABI pour balanceOf
            erc20_abi = [
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function"
                }
            ]
            
            usdc_contract = w3.eth.contract(
                address=Web3.to_checksum_address(self.arbitrum_usdc_address),
                abi=erc20_abi
            )
            
            start_time = time.time()
            check_interval = 10  # Vérifier toutes les 10 secondes
            
            while time.time() - start_time < max_wait_seconds:
                balance = usdc_contract.functions.balanceOf(
                    Web3.to_checksum_address(address)
                ).call()
                balance_usd = balance / 1e6
                
                if balance_usd >= min_balance:
                    logger.success(f"✅ Solde disponible: ${balance_usd:,.2f} USDC")
                    return True
                
                elapsed = int(time.time() - start_time)
                remaining = max_wait_seconds - elapsed
                logger.info(f"⏳ Attente du solde... (${balance_usd:,.2f} / ${min_balance:,.2f} requis) - {remaining}s restantes")
                time.sleep(check_interval)
            
            logger.error(f"⏱️  Timeout: Le solde n'est pas disponible après {max_wait_seconds} secondes")
            return False
            
        except Exception as e:
            logger.error(f"Erreur lors de la vérification du solde: {e}")
            return False
    
    def _load_account_config(self, account_num: int) -> Dict:
        """Charge la configuration d'un compte depuis .env"""
        prefix = f"ACCOUNT{account_num}_"
        
        config = {
            'name': os.getenv(f"{prefix}NAME", f"Account {account_num}"),
            'api_key': os.getenv(f"{prefix}API_KEY"),
            'stark_public_key': os.getenv(f"{prefix}PUBLIC_KEY"),  # PUBLIC_KEY = STARK_PUBLIC_KEY
            'stark_private_key': os.getenv(f"{prefix}PRIVATE_KEY"),  # PRIVATE_KEY = STARK_PRIVATE_KEY
            'vault_id': int(os.getenv(f"{prefix}VAULT_ID", "0")),
            'arbitrum_address': os.getenv(f"{prefix}ARBITRUM_ADDRESS"),
            'arbitrum_private_key': os.getenv(f"{prefix}ARBITRUM_PRIVATE_KEY"),
        }
        
        # Pour Extended, on utilise l'adresse Arbitrum comme wallet_address (même wallet généralement)
        # L'adresse Arbitrum est utilisée comme référence pour le wallet_address
        config['wallet_address'] = config['arbitrum_address']
        
        if not config['arbitrum_address']:
            logger.warning(f"ACCOUNT{account_num}_ARBITRUM_ADDRESS non défini")
            logger.warning("Le rebalancing automatique nécessite ARBITRUM_ADDRESS")
        
        # Vérifier que tous les champs essentiels sont présents
        required_fields = ['api_key', 'stark_public_key', 'stark_private_key', 'vault_id']
        missing = [k for k in required_fields if not config.get(k)]
        if missing:
            raise ValueError(f"Configuration incomplète pour ACCOUNT{account_num}. Champs manquants: {missing}")
        
        # Vérifier les champs Arbitrum (optionnels mais recommandés pour le rebalancing)
        if not config['arbitrum_address'] or not config['arbitrum_private_key']:
            logger.warning(f"⚠️  ACCOUNT{account_num}: Adresse ou clé privée Arbitrum manquante - le rebalancing automatique ne fonctionnera pas")
        
        return config
    
    def _load_hyperliquid_config(self) -> Dict:
        """Charge la configuration Hyperliquid depuis .env avec les variables HYPERLIQUID_*"""
        config = {
            'name': os.getenv("HYPERLIQUID_NAME", "Hyperliquid Account"),
            'arbitrum_address': os.getenv("HYPERLIQUID_ARBITRUM_ADDRESS"),
            'arbitrum_private_key': os.getenv("HYPERLIQUID_ARBITRUM_PRIVATE_KEY"),
        }
        
        # Pour Hyperliquid, on utilise l'adresse Arbitrum comme wallet_address
        config['wallet_address'] = config['arbitrum_address']
        
        if not config['arbitrum_address']:
            logger.warning("HYPERLIQUID_ARBITRUM_ADDRESS non défini")
            logger.warning("Le rebalancing automatique nécessite HYPERLIQUID_ARBITRUM_ADDRESS")
        
        if not config['arbitrum_private_key']:
            logger.warning("HYPERLIQUID_ARBITRUM_PRIVATE_KEY non défini")
            logger.warning("Les transactions Hyperliquid nécessitent HYPERLIQUID_ARBITRUM_PRIVATE_KEY")
        
        return config
    
    def _load_lighter_config(self) -> Dict:
        """Charge la configuration Lighter depuis .env avec les variables LIGHTER_*"""
        config = {
            'name': os.getenv("LIGHTER_NAME", "Lighter Account"),
            'account_index': int(os.getenv("LIGHTER_ACCOUNT_INDEX", "0")),
            'l1_address': os.getenv("LIGHTER_L1_ADDRESS"),
            'arbitrum_address': os.getenv("LIGHTER_ARBITRUM_ADDRESS"),
            'arbitrum_private_key': os.getenv("LIGHTER_ARBITRUM_PRIVATE_KEY"),
            'l1_private_key': os.getenv("LIGHTER_L1_PRIVATE_KEY"),
        }
        
        # Charger les clés API Lighter (format: LIGHTER_API_KEY_0, LIGHTER_API_KEY_1, etc.)
        api_keys = {}
        for i in range(10):  # Support jusqu'à 10 clés API
            key = os.getenv(f"LIGHTER_API_KEY_{i}")
            if key:
                api_keys[i] = key
        
        # Si pas de clé avec index, essayer LIGHTER_API_KEY simple
        if not api_keys:
            single_key = os.getenv("LIGHTER_API_KEY")
            if single_key:
                api_keys[0] = single_key
        
        config['api_private_keys'] = api_keys
        
        # Pour Lighter, on utilise l'adresse Arbitrum ou L1 comme wallet_address
        config['wallet_address'] = config['arbitrum_address'] or config['l1_address']
        
        if not config['account_index'] and config['account_index'] != 0:
            logger.warning("LIGHTER_ACCOUNT_INDEX non défini")
            logger.warning("L'index de compte Lighter est requis")
        
        if not api_keys:
            logger.warning("LIGHTER_API_KEY_0 ou LIGHTER_API_KEY non défini")
            logger.warning("Les transactions Lighter nécessitent une clé API")
        
        if not config['arbitrum_address']:
            logger.warning("LIGHTER_ARBITRUM_ADDRESS non défini")
            logger.warning("Le rebalancing automatique nécessite LIGHTER_ARBITRUM_ADDRESS")
        
        return config
    
    def _create_rebalance_manager(self, account_config: Dict) -> RebalancingManager:
        """Crée un RebalancingManager pour un compte"""
        # Créer une config minimale pour le rebalancing
        class MinimalConfig:
            def __init__(self, account_config):
                self.account_config = account_config
            
            def get(self, section, key, default=None):
                if section == 'wallet':
                    if key == 'address':
                        return self.account_config.get('arbitrum_address') or self.account_config.get('wallet_address')
                    elif key == 'private_key':
                        return self.account_config.get('arbitrum_private_key')
                elif section == 'exchanges':
                    if key == 'extended':
                        return {
                            'api_key': self.account_config.get('api_key'),
                            'public_key': self.account_config.get('stark_public_key'),
                            'private_key': self.account_config.get('stark_private_key'),
                            'vault_id': self.account_config.get('vault_id')
                        }
                elif section == 'arbitrage':
                    if key == 'auto_rebalance':
                        return True
                    elif key == 'rebalance_threshold':
                        return 0.01  # 1% threshold
                return default
        
        config = MinimalConfig(account_config)
        return RebalancingManager(config)
    
    def _create_rebalance_config_for_mode2(self):
        """Crée une config minimale pour le RebalancingManager en mode 2 (Extended <-> Hyperliquid)"""
        class Mode2RebalanceConfig:
            def __init__(self, account1, account2):
                self.account1 = account1  # Extended
                self.account2 = account2  # Hyperliquid
            
            def get(self, section, key, default=None):
                if section == 'wallet':
                    if key == 'address':
                        # Utiliser l'adresse Hyperliquid (même wallet généralement)
                        return self.account2.get('arbitrum_address') or self.account2.get('wallet_address')
                    elif key == 'private_key':
                        # Utiliser la clé privée Hyperliquid
                        return self.account2.get('arbitrum_private_key')
                elif section == 'exchanges':
                    if key == 'extended':
                        # Credentials Extended depuis account1
                        return {
                            'api_key': self.account1.get('api_key'),
                            'public_key': self.account1.get('stark_public_key'),
                            'private_key': self.account1.get('stark_private_key'),
                            'vault_id': self.account1.get('vault_id')
                        }
                elif section == 'arbitrage':
                    if key == 'auto_rebalance':
                        return True
                    elif key == 'rebalance_threshold':
                        # Utiliser le seuil depuis la config dnfarming.json si disponible
                        try:
                            from pathlib import Path
                            import json
                            import os
                            # Chemin relatif depuis dnfarming.py vers config/dnfarming.json
                            base_dir = Path(__file__).parent
                            config_path = base_dir / "config" / "dnfarming.json"
                            if not config_path.exists():
                                # Essayer aussi depuis le répertoire parent
                                config_path = base_dir.parent / "config" / "dnfarming.json"
                            if config_path.exists():
                                with open(config_path, 'r') as f:
                                    dnf_config = json.load(f)
                                    threshold = float(dnf_config.get('rebalance_threshold', 100.0))
                                    logger.debug(f"Seuil de rebalancing chargé depuis dnfarming.json: ${threshold:.2f}")
                                    return threshold
                        except Exception as e:
                            logger.debug(f"Erreur lors du chargement du seuil depuis dnfarming.json: {e}")
                        return 100.0  # Seuil par défaut en USD
                return default
        
        return Mode2RebalanceConfig(self.account1, self.account2)
    
    def _create_rebalance_config_for_mode3(self):
        """Crée une config minimale pour le RebalancingManager en mode 3 (Extended <-> Lighter)"""
        class Mode3RebalanceConfig:
            def __init__(self, account1, account2):
                self.account1 = account1  # Extended
                self.account2 = account2  # Lighter
            
            def get(self, section, key, default=None):
                if section == 'wallet':
                    if key == 'address':
                        # Utiliser l'adresse Lighter
                        return self.account2.get('arbitrum_address') or self.account2.get('wallet_address')
                    elif key == 'private_key':
                        # Utiliser la clé privée Lighter
                        return self.account2.get('arbitrum_private_key')
                elif section == 'exchanges':
                    if key == 'extended':
                        # Credentials Extended depuis account1
                        return {
                            'api_key': self.account1.get('api_key'),
                            'public_key': self.account1.get('stark_public_key'),
                            'private_key': self.account1.get('stark_private_key'),
                            'vault_id': self.account1.get('vault_id')
                        }
                elif section == 'arbitrage':
                    if key == 'auto_rebalance':
                        return True
                    elif key == 'rebalance_threshold':
                        # Utiliser le seuil depuis la config dnfarming.json si disponible
                        try:
                            from pathlib import Path
                            import json
                            import os
                            base_dir = Path(__file__).parent
                            config_path = base_dir / "config" / "dnfarming.json"
                            if not config_path.exists():
                                config_path = base_dir.parent / "config" / "dnfarming.json"
                            if config_path.exists():
                                with open(config_path, 'r') as f:
                                    dnf_config = json.load(f)
                                    threshold = float(dnf_config.get('rebalance_threshold', 100.0))
                                    logger.debug(f"Seuil de rebalancing chargé depuis dnfarming.json: ${threshold:.2f}")
                                    return threshold
                        except Exception as e:
                            logger.debug(f"Erreur lors du chargement du seuil depuis dnfarming.json: {e}")
                        return 100.0  # Seuil par défaut en USD
                return default
        
        return Mode3RebalanceConfig(self.account1, self.account2)
    
    def load_config(self, config_path: str = None) -> Dict:
        """
        Charge la configuration depuis un fichier config.json
        
        Args:
            config_path: Chemin vers le fichier config.json (par défaut: config/dnfarming.json)
        
        Returns:
            Dict avec les paramètres de configuration
        """
        import json
        from pathlib import Path
        
        if config_path is None:
            # Chercher dans config/dnfarming.json ou config.json à la racine
            config_dir = Path(__file__).parent / "config"
            config_path = config_dir / "dnfarming.json"
            
            # Si pas trouvé, essayer config.json à la racine
            if not config_path.exists():
                config_path = Path(__file__).parent / "config.json"
        
        config_path = Path(config_path)
        
        if not config_path.exists():
            logger.error(f"❌ Fichier de configuration non trouvé: {config_path}")
            logger.info("💡 Créez un fichier config/dnfarming.json avec la structure suivante:")
            logger.info("""
{
    "symbol": "BTC",
    "leverage": 3,
    "margin": 100.0,
    "min_duration": 50,
    "max_duration": 70,
    "num_cycles": 5,
    "delay_between_cycles": 0,
    "rebalance_threshold": 10.0
}
""")
            raise FileNotFoundError(f"Configuration file not found: {config_path}")
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            logger.info(f"✅ Configuration chargée depuis: {config_path}")
            
            # Valider les paramètres requis (pnl_check_delay est optionnel, défaut = 5)
            required_params = ['symbol', 'leverage', 'margin', 'min_duration', 'max_duration', 'num_cycles', 'delay_between_cycles', 'rebalance_threshold']
            missing = [p for p in required_params if p not in config]
            if missing:
                raise ValueError(f"Paramètres manquants dans la configuration: {missing}")
            
            # Valider les valeurs
            symbol = str(config['symbol']).strip().upper()
            if not symbol:
                raise ValueError("Le symbole ne peut pas être vide")
            
            leverage = int(config['leverage'])
            if leverage < 1:
                raise ValueError("Le levier doit être >= 1")
            
            margin = float(config['margin'])
            if margin <= 0:
                raise ValueError("La marge doit être > 0")
            
            min_duration = int(config['min_duration'])
            if min_duration <= 0:
                raise ValueError("La durée minimale doit être > 0")
            
            max_duration = int(config['max_duration'])
            if max_duration < min_duration:
                raise ValueError(f"La durée maximale ({max_duration}) doit être >= durée minimale ({min_duration})")
            
            num_cycles = int(config['num_cycles'])
            if num_cycles < 1:
                raise ValueError("Le nombre de cycles doit être >= 1")
            
            delay_between_cycles = int(config.get('delay_between_cycles', 0))
            if delay_between_cycles < 0:
                raise ValueError("Le délai entre les cycles doit être >= 0")
            
            rebalance_threshold = float(config.get('rebalance_threshold', 10.0))
            if rebalance_threshold < 0:
                raise ValueError("Le seuil de rebalancing doit être >= 0")
            
            pnl_check_delay = int(config.get('pnl_check_delay', 5))
            if pnl_check_delay < 0:
                raise ValueError("Le délai de vérification PnL doit être >= 0")
            
            # Option de retrait vers Extended à la fin des cycles (défaut: True)
            withdraw_to_extended = config.get('withdraw_to_extended', True)
            if not isinstance(withdraw_to_extended, bool):
                withdraw_to_extended = str(withdraw_to_extended).lower() in ('true', '1', 'yes', 'oui')
            
            result = {
                'symbol': symbol,
                'leverage': leverage,
                'margin': margin,
                'min_duration': min_duration,
                'max_duration': max_duration,
                'num_cycles': num_cycles,
                'delay_between_cycles': delay_between_cycles,
                'rebalance_threshold': rebalance_threshold,
                'pnl_check_delay': pnl_check_delay,
                'withdraw_to_extended': withdraw_to_extended
            }
            
            # Afficher la configuration chargée
            logger.info("\n" + "="*60)
            logger.info("📋 CONFIGURATION CHARGÉE")
            logger.info("="*60)
            logger.info(f"  Paire: {result['symbol']}")
            logger.info(f"  Levier: {result['leverage']}x")
            logger.info(f"  Marge: ${result['margin']:.2f} USDC")
            logger.info(f"  Durée: {result['min_duration']}-{result['max_duration']} minutes")
            logger.info(f"  Cycles: {result['num_cycles']}")
            logger.info(f"  Délai entre cycles: {result['delay_between_cycles']} minutes")
            logger.info(f"  Seuil de rebalancing: ${result['rebalance_threshold']:.2f}")
            logger.info(f"  Délai vérif. PnL: {result['pnl_check_delay']} minutes")
            logger.info(f"  Retrait vers Extended: {'✅ Activé' if result['withdraw_to_extended'] else '❌ Désactivé'}")
            logger.info("="*60 + "\n")
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ Erreur de parsing JSON dans {config_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ Erreur lors du chargement de la configuration: {e}")
            raise
    
    def check_initial_balances(self) -> Tuple[float, float]:
        """Vérifie les balances initiales des deux comptes"""
        logger.info("Vérification des balances initiales...")
        
        if self.mode == 1:
            # Mode 1: Deux comptes Extended
            balance1 = self.client1.get_balance()
            balance2 = self.client2.get_balance()
            
            bal1 = balance1.get('total', 0) if isinstance(balance1, dict) else balance1
            bal2 = balance2.get('total', 0) if isinstance(balance2, dict) else balance2
            
            logger.info(f"Extended Compte 1: ${bal1:,.2f} USDC")
            logger.info(f"Extended Compte 2: ${bal2:,.2f} USDC")
        elif self.mode == 2:
            # Mode 2: Extended + Hyperliquid
            balance1 = self.client1.get_balance()
            balance2 = self.hyperliquid_client.get_balance()
            
            bal1 = balance1.get('total', 0) if isinstance(balance1, dict) else balance1
            bal2 = balance2 if isinstance(balance2, (int, float)) else 0.0
            
            logger.info(f"Extended: ${bal1:,.2f} USDC")
            logger.info(f"Hyperliquid: ${bal2:,.2f} USDC")
        else:
            # Mode 3: Extended + Lighter
            balance1 = self.client1.get_balance()
            balance2 = self.lighter_client.get_balance()
            
            bal1 = balance1.get('total', 0) if isinstance(balance1, dict) else balance1
            bal2 = balance2 if isinstance(balance2, (int, float)) else 0.0
            
            logger.info(f"Extended: ${bal1:,.2f} USDC")
            logger.info(f"Lighter: ${bal2:,.2f} USDC")
        
        return bal1, bal2
    
    def transfer_all_funds_to_account1(self) -> bool:
        """
        Transfère tous les fonds vers le compte 1 Extended
        
        Mode 1: Transfère depuis Extended compte 2 vers Extended compte 1
        Mode 2: Transfère depuis Hyperliquid vers Extended compte 1
        
        Returns:
            True si succès
        """
        logger.info("\n" + "="*60)
        logger.info("💰 TRANSFERT DE TOUS LES FONDS VERS LE COMPTE 1 EXTENDED")
        logger.info("="*60)
        
        try:
            # Récupérer les balances actuelles
            bal1, bal2 = self.check_initial_balances()
            
            if self.mode == 1:
                # Mode 1: Extended compte 2 -> Extended compte 1
                logger.info(f"Mode 1: Transfert depuis Extended compte 2 (${bal2:,.2f}) vers Extended compte 1")
                
                if bal2 < 5.0:  # Minimum pour un transfert
                    logger.warning(f"⚠️  Solde du compte 2 trop faible (${bal2:,.2f} < $5.00), pas de transfert nécessaire")
                    return True
                
                # Utiliser le RebalancingManager pour transférer
                # On transfère tout le solde du compte 2 vers le compte 1
                logger.info(f"📤 Retrait de ${bal2:,.2f} depuis Extended compte 2 vers Arbitrum...")
                
                # Récupérer l'adresse Arbitrum du compte 2 (source) et du compte 1 (destination)
                account2_address = self.account2.get('arbitrum_address') or self.account2.get('wallet_address')
                account1_address = self.account1.get('arbitrum_address') or self.account1.get('wallet_address')
                
                if not account2_address:
                    logger.error("❌ Adresse Arbitrum du compte 2 non trouvée")
                    return False
                if not account1_address:
                    logger.error("❌ Adresse Arbitrum du compte 1 non trouvée")
                    return False
                
                # Retirer depuis le compte 2 (vers son adresse Arbitrum)
                withdraw_result = self.rebalance_manager2.withdraw_extended(bal2)
                
                if withdraw_result.get('status') != 'success':
                    error_msg = withdraw_result.get('message', 'Unknown error')
                    logger.error(f"❌ Échec du retrait Extended compte 2: {error_msg}")
                    return False
                
                logger.success(f"✅ Retrait Extended compte 2 initié: {withdraw_result.get('withdrawal_id', 'N/A')}")
                bridge_fee = withdraw_result.get('bridge_fee', 0)
                expected_amount = bal2 - bridge_fee if bridge_fee > 0 else bal2 * 0.9975
                
                logger.info(f"⏳ Attente de la finalisation du bridge (environ 5-10 minutes)...")
                logger.info(f"   Montant retiré: ${bal2:,.2f}")
                logger.info(f"   Frais bridge: ${bridge_fee:,.2f}")
                logger.info(f"   Montant attendu sur Arbitrum: ${expected_amount:,.2f}")
                
                # Attendre que les fonds arrivent sur Arbitrum
                if not HAS_WEB3:
                    logger.error("web3 not available, cannot check Arbitrum balance")
                    return False
                
                from web3 import Web3
                w3 = Web3(Web3.HTTPProvider("https://arb1.arbitrum.io/rpc"))
                
                min_expected = expected_amount * 0.95
                logger.info(f"Vérification du solde USDC sur Arbitrum pour {account2_address}...")
                
                # Attendre jusqu'à 10 minutes que les fonds arrivent sur l'adresse du compte 2
                if not self._wait_for_arbitrum_balance_simple(w3, account2_address, min_expected, max_wait_seconds=600):
                    logger.error("❌ Le retrait n'a pas été finalisé dans les temps")
                    return False
                
                # Récupérer le solde réel sur l'adresse du compte 2
                actual_balance = self._get_arbitrum_balance_simple(w3, account2_address)
                
                # Si les deux comptes ont des adresses Arbitrum différentes, on doit transférer on-chain
                if account2_address.lower() != account1_address.lower():
                    logger.info(f"Les deux comptes ont des adresses Arbitrum différentes")
                    logger.info(f"   Compte 2: {account2_address}")
                    logger.info(f"   Compte 1: {account1_address}")
                    logger.info(f"📤 Transfert on-chain de ${actual_balance:,.2f} USDC depuis {account2_address} vers {account1_address}...")
                    
                    # Transférer on-chain depuis l'adresse du compte 2 vers l'adresse du compte 1
                    transfer_success = self._transfer_usdc_on_chain(
                        w3,
                        account2_address,
                        account1_address,
                        actual_balance,
                        self.account2.get('arbitrum_private_key')
                    )
                    
                    if not transfer_success:
                        logger.error("❌ Échec du transfert on-chain")
                        return False
                    
                    logger.success("✅ Transfert on-chain réussi")
                    logger.info(f"⏳ Attente de quelques secondes pour que les fonds arrivent sur {account1_address}...")
                    time.sleep(5)
                    
                    # Vérifier que les fonds sont arrivés sur l'adresse du compte 1
                    balance_account1 = self._get_arbitrum_balance_simple(w3, account1_address)
                    if balance_account1 < actual_balance * 0.95:  # Tolérance de 5%
                        logger.warning(f"⚠️  Les fonds ne semblent pas encore arrivés (solde: ${balance_account1:,.2f})")
                        logger.warning("⚠️  Attente supplémentaire...")
                        time.sleep(10)
                        balance_account1 = self._get_arbitrum_balance_simple(w3, account1_address)
                    
                    actual_balance = balance_account1
                    logger.info(f"✅ Solde disponible sur l'adresse du compte 1: ${actual_balance:,.2f} USDC")
                if actual_balance > 0:
                    deposit_amount = actual_balance
                    logger.info(f"✅ Solde disponible sur Arbitrum: ${deposit_amount:,.2f} USDC")
                else:
                    deposit_amount = expected_amount
                    logger.warning(f"⚠️  Impossible de récupérer le solde exact, utilisation de l'estimation: ${deposit_amount:,.2f}")
                
                # Déposer vers Extended compte 1
                logger.info(f"📥 Dépôt de ${deposit_amount:,.2f} depuis Arbitrum vers Extended compte 1...")
                deposit_result = self.rebalance_manager1.deposit_extended(deposit_amount)
                
                if deposit_result.get('status') != 'success':
                    error_msg = deposit_result.get('message', 'Unknown error')
                    logger.error(f"❌ Échec du dépôt Extended compte 1: {error_msg}")
                    return False
                
                logger.success(f"✅ Dépôt Extended compte 1 réussi: {deposit_result.get('transaction_hash', 'N/A')}")
                logger.info("⏳ Le dépôt sera crédité sur votre compte Extended après traitement du bridge")
                
            elif self.mode == 2:
                # Mode 2: Hyperliquid -> Extended compte 1
                logger.info(f"Mode 2: Transfert depuis Hyperliquid (${bal2:,.2f}) vers Extended compte 1")
                
                if bal2 < 5.0:  # Minimum pour un transfert
                    logger.warning(f"⚠️  Solde Hyperliquid trop faible (${bal2:,.2f} < $5.00), pas de transfert nécessaire")
                    return True
                
                # Utiliser le RebalancingManager pour transférer
                logger.info(f"📤 Retrait de ${bal2:,.2f} depuis Hyperliquid vers Arbitrum...")
                
                # Récupérer l'adresse Arbitrum du compte 1 (destination)
                account1_address = self.account1.get('arbitrum_address') or self.account1.get('wallet_address')
                if not account1_address:
                    logger.error("❌ Adresse Arbitrum du compte 1 non trouvée")
                    return False
                
                # Retirer depuis Hyperliquid
                withdraw_result = self.rebalance_manager2.withdraw_hyperliquid(bal2, account1_address)
                
                if withdraw_result.get('status') != 'success':
                    error_msg = withdraw_result.get('message', 'Unknown error')
                    logger.error(f"❌ Échec du retrait Hyperliquid: {error_msg}")
                    return False
                
                logger.success(f"✅ Retrait Hyperliquid initié vers {account1_address}")
                logger.info("⏳ Attente de la finalisation du bridge Hyperliquid (environ 5 minutes)...")
                logger.info("   Note: Frais de retrait Hyperliquid = $1.00")
                
                expected_amount = bal2 - 1.0  # Frais Hyperliquid de $1
                
                # Attendre que les fonds arrivent sur Arbitrum
                if not HAS_WEB3:
                    logger.error("web3 not available, cannot check Arbitrum balance")
                    return False
                
                from web3 import Web3
                w3 = Web3(Web3.HTTPProvider("https://arb1.arbitrum.io/rpc"))
                
                min_expected = expected_amount * 0.95
                logger.info(f"Vérification du solde USDC sur Arbitrum pour {account1_address}...")
                
                # Attendre jusqu'à 10 minutes
                if not self._wait_for_arbitrum_balance_simple(w3, account1_address, min_expected, max_wait_seconds=600):
                    logger.error("❌ Le retrait Hyperliquid n'a pas été finalisé dans les temps")
                    return False
                
                # Récupérer le solde réel
                actual_balance = self._get_arbitrum_balance_simple(w3, account1_address)
                if actual_balance > 0:
                    deposit_amount = actual_balance
                    logger.info(f"✅ Solde disponible sur Arbitrum: ${deposit_amount:,.2f} USDC")
                else:
                    deposit_amount = expected_amount
                    logger.warning(f"⚠️  Impossible de récupérer le solde exact, utilisation de l'estimation: ${deposit_amount:,.2f}")
                
                # Déposer vers Extended compte 1
                logger.info(f"📥 Dépôt de ${deposit_amount:,.2f} depuis Arbitrum vers Extended compte 1...")
                deposit_result = self.rebalance_manager1.deposit_extended(deposit_amount)
                
                if deposit_result.get('status') != 'success':
                    error_msg = deposit_result.get('message', 'Unknown error')
                    logger.error(f"❌ Échec du dépôt Extended compte 1: {error_msg}")
                    return False
                
                logger.success(f"✅ Dépôt Extended compte 1 réussi: {deposit_result.get('transaction_hash', 'N/A')}")
                logger.info("⏳ Le dépôt sera crédité sur votre compte Extended après traitement du bridge")
            
            else:
                # Mode 3: Lighter -> Extended compte 1
                logger.info(f"Mode 3: Transfert depuis Lighter (${bal2:,.2f}) vers Extended compte 1")
                
                if bal2 < 5.0:  # Minimum pour un transfert
                    logger.warning(f"⚠️  Solde Lighter trop faible (${bal2:,.2f} < $5.00), pas de transfert nécessaire")
                    return True
                
                # Récupérer l'adresse Arbitrum du compte 1 (destination)
                account1_address = self.account1.get('arbitrum_address') or self.account1.get('wallet_address')
                if not account1_address:
                    logger.error("❌ Adresse Arbitrum du compte 1 non trouvée")
                    return False
                
                # Retirer depuis Lighter
                logger.info(f"📤 Retrait de ${bal2:,.2f} depuis Lighter vers Arbitrum...")
                withdraw_result = self.lighter_client.withdraw(bal2, account1_address, fast=True)
                
                if not withdraw_result or withdraw_result.get('status') != 'success':
                    error_msg = withdraw_result.get('message', 'Unknown error') if withdraw_result else 'Withdrawal failed'
                    logger.error(f"❌ Échec du retrait Lighter: {error_msg}")
                    return False
                
                logger.success(f"✅ Retrait Lighter initié vers {account1_address}")
                logger.info("⏳ Attente de la finalisation du retrait Lighter...")
                
                expected_amount = bal2  # Lighter a généralement des frais minimaux
                
                # Attendre que les fonds arrivent sur Arbitrum
                if not HAS_WEB3:
                    logger.error("web3 not available, cannot check Arbitrum balance")
                    return False
                
                from web3 import Web3
                w3 = Web3(Web3.HTTPProvider("https://arb1.arbitrum.io/rpc"))
                
                min_expected = expected_amount * 0.95
                logger.info(f"Vérification du solde USDC sur Arbitrum pour {account1_address}...")
                
                # Attendre jusqu'à 10 minutes
                if not self._wait_for_arbitrum_balance_simple(w3, account1_address, min_expected, max_wait_seconds=600):
                    logger.error("❌ Le retrait Lighter n'a pas été finalisé dans les temps")
                    return False
                
                # Récupérer le solde réel
                actual_balance = self._get_arbitrum_balance_simple(w3, account1_address)
                if actual_balance > 0:
                    deposit_amount = actual_balance
                    logger.info(f"✅ Solde disponible sur Arbitrum: ${deposit_amount:,.2f} USDC")
                else:
                    deposit_amount = expected_amount
                    logger.warning(f"⚠️  Impossible de récupérer le solde exact, utilisation de l'estimation: ${deposit_amount:,.2f}")
                
                # Déposer vers Extended compte 1
                logger.info(f"📥 Dépôt de ${deposit_amount:,.2f} depuis Arbitrum vers Extended compte 1...")
                deposit_result = self.rebalance_manager1.deposit_extended(deposit_amount)
                
                if deposit_result.get('status') != 'success':
                    error_msg = deposit_result.get('message', 'Unknown error')
                    logger.error(f"❌ Échec du dépôt Extended compte 1: {error_msg}")
                    return False
                
                logger.success(f"✅ Dépôt Extended compte 1 réussi: {deposit_result.get('transaction_hash', 'N/A')}")
                logger.info("⏳ Le dépôt sera crédité sur votre compte Extended après traitement du bridge")
            
            logger.success("\n✅ Transfert de tous les fonds vers le compte 1 Extended initié avec succès!")
            logger.info("⏳ Les fonds seront crédités après le traitement du bridge (5-10 minutes)")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur lors du transfert de tous les fonds: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _get_arbitrum_balance_simple(self, w3, address: str) -> float:
        """Récupère le solde USDC sur Arbitrum pour une adresse"""
        try:
            erc20_abi = [
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function"
                }
            ]
            
            usdc_contract = w3.eth.contract(
                address=Web3.to_checksum_address("0xaf88d065e77c8cC2239327C5EDb3A432268e5831"),  # USDC on Arbitrum
                abi=erc20_abi
            )
            
            balance = usdc_contract.functions.balanceOf(
                Web3.to_checksum_address(address)
            ).call()
            return balance / 1e6  # USDC a 6 décimales
        except Exception as e:
            logger.error(f"Erreur lors de la récupération du solde Arbitrum: {e}")
            return 0.0
    
    def _wait_for_arbitrum_balance_simple(self, w3, address: str, min_balance: float, max_wait_seconds: int = 600) -> bool:
        """Attend que le solde USDC sur Arbitrum atteigne un minimum"""
        try:
            from web3 import Web3
            check_interval = 10  # Vérifier toutes les 10 secondes
            start_time = time.time()
            
            while time.time() - start_time < max_wait_seconds:
                balance = self._get_arbitrum_balance_simple(w3, address)
                
                if balance >= min_balance:
                    logger.success(f"✅ Solde disponible: ${balance:,.2f} USDC")
                    return True
                
                elapsed = int(time.time() - start_time)
                remaining = max_wait_seconds - elapsed
                logger.info(f"⏳ Attente du solde... (${balance:,.2f} / ${min_balance:,.2f} requis) - {remaining}s restantes")
                time.sleep(check_interval)
            
            logger.error(f"⏱️  Timeout: Le solde n'est pas disponible après {max_wait_seconds} secondes")
            return False
        except Exception as e:
            logger.error(f"Erreur lors de l'attente du solde: {e}")
            return False
    
    def _transfer_usdc_on_chain(self, w3, from_address: str, to_address: str, amount: float, private_key: str) -> bool:
        """
        Transfère des USDC on-chain entre deux adresses Arbitrum
        
        Args:
            w3: Instance Web3 connectée à Arbitrum
            from_address: Adresse source
            to_address: Adresse destination
            amount: Montant en USDC
            private_key: Clé privée de l'adresse source
            
        Returns:
            True si succès
        """
        if not HAS_WEB3:
            logger.error("web3 not available")
            return False
        
        try:
            from web3 import Web3
            import eth_account
            
            # Vérifier que la clé privée correspond à l'adresse source
            account = eth_account.Account.from_key(private_key)
            if account.address.lower() != from_address.lower():
                logger.error(f"❌ La clé privée ne correspond pas à l'adresse source")
                logger.error(f"   Adresse attendue: {from_address}")
                logger.error(f"   Adresse de la clé: {account.address}")
                return False
            
            # ABI pour USDC (transfer et balanceOf)
            erc20_abi = [
                {
                    "constant": False,
                    "inputs": [
                        {"name": "_to", "type": "address"},
                        {"name": "_value", "type": "uint256"}
                    ],
                    "name": "transfer",
                    "outputs": [{"name": "", "type": "bool"}],
                    "type": "function"
                },
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function"
                }
            ]
            
            # Adresse USDC sur Arbitrum
            usdc_address = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
            
            # Créer le contrat USDC
            usdc_contract = w3.eth.contract(
                address=Web3.to_checksum_address(usdc_address),
                abi=erc20_abi
            )
            
            # Vérifier le solde disponible
            balance = usdc_contract.functions.balanceOf(
                Web3.to_checksum_address(from_address)
            ).call()
            balance_usd = balance / 1e6  # USDC a 6 décimales
            
            if balance_usd < amount:
                logger.error(f"❌ Solde insuffisant: ${balance_usd:,.2f} < ${amount:,.2f}")
                return False
            
            # Convertir le montant en wei (USDC a 6 décimales)
            amount_wei = int(amount * 1e6)
            
            # Obtenir le nonce
            nonce = w3.eth.get_transaction_count(from_address)
            
            # Obtenir les paramètres de gas EIP-1559
            gas_params = self.rebalance_manager1._get_gas_params(w3)
            
            # Construire la transaction transfer
            transaction = usdc_contract.functions.transfer(
                Web3.to_checksum_address(to_address),
                amount_wei
            ).build_transaction({
                'from': from_address,
                'nonce': nonce,
                'gas': 100000,  # Gas limit pour un transfer ERC20
                'chainId': 42161,  # Arbitrum mainnet chain ID
                **gas_params  # Ajouter maxFeePerGas et maxPriorityFeePerGas ou gasPrice
            })
            
            # Signer la transaction
            signed_txn = w3.eth.account.sign_transaction(transaction, private_key)
            
            # Envoyer la transaction
            logger.info("Envoi de la transaction de transfert on-chain...")
            raw_tx = signed_txn.raw_transaction if hasattr(signed_txn, 'raw_transaction') else signed_txn.rawTransaction
            tx_hash = w3.eth.send_raw_transaction(raw_tx)
            
            logger.info(f"Transaction envoyée: {tx_hash.hex()}")
            logger.info("Attente de la confirmation...")
            
            # Attendre la confirmation
            tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if tx_receipt.status == 1:
                logger.success(f"✅ Transfert on-chain réussi! Transaction: {tx_hash.hex()}")
                return True
            else:
                logger.error(f"❌ La transaction a échoué: {tx_hash.hex()}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Erreur lors du transfert on-chain: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def rebalance_accounts(self) -> bool:
        """
        Rebalance les deux comptes pour qu'ils aient le même montant
        
        Mode 1: Deux comptes Extended
        Mode 2: Extended <-> Hyperliquid
        Mode 3: Extended <-> Lighter
        """
        logger.info("🔄 Début du rebalancing...")
        
        if self.mode == 2:
            # Mode 2: Utiliser le RebalancingManager qui gère Extended <-> Hyperliquid
            return self.rebalance_manager2.auto_rebalance_if_needed()
        
        if self.mode == 3:
            # Mode 3: Extended <-> Lighter
            return self._rebalance_extended_lighter()
        
        # Mode 1: Deux comptes Extended (code existant)
        # Récupérer les balances
        balance1 = self.client1.get_balance()
        balance2 = self.client2.get_balance()
        
        bal1 = balance1.get('total', 0) if isinstance(balance1, dict) else balance1
        bal2 = balance2.get('total', 0) if isinstance(balance2, dict) else balance2
        
        logger.info(f"Balance compte 1: ${bal1:,.2f} USDC")
        logger.info(f"Balance compte 2: ${bal2:,.2f} USDC")
        
        # Calculer la différence
        diff = abs(bal1 - bal2)
        if diff < 1.0:  # Moins de 1 USDC de différence, pas besoin de rebalancer
            logger.info("✅ Les balances sont déjà équilibrées")
            return True
        
        # Déterminer quel compte a le plus
        if bal1 > bal2:
            from_account = 1
            to_account = 2
            amount_to_transfer = diff / 2  # Transférer la moitié de la différence
        else:
            from_account = 2
            to_account = 1
            amount_to_transfer = diff / 2
        
        logger.info(f"Transfert de ${amount_to_transfer:,.2f} USDC du compte {from_account} vers le compte {to_account}")
        
        # Étape 1: Retirer depuis Extended vers Arbitrum (compte source)
        if from_account == 1:
            rebalance_mgr = self.rebalance_manager1
            client_from = self.client1
            from_private_key = self.account1.get('arbitrum_private_key')
            from_address = self.account1.get('arbitrum_address') or self.account1['wallet_address']
        else:
            rebalance_mgr = self.rebalance_manager2
            client_from = self.client2
            from_private_key = self.account2.get('arbitrum_private_key')
            from_address = self.account2.get('arbitrum_address') or self.account2['wallet_address']
        
        logger.info(f"Étape 1: Retrait de ${amount_to_transfer:,.2f} depuis Extended (compte {from_account}) vers Arbitrum...")
        
        # Essayer le retrait avec retries en cas d'erreur serveur
        max_retries = 3
        retry_delay = 5  # secondes
        withdraw_result = None
        
        for attempt in range(1, max_retries + 1):
            withdraw_result = rebalance_mgr.withdraw_extended(amount_to_transfer)
            
            if withdraw_result.get('status') == 'success':
                break
            
            error_msg = withdraw_result.get('message', 'Unknown error')
            
            # Si c'est une erreur 500 (Internal Server Error), on peut réessayer
            if '500' in str(error_msg) or 'Internal Server Error' in str(error_msg):
                if attempt < max_retries:
                    logger.warning(f"⚠️  Erreur serveur (tentative {attempt}/{max_retries}), nouvelle tentative dans {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Backoff exponentiel
                else:
                    logger.error(f"❌ Échec du retrait après {max_retries} tentatives: {error_msg}")
                    logger.error("💡 Suggestions:")
                    logger.error("   - Vérifiez que le compte Extended a suffisamment de fonds")
                    logger.error("   - Vérifiez que le bridge Extended est opérationnel")
                    logger.error("   - Réessayez plus tard si c'est une erreur temporaire du serveur")
                    return False
            else:
                # Autre type d'erreur, ne pas réessayer
                logger.error(f"❌ Échec du retrait: {error_msg}")
                return False
        
        if withdraw_result.get('status') != 'success':
            logger.error(f"❌ Échec du retrait: {withdraw_result.get('message', 'Unknown error')}")
            return False
        
        logger.success(f"✅ Retrait réussi: {withdraw_result.get('withdrawal_id', 'N/A')}")
        logger.info("⏳ Attente de la finalisation du bridge (environ 5-10 minutes)...")
        
        # Calculer le montant attendu sur Arbitrum (montant retiré - frais de bridge ~0.25%)
        bridge_fee = withdraw_result.get('bridge_fee', 0)
        if bridge_fee > 0:
            expected_amount = amount_to_transfer - bridge_fee
            logger.info(f"Montant retiré: ${amount_to_transfer:.2f}, Frais bridge: ${bridge_fee:.2f}")
        else:
            # Si les frais ne sont pas disponibles, utiliser 0.25% comme estimation
            expected_amount = amount_to_transfer * 0.9975  # 1 - 0.25% = 99.75%
            logger.info(f"Montant retiré: ${amount_to_transfer:.2f}, Montant attendu (estimation -0.25%): ${expected_amount:.2f}")
        
        # Attendre que le retrait soit finalisé en vérifiant le solde Arbitrum
        # On accepte un montant légèrement inférieur (95% du montant attendu) pour gérer les variations
        logger.info(f"Vérification du solde USDC sur Arbitrum pour {from_address}...")
        min_expected = expected_amount * 0.95  # 95% du montant attendu après frais
        if not self.wait_for_arbitrum_balance(from_address, min_expected, max_wait_seconds=600):
            logger.error("❌ Le retrait n'a pas été finalisé dans les temps")
            return False
        
        # Récupérer le solde réel reçu sur Arbitrum
        actual_balance = self._get_arbitrum_balance(from_address)
        if actual_balance > 0:
            logger.info(f"✅ Solde reçu sur Arbitrum: ${actual_balance:.2f} USDC")
            # Utiliser le solde réel pour le transfert
            amount_to_transfer_arbitrum = actual_balance
        else:
            # Fallback sur le montant attendu
            amount_to_transfer_arbitrum = expected_amount
            logger.warning(f"⚠️  Impossible de récupérer le solde exact, utilisation de l'estimation: ${amount_to_transfer_arbitrum:.2f}")
        
        # Étape 2: Envoyer les USDC depuis Arbitrum du compte source vers le compte destination
        if to_account == 1:
            dest_address = self.account1.get('arbitrum_address') or self.account1['wallet_address']
            rebalance_mgr_dest = self.rebalance_manager1
        else:
            dest_address = self.account2.get('arbitrum_address') or self.account2['wallet_address']
            rebalance_mgr_dest = self.rebalance_manager2
        
        # Vérifier que la clé privée Arbitrum est disponible
        if not from_private_key:
            logger.error(f"❌ Clé privée Arbitrum manquante pour le compte {from_account}")
            logger.error(f"Ajoutez ACCOUNT{from_account}_ARBITRUM_PRIVATE_KEY dans le fichier .env")
            return False
        
        # Vérifier que l'adresse Arbitrum est disponible
        if not from_address:
            logger.error(f"❌ Adresse Arbitrum manquante pour le compte {from_account}")
            logger.error(f"Ajoutez ACCOUNT{from_account}_ARBITRUM_ADDRESS dans le fichier .env")
            return False
        
        logger.info(f"Étape 2: Transfert automatique de ${amount_to_transfer_arbitrum:,.2f} USDC sur Arbitrum...")
        logger.info(f"  De: {from_address}")
        logger.info(f"  Vers: {dest_address}")
        logger.info(f"  (Montant ajusté selon le solde réel reçu après frais de bridge)")
        
        transfer_result = self.transfer_usdc_on_arbitrum(
            from_private_key=from_private_key,
            to_address=dest_address,
            amount=amount_to_transfer_arbitrum
        )
        
        if transfer_result.get('status') != 'success':
            logger.error(f"❌ Échec du transfert Arbitrum: {transfer_result.get('message', 'Unknown error')}")
            return False
        
        logger.success(f"✅ Transfert Arbitrum réussi: {transfer_result.get('transaction_hash', 'N/A')}")
        
        # Attendre que le transfert soit confirmé et que le solde soit disponible sur le compte destination
        logger.info(f"Vérification du solde USDC sur Arbitrum pour {dest_address}...")
        if not self.wait_for_arbitrum_balance(dest_address, amount_to_transfer_arbitrum * 0.95, max_wait_seconds=120):
            logger.warning("⚠️  Le solde n'est pas encore disponible, mais on continue...")
        
        # Récupérer le solde réel sur le compte destination
        actual_dest_balance = self._get_arbitrum_balance(dest_address)
        if actual_dest_balance > 0:
            deposit_amount = actual_dest_balance
            logger.info(f"Solde disponible sur Arbitrum (compte destination): ${deposit_amount:.2f} USDC")
        else:
            deposit_amount = amount_to_transfer_arbitrum
            logger.warning(f"⚠️  Impossible de récupérer le solde exact, utilisation de l'estimation: ${deposit_amount:.2f}")
        
        # Étape 3: Déposer depuis Arbitrum vers Extended (compte destination)
        logger.info(f"Étape 3: Dépôt de ${deposit_amount:,.2f} depuis Arbitrum vers Extended (compte {to_account})...")
        deposit_result = rebalance_mgr_dest.deposit_extended(deposit_amount)
        
        if deposit_result.get('status') != 'success':
            logger.error(f"❌ Échec du dépôt: {deposit_result.get('message', 'Unknown error')}")
            return False
        
        logger.success(f"✅ Dépôt réussi: {deposit_result.get('transaction_hash', 'N/A')}")
        logger.info("⏳ Attente de la finalisation du bridge (environ 1-2 minutes)...")
        time.sleep(120)  # 2 minutes
        
        # Vérifier les nouvelles balances
        balance1_new = self.client1.get_balance()
        balance2_new = self.client2.get_balance()
        
        bal1_new = balance1_new.get('total', 0)
        bal2_new = balance2_new.get('total', 0)
        
        logger.info(f"Nouvelles balances:")
        logger.info(f"  Compte 1: ${bal1_new:,.2f} USDC")
        logger.info(f"  Compte 2: ${bal2_new:,.2f} USDC")
        
        logger.success("✅ Rebalancing terminé")
        return True
    
    def _rebalance_extended_lighter(self) -> bool:
        """
        Rebalance entre Extended (compte 1) et Lighter (compte 2)
        
        Returns:
            True si succès, False sinon
        """
        logger.info("🔄 Rebalancing Extended <-> Lighter...")
        
        # Récupérer les balances
        balance1 = self.client1.get_balance()
        balance2 = self.lighter_client.get_balance()
        
        bal1 = balance1.get('total', 0) if isinstance(balance1, dict) else balance1
        bal2 = balance2 if isinstance(balance2, (int, float)) else 0
        
        logger.info(f"Balance Extended (compte 1): ${bal1:,.2f} USDC")
        logger.info(f"Balance Lighter (compte 2): ${bal2:,.2f} USDC")
        
        # Calculer la différence
        diff = abs(bal1 - bal2)
        if diff < 1.0:  # Moins de 1 USDC de différence, pas besoin de rebalancer
            logger.info("✅ Les balances sont déjà équilibrées")
            return True
        
        # Déterminer la direction du transfert
        if bal1 > bal2:
            # Extended -> Lighter
            from_account = 1
            to_account = 2
            amount_to_transfer = diff / 2
            logger.info(f"Transfert de ${amount_to_transfer:,.2f} USDC d'Extended vers Lighter")
            
            # Étape 1: Retirer depuis Extended vers Arbitrum
            logger.info("=" * 70)
            logger.info("🔄 REBALANCING: Extended → Lighter")
            logger.info("=" * 70)
            logger.info(f"Étape 1: Retrait de ${amount_to_transfer:,.2f} USDC depuis Extended vers Arbitrum...")
            withdraw_result = self.rebalance_manager1.withdraw_extended(amount_to_transfer)
            
            if withdraw_result.get('status') != 'success':
                logger.error(f"❌ Échec du retrait Extended: {withdraw_result.get('message', 'Unknown error')}")
                return False
            
            logger.success(f"✅ Retrait Extended réussi: {withdraw_result.get('withdrawal_id', 'N/A')}")
            
            # Calculer le montant attendu sur Arbitrum
            bridge_fee = withdraw_result.get('bridge_fee', 0)
            if bridge_fee > 0:
                expected_amount = amount_to_transfer - bridge_fee
                logger.info(f"Montant retiré: ${amount_to_transfer:.2f}, Frais bridge: ${bridge_fee:.2f}")
            else:
                expected_amount = amount_to_transfer * 0.9975  # Estimation -0.25%
                logger.info(f"Montant retiré: ${amount_to_transfer:.2f}, Montant attendu (estimation): ${expected_amount:.2f}")
            
            # Attendre que le retrait soit finalisé
            from_address = self.account1.get('arbitrum_address') or self.account1['wallet_address']
            logger.info(f"Vérification du solde USDC sur Arbitrum pour {from_address}...")
            min_expected = expected_amount * 0.95
            if not self.wait_for_arbitrum_balance(from_address, min_expected, max_wait_seconds=600):
                logger.error("❌ Le retrait Extended n'a pas été finalisé dans les temps")
                return False
            
            # Récupérer le solde réel
            actual_balance = self._get_arbitrum_balance(from_address)
            if actual_balance > 0:
                deposit_amount = actual_balance
                logger.info(f"✅ Solde disponible sur Arbitrum: ${deposit_amount:.2f} USDC")
            else:
                deposit_amount = expected_amount
                logger.warning(f"⚠️  Utilisation de l'estimation: ${deposit_amount:.2f}")
            
            # Étape 2: Déposer vers Lighter depuis Arbitrum
            logger.info(f"Étape 2: Dépôt de ${deposit_amount:,.2f} USDC depuis Arbitrum vers Lighter...")
            
            # Récupérer la clé privée Arbitrum du compte 1
            from_private_key = self.account1.get('arbitrum_private_key')
            if not from_private_key:
                logger.error("❌ Clé privée Arbitrum manquante pour le compte 1")
                logger.error("   Ajoutez ACCOUNT1_ARBITRUM_PRIVATE_KEY dans le fichier .env")
                return False
            
            # Utiliser la méthode deposit de Lighter
            deposit_result = self.lighter_client.deposit(
                amount=deposit_amount,
                from_address=from_address,
                private_key=from_private_key
            )
            
            if not deposit_result or deposit_result.get('status') != 'success':
                error_msg = deposit_result.get('message', 'Unknown error') if deposit_result else 'Deposit failed'
                logger.error(f"❌ Échec du dépôt automatique Lighter: {error_msg}")
                logger.warning("")
                logger.warning("=" * 70)
                logger.warning("⚠️  DÉPÔT MANUEL NÉCESSAIRE VERS LIGHTER")
                logger.warning("=" * 70)
                logger.warning(f"   Montant à déposer: ${deposit_amount:,.2f} USDC")
                logger.warning("")
                logger.warning("   Instructions pour déposer manuellement:")
                logger.warning("   1. Allez sur https://lighter.xyz")
                logger.warning("   2. Connectez-vous avec votre wallet (même adresse que le compte)")
                logger.warning("   3. Allez dans la section 'Deposit' ou 'Bridge'")
                logger.warning("   4. Sélectionnez Arbitrum comme source")
                logger.warning("   5. Déposez les USDC depuis votre wallet Arbitrum")
                logger.warning(f"   6. Montant: ${deposit_amount:,.2f} USDC")
                logger.warning("")
                logger.warning("   ⚠️  Le bot va continuer mais Lighter ne sera pas utilisable")
                logger.warning("      jusqu'à ce que le dépôt soit effectué manuellement.")
                logger.warning("")
                logger.warning("   Une fois le dépôt effectué sur lighter.xyz,")
                logger.warning("   relancez le bot pour continuer le rebalancing.")
                logger.warning("=" * 70)
                logger.warning("")
                # Retourner False pour indiquer l'échec, mais permettre au bot de continuer
                # Le bot pourra quand même fonctionner avec Extended seul
                return False
            
            logger.success(f"✅ Dépôt Lighter initié: {deposit_result.get('transaction_hash', 'N/A')}")
            logger.info("⏳ Le dépôt sera crédité sur votre compte Lighter après traitement du bridge")
            logger.info("⏳ Attente de 5 minutes pour que le bridge traite le dépôt...")
            
            # Attendre que le dépôt soit crédité sur Lighter
            max_wait_seconds = 600  # 10 minutes max
            wait_interval = 30  # Vérifier toutes les 30 secondes
            elapsed = 0
            
            while elapsed < max_wait_seconds:
                time.sleep(wait_interval)
                elapsed += wait_interval
                
                # Vérifier le solde Lighter
                balance2_check = self.lighter_client.get_balance()
                bal2_check = balance2_check if isinstance(balance2_check, (int, float)) else balance2_check
                
                if bal2_check >= deposit_amount * 0.95:  # Au moins 95% du montant déposé
                    logger.success(f"✅ Dépôt crédité sur Lighter: ${bal2_check:.2f} USDC")
                    break
                else:
                    logger.info(f"⏳ Attente... ({elapsed}/{max_wait_seconds}s) - Solde actuel: ${bal2_check:.2f} USDC")
            
            if elapsed >= max_wait_seconds:
                logger.warning(f"⚠️  Le dépôt n'a pas été crédité dans les temps ({max_wait_seconds}s)")
                logger.warning("   Le bot continuera mais Lighter peut ne pas avoir les fonds nécessaires")
            
        else:
            # Lighter -> Extended
            from_account = 2
            to_account = 1
            amount_to_transfer = diff / 2
            logger.info(f"Transfert de ${amount_to_transfer:,.2f} USDC de Lighter vers Extended")
            
            # Étape 1: Retirer depuis Lighter vers Arbitrum
            logger.info("=" * 70)
            logger.info("🔄 REBALANCING: Lighter → Extended")
            logger.info("=" * 70)
            logger.info(f"Étape 1: Retrait de ${amount_to_transfer:,.2f} USDC depuis Lighter vers Arbitrum...")
            
            # Récupérer l'adresse Arbitrum de destination (Extended compte 1)
            dest_address = self.account1.get('arbitrum_address') or self.account1['wallet_address']
            if not dest_address:
                logger.error("❌ Adresse Arbitrum du compte 1 non trouvée")
                return False
            
            withdraw_result = self.lighter_client.withdraw(amount_to_transfer, dest_address, fast=True)
            
            if not withdraw_result or withdraw_result.get('status') != 'success':
                error_msg = withdraw_result.get('message', 'Unknown error') if withdraw_result else 'Withdrawal failed'
                logger.error(f"❌ Échec du retrait Lighter: {error_msg}")
                return False
            
            logger.success(f"✅ Retrait Lighter initié: {withdraw_result.get('tx_hash', 'N/A')}")
            logger.info("⏳ Attente de la finalisation du retrait Lighter...")
            
            # Attendre que les fonds arrivent sur Arbitrum
            expected_amount = amount_to_transfer  # Lighter a généralement des frais minimaux
            logger.info(f"Vérification du solde USDC sur Arbitrum pour {dest_address}...")
            min_expected = expected_amount * 0.95
            if not self.wait_for_arbitrum_balance(dest_address, min_expected, max_wait_seconds=600):
                logger.error("❌ Le retrait Lighter n'a pas été finalisé dans les temps")
                return False
            
            # Récupérer le solde réel
            actual_balance = self._get_arbitrum_balance(dest_address)
            if actual_balance > 0:
                deposit_amount = actual_balance
                logger.info(f"✅ Solde disponible sur Arbitrum: ${deposit_amount:.2f} USDC")
            else:
                deposit_amount = expected_amount
                logger.warning(f"⚠️  Utilisation de l'estimation: ${deposit_amount:.2f}")
            
            # Étape 2: Déposer vers Extended depuis Arbitrum
            logger.info(f"Étape 2: Dépôt de ${deposit_amount:,.2f} depuis Arbitrum vers Extended...")
            deposit_result = self.rebalance_manager1.deposit_extended(deposit_amount)
            
            if deposit_result.get('status') != 'success':
                logger.error(f"❌ Échec du dépôt Extended: {deposit_result.get('message', 'Unknown error')}")
                return False
            
            logger.success(f"✅ Dépôt Extended réussi: {deposit_result.get('transaction_hash', 'N/A')}")
            logger.info("⏳ Attente de la finalisation du bridge (environ 1-2 minutes)...")
            time.sleep(120)  # 2 minutes
        
        # Vérifier les nouvelles balances (si disponibles)
        try:
            balance1_new = self.client1.get_balance()
            balance2_new = self.lighter_client.get_balance()
            
            bal1_new = balance1_new.get('total', 0) if isinstance(balance1_new, dict) else balance1_new
            bal2_new = balance2_new if isinstance(balance2_new, (int, float)) else balance2_new
            
            logger.info(f"Nouvelles balances:")
            logger.info(f"  Extended: ${bal1_new:,.2f} USDC")
            logger.info(f"  Lighter: ${bal2_new:,.2f} USDC")
            
            diff_final = abs(bal1_new - bal2_new)
            if diff_final < 10.0:  # Moins de 10 USDC de différence
                logger.success("✅ Rebalancing Extended <-> Lighter terminé avec succès")
            else:
                logger.warning(f"⚠️  Rebalancing partiel: différence restante de ${diff_final:.2f}")
                logger.warning("   Cela peut être dû à un dépôt manuel nécessaire sur Lighter")
        except Exception as e:
            logger.warning(f"⚠️  Impossible de récupérer les nouvelles balances: {e}")
            logger.warning("   Le rebalancing peut avoir partiellement réussi")
        
        # Retourner True pour permettre au bot de continuer même si le rebalancing est partiel
        return True
    
    def calculate_position_size(self, margin: float, leverage: int, symbol: str, client) -> float:
        """
        Calcule la taille de position en fonction de la marge et du levier
        
        Args:
            margin: Marge en USDC
            leverage: Levier
            symbol: Symbole de la paire
            client: Client Extended, Hyperliquid ou Lighter pour récupérer le prix
        
        Returns:
            Taille de position en unités de l'asset
        """
        # Récupérer le prix actuel
        if isinstance(client, ExtendedAPI):
            ticker = client.get_ticker(symbol)
            price = ticker.get('last', ticker.get('ask', 0))
        elif isinstance(client, HyperliquidAPI):
            ticker = client.get_ticker(symbol)
            price = ticker.get('last', ticker.get('ask', 0)) if ticker else 0
        elif isinstance(client, LighterAPI):
            ticker = client.get_ticker(symbol)
            price = ticker.get('last', ticker.get('ask', 0)) if ticker else 0
        else:
            raise ValueError(f"Type de client non supporté: {type(client)}")
        
        if price == 0:
            raise ValueError(f"Impossible de récupérer le prix pour {symbol}")
        
        # Taille = (marge * levier) / prix
        position_size = (margin * leverage) / price
        
        return position_size
    
    def open_trades(self, symbol: str, leverage: int, margin: float, 
                   account1_side: str, account2_side: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Ouvre les deux trades opposés simultanément
        
        Args:
            symbol: Paire à trader
            leverage: Levier
            margin: Marge en USDC
            account1_side: "buy" (long) ou "sell" (short) pour le compte 1
            account2_side: "buy" (long) ou "sell" (short) pour le compte 2
        
        Returns:
            Tuple (order_id_1, order_id_2)
        """
        if self.mode == 1:
            logger.info(f"📊 Ouverture des trades: Extended 1 {account1_side.upper()}, Extended 2 {account2_side.upper()}")
        else:
            logger.info(f"📊 Ouverture des trades: Extended {account1_side.upper()}, Hyperliquid {account2_side.upper()}")
        
        # Configurer le levier pour les deux comptes
        logger.info(f"Configuration du levier {leverage}x pour {symbol}...")
        self.client1.set_leverage(symbol, leverage)
        
        # Mode 1, 2 ou 3: utiliser client2 qui pointe vers le bon exchange
        self.client2.set_leverage(symbol, leverage)
        
        time.sleep(1)  # Attendre que le levier soit appliqué
        
        # Calculer la taille de position
        size1 = self.calculate_position_size(margin, leverage, symbol, self.client1)
        size2 = self.calculate_position_size(margin, leverage, symbol, self.client2)
        
        # Pour Hyperliquid/Lighter (mode 2/3), arrondir selon les sz_decimals
        if self.mode in [2, 3]:
            sz_decimals = self.client2.get_size_decimals(symbol)
            size2 = round(size2, sz_decimals)
            second_exchange = "Hyperliquid" if self.mode == 2 else "Lighter"
            logger.info(f"Taille {second_exchange} arrondie: {size2} {symbol} ({sz_decimals} décimales)")
        
        logger.info(f"Taille de position: {size1:.6f} {symbol} (marge: ${margin:.2f}, levier: {leverage}x)")
        
        # Placer les ordres market simultanément
        logger.info("Placement des ordres market...")
        
        order1 = self.client1.place_order(
            symbol=symbol,
            side=account1_side,
            size=size1,
            order_type="market"
        )
        
        # Tous les modes: utiliser client2
        order2 = self.client2.place_order(
            symbol=symbol,
            side=account2_side,
            size=size2,
            order_type="market"
        )
        
        # Vérifier les résultats
        if not order1 or order1.get('status') not in ['OK', 'ok', 'success']:
            error_msg = order1.get('error', 'Unknown error') if order1 else 'Order returned None'
            logger.error(f"❌ Échec ordre compte 1: {error_msg}")
            return None, None
        
        if not order2 or order2.get('status') not in ['OK', 'ok', 'success']:
            error_msg = order2.get('error', 'Unknown error') if order2 else 'Order returned None'
            logger.error(f"❌ Échec ordre compte 2: {error_msg}")
            return None, None
        
        # Récupérer les order IDs selon le type d'exchange
        # Extended: order_id ou data.id
        order_id1 = order1.get('order_id') or order1.get('data', {}).get('id')
        
        # Récupérer order_id2 selon le mode
        if self.mode == 2:
            # Hyperliquid: structure différente - response.data.statuses[0].resting.oid ou filled.oid
            order_id2 = None
            if order2.get('status') == 'ok' and 'response' in order2:
                response_data = order2.get('response', {}).get('data', {})
                statuses = response_data.get('statuses', [])
                if statuses:
                    status = statuses[0]
                    if 'resting' in status:
                        order_id2 = status['resting'].get('oid')
                    elif 'filled' in status:
                        order_id2 = status['filled'].get('oid')
            if not order_id2:
                order_id2 = order2.get('oid') or order2.get('data', {}).get('oid')
        elif self.mode == 3:
            # Lighter: order_id ou tx_hash
            order_id2 = order2.get('order_id') or order2.get('tx_hash') or order2.get('data', {}).get('id')
        else:
            # Mode 1: Extended
            order_id2 = order2.get('order_id') or order2.get('data', {}).get('id')
        
        logger.success(f"✅ Ordre compte 1 placé: {order_id1}")
        logger.success(f"✅ Ordre compte 2 placé: {order_id2}")
        
        # Attendre un peu pour que les ordres soient exécutés
        time.sleep(2)
        
        # Attendre un peu pour que les positions soient créées
        time.sleep(3)
        
        # Vérifier que les positions sont ouvertes et opposées
        try:
            if self.mode == 1:
                # Mode 1: Deux comptes Extended - utiliser le SDK
                try:
                    positions_sdk1 = self.client1.get_event_loop().run_until_complete(
                        self.client1.trading_client.account.get_positions()
                    )
                    positions_sdk2 = self.client2.get_event_loop().run_until_complete(
                        self.client2.trading_client.account.get_positions()
                    )
                    
                    pos1_raw = None
                    pos2_raw = None
                    
                    for pos_sdk in positions_sdk1.data:
                        if symbol.upper() in pos_sdk.market:
                            pos1_raw = pos_sdk
                            break
                    
                    for pos_sdk in positions_sdk2.data:
                        if symbol.upper() in pos_sdk.market:
                            pos2_raw = pos_sdk
                            break
                    
                    if pos1_raw and pos2_raw:
                        size1 = float(pos1_raw.size)
                        size2 = float(pos2_raw.size)
                        side1 = "LONG" if size1 > 0 else "SHORT"
                        side2 = "LONG" if size2 > 0 else "SHORT"
                        
                        logger.info(f"Positions brutes depuis SDK:")
                        logger.info(f"   Extended 1: size={size1}, côté={side1}")
                        logger.info(f"   Extended 2: size={size2}, côté={side2}")
                        
                        if side1 == side2:
                            logger.warning(f"⚠️  ATTENTION: Les deux positions sont du même côté ({side1})!")
                            logger.warning("   Les positions devraient être opposées (LONG/SHORT)")
                        else:
                            logger.success(f"✅ Positions opposées confirmées:")
                            logger.success(f"   Extended 1: {side1} {abs(size1)} {symbol}")
                            logger.success(f"   Extended 2: {side2} {abs(size2)} {symbol}")
                except Exception as e:
                    logger.debug(f"Erreur lors de la vérification SDK des positions: {e}")
                    # Fallback sur la méthode normale
                    positions1 = self.client1.get_positions()
                    positions2 = self.client2.get_positions()
                    
                    pos1 = next((p for p in positions1 if p['symbol'] == symbol), None)
                    pos2 = next((p for p in positions2 if p['symbol'] == symbol), None)
                    
                    if pos1 and pos2:
                        if pos1['side'] == pos2['side']:
                            logger.warning(f"⚠️  ATTENTION: Les deux positions sont du même côté ({pos1['side']})!")
                        else:
                            logger.success(f"✅ Positions opposées confirmées:")
                            logger.success(f"   Extended 1: {pos1['side']} {pos1['size']} {symbol}")
                            logger.success(f"   Extended 2: {pos2['side']} {pos2['size']} {symbol}")
            else:
                # Mode 2: Extended + Hyperliquid
                positions1 = self.client1.get_positions()
                positions2 = self.hyperliquid_client.get_open_positions()
                
                pos1 = next((p for p in positions1 if p['symbol'] == symbol), None)
                pos2 = next((p for p in positions2 if p.get('position', {}).get('coin') == symbol), None)
                
                if pos1 and pos2:
                    side1 = pos1.get('side', 'UNKNOWN')
                    pos2_data = pos2.get('position', {})
                    pos2_size = float(pos2_data.get('szi', 0))
                    side2 = "LONG" if pos2_size > 0 else "SHORT"
                    
                    if side1 == side2:
                        logger.warning(f"⚠️  ATTENTION: Les deux positions sont du même côté ({side1})!")
                    else:
                        logger.success(f"✅ Positions opposées confirmées:")
                        logger.success(f"   Extended: {side1} {pos1['size']} {symbol}")
                        logger.success(f"   Hyperliquid: {side2} {abs(pos2_size)} {symbol}")
        except Exception as e:
            logger.debug(f"Erreur lors de la vérification des positions: {e}")
        
        return order_id1, order_id2
    
    def close_trades(self, symbol: str) -> bool:
        """
        Ferme les positions ouvertes sur les deux comptes en market
        
        Args:
            symbol: Paire à fermer
        
        Returns:
            True si succès
        """
        logger.info(f"🔒 Fermeture des positions pour {symbol}...")
        
        # Récupérer les positions actuelles
        positions1 = self.client1.get_positions()
        
        if self.mode == 1:
            positions2 = self.client2.get_positions()
            pos1 = next((p for p in positions1 if p['symbol'] == symbol), None)
            pos2 = next((p for p in positions2 if p['symbol'] == symbol), None)
        elif self.mode == 2:
            # Mode 2: Hyperliquid
            positions2 = self.hyperliquid_client.get_open_positions()
            pos1 = next((p for p in positions1 if p['symbol'] == symbol), None)
            pos2 = next((p for p in positions2 if p.get('position', {}).get('coin') == symbol), None)
        else:
            # Mode 3: Lighter
            positions2 = self.lighter_client.get_positions()
            pos1 = next((p for p in positions1 if p['symbol'] == symbol), None)
            # Chercher la position Lighter par symbol ou market_symbol
            pos2 = next((p for p in positions2 if p.get('symbol') == symbol or p.get('market_symbol') == symbol), None)
            logger.debug(f"Positions Lighter récupérées: {positions2}")
            logger.debug(f"Position Lighter trouvée pour {symbol}: {pos2}")
        
        if not pos1 and not pos2:
            logger.warning("Aucune position à fermer")
            # En mode 3, vérifier une dernière fois les positions Lighter directement
            if self.mode == 3:
                positions2_recheck = self.lighter_client.get_positions()
                logger.debug(f"Vérification finale des positions Lighter: {positions2_recheck}")
                for p in positions2_recheck:
                    if p.get('symbol') == symbol and abs(float(p.get('size_signed', 0))) > 0:
                        logger.warning(f"⚠️  Position Lighter détectée mais non fermée: {p}")
            return True
        
        # Fermer les positions en market (reduce_only)
        success = True
        
        if pos1:
            # Récupérer la position brute depuis le SDK pour avoir le signe exact
            try:
                positions_sdk1 = self.client1.get_event_loop().run_until_complete(
                    self.client1.trading_client.account.get_positions()
                )
                raw_size1 = None
                for pos_sdk in positions_sdk1.data:
                    if symbol.upper() in pos_sdk.market:
                        raw_size1 = float(pos_sdk.size)
                        break
                
                if raw_size1 is not None and raw_size1 != 0:
                    # Utiliser le signe brut pour déterminer le côté réel
                    # Si raw_size est positif, c'est LONG -> fermer avec SELL
                    # Si raw_size est négatif, c'est SHORT -> fermer avec BUY
                    actual_side1 = "LONG" if raw_size1 > 0 else "SHORT"
                    close_side1 = "sell" if raw_size1 > 0 else "buy"
                    logger.info(f"Fermeture position compte 1: {actual_side1} {abs(raw_size1)} {symbol} (size brut: {raw_size1})")
                    logger.info(f"  Ordre de fermeture: {close_side1.upper()} {abs(raw_size1)} {symbol} (reduce_only=True)")
                    
                    # Log supplémentaire pour debug
                    logger.debug(f"  Détails: raw_size1={raw_size1}, actual_side1={actual_side1}, close_side1={close_side1}")
                    
                    result1 = self.client1.place_order(
                        symbol=symbol,
                        side=close_side1,
                        size=abs(raw_size1),
                        order_type="market",
                        reduce_only=True
                    )
                    
                    if result1.get('status') not in ['OK', 'ok', 'success']:
                        error_msg1 = result1.get('error', '')
                        
                        # Si erreur "same side", inverser automatiquement
                        if 'same side' in str(error_msg1).lower() or '1138' in str(error_msg1):
                            # Cette erreur est normale - l'API Extended a parfois un décalage dans la détection du côté
                            # On inverse automatiquement sans afficher d'erreur
                            logger.debug(f"Erreur 'same side' (1138) - inversion automatique du côté")
                            logger.debug(f"   Position détectée: {actual_side1} (size brut: {raw_size1})")
                            logger.debug(f"   Ordre tenté: {close_side1.upper()} - correction automatique en cours...")
                            
                            # Inverser le côté
                            close_side1 = "buy" if raw_size1 > 0 else "sell"
                            logger.info(f"  Correction automatique: Ordre {close_side1.upper()} (côté inversé)")
                            
                            result1_retry = self.client1.place_order(
                                symbol=symbol,
                                side=close_side1,
                                size=abs(raw_size1),
                                order_type="market",
                                reduce_only=True
                            )
                            if result1_retry.get('status') in ['OK', 'ok', 'success']:
                                logger.success(f"✅ Position compte 1 fermée (côté corrigé automatiquement)")
                                success = True
                            else:
                                success = False
                        else:
                            logger.error(f"❌ Échec fermeture compte 1: {error_msg1}")
                            success = False
                    else:
                        logger.success(f"✅ Position compte 1 fermée")
                else:
                    logger.warning("⚠️  Position compte 1 non trouvée dans le SDK")
                    success = False
            except Exception as e:
                logger.error(f"❌ Erreur lors de la récupération de la position compte 1: {e}")
                # Fallback sur la méthode normale
                side = "sell" if pos1['side'] == "LONG" else "buy"
                result1 = self.client1.place_order(
                    symbol=symbol,
                    side=side,
                    size=pos1['size'],
                    order_type="market",
                    reduce_only=True
                )
                if result1.get('status') not in ['OK', 'ok', 'success']:
                    success = False
                else:
                    logger.success(f"✅ Position compte 1 fermée")
        
        if pos2:
            if self.mode == 1:
                # Mode 1: Deux comptes Extended
                try:
                    positions_sdk2 = self.client2.get_event_loop().run_until_complete(
                        self.client2.trading_client.account.get_positions()
                    )
                    raw_size2 = None
                    for pos_sdk in positions_sdk2.data:
                        if symbol.upper() in pos_sdk.market:
                            raw_size2 = float(pos_sdk.size)
                            break
                    
                    if raw_size2 is not None and raw_size2 != 0:
                        actual_side2 = "LONG" if raw_size2 > 0 else "SHORT"
                        close_side2 = "sell" if raw_size2 > 0 else "buy"
                        logger.info(f"Fermeture position Extended 2: {actual_side2} {abs(raw_size2)} {symbol}")
                        
                        result2 = self.client2.place_order(
                            symbol=symbol,
                            side=close_side2,
                            size=abs(raw_size2),
                            order_type="market",
                            reduce_only=True
                        )
                        
                        if result2.get('status') not in ['OK', 'ok', 'success']:
                            error_msg2 = result2.get('error', '')
                            if 'same side' in str(error_msg2).lower() or '1138' in str(error_msg2):
                                close_side2 = "buy" if raw_size2 > 0 else "sell"
                                result2 = self.client2.place_order(
                                    symbol=symbol,
                                    side=close_side2,
                                    size=abs(raw_size2),
                                    order_type="market",
                                    reduce_only=True
                                )
                                if result2.get('status') in ['OK', 'ok', 'success']:
                                    logger.success(f"✅ Position Extended 2 fermée")
                                    success = True
                                else:
                                    success = False
                            else:
                                logger.error(f"❌ Échec fermeture Extended 2: {error_msg2}")
                                success = False
                        else:
                            logger.success(f"✅ Position Extended 2 fermée")
                    else:
                        logger.warning("⚠️  Position Extended 2 non trouvée")
                        success = True
                except Exception as e:
                    logger.error(f"❌ Erreur lors de la récupération de la position Extended 2: {e}")
                    positions2_raw = self.client2.get_positions()
                    pos2_raw = next((p for p in positions2_raw if p['symbol'] == symbol), None)
                    if pos2_raw:
                        side = "sell" if pos2_raw['side'] == "LONG" else "buy"
                        result2 = self.client2.place_order(
                            symbol=symbol,
                            side=side,
                            size=pos2_raw['size'],
                            order_type="market",
                            reduce_only=True
                        )
                        if result2.get('status') not in ['OK', 'ok', 'success']:
                            success = False
                        else:
                            logger.success(f"✅ Position Extended 2 fermée")
                    else:
                        success = True
            elif self.mode == 2:
                # Mode 2: Hyperliquid
                try:
                    pos2_data = pos2.get('position', {})
                    pos2_size = float(pos2_data.get('szi', 0))
                    
                    if pos2_size != 0:
                        actual_side2 = "LONG" if pos2_size > 0 else "SHORT"
                        close_side2 = "sell" if pos2_size > 0 else "buy"
                        logger.info(f"Fermeture position Hyperliquid: {actual_side2} {abs(pos2_size)} {symbol}")
                        
                        result2 = self.hyperliquid_client.place_order(
                            symbol=symbol,
                            side=close_side2,
                            size=abs(pos2_size),
                            order_type="market",
                            reduce_only=True
                        )
                        
                        if result2 and result2.get('status') in ['OK', 'ok', 'success']:
                            logger.success(f"✅ Position Hyperliquid fermée")
                        else:
                            logger.error(f"❌ Échec fermeture Hyperliquid: {result2}")
                            success = False
                    else:
                        logger.warning("⚠️  Position Hyperliquid non trouvée ou déjà fermée")
                        success = True
                except Exception as e:
                    logger.error(f"❌ Erreur lors de la fermeture de la position Hyperliquid: {e}")
                    success = False
            else:
                # Mode 3: Lighter
                try:
                    # Récupérer le market_index pour ce symbole pour une recherche plus précise
                    market_index = None
                    try:
                        market_index = self.lighter_client.get_market_index(symbol)
                        logger.debug(f"Market index pour {symbol}: {market_index}")
                    except:
                        pass
                    
                    # Faire plusieurs tentatives pour trouver la position (avec délais)
                    pos2_fresh = None
                    max_attempts = 3
                    for attempt in range(max_attempts):
                        if attempt > 0:
                            time.sleep(0.5)  # Attendre entre les tentatives
                        
                        positions2_fresh = self.lighter_client.get_positions()
                        logger.info(f"Tentative {attempt + 1}/{max_attempts} - Positions Lighter récupérées: {len(positions2_fresh)} positions")
                        
                        if positions2_fresh:
                            logger.debug(f"Détails des positions: {positions2_fresh}")
                        
                        # Chercher la position pour ce symbole (par symbol, market_symbol ou market_id)
                        for p in positions2_fresh:
                            pos_symbol = p.get('symbol', '')
                            pos_market_symbol = p.get('market_symbol', '')
                            pos_market_id = p.get('market_id')
                            
                            # Vérifier par symbole
                            if pos_symbol == symbol or pos_market_symbol == symbol:
                                pos2_fresh = p
                                logger.info(f"✅ Position Lighter trouvée par symbole: {pos2_fresh}")
                                break
                            
                            # Vérifier par market_id si disponible
                            if market_index is not None and pos_market_id == market_index:
                                pos2_fresh = p
                                logger.info(f"✅ Position Lighter trouvée par market_id: {pos2_fresh}")
                                break
                        
                        if pos2_fresh:
                            break
                    
                    # Si pos2 n'était pas trouvé initialement mais qu'on le trouve maintenant, l'utiliser
                    if not pos2 and pos2_fresh:
                        pos2 = pos2_fresh
                        logger.info(f"Position Lighter trouvée lors de la vérification: {pos2}")
                    elif pos2_fresh:
                        # Utiliser la position la plus récente
                        pos2 = pos2_fresh
                        logger.info(f"Position Lighter mise à jour: {pos2}")
                    
                    if not pos2:
                        logger.warning(f"⚠️  Aucune position Lighter trouvée pour {symbol}")
                        # Vérifier une dernière fois toutes les positions
                        all_positions = self.lighter_client.get_positions()
                        logger.debug(f"Toutes les positions Lighter: {all_positions}")
                        for p in all_positions:
                            pos_size = float(p.get('size_signed', 0) or p.get('size', 0))
                            if abs(pos_size) > 0:
                                logger.warning(f"⚠️  Position Lighter ouverte détectée: {p}")
                        
                        # Si la position n'est pas détectée mais qu'on a les infos de l'ordre, fermer quand même
                        logger.info(f"🔍 Vérification des infos stockées pour fermeture forcée:")
                        logger.info(f"   - size: {self.last_lighter_order_size}")
                        logger.info(f"   - side: {self.last_lighter_order_side}")
                        logger.info(f"   - symbol stocké: {self.last_lighter_order_symbol}")
                        logger.info(f"   - symbol actuel: {symbol}")
                        
                        # Vérifier si on peut faire une fermeture forcée (comparaison flexible du symbole)
                        can_force_close = (
                            self.last_lighter_order_size is not None and 
                            self.last_lighter_order_size > 0 and
                            self.last_lighter_order_side is not None and
                            (self.last_lighter_order_symbol == symbol or 
                             self.last_lighter_order_symbol == symbol.upper() or
                             self.last_lighter_order_symbol == symbol.lower())
                        )
                        
                        if can_force_close:
                            logger.warning(f"⚠️  Position non détectée, fermeture forcée avec les infos de l'ordre initial")
                            logger.info(f"Fermeture position Lighter (forcée): {self.last_lighter_order_side.upper()} {self.last_lighter_order_size} {symbol}")
                            logger.info(f"  Ordre de fermeture: {'SELL' if self.last_lighter_order_side == 'buy' else 'BUY'} {self.last_lighter_order_size} {symbol} (reduce_only=True)")
                            
                            # Inverser le côté pour fermer
                            close_side2_forced = "sell" if self.last_lighter_order_side == "buy" else "buy"
                            
                            result2_forced = self.lighter_client.place_order(
                                symbol=symbol,
                                side=close_side2_forced,
                                size=self.last_lighter_order_size,
                                order_type="market",
                                reduce_only=True
                            )
                            
                            if result2_forced and result2_forced.get('status') in ['OK', 'ok', 'success']:
                                logger.success(f"✅ Position Lighter fermée (forcée avec infos de l'ordre initial)")
                                # Vérifier après un délai
                                time.sleep(2)
                                positions2_after_forced = self.lighter_client.get_positions()
                                pos2_after_forced = next((p for p in positions2_after_forced if p.get('symbol') == symbol or p.get('market_symbol') == symbol), None)
                                if pos2_after_forced:
                                    remaining_size_forced = float(pos2_after_forced.get('size_signed', 0) or pos2_after_forced.get('size', 0))
                                    if abs(remaining_size_forced) > 0.0001:
                                        logger.warning(f"⚠️  Position Lighter toujours ouverte après fermeture forcée: {remaining_size_forced}")
                                    else:
                                        logger.success(f"✅ Position Lighter confirmée fermée (forcée)")
                                else:
                                    logger.success(f"✅ Position Lighter confirmée fermée (plus de position détectée)")
                                success = True
                            else:
                                error_msg_forced = result2_forced.get('error', 'Unknown error') if result2_forced else 'Order returned None'
                                logger.error(f"❌ Échec fermeture Lighter forcée: {error_msg_forced}")
                                logger.debug(f"   Réponse complète: {result2_forced}")
                                success = False
                        else:
                            logger.error(f"❌ Pas d'infos d'ordre stockées pour fermeture forcée ou symboles ne correspondent pas")
                            logger.error(f"   Conditions: size={self.last_lighter_order_size is not None}, side={self.last_lighter_order_side is not None}, symbol_match={self.last_lighter_order_symbol == symbol if self.last_lighter_order_symbol else False}")
                            success = False  # Changer en False pour signaler l'échec
                    else:
                        # Essayer d'abord avec size_signed, puis avec size si size_signed n'est pas disponible
                        pos2_size = 0
                        if 'size_signed' in pos2:
                            pos2_size = float(pos2.get('size_signed', 0))
                        elif 'size' in pos2:
                            # Si on a seulement size, déterminer le côté depuis 'side'
                            pos2_size_raw = float(pos2.get('size', 0))
                            pos2_side = pos2.get('side', 'UNKNOWN')
                            if pos2_side == 'LONG':
                                pos2_size = pos2_size_raw
                            elif pos2_side == 'SHORT':
                                pos2_size = -pos2_size_raw
                            else:
                                logger.warning(f"⚠️  Côté de position Lighter inconnu: {pos2_side}")
                        
                        logger.info(f"Position Lighter détectée: {pos2}, size_signed={pos2_size}")
                        
                        if pos2_size != 0:
                            actual_side2 = "LONG" if pos2_size > 0 else "SHORT"
                            close_side2 = "sell" if pos2_size > 0 else "buy"
                            logger.info(f"Fermeture position Lighter: {actual_side2} {abs(pos2_size)} {symbol}")
                            logger.info(f"  Ordre de fermeture: {close_side2.upper()} {abs(pos2_size)} {symbol} (reduce_only=True)")
                            
                            result2 = self.lighter_client.place_order(
                                symbol=symbol,
                                side=close_side2,
                                size=abs(pos2_size),
                                order_type="market",
                                reduce_only=True
                            )
                            
                            if result2 and result2.get('status') in ['OK', 'ok', 'success']:
                                logger.success(f"✅ Position Lighter fermée")
                                # Vérifier que la position est bien fermée
                                time.sleep(2)  # Attendre un peu pour que l'ordre soit exécuté
                                positions2_after = self.lighter_client.get_positions()
                                pos2_after = next((p for p in positions2_after if p.get('symbol') == symbol), None)
                                if pos2_after:
                                    remaining_size = float(pos2_after.get('size_signed', 0) or pos2_after.get('size', 0))
                                    if abs(remaining_size) > 0.0001:  # Tolérance pour les arrondis
                                        logger.warning(f"⚠️  Position Lighter toujours ouverte après fermeture: {remaining_size}")
                                    else:
                                        logger.success(f"✅ Position Lighter confirmée fermée")
                            else:
                                error_msg2 = result2.get('error', 'Unknown error') if result2 else 'Order returned None'
                                logger.error(f"❌ Échec fermeture Lighter: {error_msg2}")
                                logger.debug(f"   Réponse complète: {result2}")
                                success = False
                        else:
                            logger.warning(f"⚠️  Position Lighter non trouvée ou déjà fermée (size_signed={pos2_size})")
                            logger.debug(f"   Détails de pos2: {pos2}")
                            success = True
                except Exception as e:
                    logger.error(f"❌ Erreur lors de la fermeture de la position Lighter: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    success = False
        
        # Attendre un peu pour que les fermetures soient confirmées
        time.sleep(2)
        
        return success
    
    def get_combined_pnl(self, symbol: str) -> Tuple[float, float, float]:
        """
        Calcule le PnL combiné des positions sur les deux exchanges
        Extended: Calcul manuel avec MID PRICE (moyenne bid/ask)
        
        Args:
            symbol: Symbole de la paire
            
        Returns:
            Tuple (extended_pnl, hyperliquid_pnl, total_pnl)
        """
        extended_pnl = 0.0
        hyperliquid_pnl = 0.0
        
        try:
            # PnL Extended - Calcul avec MID PRICE
            positions1 = self.client1.get_positions()
            for pos in positions1:
                if pos['symbol'] == symbol:
                    # Récupérer le MID PRICE (moyenne bid/ask)
                    ticker = self.client1.get_ticker(symbol)
                    if ticker:
                        bid = ticker.get('bid', 0)
                        ask = ticker.get('ask', 0)
                        mid_price = (bid + ask) / 2 if bid and ask else ticker.get('last', 0)
                        
                        entry_price = pos.get('entry_price', 0)
                        size = pos.get('size', 0)
                        side = pos.get('side', 'LONG')
                        
                        # Calculer le PnL: (mid - entry) * size * direction
                        if side == 'LONG':
                            extended_pnl = (mid_price - entry_price) * size
                        else:  # SHORT
                            extended_pnl = (entry_price - mid_price) * size
                    else:
                        # Fallback sur le PnL du SDK si pas de ticker
                        extended_pnl = pos.get('unrealized_pnl', 0)
                    break
            
            # PnL du second exchange (Hyperliquid ou Lighter)
            if self.mode == 2 and self.hyperliquid_client:
                # Mode 2: Hyperliquid
                positions2 = self.hyperliquid_client.get_open_positions()
                for pos in positions2:
                    pos_data = pos.get('position', {})
                    if pos_data.get('coin') == symbol:
                        # unrealizedPnl est dans position
                        hyperliquid_pnl = float(pos_data.get('unrealizedPnl', 0))
                        break
            elif self.mode == 3 and self.lighter_client:
                # Mode 3: Lighter
                positions2 = self.lighter_client.get_positions()
                for pos in positions2:
                    if pos.get('symbol') == symbol or pos.get('market_symbol') == symbol:
                        # unrealized_pnl est dans la position
                        hyperliquid_pnl = float(pos.get('unrealized_pnl', 0))
                        break
            
        except Exception as e:
            logger.error(f"Erreur lors du calcul du PnL: {e}")
        
        total_pnl = extended_pnl + hyperliquid_pnl
        return extended_pnl, hyperliquid_pnl, total_pnl
    
    def wait_for_duration(self, symbol: str, duration_minutes: int) -> None:
        """
        Attend la durée normale du cycle en affichant le PnL périodiquement (API REST)
        
        Args:
            symbol: Symbole de la paire
            duration_minutes: Durée en minutes
        """
        logger.info(f"\n⏳ Attente de {duration_minutes} minute(s)...")
        
        start_time = datetime.now()
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        last_log_time = start_time - timedelta(seconds=60)  # Force le premier log
        log_interval = 60  # Logger le PnL toutes les 60 secondes
        
        while datetime.now() < end_time:
            # Logger périodiquement
            if (datetime.now() - last_log_time).total_seconds() >= log_interval:
                ext_pnl, hl_pnl, total_pnl = self.get_combined_pnl(symbol)
                remaining = (end_time - datetime.now()).total_seconds()
                minutes = int(remaining // 60)
                seconds = int(remaining % 60)
                
                logger.info(f"📊 PnL {symbol}: Extended=${ext_pnl:,.2f}, Hyperliquid=${hl_pnl:,.2f}, Total=${total_pnl:,.2f}")
                logger.info(f"⏱️  Temps restant: {minutes:02d}:{seconds:02d}")
                
                last_log_time = datetime.now()
            
            time.sleep(10)  # Check toutes les 10 secondes
        
        logger.info(f"\n⏰ Durée de {duration_minutes} minute(s) atteinte")
    
    def wait_for_duration_with_ws(self, symbol: str, duration_minutes: int, 
                                   pnl_ws_manager: Optional['PnLWebSocketManager'] = None) -> None:
        """
        Attend la durée normale du cycle en affichant le PnL en temps réel (WebSocket)
        
        Args:
            symbol: Symbole de la paire
            duration_minutes: Durée en minutes
            pnl_ws_manager: Manager WebSocket pour PnL temps réel (optionnel)
        """
        logger.info(f"\n⏳ Attente de {duration_minutes} minute(s)...")
        if pnl_ws_manager:
            logger.info(f"   📡 Surveillance PnL en temps réel via WebSocket")
        
        start_time = datetime.now()
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        last_log_time = start_time - timedelta(seconds=30)  # Force le premier log
        log_interval = 30  # Logger le PnL toutes les 30 secondes avec WebSocket
        
        while datetime.now() < end_time:
            # Logger périodiquement
            if (datetime.now() - last_log_time).total_seconds() >= log_interval:
                # Utiliser WebSocket si disponible, sinon API REST
                if pnl_ws_manager and pnl_ws_manager.extended_connected and pnl_ws_manager.hyperliquid_connected:
                    ext_pnl, hl_pnl, total_pnl = pnl_ws_manager.get_combined_pnl()
                    source = "WS"
                else:
                    ext_pnl, hl_pnl, total_pnl = self.get_combined_pnl(symbol)
                    source = "REST"
                
                remaining = (end_time - datetime.now()).total_seconds()
                minutes = int(remaining // 60)
                seconds = int(remaining % 60)
                
                second_name = "Lighter" if self.mode == 3 else "Hyperliquid"
                logger.info(f"📊 [{source}] PnL {symbol}: Ext=${ext_pnl:,.2f}, {second_name}=${hl_pnl:,.2f}, Total=${total_pnl:,.2f} | ⏱️ {minutes:02d}:{seconds:02d}")
                
                last_log_time = datetime.now()
            
            time.sleep(5)  # Check toutes les 5 secondes
        
        logger.info(f"\n⏰ Durée de {duration_minutes} minute(s) atteinte")
    
    def close_with_pnl_check(self, symbol: str, pnl_check_delay: int) -> Tuple[bool, str]:
        """
        Ferme les positions en vérifiant le PnL (version API REST)
        """
        return self.close_with_pnl_check_ws(symbol, pnl_check_delay, None)
    
    def close_with_pnl_check_ws(self, symbol: str, pnl_check_delay: int,
                                 pnl_ws_manager: Optional['PnLWebSocketManager'] = None) -> Tuple[bool, str]:
        """
        Ferme les positions en vérifiant le PnL en temps réel (WebSocket si disponible):
        1. Si PnL >= 0 → Fermer immédiatement
        2. Si PnL < 0 → Attendre jusqu'à pnl_check_delay minutes en vérifiant le PnL
           - Vérification continue via WebSocket (ou toutes les secondes via REST)
           - Si PnL devient >= 0 pendant l'attente → Fermer
           - Si toujours < 0 après pnl_check_delay → Fermer quand même
        
        Args:
            symbol: Symbole de la paire
            pnl_check_delay: Temps max d'attente si PnL négatif (en minutes)
            pnl_ws_manager: Manager WebSocket pour PnL temps réel (optionnel)
            
        Returns:
            Tuple (success: bool, close_reason: str)
        """
        use_ws = pnl_ws_manager and pnl_ws_manager.extended_connected and pnl_ws_manager.hyperliquid_connected
        source = "WS" if use_ws else "REST"
        
        # Vérifier le PnL actuel
        if use_ws:
            ext_pnl, hl_pnl, total_pnl = pnl_ws_manager.get_combined_pnl()
        else:
            ext_pnl, hl_pnl, total_pnl = self.get_combined_pnl(symbol)
        
        logger.info(f"\n📊 [{source}] Vérification du PnL avant fermeture:")
        second_name = "Lighter" if self.mode == 3 else "Hyperliquid"
        logger.info(f"   Extended:    ${ext_pnl:,.2f}")
        logger.info(f"   {second_name}: ${hl_pnl:,.2f}")
        logger.info(f"   Total:       ${total_pnl:,.2f}")
        
        # Cas 1: PnL positif ou nul → Fermer immédiatement
        if total_pnl >= 0:
            logger.success(f"\n✅ PnL positif ou neutre (${total_pnl:,.2f}) → Fermeture immédiate")
            success = self.close_trades(symbol)
            return success, "positive_pnl"
        
        # Cas 2: PnL négatif → Attendre jusqu'à pnl_check_delay minutes
        logger.warning(f"\n⚠️  PnL négatif (${total_pnl:,.2f})")
        logger.info(f"   → Attente jusqu'à {pnl_check_delay} minute(s) pour que le PnL devienne positif ou neutre...")
        if use_ws:
            logger.info(f"   → Surveillance en temps réel via WebSocket (vérification continue)")
        else:
            logger.info(f"   → Vérification via API REST toutes les secondes")
        
        start_wait = datetime.now()
        end_wait = start_wait + timedelta(minutes=pnl_check_delay)
        
        last_log_time = start_wait
        log_interval = 5  # Logger toutes les 5 secondes pendant l'attente
        
        # Intervalle de vérification: 0.1s avec WebSocket, 1s avec REST
        check_interval = 0.1 if use_ws else 1
        
        while datetime.now() < end_wait:
            # Vérifier le PnL
            if use_ws:
                ext_pnl, hl_pnl, total_pnl = pnl_ws_manager.get_combined_pnl()
            else:
                ext_pnl, hl_pnl, total_pnl = self.get_combined_pnl(symbol)
            
            # Si PnL devient positif ou nul → Fermer IMMÉDIATEMENT
            if total_pnl >= 0:
                logger.success(f"\n🎯 PnL devenu positif/neutre! Total: ${total_pnl:,.2f}")
                logger.info(f"   Extended:    ${ext_pnl:,.2f}")
                logger.info(f"   Hyperliquid: ${hl_pnl:,.2f}")
                logger.info("   → Fermeture des positions...")
                
                success = self.close_trades(symbol)
                return success, "pnl_recovered"
            
            # Logger périodiquement
            if (datetime.now() - last_log_time).total_seconds() >= log_interval:
                remaining = (end_wait - datetime.now()).total_seconds()
                minutes = int(remaining // 60)
                seconds = int(remaining % 60)
                
                second_name = "Lighter" if self.mode == 3 else "Hyperliquid"
                logger.info(f"📊 [{source}] PnL: Ext=${ext_pnl:,.2f}, {second_name}=${hl_pnl:,.2f}, Total=${total_pnl:,.2f} | Attente: {minutes:02d}:{seconds:02d}")
                last_log_time = datetime.now()
            
            # Attendre avant le prochain check
            time.sleep(check_interval)
        
        # Timeout atteint, PnL toujours négatif → Fermer quand même
        if use_ws:
            ext_pnl, hl_pnl, total_pnl = pnl_ws_manager.get_combined_pnl()
        else:
            ext_pnl, hl_pnl, total_pnl = self.get_combined_pnl(symbol)
        
        logger.warning(f"\n⏱️  Timeout de {pnl_check_delay} minute(s) atteint - PnL toujours négatif")
        logger.warning(f"   PnL final: Extended=${ext_pnl:,.2f}, Hyperliquid=${hl_pnl:,.2f}, Total=${total_pnl:,.2f}")
        logger.info("   → Fermeture forcée des positions...")
        
        success = self.close_trades(symbol)
        return success, "timeout_negative_pnl"
    
    def open_trades_dynamic_mode2(self, symbol: str, leverage: int, margin: float) -> Tuple[Optional[str], Optional[str], str, str]:
        """
        Ouvre les trades en mode 2/3 avec comparaison des prix en temps réel
        
        Compare les prix Extended vs Hyperliquid/Lighter et:
        - SHORT le plus haut
        - LONG le plus bas
        
        Args:
            symbol: Paire à trader
            leverage: Levier
            margin: Marge en USDC
            
        Returns:
            Tuple (order_id_extended, order_id_second, extended_side, second_side)
        """
        # Déterminer le nom du second exchange
        second_exchange_name = "Hyperliquid" if self.mode == 2 else "Lighter"
        second_client = self.hyperliquid_client if self.mode == 2 else self.lighter_client
        
        logger.info(f"\n📊 Mode {self.mode} - Préparation des trades pour {symbol}")
        
        # ÉTAPE 1: Configurer le levier AVANT la comparaison des prix
        logger.info(f"Configuration du levier {leverage}x pour {symbol}...")
        self.client1.set_leverage(symbol, leverage)
        second_client.set_leverage(symbol, leverage)
        time.sleep(1)
        
        # ÉTAPE 2: Calculer les tailles de position AVANT la comparaison des prix
        size1 = self.calculate_position_size(margin, leverage, symbol, self.client1)
        size2 = self.calculate_position_size(margin, leverage, symbol, second_client)
        
        # Arrondir selon les décimales du second exchange
        sz_decimals = second_client.get_size_decimals(symbol)
        size2 = round(size2, sz_decimals)
        
        logger.info(f"Taille de position: Extended={size1:.6f}, {second_exchange_name}={size2:.6f} {symbol}")
        
        # ÉTAPE 3: Comparaison des prix JUSTE AVANT le placement des ordres
        logger.info(f"\n📊 Comparaison des prix en temps réel...")
        comparator = PriceComparator(self.client1, second_client, symbol, mode=self.mode)
        extended_side, second_side, price_diff, ext_price, second_price = comparator.compare_and_decide()
        
        if not extended_side or not second_side:
            logger.error("❌ Impossible de déterminer les côtés de trading")
            return None, None, "", ""
        
        # Vérification de sécurité: afficher clairement la décision
        logger.info(f"🎯 DÉCISION FINALE:")
        if extended_side == "sell":
            logger.info(f"   Extended:    SHORT (prix ${ext_price:,.2f} = plus haut)")
            logger.info(f"   {second_exchange_name}: LONG  (prix ${second_price:,.2f} = plus bas)")
        else:
            logger.info(f"   Extended:    LONG  (prix ${ext_price:,.2f} = plus bas)")
            logger.info(f"   {second_exchange_name}: SHORT (prix ${second_price:,.2f} = plus haut)")
        logger.info(f"   Spread:      {price_diff:.4f}%")
        
        # Ajuster les tailles selon le side réel et le slippage des ordres market
        # Extended utilise ask + 1% pour BUY et bid - 1% pour SELL
        # Récupérer les tickers pour obtenir ask/bid
        ticker1 = self.client1.get_ticker(symbol)
        ticker2 = second_client.get_ticker(symbol)
        
        if ticker1:
            ext_ask = ticker1.get('ask', ext_price)
            ext_bid = ticker1.get('bid', ext_price)
            
            if extended_side == "buy":
                # BUY: prix réel = ask * 1.01, donc réduire la taille
                ext_execution_price = ext_ask * 1.01
                size1 = size1 * (ext_price / ext_execution_price)
            else:
                # SELL: prix réel = bid * 0.99, donc réduire la taille
                ext_execution_price = ext_bid * 0.99
                size1 = size1 * (ext_price / ext_execution_price)
        
        if ticker2:
            sec_ask = ticker2.get('ask', second_price)
            sec_bid = ticker2.get('bid', second_price)
            
            # Même logique pour le second exchange
            if second_side == "buy":
                sec_execution_price = sec_ask * 1.01
                size2 = size2 * (second_price / sec_execution_price)
            else:
                sec_execution_price = sec_bid * 0.99
                size2 = size2 * (second_price / sec_execution_price)
        
        # Arrondir à nouveau après ajustement
        sz_decimals = second_client.get_size_decimals(symbol)
        size2 = round(size2, sz_decimals)
        
        logger.info(f"Taille ajustée pour slippage: Extended={size1:.6f}, {second_exchange_name}={size2:.6f} {symbol}")
        
        # ÉTAPE 4: Placement IMMÉDIAT des ordres (pas de délai après la comparaison)
        logger.info("\n📝 Placement des ordres market...")
        
        # Ordre Extended
        order1 = self.client1.place_order(
            symbol=symbol,
            side=extended_side,
            size=size1,
            order_type="market"
        )
        
        # Ordre sur le second exchange (Hyperliquid ou Lighter)
        order2 = second_client.place_order(
            symbol=symbol,
            side=second_side,
            size=size2,
            order_type="market"
        )
        
        # Stocker les infos de l'ordre Lighter pour la fermeture si nécessaire
        if self.mode == 3:
            self.last_lighter_order_size = size2
            self.last_lighter_order_side = second_side
            self.last_lighter_order_symbol = symbol
            logger.info(f"💾 Ordre Lighter stocké pour fermeture: {second_side.upper()} {size2} {symbol}")
        
        # Vérifier les résultats
        if not order1 or order1.get('status') not in ['OK', 'ok', 'success']:
            error_msg = order1.get('error', 'Unknown error') if order1 else 'Order returned None'
            logger.error(f"❌ Échec ordre Extended: {error_msg}")
            return None, None, extended_side, second_side
        
        if not order2 or order2.get('status') not in ['OK', 'ok', 'success']:
            error_msg = order2.get('error', 'Unknown error') if order2 else 'Order returned None'
            logger.error(f"❌ Échec ordre {second_exchange_name}: {error_msg}")
            return None, None, extended_side, second_side
        
        # Récupérer les order IDs
        order_id1 = order1.get('order_id') or order1.get('data', {}).get('id')
        
        order_id2 = None
        if self.mode == 2:
            # Format Hyperliquid
            if order2.get('status') == 'ok' and 'response' in order2:
                response_data = order2.get('response', {}).get('data', {})
                statuses = response_data.get('statuses', [])
                if statuses:
                    status = statuses[0]
                    if 'resting' in status:
                        order_id2 = status['resting'].get('oid')
                    elif 'filled' in status:
                        order_id2 = status['filled'].get('oid')
            if not order_id2:
                order_id2 = order2.get('oid') or order2.get('data', {}).get('oid')
        else:
            # Format Lighter
            order_id2 = order2.get('order_id') or order2.get('tx_hash') or order2.get('data', {}).get('id')
        
        logger.success(f"✅ Ordre Extended placé: {order_id1}")
        logger.success(f"✅ Ordre {second_exchange_name} placé: {order_id2}")
        
        # Attendre confirmation (latence minimale de 300ms pour Lighter)
        if self.mode == 3:
            # Pour Lighter, attendre au moins 300ms avant de récupérer la position
            time.sleep(0.3)
            logger.info("⏳ Vérification de la position Lighter après ouverture...")
        else:
            time.sleep(3)
        
        # Afficher les positions ouvertes
        try:
            positions1 = self.client1.get_positions()
            
            if self.mode == 2:
                # Hyperliquid
                positions2 = self.hyperliquid_client.get_open_positions()
                pos1 = next((p for p in positions1 if p['symbol'] == symbol), None)
                pos2 = next((p for p in positions2 if p.get('position', {}).get('coin') == symbol), None)
                
                if pos1 and pos2:
                    pos2_data = pos2.get('position', {})
                    pos2_size = float(pos2_data.get('szi', 0))
                    side2 = "LONG" if pos2_size > 0 else "SHORT"
                    
                    logger.success(f"\n✅ Positions ouvertes:")
                    logger.success(f"   Extended:    {pos1['side']} {pos1['size']} {symbol}")
                    logger.success(f"   Hyperliquid: {side2} {abs(pos2_size)} {symbol}")
            else:
                # Lighter - Récupérer la position directement après ouverture
                positions2 = second_client.get_positions() if hasattr(second_client, 'get_positions') else []
                pos1 = next((p for p in positions1 if p['symbol'] == symbol), None)
                pos2 = next((p for p in positions2 if p.get('symbol') == symbol or p.get('market_symbol') == symbol), None)
                
                if pos1:
                    logger.success(f"✅ Position Extended ouverte: {pos1['side']} {pos1['size']} {symbol}")
                else:
                    logger.warning(f"⚠️  Position Extended non détectée pour {symbol}")
                
                if pos2:
                    pos2_size_signed = float(pos2.get('size_signed', 0))
                    pos2_size = float(pos2.get('size', 0))
                    pos2_side = pos2.get('side', 'UNKNOWN')
                    
                    # Utiliser size_signed si disponible, sinon size avec side
                    if pos2_size_signed != 0:
                        actual_size = abs(pos2_size_signed)
                        actual_side = "LONG" if pos2_size_signed > 0 else "SHORT"
                    else:
                        actual_size = pos2_size
                        actual_side = pos2_side
                    
                    logger.success(f"✅ Position Lighter ouverte: {actual_side} {actual_size} {symbol}")
                    logger.info(f"   Détails: size_signed={pos2_size_signed}, size={pos2_size}, side={pos2_side}")
                    logger.info(f"   Entry price: ${pos2.get('entry_price', 0):.2f}, Unrealized PnL: ${pos2.get('unrealized_pnl', 0):.2f}")
                    
                    logger.success(f"\n✅ Positions ouvertes confirmées:")
                    logger.success(f"   Extended:    {pos1['side'] if pos1 else 'N/A'} {pos1['size'] if pos1 else 0} {symbol}")
                    logger.success(f"   Lighter:     {actual_side} {actual_size} {symbol}")
                else:
                    logger.warning(f"⚠️  Position Lighter non détectée pour {symbol} après ouverture")
                    logger.debug(f"   Positions Lighter récupérées: {positions2}")
                    # Réessayer après un court délai supplémentaire
                    time.sleep(0.5)
                    positions2_retry = second_client.get_positions() if hasattr(second_client, 'get_positions') else []
                    pos2_retry = next((p for p in positions2_retry if p.get('symbol') == symbol or p.get('market_symbol') == symbol), None)
                    if pos2_retry:
                        pos2_size_signed = float(pos2_retry.get('size_signed', 0))
                        pos2_size = float(pos2_retry.get('size', 0))
                        pos2_side = pos2_retry.get('side', 'UNKNOWN')
                        if pos2_size_signed != 0:
                            actual_size = abs(pos2_size_signed)
                            actual_side = "LONG" if pos2_size_signed > 0 else "SHORT"
                        else:
                            actual_size = pos2_size
                            actual_side = pos2_side
                        logger.success(f"✅ Position Lighter détectée après réessai: {actual_side} {actual_size} {symbol}")
                    else:
                        logger.error(f"❌ Position Lighter toujours non détectée après réessai")
        except Exception as e:
            logger.error(f"❌ Erreur lors de la vérification des positions: {e}")
            import traceback
            logger.debug(traceback.format_exc())
        
        return order_id1, order_id2, extended_side, second_side
    
    def run_cycle_mode2(self, symbol: str, leverage: int, margin: float, 
                        duration_minutes: int, pnl_check_delay: int = 5) -> bool:
        """
        Exécute un cycle en mode 2/3 (Extended <-> Hyperliquid/Lighter) avec:
        1. Comparaison des prix en temps réel pour décider du côté
        2. Attente de la durée normale du cycle (avec surveillance PnL WebSocket)
        3. À la fin: vérification du PnL et fermeture intelligente
        
        Args:
            symbol: Paire à trader
            leverage: Levier
            margin: Marge en USDC
            duration_minutes: Durée du cycle en minutes
            pnl_check_delay: Temps max d'attente si PnL négatif (en minutes)
            
        Returns:
            True si succès
        """
        second_exchange_name = "Hyperliquid" if self.mode == 2 else "Lighter"
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 CYCLE MODE {self.mode} (Extended <-> {second_exchange_name}) - Durée: {duration_minutes} minutes")
        logger.info(f"   PnL check delay: {pnl_check_delay} minutes")
        logger.info(f"{'='*60}\n")
        
        # Ouvrir les trades avec comparaison des prix
        order_id1, order_id2, ext_side, second_side = self.open_trades_dynamic_mode2(
            symbol, leverage, margin
        )
        
        if not order_id1 or not order_id2:
            logger.error("❌ Échec de l'ouverture des trades")
            return False
        
        # Démarrer le WebSocket PnL pour surveillance en temps réel
        # Pour le mode 3 (Lighter), on utilise le même manager mais avec Lighter comme second exchange
        pnl_ws_manager = PnLWebSocketManager(
            extended_api_key=self.account1.get('api_key'),
            hyperliquid_wallet=self.account2.get('arbitrum_address') if self.mode == 2 else None,
            symbol=symbol,
            extended_client=self.client1,  # Pour fallback REST si WebSocket échoue
            mode=self.mode,
            lighter_client=self.lighter_client if self.mode == 3 else None
        )
        
        ws_started = pnl_ws_manager.start()
        if ws_started:
            logger.success("✅ Surveillance PnL en temps réel activée (WebSocket)")
        else:
            logger.warning("⚠️  WebSocket PnL non disponible, fallback sur API REST")
        
        # Attendre la durée normale du cycle (avec affichage PnL WebSocket si disponible)
        self.wait_for_duration_with_ws(symbol, duration_minutes, pnl_ws_manager if ws_started else None)
        
        # Fermer avec vérification du PnL (utilise WebSocket si disponible)
        success, close_reason = self.close_with_pnl_check_ws(
            symbol, pnl_check_delay, pnl_ws_manager if ws_started else None
        )
        
        # Arrêter le WebSocket
        if ws_started:
            pnl_ws_manager.stop()
        
        if close_reason == "positive_pnl":
            logger.success(f"✅ Cycle terminé - PnL positif/neutre → Fermeture immédiate")
        elif close_reason == "pnl_recovered":
            logger.success(f"✅ Cycle terminé - PnL récupéré pendant l'attente")
        else:  # timeout_negative_pnl
            logger.warning(f"⚠️  Cycle terminé - Fermeture forcée après timeout (PnL négatif)")
        
        return success
    
    def run_cycle(self, symbol: str, leverage: int, margin: float, 
                 duration_minutes: int, account1_side: str, account2_side: str) -> bool:
        """
        Exécute un cycle complet: ouverture, attente, fermeture
        
        Args:
            symbol: Paire à trader
            leverage: Levier
            margin: Marge en USDC
            duration_minutes: Durée en minutes
            account1_side: "buy" ou "sell" pour compte 1
            account2_side: "buy" ou "sell" pour compte 2
        
        Returns:
            True si succès
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"🔄 DÉBUT DU CYCLE - Durée: {duration_minutes} minutes")
        logger.info(f"{'='*60}\n")
        
        # Ouvrir les trades
        order_id1, order_id2 = self.open_trades(symbol, leverage, margin, account1_side, account2_side)
        
        if not order_id1 or not order_id2:
            logger.error("❌ Échec de l'ouverture des trades")
            return False
        
        # Attendre la durée spécifiée
        logger.info(f"⏳ Attente de {duration_minutes} minutes...")
        start_time = datetime.now()
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        while datetime.now() < end_time:
            remaining = (end_time - datetime.now()).total_seconds()
            minutes = int(remaining // 60)
            seconds = int(remaining % 60)
            logger.info(f"⏱️  Temps restant: {minutes:02d}:{seconds:02d}")
            time.sleep(60)  # Attendre 1 minute entre chaque log
        
        # Fermer les trades
        logger.info("Fermeture des positions...")
        close_success = self.close_trades(symbol)
        
        if not close_success:
            logger.error("❌ Échec de la fermeture des trades")
            return False
        
        logger.success(f"✅ Cycle terminé avec succès")
        return True
    
    def run(self):
        """Lance le bot principal"""
        try:
            # Charger la configuration depuis config.json
            params = self.load_config()
            
            # Vérifier les balances initiales
            bal1, bal2 = self.check_initial_balances()
            
            # Vérifier que le margin est suffisant sur les deux comptes
            margin_required = params['margin']
            min_balance_needed = margin_required * 1.1  # 10% de marge de sécurité
            
            insufficient_balance = False
            if bal1 < min_balance_needed:
                logger.error(f"❌ Solde insuffisant sur le compte 1")
                logger.error(f"   Solde disponible: ${bal1:,.2f} USDC")
                logger.error(f"   Marge requise: ${margin_required:,.2f} USDC (minimum recommandé: ${min_balance_needed:,.2f})")
                insufficient_balance = True
            
            if bal2 < min_balance_needed:
                logger.error(f"❌ Solde insuffisant sur le compte 2")
                logger.error(f"   Solde disponible: ${bal2:,.2f} USDC")
                logger.error(f"   Marge requise: ${margin_required:,.2f} USDC (minimum recommandé: ${min_balance_needed:,.2f})")
                insufficient_balance = True
            
            if insufficient_balance:
                logger.error("\n" + "="*60)
                logger.error("❌ SOLDE INSUFFISANT POUR LE MARGIN CONFIGURÉ")
                logger.error("="*60)
                logger.error(f"Le margin configuré (${margin_required:,.2f}) est supérieur au solde disponible")
                logger.error("sur au moins un des comptes.")
                logger.error("\nOptions:")
                logger.error("1. Réduire le margin dans config/dnfarming.json")
                logger.error("2. Rebalancer les comptes pour équilibrer les soldes")
                logger.error("="*60 + "\n")
                
                response = input("Souhaitez-vous rebalancer les comptes maintenant? (o/n): ").strip().lower()
                if response == 'o':
                    logger.info("🔄 Démarrage du rebalancing...")
                    rebalance_success = self.rebalance_accounts()
                    if not rebalance_success:
                        logger.warning("⚠️  Le rebalancing n'a pas complètement réussi")
                        logger.warning("   Cela peut être dû à un dépôt manuel nécessaire sur Lighter")
                        logger.warning("   Le bot va continuer mais les balances peuvent ne pas être équilibrées")
                        # Ne pas arrêter le bot, continuer quand même
                        # L'utilisateur pourra déposer manuellement et relancer le bot
                    else:
                        logger.success("✅ Rebalancing réussi")
                    
                    # Vérifier à nouveau les balances après rebalancing
                    # Note: Le bridge peut prendre 5-10 minutes, donc les balances peuvent ne pas être mises à jour immédiatement
                    logger.info("⏳ Attente de quelques secondes pour que les balances se mettent à jour...")
                    time.sleep(5)  # Attendre 5 secondes
                    
                    bal1, bal2 = self.check_initial_balances()
                    logger.info(f"Balances après rebalancing: Extended=${bal1:,.2f}, Hyperliquid=${bal2:,.2f}")
                    
                    if bal1 < min_balance_needed or bal2 < min_balance_needed:
                        logger.warning("⚠️  Les balances ne sont pas encore mises à jour (le bridge peut prendre 5-10 minutes)")
                        logger.warning("⚠️  Le rebalancing a été initié avec succès, mais les fonds peuvent ne pas être crédités immédiatement")
                        logger.warning("⚠️  Continuation du bot - Les balances seront vérifiées à nouveau au prochain cycle")
                        # Ne pas arrêter le bot si le rebalancing a été initié avec succès
                        # Les balances seront mises à jour après le traitement du bridge
                else:
                    logger.error("Arrêt du bot - Rebalancing refusé")
                    return
            
            # Vérifier si un rebalancing automatique est nécessaire
            diff = abs(bal1 - bal2)
            rebalance_threshold = params['rebalance_threshold']
            
            if diff > rebalance_threshold:
                logger.warning(f"⚠️  Différence de balance détectée: ${diff:,.2f} (seuil: ${rebalance_threshold:,.2f})")
                logger.info(f"   Compte 1: ${bal1:,.2f} USDC")
                logger.info(f"   Compte 2: ${bal2:,.2f} USDC")
                logger.info("🔄 Rebalancing automatique...")
                
                if not self.rebalance_accounts():
                    logger.error("❌ Échec du rebalancing automatique")
                    logger.warning("⚠️  Continuation avec des balances déséquilibrées")
                else:
                    # Vérifier les nouvelles balances après rebalancing
                    bal1, bal2 = self.check_initial_balances()
                    logger.info(f"Nouvelles balances après rebalancing:")
                    logger.info(f"   Compte 1: ${bal1:,.2f} USDC")
                    logger.info(f"   Compte 2: ${bal2:,.2f} USDC")
            else:
                logger.info(f"✅ Les balances sont équilibrées (différence: ${diff:,.2f} < ${rebalance_threshold:,.2f})")
            
            # Générer une durée aléatoire pour chaque cycle
            durations = []
            for i in range(params['num_cycles']):
                duration = random.randint(params['min_duration'], params['max_duration'])
                durations.append(duration)
            
            logger.info(f"\n📋 Plan d'exécution:")
            logger.info(f"  Paire: {params['symbol']}")
            logger.info(f"  Levier: {params['leverage']}x")
            logger.info(f"  Marge: ${params['margin']:.2f} USDC")
            logger.info(f"  Nombre de cycles: {params['num_cycles']}")
            logger.info(f"  Durées: {durations} minutes")
            logger.info(f"  Délai entre cycles: {params['delay_between_cycles']} minutes")
            
            # Alterner les positions: cycle 1 = compte1 long, compte2 short
            # cycle 2 = compte1 short, compte2 long, etc.
            account1_side = "buy"  # Commencer avec compte1 long
            account2_side = "sell"  # Compte2 short
            
            if self.mode == 1:
                logger.info("  Mode: Extended <-> Extended")
            elif self.mode == 2:
                logger.info("  Mode: Extended <-> Hyperliquid")
            else:
                logger.info("  Mode: Extended <-> Lighter")
            
            # Exécuter les cycles
            for cycle_num in range(1, params['num_cycles'] + 1):
                logger.info(f"\n{'='*60}")
                logger.info(f"🚀 CYCLE {cycle_num}/{params['num_cycles']}")
                logger.info(f"{'='*60}")
                
                duration = durations[cycle_num - 1]
                
                # Mode 2/3: Utiliser la nouvelle logique avec comparaison des prix en temps réel
                if self.mode in [2, 3]:
                    second_exchange = "Hyperliquid" if self.mode == 2 else "Lighter"
                    logger.info(f"📊 Mode {self.mode}: Comparaison des prix en temps réel Extended vs {second_exchange}")
                    success = self.run_cycle_mode2(
                        symbol=params['symbol'],
                        leverage=params['leverage'],
                        margin=params['margin'],
                        duration_minutes=duration,
                        pnl_check_delay=params['pnl_check_delay']
                    )
                else:
                    # Mode 1: Exécuter le cycle classique
                    success = self.run_cycle(
                        symbol=params['symbol'],
                        leverage=params['leverage'],
                        margin=params['margin'],
                        duration_minutes=duration,
                        account1_side=account1_side,
                        account2_side=account2_side
                    )
                
                if not success:
                    logger.error(f"❌ Échec du cycle {cycle_num}")
                    break
                
                # Rebalancer après chaque cycle (sauf le dernier) seulement si différence > seuil configuré
                if cycle_num < params['num_cycles']:
                    # Vérifier les balances avant de rebalancer
                    bal1, bal2 = self.check_initial_balances()
                    diff = abs(bal1 - bal2)
                    rebalance_threshold = params['rebalance_threshold']
                    
                    if diff > rebalance_threshold:
                        logger.info(f"\n🔄 Rebalancing entre les cycles...")
                        logger.info(f"⚠️  Différence détectée: ${diff:,.2f} (seuil: ${rebalance_threshold:,.2f})")
                        if not self.rebalance_accounts():
                            logger.error("❌ Échec du rebalancing")
                            break
                    else:
                        logger.info(f"\n✅ Pas de rebalancing nécessaire (différence: ${diff:,.2f} < ${rebalance_threshold:,.2f})")
                    
                    # Délai avant le prochain cycle (si configuré)
                    if params['delay_between_cycles'] > 0:
                        delay_minutes = params['delay_between_cycles']
                        logger.info(f"\n⏳ Délai de {delay_minutes} minute(s) avant le prochain cycle...")
                        delay_seconds = delay_minutes * 60
                        start_time = time.time()
                        while time.time() - start_time < delay_seconds:
                            remaining = int(delay_seconds - (time.time() - start_time))
                            if remaining > 0:
                                mins = remaining // 60
                                secs = remaining % 60
                                logger.info(f"⏱️  Temps restant: {mins:02d}:{secs:02d}")
                                time.sleep(min(10, remaining))  # Afficher toutes les 10 secondes max
                        logger.info("✅ Délai terminé, démarrage du prochain cycle...\n")
                
                # Alterner les positions pour le prochain cycle (Mode 1 uniquement)
                # En Mode 2, les côtés sont déterminés dynamiquement par la comparaison des prix
                if self.mode == 1:
                    account1_side, account2_side = account2_side, account1_side
                    if cycle_num < params['num_cycles']:
                        logger.info(f"Prochain cycle: Extended 1 {account1_side.upper()}, Extended 2 {account2_side.upper()}")
                else:
                    if cycle_num < params['num_cycles']:
                        logger.info(f"Prochain cycle: Les côtés seront déterminés par la comparaison des prix en temps réel")
            
            logger.success(f"\n✅ Tous les cycles terminés avec succès!")
            
            # Transférer tous les fonds vers le compte 1 Extended (si activé)
            if params.get('withdraw_to_extended', True):
                logger.info("\n💰 Transfert de tous les fonds vers le compte 1 Extended...")
                self.transfer_all_funds_to_account1()
            else:
                logger.info("\n💡 Retrait vers Extended désactivé dans la configuration")
            
        except KeyboardInterrupt:
            logger.warning("\n⚠️  Arrêt demandé par l'utilisateur")
            # Fermer les positions ouvertes en cas d'arrêt
            logger.info("Fermeture des positions ouvertes...")
            if 'params' in locals():
                self.close_trades(params['symbol'])
            
            # Transférer tous les fonds vers le compte 1 Extended (si activé)
            withdraw_enabled = params.get('withdraw_to_extended', True) if 'params' in locals() else True
            if withdraw_enabled:
                logger.info("\n💰 Transfert de tous les fonds vers le compte 1 Extended...")
                self.transfer_all_funds_to_account1()
            else:
                logger.info("\n💡 Retrait vers Extended désactivé dans la configuration")
            
        except Exception as e:
            logger.error(f"❌ Erreur: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # Essayer de transférer les fonds même en cas d'erreur (si activé)
            withdraw_enabled = params.get('withdraw_to_extended', True) if 'params' in locals() else True
            if withdraw_enabled:
                try:
                    logger.info("\n💰 Tentative de transfert de tous les fonds vers le compte 1 Extended...")
                    self.transfer_all_funds_to_account1()
                except Exception as cleanup_error:
                    logger.error(f"❌ Erreur lors du transfert de nettoyage: {cleanup_error}")
            else:
                logger.info("\n💡 Retrait vers Extended désactivé dans la configuration")


if __name__ == "__main__":
    # Configuration du logger
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    logger.add(
        "dnfarming.log",
        rotation="10 MB",
        retention="7 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="DEBUG"
    )
    
    # Sélection du mode
    print("\n" + "="*60)
    print("🚀 DN FARMING BOT")
    print("="*60)
    print("\nSélectionnez le mode de trading:")
    print("  1. Extended <-> Extended (défaut)")
    print("     Trading delta neutre entre deux comptes Extended")
    print("  2. Extended <-> Hyperliquid")
    print("     Trading delta neutre entre Extended et Hyperliquid")
    print("  3. Extended <-> Lighter")
    print("     Trading delta neutre entre Extended et Lighter")
    print()
    
    choice = input("Votre choix (1/2/3) [défaut: 1]: ").strip()
    
    if not choice:
        choice = "1"
    
    if choice not in ["1", "2", "3"]:
        logger.error("Choix invalide. Utilisation du mode 1 par défaut.")
        choice = "1"
    
    mode = int(choice)
    
    if mode == 1:
        logger.info("✅ Mode 1 sélectionné: Extended <-> Extended")
    elif mode == 2:
        logger.info("✅ Mode 2 sélectionné: Extended <-> Hyperliquid")
    else:
        logger.info("✅ Mode 3 sélectionné: Extended <-> Lighter")
    
    print()
    
    bot = DNFarmingBot(mode=mode)
    bot.run()

"""
Lighter Exchange API Integration
Utilise le SDK officiel Lighter avec SignerClient
Documentation: https://apidocs.lighter.xyz/
"""
from typing import Optional, Dict, List
import asyncio
import json
import sys
import os
import time
import threading

# Ajouter le SDK Lighter au path
# Essayer d'abord d'importer depuis pip (si installé)
try:
    import lighter
    HAS_LIGHTER_SDK = True
except ImportError:
    # Fallback: utiliser le SDK local
    SDK_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'lighter-python-main')
    if SDK_PATH not in sys.path:
        sys.path.insert(0, SDK_PATH)

try:
    from loguru import logger
    # Désactiver les logs DEBUG pour réduire le bruit
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <level>{message}</level>")
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.INFO)

try:
    import lighter
    from lighter import SignerClient, ApiClient, Configuration
    from lighter import AccountApi, OrderApi, FundingApi, BridgeApi
    from lighter import WsClient
    HAS_LIGHTER_SDK = True
except ImportError as e:
    HAS_LIGHTER_SDK = False
    logger.warning(f"Lighter SDK not available: {e}")

# Vérifier la disponibilité de web3 pour les transactions Arbitrum
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
    HAS_WEB3 = True
except ImportError:
    HAS_WEB3 = False
    logger.warning("web3 not found. Install it with: pip install web3")


class LighterAPI:
    """Client API pour Lighter avec SignerClient"""
    
    # URLs Lighter
    MAINNET_URL = "https://mainnet.zklighter.elliot.ai"
    TESTNET_URL = "https://testnet.zklighter.elliot.ai"
    
    # Scales
    USDC_SCALE = 1e6  # USDC a 6 décimales
    ETH_SCALE = 1e8   # ETH a 8 décimales
    PRICE_SCALE = 100  # Prix en centimes (ex: $4000 = 400000)
    
    def __init__(self, account_index: int, api_private_keys: Dict[int, str], 
                 l1_address: str = None, l1_private_key: str = None, testnet: bool = False):
        """
        Initialise le client Lighter
        
        Args:
            account_index: Index du compte Lighter
            api_private_keys: Dict {api_key_index: private_key} (ex: {0: "0x..."})
            l1_address: Adresse L1 du wallet (optionnel, pour récupérer account_index)
            l1_private_key: Clé privée L1 (requis pour fast withdraw)
            testnet: True pour testnet, False pour mainnet
        """
        self.account_index = account_index
        self.api_private_keys = api_private_keys
        self.l1_address = l1_address
        self.l1_private_key = l1_private_key
        self.testnet = testnet
        
        self.base_url = self.TESTNET_URL if testnet else self.MAINNET_URL
        
        # Clients
        self.signer_client = None
        self.api_client = None
        self.account_api = None
        self.order_api = None
        self.funding_api = None
        
        # Cache pour les métadonnées
        self.markets_cache = None
        self.market_index_by_symbol = {}  # {"ETH": 0, "BTC": 1, ...}
        
        # Event loop pour async
        self._loop = None
        self._loop_thread = None
        
        # WebSocket pour orderbook en temps réel
        self.ws_client = None
        self.orderbook_cache = {}  # {market_id: {"bid": float, "ask": float, "last_update": float}}
        self.ws_connected = False
        self.ws_market_id = None
        
        # WebSocket pour market stats (mark_price) en temps réel
        self.ws_market_stats_client = None
        self.market_stats_cache = {}  # {market_id: {"mark_price": float, "index_price": float, "last_update": float}}
        self.ws_market_stats_connected = False
        self.ws_market_stats_symbols = set()  # Symboles déjà abonnés
        
        # WebSocket pour positions en temps réel
        self.ws_positions_client = None
        self.positions_cache = {}  # {market_index: Position}
        self.ws_positions_connected = False
        self.ws_positions_thread = None
        
        # Compteur pour client_order_index unique
        self._order_index_counter = 0
        
        # Flag pour savoir si l'initialisation a réussi
        self.initialized = False
        
        if HAS_LIGHTER_SDK:
            self._initialize_clients()
        else:
            logger.error("Lighter SDK not available - install it from lighter-python-main")
    
    def _get_event_loop(self):
        """Récupère ou crée un event loop dans un thread séparé"""
        if self._loop is None or self._loop.is_closed():
            self._loop = asyncio.new_event_loop()
            
            def run_loop():
                asyncio.set_event_loop(self._loop)
                self._loop.run_forever()
            
            self._loop_thread = threading.Thread(target=run_loop, daemon=True)
            self._loop_thread.start()
            time.sleep(0.2)  # Laisser le temps au loop de démarrer
        
        return self._loop
    
    def _run_async(self, coro):
        """Exécute une coroutine de manière synchrone"""
        loop = self._get_event_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=30)
    
    def _initialize_clients(self):
        """Initialise les clients Lighter"""
        try:
            # Créer l'event loop d'abord pour aiohttp
            loop = self._get_event_loop()
            
            # Attendre que l'event loop soit bien démarré
            time.sleep(0.5)
            
            # Créer les clients dans un contexte async via le thread avec la boucle en cours d'exécution
            async def create_clients():
                # S'assurer que l'event loop est défini pour ce thread
                asyncio.set_event_loop(asyncio.get_running_loop())
                config = Configuration(host=self.base_url)
                api_client = ApiClient(configuration=config)
                
                # APIs publiques
                account_api = AccountApi(api_client)
                order_api = OrderApi(api_client)
                funding_api = FundingApi(api_client)
                
                return api_client, account_api, order_api, funding_api
            
            # Utiliser _run_async pour exécuter dans le thread avec la boucle en cours d'exécution
            self.api_client, self.account_api, self.order_api, self.funding_api = self._run_async(create_clients())
            
            # Si l1_address est fourni et account_index est 0, essayer de récupérer l'account_index automatiquement
            # Mais continuer avec account_index=0 si la récupération échoue (0 peut être un index valide)
            if self.l1_address and self.account_index == 0:
                found_index = self._get_account_index_from_l1()
                if found_index is not None:
                    logger.info(f"✅ Account index trouvé automatiquement: {found_index}")
                    self.account_index = found_index
                else:
                    # Si la récupération échoue, continuer avec account_index=0
                    # car 0 peut être un index valide (compte principal)
                    logger.info(f"ℹ️  Utilisation de l'account_index {self.account_index} (récupération automatique échouée ou compte non trouvé)")
                    logger.info("   Si ce n'est pas le bon index, définissez LIGHTER_ACCOUNT_INDEX dans votre .env")
            
            # SignerClient pour les transactions signées
            try:
                # Créer le SignerClient dans une coroutine qui s'exécute dans l'event loop
                # ApiClient nécessite un event loop en cours d'exécution (aiohttp)
                # Le problème: ApiClient crée RESTClientObject qui crée aiohttp.TCPConnector
                # qui nécessite asyncio.get_running_loop() même dans __init__
                logger.info("Création du SignerClient...")
                
                # Utiliser run_in_executor pour créer le SignerClient dans le thread de l'event loop
                # mais avec l'event loop défini
                async def create_signer_async():
                    """Crée le SignerClient dans le contexte d'une coroutine avec event loop"""
                    # Dans ce contexte async, asyncio.get_running_loop() retournera l'event loop
                    # ce qui permettra à ApiClient de créer son aiohttp.TCPConnector
                    current_loop = asyncio.get_running_loop()
                    asyncio.set_event_loop(current_loop)
                    
                    # Créer le SignerClient dans le thread de l'event loop
                    # ApiClient créera RESTClientObject, mais le connector sera créé
                    # de manière paresseuse dans _ensure_initialized() qui est appelée
                    # dans request() (async), donc l'event loop sera disponible
                    return SignerClient(
                        url=self.base_url,
                        account_index=self.account_index,
                        api_private_keys=self.api_private_keys
                    )
                
                self.signer_client = self._run_async(create_signer_async())
                logger.debug("SignerClient créé, vérification du client...")
                
                # Vérifier que le client est correctement configuré
                # check_client() fait des appels réseau synchrones, donc on peut l'appeler directement
                try:
                    check_err = self.signer_client.check_client()
                    if check_err:
                        raise Exception(check_err)
                    
                    # Vérifier que le nonce_manager est correctement initialisé
                    if not hasattr(self.signer_client, 'nonce_manager') or self.signer_client.nonce_manager is None:
                        raise Exception("nonce_manager not initialized")
                    
                    # Tester que next_nonce() fonctionne
                    try:
                        test_api_key, test_nonce = self.signer_client.nonce_manager.next_nonce()
                        logger.debug(f"Nonce manager test: api_key_index={test_api_key}, nonce={test_nonce}")
                    except Exception as nonce_test_err:
                        logger.warning(f"Erreur test nonce_manager: {nonce_test_err}")
                        # Ne pas échouer complètement, mais logger un warning
                    
                    logger.success(f"✅ Lighter API initialized for account {self.account_index}")
                    self.initialized = True
                except Exception as check_err:
                    error_str = str(check_err).lower()
                    # Vérifier si c'est l'erreur "invalid PublicKey" (code 21136)
                    if '21136' in str(check_err) or 'invalid PublicKey' in error_str or 'update the sdk' in error_str:
                        logger.error(f"❌ Erreur PublicKey invalide (code 21136) lors de l'initialisation")
                        logger.error(f"   Détails: {check_err}")
                        logger.warning("   Causes possibles:")
                        logger.warning("   1. Les clés API Lighter sont invalides ou expirées")
                        logger.warning("   2. Le SDK Lighter est obsolète (mettez à jour: pip install --upgrade lighter-python)")
                        logger.warning("   3. Le compte Lighter n'existe pas ou n'est pas actif")
                        logger.warning("   Vérifiez vos clés API dans le .env et mettez à jour le SDK si nécessaire")
                        self.initialized = False
                        return
                    elif "account not found" in error_str or "not found" in error_str or "invalid account index" in error_str:
                        logger.warning(f"⚠️  Compte Lighter {self.account_index} non trouvé")
                        logger.warning("   Vous devez d'abord créer un compte sur lighter.xyz et y déposer des fonds")
                        logger.warning("   Le bot continuera mais Lighter ne sera pas utilisable jusqu'à ce qu'un compte soit créé")
                    else:
                        logger.error(f"Lighter client check failed: {check_err}")
                        logger.warning("   Vérifiez que votre LIGHTER_ACCOUNT_INDEX et LIGHTER_API_KEY sont corrects")
                        logger.warning("   Le bot continuera mais Lighter ne sera pas utilisable")
                    self.initialized = False
                    return
            except Exception as e:
                error_str = str(e).lower()
                # Détecter l'erreur "invalid account index" qui signifie que le compte n'existe pas
                if "invalid account index" in error_str or "21102" in error_str:
                    logger.warning(f"⚠️  Compte Lighter {self.account_index} n'existe pas encore")
                    logger.warning("   Le SignerClient ne peut pas être créé car le compte n'a pas été créé sur Lighter")
                    logger.warning("   Pour créer un compte Lighter:")
                    logger.warning("   1. Allez sur https://lighter.xyz")
                    logger.warning("   2. Connectez-vous avec votre wallet (adresse: {})".format(self.l1_address or "non configurée"))
                    logger.warning("   3. Créez un compte et déposez des fonds")
                    logger.warning("   4. Une fois le compte créé, trouvez votre account_index sur lighter.xyz")
                    logger.warning("   5. Configurez LIGHTER_ACCOUNT_INDEX dans votre .env avec le bon index")
                    logger.warning("   Le bot continuera mais Lighter ne sera pas utilisable jusqu'à ce qu'un compte soit créé")
                else:
                    logger.error(f"Failed to create SignerClient: {e}")
                    import traceback
                    traceback.print_exc()
                    logger.warning("Le bot continuera mais Lighter ne sera pas utilisable")
                self.initialized = False
                return
            
            # Charger les marchés
            self._load_markets()
            
        except Exception as e:
            logger.error(f"Failed to initialize Lighter clients: {e}")
            import traceback
            traceback.print_exc()
            # Ne pas lever d'erreur, juste marquer comme non initialisé
            self.initialized = False
    
    def _get_account_index_from_l1(self) -> Optional[int]:
        """
        Récupère l'account_index à partir de l'adresse L1
        
        Returns:
            account_index ou None si non trouvé
        """
        if not self.l1_address:
            return None
        
        try:
            logger.info(f"Recherche du compte Lighter pour l'adresse {self.l1_address}...")
            
            # Récupérer les sous-comptes associés à l'adresse L1
            sub_accounts = self._run_async(
                self.account_api.accounts_by_l1_address(l1_address=self.l1_address)
            )
            
            if sub_accounts and sub_accounts.sub_accounts and len(sub_accounts.sub_accounts) > 0:
                # Prendre le premier sous-compte (ou le master account si plusieurs)
                if len(sub_accounts.sub_accounts) > 1:
                    # Si plusieurs comptes, prendre le master account (index le plus bas)
                    accounts = sorted(sub_accounts.sub_accounts, key=lambda x: int(x.index) if hasattr(x, 'index') else 999999)
                    first_account = accounts[0]
                    logger.info(f"Plusieurs comptes trouvés, utilisation du master account")
                else:
                    first_account = sub_accounts.sub_accounts[0]
                
                account_index = first_account.index if hasattr(first_account, 'index') else None
                
                if account_index is not None:
                    logger.info(f"Compte trouvé: index={account_index}")
                    return account_index
                    
            return None
            
        except Exception as e:
            # Gérer spécifiquement l'erreur "account not found" sans afficher de warning
            error_str = str(e)
            if "account not found" in error_str.lower() or "21100" in error_str:
                # C'est normal si le compte n'existe pas encore
                logger.debug(f"Compte Lighter non trouvé pour l'adresse {self.l1_address}")
            else:
                logger.warning(f"Impossible de récupérer l'account_index depuis l'adresse L1: {e}")
            return None
    
    def _load_markets(self):
        """Charge les informations des marchés"""
        try:
            order_books = self._run_async(self.order_api.order_books())
            
            self.markets_cache = {}
            self.market_index_by_symbol = {}
            
            for ob in order_books.order_books:
                market_id = ob.market_id
                # Le symbole est dans l'attribut 'symbol' (ex: "ETH-PERP", "BTC-PERP", etc.)
                symbol = ob.symbol if hasattr(ob, 'symbol') else f"MARKET_{market_id}"
                
                # Extraire le symbole de base (ex: "ETH" de "ETH-PERP", "BTC" de "BTC-PERP")
                # Le symbole peut être "ETH-PERP", "BTC-PERP", ou juste "ETH", "BTC"
                if '-' in symbol:
                    base_symbol = symbol.split('-')[0]  # "ETH-PERP" -> "ETH"
                elif '_' in symbol:
                    base_symbol = symbol.split('_')[0]  # "ETH_USDC" -> "ETH"
                else:
                    base_symbol = symbol  # "ETH" -> "ETH"
                
                # Normaliser le symbole (enlever les espaces, etc.)
                base_symbol = base_symbol.strip().upper()
                
                # Debug: afficher le symbole brut pour comprendre le format (seulement pour BTC/ETH)
                if 'BTC' in base_symbol or 'ETH' in base_symbol:
                    logger.debug(f"Market {market_id}: symbol='{symbol}' -> base_symbol='{base_symbol}'")
                
                # Récupérer les décimales supportées pour calculer le scale
                size_decimals = int(ob.supported_size_decimals) if hasattr(ob, 'supported_size_decimals') else 4
                base_amount_scale = 10 ** size_decimals  # Ex: 4 décimales = 10000
                
                self.markets_cache[market_id] = {
                    'market_id': market_id,
                    'symbol': symbol,
                    'base_symbol': base_symbol,
                    'tick_size': float(ob.tick_size) if hasattr(ob, 'tick_size') else 0.01,
                    'min_base_amount': float(ob.min_base_amount) if hasattr(ob, 'min_base_amount') else 1,
                    'size_decimals': size_decimals,
                    'base_amount_scale': base_amount_scale,
                }
                # Stocker le mapping symbole -> market_id
                base_symbol_upper = base_symbol.upper()
                self.market_index_by_symbol[base_symbol_upper] = market_id
                
                # Aussi stocker le symbole complet si différent (ex: "ETH-PERP" -> market_id)
                if symbol != base_symbol:
                    self.market_index_by_symbol[symbol.upper()] = market_id
            
            logger.info(f"Loaded {len(self.markets_cache)} Lighter markets")
            # Afficher quelques exemples de symboles trouvés
            sample_symbols = list(self.market_index_by_symbol.keys())[:20]
            logger.debug(f"Sample symbols found: {sample_symbols}")
            logger.debug(f"Total symbols: {len(self.market_index_by_symbol)}")
            
        except Exception as e:
            logger.error(f"Failed to load Lighter markets: {e}")
            # Valeurs par défaut
            self.market_index_by_symbol = {"ETH": 0, "BTC": 1}
    
    def get_market_index(self, symbol: str) -> int:
        """
        Récupère l'index de marché pour un symbole
        
        Args:
            symbol: Symbole (ex: "ETH", "BTC")
            
        Returns:
            Index du marché
        """
        symbol = symbol.upper().strip()
        if symbol in self.market_index_by_symbol:
            return self.market_index_by_symbol[symbol]
        
        # Essayer de charger les marchés si pas encore fait
        if not self.markets_cache:
            self._load_markets()
        
        if symbol in self.market_index_by_symbol:
            return self.market_index_by_symbol[symbol]
        
        # Essayer de recharger les marchés une dernière fois
        try:
            self._load_markets()
            if symbol in self.market_index_by_symbol:
                logger.info(f"✅ Symbol {symbol} trouvé après rechargement: market_index={self.market_index_by_symbol[symbol]}")
                return self.market_index_by_symbol[symbol]
        except Exception as e:
            logger.debug(f"Erreur lors du rechargement des marchés: {e}")
        
        # Si toujours pas trouvé, chercher des variantes (BTC-PERP, BTC_USDC, etc.)
        for key in self.market_index_by_symbol.keys():
            if symbol in key or key.startswith(symbol):
                logger.info(f"✅ Symbol {symbol} trouvé via variante '{key}': market_index={self.market_index_by_symbol[key]}")
                return self.market_index_by_symbol[key]
        
        # Si toujours pas trouvé, lister les symboles disponibles
        available_symbols = list(self.market_index_by_symbol.keys())
        logger.error(f"❌ Symbol {symbol} not found in Lighter markets")
        logger.error(f"   Symboles disponibles: {available_symbols[:50]}...")  # Limiter à 50 pour éviter trop de logs
        logger.warning(f"   Utilisation du market index 0 (ETH) par défaut - VÉRIFIEZ QUE C'EST LA BONNE PAIRE!")
        return 0
    
    def get_balance(self) -> float:
        """
        Récupère le balance USDC disponible
        
        Returns:
            Balance en USDC
        """
        if not self.initialized:
            logger.warning("Lighter client not initialized - returning 0 balance")
            return 0.0
        
        try:
            account = self._run_async(
                self.account_api.account(by="index", value=str(self.account_index))
            )
            
            if account and account.accounts:
                acc = account.accounts[0]
                # Collateral est en USDC (déjà formaté)
                collateral = float(acc.collateral) if hasattr(acc, 'collateral') else 0.0
                return collateral
            
            return 0.0
            
        except Exception as e:
            logger.error(f"Error fetching Lighter balance: {e}")
            return 0.0
    
    def ws_positions(self) -> bool:
        """
        Se connecte au WebSocket account_all_positions pour récupérer les positions en temps réel
        Documentation: https://apidocs.lighter.xyz/docs/websocket-reference#account-all-positions
        
        Returns:
            True si la connexion est établie
        """
        if not self.initialized:
            return False
        
        if self.ws_positions_connected:
            logger.info("WebSocket positions déjà connecté")
            return True
        
        try:
            import websocket
            
            host = self.base_url.replace("https://", "").replace("http://", "")
            ws_url = f"wss://{host}/stream"
            
            logger.info(f"🔌 Connexion WebSocket positions Lighter pour account {self.account_index}...")
            
            def subscribe_to_positions(ws):
                """Fonction helper pour s'abonner au channel positions avec auth"""
                try:
                    auth_token, err = self.signer_client.create_auth_token_with_expiry()
                    if err:
                        logger.error(f"Failed to create auth token for WebSocket: {err}")
                        auth_token = None
                except Exception as auth_err:
                    logger.warning(f"Erreur création auth token: {auth_err}")
                    auth_token = None
                
                subscribe_msg = {
                    "type": "subscribe",
                    "channel": f"account_all_positions/{self.account_index}"
                }
                
                # Ajouter auth si disponible (requis selon la doc pour comptes privés)
                if auth_token:
                    subscribe_msg["auth"] = auth_token
                    logger.debug(f"Abonnement avec auth token au channel account_all_positions/{self.account_index}")
                else:
                    logger.warning(f"Abonnement sans auth token (peut échouer pour compte privé)")
                
                ws.send(json.dumps(subscribe_msg))
                logger.debug(f"Message d'abonnement envoyé: {subscribe_msg}")
            
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                    msg_type = data.get('type')
                    channel = data.get('channel', '')
                    
                    logger.info(f"📨 WebSocket positions message reçu: type={msg_type}, channel={channel}")
                    logger.info(f"   Message brut: {message[:500]}...")  # Afficher les 500 premiers caractères
                    
                    if msg_type == 'connected':
                        # S'abonner au channel account_all_positions avec auth token
                        # Selon la doc: auth est requis pour les comptes privés
                        subscribe_to_positions(ws)
                    
                    # Gérer les différents types de messages selon la doc
                    # Le type peut être 'subscribed' ou 'subscribed/account_all_positions'
                    elif msg_type and 'subscribed' in str(msg_type) and 'account_all_positions' in (channel or str(msg_type) or ''):
                        logger.debug(f"✅ Abonnement confirmé: {channel}")
                        # Le premier message peut contenir les positions initiales
                        positions_data = data.get('positions', {})
                        if positions_data:
                            logger.debug(f"   Positions initiales reçues: {len(positions_data)} positions")
                            # Parser les positions initiales de la même manière que les updates
                            for market_index_str, position in positions_data.items():
                                try:
                                    market_index = int(market_index_str)
                                    sign = int(position.get('sign', 0))
                                    position_amount_str = position.get('position', '0')
                                    position_amount = float(position_amount_str)
                                    
                                    if abs(position_amount) < 0.0001:
                                        continue
                                    
                                    symbol = "UNKNOWN"
                                    for sym, mid in self.market_index_by_symbol.items():
                                        if mid == market_index:
                                            symbol = sym
                                            break
                                    
                                    self.positions_cache[market_index] = {
                                        'symbol': symbol,
                                        'market_id': market_index,
                                        'market_index': market_index,
                                        'side': 'LONG' if sign > 0 else 'SHORT',
                                        'size': abs(position_amount),
                                        'size_signed': position_amount * sign,
                                        'position': position_amount_str,
                                        'sign': sign,
                                        'entry_price': float(position.get('avg_entry_price', '0')),
                                        'unrealized_pnl': float(position.get('unrealized_pnl', '0')),
                                        'realized_pnl': float(position.get('realized_pnl', '0')),
                                        'last_update': time.time()
                                    }
                                    logger.debug(f"   Position initiale: {symbol} {self.positions_cache[market_index]['side']} {abs(position_amount)}")
                                except Exception as pos_err:
                                    logger.error(f"Erreur parsing position initiale {market_index_str}: {pos_err}")
                    
                    elif msg_type and 'update' in str(msg_type) and 'account_all_positions' in (channel or str(msg_type) or ''):
                        # Mettre à jour le cache des positions
                        positions_data = data.get('positions', {})
                        shares = data.get('shares', [])
                        
                        logger.debug(f"📊 Mise à jour positions WebSocket: {len(positions_data)} positions, {len(shares)} shares")
                        
                        # Parser les positions selon la doc
                        # Format: positions = { "{MARKET_INDEX}": Position }
                        for market_index_str, position in positions_data.items():
                            try:
                                market_index = int(market_index_str)
                                
                                # Position JSON selon la doc: sign (1=Long, -1=Short), position (string)
                                sign = int(position.get('sign', 0))
                                position_amount_str = position.get('position', '0')
                                position_amount = float(position_amount_str)
                                
                                if abs(position_amount) < 0.0001:
                                    # Position fermée, mais ne pas la supprimer immédiatement du cache
                                    # Car cela pourrait être une erreur temporaire ou un arrondi
                                    # On la marque comme fermée mais on la garde dans le cache pendant 60 secondes
                                    # pour éviter de perdre les données si c'est une erreur
                                    if market_index in self.positions_cache:
                                        old_pos = self.positions_cache[market_index]
                                        old_size = abs(float(old_pos.get('position', 0)))
                                        # Si la position était significative avant (> 0.0001), logger un warning
                                        if old_size > 0.0001:
                                            logger.warning(f"⚠️  Position WebSocket semble fermée (size={position_amount}) pour {old_pos.get('symbol', 'UNKNOWN')}, mais on garde dans le cache 60s au cas où")
                                            # Marquer comme fermée mais garder dans le cache avec un timestamp
                                            self.positions_cache[market_index]['closed_at'] = time.time()
                                            self.positions_cache[market_index]['size'] = 0
                                            self.positions_cache[market_index]['size_signed'] = 0
                                        else:
                                            # Si déjà marquée comme fermée depuis plus de 60s, la supprimer
                                            closed_at = old_pos.get('closed_at', 0)
                                            if closed_at > 0 and time.time() - closed_at > 60:
                                                logger.debug(f"   Position fermée depuis >60s, suppression du cache: market_index={market_index}")
                                                del self.positions_cache[market_index]
                                    continue
                                
                                # Trouver le symbole
                                symbol = "UNKNOWN"
                                for sym, mid in self.market_index_by_symbol.items():
                                    if mid == market_index:
                                        symbol = sym
                                        break
                                
                                # Mettre à jour le cache avec toutes les données de la Position selon la doc
                                old_position = self.positions_cache.get(market_index)
                                self.positions_cache[market_index] = {
                                    'symbol': symbol,
                                    'market_id': market_index,
                                    'market_index': market_index,
                                    'side': 'LONG' if sign > 0 else 'SHORT',
                                    'size': abs(position_amount),
                                    'size_signed': position_amount * sign,
                                    'position': position_amount_str,
                                    'sign': sign,
                                    'entry_price': float(position.get('avg_entry_price', '0')),
                                    'unrealized_pnl': float(position.get('unrealized_pnl', '0')),
                                    'realized_pnl': float(position.get('realized_pnl', '0')),
                                    'last_update': time.time(),
                                    # Supprimer le flag closed_at si la position est rouverte
                                    'closed_at': 0
                                }
                                
                                # Logger si c'est une nouvelle position ou une mise à jour
                                if old_position:
                                    time_since_last = time.time() - old_position.get('last_update', 0)
                                    if time_since_last > 30:
                                        logger.info(f"📊 Position WebSocket mise à jour après {time_since_last:.0f}s: {symbol} {self.positions_cache[market_index]['side']} {abs(position_amount)}")
                                    else:
                                        logger.debug(f"✅ Position mise à jour dans le cache: {symbol} {self.positions_cache[market_index]['side']} {abs(position_amount)} (market_index={market_index})")
                                else:
                                    logger.info(f"🆕 Nouvelle position ajoutée au cache: {symbol} {self.positions_cache[market_index]['side']} {abs(position_amount)}")
                            except Exception as pos_err:
                                logger.error(f"Erreur parsing position {market_index_str}: {pos_err}")
                                import traceback
                                logger.debug(traceback.format_exc())
                    
                    elif msg_type == 'ping':
                        ws.send(json.dumps({"type": "pong"}))
                    
                    else:
                        # Logger les autres types de messages pour debug
                        logger.debug(f"📨 Message WebSocket positions: type={msg_type}, channel={channel}")
                        if msg_type not in ['ping', 'pong']:
                            logger.debug(f"   Données: {data}")
                    
                except Exception as e:
                    logger.error(f"Error processing positions WebSocket message: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
            
            def on_error(ws, error):
                logger.error(f"WebSocket positions error: {error}")
            
            def on_close(ws, close_status_code, close_msg):
                logger.warning(f"WebSocket positions fermé: {close_status_code} - {close_msg}")
                self.ws_positions_connected = False
                # Tentative de reconnexion automatique après 5 secondes
                if close_status_code != 1000:  # Pas une fermeture normale
                    logger.info("Tentative de reconnexion automatique WebSocket positions Lighter dans 5 secondes...")
                    time.sleep(5)
                    try:
                        self.ws_positions()
                    except:
                        pass
            
            def subscribe_to_positions(ws):
                """Fonction helper pour s'abonner au channel positions"""
                try:
                    auth_token, err = self.signer_client.create_auth_token_with_expiry()
                    if err:
                        logger.error(f"Failed to create auth token for WebSocket: {err}")
                        auth_token = None
                except Exception as auth_err:
                    logger.warning(f"Erreur création auth token: {auth_err}")
                    auth_token = None
                
                subscribe_msg = {
                    "type": "subscribe",
                    "channel": f"account_all_positions/{self.account_index}"
                }
                
                # Ajouter auth si disponible (requis selon la doc pour comptes privés)
                if auth_token:
                    subscribe_msg["auth"] = auth_token
                    logger.debug(f"Abonnement avec auth token au channel account_all_positions/{self.account_index}")
                else:
                    logger.warning(f"Abonnement sans auth token (peut échouer pour compte privé)")
                
                ws.send(json.dumps(subscribe_msg))
                logger.debug(f"Message d'abonnement envoyé: {subscribe_msg}")
            
            def on_open(ws):
                logger.success("✅ WebSocket positions Lighter connecté")
                self.ws_positions_connected = True
                # Envoyer l'abonnement immédiatement après connexion
                time.sleep(0.5)  # Attendre un peu que la connexion soit stable
                subscribe_to_positions(ws)
            
            def run_ws():
                self.ws_positions_client = websocket.WebSocketApp(
                    ws_url,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close,
                    on_open=on_open
                )
                self.ws_positions_client.run_forever()
            
            self.ws_positions_thread = threading.Thread(target=run_ws, daemon=True)
            self.ws_positions_thread.start()
            
            # Attendre la connexion
            time.sleep(2)
            
            if self.ws_positions_connected:
                logger.success(f"✅ WebSocket positions Lighter démarré pour account {self.account_index}")
                return True
            else:
                logger.warning("WebSocket positions Lighter: connexion en cours...")
                return False
            
        except Exception as e:
            logger.error(f"Erreur connexion WebSocket positions Lighter: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def get_positions(self) -> List[Dict]:
        """
        Récupère les positions ouvertes
        Utilise d'abord le cache WebSocket, puis l'API REST en fallback
        
        Returns:
            Liste des positions formatées
        """
        if not self.initialized:
            return []
        
        # Essayer d'abord le cache WebSocket (plus rapide et temps réel)
        # Utiliser le cache WebSocket même s'il est un peu ancien (jusqu'à 300 secondes = 5 minutes)
        # L'API REST peut ne pas retourner les positions, donc le cache WebSocket est préférable
        # Si le WebSocket est connecté, on fait confiance au cache même s'il est ancien
        if self.ws_positions_connected:
            # Si le cache existe et contient des données
            if self.positions_cache:
                positions = []
                for market_index, pos_data in self.positions_cache.items():
                    # Ignorer les positions marquées comme fermées
                    if pos_data.get('closed_at', 0) > 0:
                        closed_at = pos_data.get('closed_at', 0)
                        # Si fermée depuis plus de 60s, ne pas l'inclure
                        if time.time() - closed_at > 60:
                            continue
                        # Si fermée récemment (<60s), ne pas l'inclure non plus (c'est une position fermée)
                        continue
                    
                    last_update = pos_data.get('last_update', 0)
                    # Ignorer les positions avec size = 0 (fermées)
                    if pos_data.get('size', 0) == 0:
                        continue
                    
                    # Utiliser les données du cache si elles sont récentes (< 300 secondes = 5 minutes)
                    # Même si elles sont anciennes, c'est mieux que l'API REST qui peut ne rien retourner
                    # Le WebSocket devrait continuer à envoyer des mises à jour, mais si ce n'est pas le cas,
                    # on garde les dernières positions connues plutôt que de perdre complètement les données
                    if time.time() - last_update < 300:
                        positions.append(pos_data.copy())
                    else:
                        # Si très ancien (>5min), utiliser quand même si c'est la seule source
                        logger.debug(f"Position cache très ancienne ({(time.time() - last_update):.0f}s) pour market_index={market_index}, utilisation quand même")
                        positions.append(pos_data.copy())  # Utiliser quand même plutôt que rien
                
                if positions:
                    # Utiliser le cache WebSocket même s'il est un peu ancien
                    # C'est plus fiable que l'API REST qui peut ne pas retourner les positions
                    age_seconds = max([time.time() - p.get('last_update', 0) for p in positions]) if positions else 0
                    # Supprimer le log warning répétitif, juste debug
                    logger.debug(f"Positions depuis cache WebSocket (âge: {age_seconds:.0f}s): {len(positions)} positions")
                    for p in positions:
                        logger.debug(f"   - {p.get('symbol')}: {p.get('side')} {p.get('size', 0)} (market_index={p.get('market_index')})")
                    return positions
            else:
                # WebSocket connecté mais cache vide - peut-être que les données n'ont pas encore été reçues
                # On passe au fallback API REST
                logger.debug(f"WebSocket positions connecté mais cache vide, utilisation de l'API REST")
        
        # Fallback sur API REST
        try:
            account = self._run_async(
                self.account_api.account(by="index", value=str(self.account_index))
            )
            
            positions = []
            
            if account and account.accounts:
                acc = account.accounts[0]
                
                # Les positions sont dans account.positions ou account.position_details
                position_details = acc.position_details if hasattr(acc, 'position_details') else []
                
                for pos in position_details:
                    # Sign: 1 = Long, -1 = Short
                    sign = int(pos.sign) if hasattr(pos, 'sign') else 0
                    position_amount = float(pos.position) if hasattr(pos, 'position') else 0
                    
                    if position_amount == 0:
                        continue
                    
                    market_id = int(pos.market_id) if hasattr(pos, 'market_id') else 0
                    
                    # Trouver le symbole
                    symbol = "UNKNOWN"
                    for sym, mid in self.market_index_by_symbol.items():
                        if mid == market_id:
                            symbol = sym
                            break
                    
                    positions.append({
                        'symbol': symbol,
                        'market_id': market_id,
                        'market_index': market_id,
                        'side': 'LONG' if sign > 0 else 'SHORT',
                        'size': abs(position_amount),
                        'size_signed': position_amount * sign,
                        'entry_price': float(pos.avg_entry_price) if hasattr(pos, 'avg_entry_price') else 0,
                        'unrealized_pnl': float(pos.unrealized_pn_l) if hasattr(pos, 'unrealized_pn_l') else 0,
                        'realized_pnl': float(pos.realized_pn_l) if hasattr(pos, 'realized_pn_l') else 0,
                    })
            
            if positions:
                logger.info(f"✅ Positions depuis API REST: {len(positions)} positions")
                for p in positions:
                    logger.debug(f"   - {p.get('symbol')}: {p.get('side')} {p.get('size', 0)} (market_index={p.get('market_index')}, size_signed={p.get('size_signed', 0)})")
            else:
                logger.debug(f"✅ Positions depuis API REST: 0 positions")
            
            return positions
            
        except Exception as e:
            logger.error(f"Error fetching Lighter positions: {e}")
            return []
    
    def get_open_positions(self) -> List[Dict]:
        """Alias pour get_positions (compatibilité avec l'interface)"""
        return self.get_positions()
    
    def get_positions_from_explorer(self) -> List[Dict]:
        """
        Récupère les positions ouvertes depuis l'API Explorer publique
        Plus fiable que le WebSocket pour vérifier l'existence des positions après placement d'ordre
        
        API: GET https://explorer.elliot.ai/api/accounts/{L1_ADDRESS}/positions
        
        Format de réponse:
        {
          "positions": {
            "1": {
              "market_index": 1,
              "pnl": "0.500028",
              "side": "short",
              "size": "-0.01299",
              "entry_price": "87350.393303"
            }
          }
        }
        
        Returns:
            Liste des positions formatées
        """
        logger.debug("🔍 Appel API Explorer pour récupérer positions Lighter...")
        logger.debug(f"   L1 address disponible: {self.l1_address}")
        
        if not self.l1_address:
            logger.error("❌ L1 address not available for Explorer API")
            return []
        
        try:
            import requests
            
            # Normaliser l'adresse (avec 0x)
            if not self.l1_address:
                logger.error("❌ LIGHTER_L1_ADDRESS non défini dans .env")
                return []
            
            address = self.l1_address if self.l1_address.startswith('0x') else f"0x{self.l1_address}"
            
            url = f"https://explorer.elliot.ai/api/accounts/{address}/positions"
            headers = {"accept": "application/json"}
            
            logger.debug(f"   URL: {url}")
            logger.debug(f"   Headers: {headers}")
            
            response = requests.get(url, headers=headers)
            logger.debug(f"   Status code: {response.status_code}")
            
            # Gérer l'erreur 404 gracieusement (compte non trouvé ou pas encore créé)
            if response.status_code == 404:
                logger.debug(f"   ⚠️  Compte non trouvé dans l'Explorer API (404) - peut-être pas encore créé sur Lighter")
                return []  # Retourner une liste vide au lieu de lever une exception
            
            response.raise_for_status()
            
            data = response.json()
            logger.debug(f"   ✅ Réponse API: {data}")
            
            positions = []
            
            # La réponse est un dict avec les market_index comme clés
            logger.debug(f"   Type de 'positions': {type(data.get('positions'))}")
            logger.debug(f"   Contenu 'positions': {data.get('positions')}")
            
            if 'positions' in data and isinstance(data['positions'], dict):
                logger.debug(f"   📊 Parsing {len(data['positions'])} positions...")
                
                for market_index_str, pos in data['positions'].items():
                    logger.debug(f"      Market {market_index_str}: {pos}")
                    
                    # Extraire les données
                    market_index = int(pos.get('market_index', market_index_str))
                    size_str = pos.get('size', '0')
                    size_float = float(size_str)
                    
                    logger.debug(f"         market_index={market_index}, size={size_float}")
                    
                    if size_float == 0:
                        logger.debug(f"         ⏭️  Skipped (size=0)")
                        continue
                    
                    side_str = pos.get('side', '').upper()
                    
                    # Trouver le symbole depuis market_index
                    symbol = "UNKNOWN"
                    for sym, mid in self.market_index_by_symbol.items():
                        if mid == market_index:
                            symbol = sym
                            break
                    
                    logger.debug(f"         ✅ Symbol={symbol}, side={side_str}")
                    
                    position_data = {
                        'symbol': symbol,
                        'market_id': market_index,
                        'market_index': market_index,
                        'side': side_str if side_str in ['LONG', 'SHORT'] else ('LONG' if size_float > 0 else 'SHORT'),
                        'size': abs(size_float),
                        'size_signed': size_float,
                        'entry_price': float(pos.get('entry_price', 0)),
                        'open_price': float(pos.get('entry_price', 0)),
                        'unrealized_pnl': float(pos.get('pnl', 0)),
                        'source': 'explorer_api'
                    }
                    positions.append(position_data)
                    logger.debug(f"         Position ajoutée: {position_data}")
            else:
                logger.warning(f"   ⚠️  Aucune position dans la réponse ou format incorrect")
            
            logger.debug(f"   ✅ Total positions retournées: {len(positions)}")
            return positions
            
        except Exception as e:
            logger.error(f"❌ Error fetching positions from Explorer API: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []
    
    def get_ticker(self, symbol: str) -> Optional[Dict]:
        """
        Récupère les prix bid/ask/last pour un symbole
        Utilise d'abord le cache WebSocket, puis l'API REST en fallback
        
        Args:
            symbol: Symbole (ex: "ETH", "BTC")
            
        Returns:
            Dict avec {'bid': float, 'ask': float, 'last': float}
        """
        try:
            market_id = self.get_market_index(symbol)
            
            # Essayer d'abord le cache WebSocket (plus rapide et temps réel)
            cached = self.orderbook_cache.get(market_id)
            if cached:
                # Vérifier que les données ne sont pas trop anciennes (max 30 secondes)
                if time.time() - cached.get('last_update', 0) < 30:
                    bid = cached.get('bid', 0)
                    ask = cached.get('ask', 0)
                    if bid > 0 and ask > 0:
                        mid_price = (bid + ask) / 2
                        logger.debug(f"✅ Prix {symbol} depuis cache WebSocket: bid={bid}, ask={ask}")
                        return {
                            'bid': bid,
                            'ask': ask,
                            'last': mid_price
                        }
            
            # Si pas de cache WebSocket, démarrer le WebSocket pour ce symbole
            if not self.ws_connected or self.ws_market_id != market_id:
                logger.debug(f"Démarrage WebSocket pour {symbol} (market_id={market_id})...")
                self.ws_orderbook(symbol)
                # Attendre un peu pour recevoir les premières données (snapshot)
                time.sleep(2)
                
                # Vérifier à nouveau le cache après démarrage du WebSocket
                cached = self.orderbook_cache.get(market_id)
                if cached:
                    bid = cached.get('bid', 0)
                    ask = cached.get('ask', 0)
                    if bid > 0 and ask > 0:
                        mid_price = (bid + ask) / 2
                        logger.debug(f"✅ Prix {symbol} depuis WebSocket: bid={bid}, ask={ask}")
                        return {
                            'bid': bid,
                            'ask': ask,
                            'last': mid_price
                        }
            
            # Fallback: utiliser l'API REST order_book_details
            logger.debug(f"Fallback API REST pour {symbol} (market_id={market_id})...")
            try:
                ob_details = self._run_async(
                    self.order_api.order_book_details(market_id=market_id)
                )
                
                if ob_details:
                    # Récupérer bid/ask depuis l'orderbook
                    best_bid = 0.0
                    best_ask = 0.0
                    
                    # Parser les niveaux de prix - vérifier différents formats
                    if hasattr(ob_details, 'bids') and ob_details.bids:
                        # ob_details.bids peut être une liste d'objets ou de dicts
                        first_bid = ob_details.bids[0]
                        if hasattr(first_bid, 'price'):
                            best_bid = float(first_bid.price)
                        elif isinstance(first_bid, dict):
                            best_bid = float(first_bid.get('price', 0))
                        else:
                            best_bid = float(first_bid)
                    
                    if hasattr(ob_details, 'asks') and ob_details.asks:
                        first_ask = ob_details.asks[0]
                        if hasattr(first_ask, 'price'):
                            best_ask = float(first_ask.price)
                        elif isinstance(first_ask, dict):
                            best_ask = float(first_ask.get('price', 0))
                        else:
                            best_ask = float(first_ask)
                    
                    # Si on n'a pas bid/ask, essayer recent_trades pour obtenir le dernier prix
                    if (best_bid == 0 or best_ask == 0) and hasattr(self.order_api, 'recent_trades'):
                        try:
                            recent_trades = self._run_async(
                                self.order_api.recent_trades(market_id=market_id, limit=1)
                            )
                            if recent_trades and hasattr(recent_trades, 'trades') and recent_trades.trades:
                                last_trade = recent_trades.trades[0]
                                if hasattr(last_trade, 'price'):
                                    last_price = float(last_trade.price)
                                    if best_bid == 0:
                                        best_bid = last_price * 0.9999
                                    if best_ask == 0:
                                        best_ask = last_price * 1.0001
                                    logger.debug(f"Utilisation du dernier trade pour {symbol}: {last_price}")
                        except Exception as trade_err:
                            logger.debug(f"Erreur lors de la récupération des trades: {trade_err}")
                    
                    # Si on n'a pas bid/ask, utiliser ticker ou mid price
                    if (best_bid == 0 or best_ask == 0) and hasattr(ob_details, 'ticker'):
                        ticker = ob_details.ticker
                        if hasattr(ticker, 'mark_price'):
                            mark_price = float(ticker.mark_price)
                            if best_bid == 0:
                                best_bid = mark_price * 0.9999
                            if best_ask == 0:
                                best_ask = mark_price * 1.0001
                    
                    mid_price = (best_bid + best_ask) / 2 if best_bid and best_ask else 0
                    
                    if mid_price > 0:
                        logger.debug(f"✅ Prix {symbol} depuis API REST: bid={best_bid}, ask={best_ask}")
                        return {
                            'bid': best_bid,
                            'ask': best_ask,
                            'last': mid_price
                        }
            except Exception as ob_err:
                logger.debug(f"Erreur order_book_details pour {symbol}: {ob_err}")
            
            # Si toujours pas de prix, essayer de recharger les marchés
            logger.warning(f"⚠️  Aucun prix trouvé pour {symbol}, rechargement des marchés...")
            try:
                self._load_markets()
                new_market_id = self.get_market_index(symbol)
                if new_market_id != market_id:
                    logger.info(f"Market ID changé pour {symbol}: {market_id} -> {new_market_id}")
                    # Réessayer avec le nouveau market_id
                    ob_details = self._run_async(
                        self.order_api.order_book_details(market_id=new_market_id)
                    )
                    if ob_details and hasattr(ob_details, 'bids') and ob_details.bids:
                        best_bid = float(ob_details.bids[0].price) if ob_details.bids else 0
                        best_ask = float(ob_details.asks[0].price) if ob_details.asks else 0
                        mid_price = (best_bid + best_ask) / 2 if best_bid and best_ask else 0
                        if mid_price > 0:
                            return {'bid': best_bid, 'ask': best_ask, 'last': mid_price}
            except Exception as retry_e:
                logger.debug(f"Retry failed: {retry_e}")
            
            logger.error(f"❌ Impossible de récupérer le prix pour {symbol} (market_id={market_id})")
            return None
            
        except Exception as e:
            logger.error(f"Error fetching Lighter ticker for {symbol}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None
    
    def get_size_decimals(self, symbol: str) -> int:
        """
        Récupère le nombre de décimales pour la taille d'un symbole
        
        Args:
            symbol: Symbole (ex: "ETH", "BTC")
            
        Returns:
            Nombre de décimales
        """
        # Lighter utilise généralement 4 décimales pour les tailles
        return 4
    
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """
        Configure le levier pour un symbole
        
        Args:
            symbol: Symbole (ex: "ETH", "BTC")
            leverage: Levier désiré (ex: 10, 20, 50)
            
        Returns:
            True si succès
        """
        if not self.initialized:
            logger.error("Lighter client not initialized - cannot set leverage")
            return False
            
        try:
            if not self.signer_client:
                logger.error("SignerClient not available - cannot set leverage")
                return False
            
            market_index = self.get_market_index(symbol)
            
            # update_leverage prend: market_index, margin_mode (0=cross, 1=isolated), leverage
            # Retourne: (tx_info, api_response, error)
            result = self._run_async(
                self.signer_client.update_leverage(
                    market_index=market_index,
                    margin_mode=self.signer_client.CROSS_MARGIN_MODE,  # Cross margin
                    leverage=leverage
                )
            )
            
            if result and len(result) >= 3:
                tx_info, api_response, error = result
                if error is None:
                    logger.info(f"✅ Lighter leverage set to {leverage}x for {symbol}")
                    return True
                else:
                    error_str = str(error)
                    logger.error(f"Failed to set Lighter leverage: {error_str}")
                    
                    # Vérifier si c'est l'erreur "invalid nonce" (code 21104)
                    if '21104' in error_str or 'invalid nonce' in error_str.lower():
                        logger.warning("⚠️  Erreur nonce invalide (code 21104) lors de la configuration du levier")
                        logger.warning("   Tentative de réinitialisation du nonce manager...")
                        # Réinitialiser le nonce manager
                        try:
                            if hasattr(self.signer_client, 'nonce_manager') and self.signer_client.nonce_manager:
                                # Réinitialiser le nonce manager pour forcer la récupération du nonce actuel
                                self.signer_client.nonce_manager._nonce_cache = {}
                                logger.debug("   Cache nonce vidé, récupération du nonce actuel...")
                                
                                # Attendre un peu avant de réessayer
                                time.sleep(1)
                                
                                # Réessayer de configurer le levier
                                logger.info(f"Tentative de reconfiguration du levier {leverage}x pour {symbol}...")
                                result_retry = self._run_async(
                                    self.signer_client.update_leverage(
                                        market_index=market_index,
                                        margin_mode=self.signer_client.CROSS_MARGIN_MODE,
                                        leverage=leverage
                                    )
                                )
                                
                                if result_retry and len(result_retry) >= 3:
                                    tx_info_retry, api_response_retry, error_retry = result_retry
                                    if error_retry is None:
                                        logger.success(f"✅ Lighter leverage set to {leverage}x for {symbol} (après retry)")
                                        return True
                                    else:
                                        logger.warning(f"⚠️  Échec retry configuration levier: {error_retry}")
                        except Exception as retry_err:
                            logger.warning(f"⚠️  Erreur lors du retry: {retry_err}")
                    
                    # Vérifier si c'est l'erreur "invalid PublicKey" (code 21136)
                    if '21136' in error_str or 'invalid PublicKey' in error_str or 'update the sdk' in error_str:
                        logger.warning("⚠️  Erreur PublicKey invalide (code 21136) lors de la configuration du levier")
                        logger.warning("   Tentative de réinitialisation du SignerClient...")
                        # Essayer de réinitialiser le SignerClient
                        try:
                            self.signer_client = SignerClient(
                                url=self.base_url,
                                account_index=self.account_index,
                                api_private_keys=self.api_private_keys
                            )
                            self.signer_client.check_client()
                            logger.success("✅ SignerClient réinitialisé")
                            
                            # Réessayer de configurer le levier
                            logger.info(f"Tentative de reconfiguration du levier {leverage}x pour {symbol}...")
                            result_retry = self._run_async(
                                self.signer_client.update_leverage(
                                    market_index=market_index,
                                    margin_mode=self.signer_client.CROSS_MARGIN_MODE,
                                    leverage=leverage
                                )
                            )
                            
                            if result_retry and len(result_retry) >= 3:
                                tx_info_retry, api_response_retry, error_retry = result_retry
                                if error_retry is None:
                                    logger.success(f"✅ Lighter leverage set to {leverage}x for {symbol} (après réinitialisation)")
                                    return True
                                else:
                                    logger.error(f"Échec après réinitialisation: {error_retry}")
                                    return False
                        except Exception as reinit_err:
                            logger.error(f"Échec réinitialisation SignerClient: {reinit_err}")
                            logger.error("   Vérifiez que les clés API Lighter sont correctes et que le SDK est à jour")
                    
                    return False
            
            return False
            
        except Exception as e:
            logger.error(f"Error setting Lighter leverage for {symbol}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def deposit(self, amount: float, from_address: str = None, private_key: str = None, prefer_fast: bool = True) -> Optional[Dict]:
        """
        Dépose des USDC depuis Arbitrum vers Lighter via leur bridge
        
        Args:
            amount: Montant en USDC à déposer
            from_address: Adresse Arbitrum source (optionnel)
            private_key: Clé privée Arbitrum pour signer la transaction (requis)
            prefer_fast: True pour préférer un fast bridge (vérifie et attend si nécessaire)
            
        Returns:
            Dict avec status et détails ou None si échec
        """
        if not self.initialized:
            logger.error("Lighter client not initialized - cannot deposit")
            return {'status': 'error', 'message': 'Lighter client not initialized'}
        
        if not HAS_WEB3:
            logger.error("web3 not available. Install it with: pip install web3")
            return {'status': 'error', 'message': 'web3 not available'}
        
        if not private_key:
            logger.error("Private key required for deposit")
            return {'status': 'error', 'message': 'Private key required'}
        
        try:
            from web3 import Web3
            from eth_account import Account
            from lighter import BridgeApi
            import requests
            
            # Adresse du contrat USDC sur Arbitrum
            ARBITRUM_USDC = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
            
            # Étape 0: Vérifier si le prochain bridge sera fast (si prefer_fast=True)
            is_next_fast = False
            fast_bridge_limit = None
            if prefer_fast:
                logger.info("Vérification si le prochain bridge sera fast...")
                try:
                    bridge_api = BridgeApi(self.api_client)
                    l1_addr = self.l1_address or from_address
                    
                    if l1_addr:
                        # Vérifier si le prochain bridge sera fast
                        fast_check = self._run_async(
                            bridge_api.bridges_is_next_bridge_fast(l1_address=l1_addr)
                        )
                        if fast_check and hasattr(fast_check, 'is_next_bridge_fast'):
                            is_next_fast = fast_check.is_next_bridge_fast
                            logger.info(f"Prochain bridge: {'FAST' if is_next_fast else 'SECURE'}")
                        
                        # Obtenir la limite du fast bridge
                        fast_bridge_info = self._run_async(bridge_api.fastbridge_info())
                        if fast_bridge_info and hasattr(fast_bridge_info, 'fast_bridge_limit'):
                            fast_bridge_limit = float(fast_bridge_info.fast_bridge_limit)
                            logger.info(f"Limite fast bridge: ${fast_bridge_limit:,.2f} USDC")
                            
                            if amount > fast_bridge_limit:
                                logger.warning(f"⚠️  Montant (${amount:.2f}) supérieur à la limite fast bridge (${fast_bridge_limit:,.2f})")
                                logger.warning("   Le dépôt utilisera un bridge SECURE")
                                is_next_fast = False
                except Exception as e:
                    logger.debug(f"Impossible de vérifier le type de bridge: {e}")
                    logger.info("Continuation avec le dépôt standard...")
            
            # Étape 1: Obtenir l'intent_address via l'API Lighter pour les dépôts externes
            logger.info("Récupération de l'intent_address pour le dépôt externe...")
            intent_address = None
            l1_addr = self.l1_address or from_address
            
            if l1_addr:
                try:
                    # Appeler l'API Lighter pour créer une intent_address
                    intent_url = "https://mainnet.zklighter.elliot.ai/api/v1/createIntentAddress"
                    intent_data = {
                        "chain_id": "42161",  # Arbitrum
                        "from_addr": l1_addr,
                        "amount": "0",
                        "is_external_deposit": "true"
                    }
                    
                    response = requests.post(
                        intent_url,
                        data=intent_data,
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                        timeout=30
                    )
                    
                    if response.status_code == 200:
                        intent_response = response.json()
                        # L'API retourne probablement l'intent_address dans la réponse
                        if isinstance(intent_response, dict):
                            # Essayer différents noms de champs possibles
                            intent_address = (
                                intent_response.get('intent_address') or
                                intent_response.get('intentAddress') or
                                intent_response.get('address') or
                                intent_response.get('data')
                            )
                            if intent_address:
                                logger.success(f"✅ Intent address obtenue: {intent_address}")
                            else:
                                logger.debug(f"Response structure: {intent_response}")
                        elif isinstance(intent_response, str):
                            # Si c'est directement une adresse
                            if intent_response.startswith('0x'):
                                intent_address = intent_response
                                logger.success(f"✅ Intent address obtenue: {intent_address}")
                    else:
                        logger.warning(f"Échec de la récupération de l'intent_address: {response.status_code} - {response.text}")
                except Exception as e:
                    logger.warning(f"Erreur lors de la récupération de l'intent_address: {e}")
                    logger.warning("Tentative avec la méthode alternative via BridgeApi...")
            
            # Étape 2: Essayer aussi via BridgeApi (méthode alternative)
            bridge_address = None
            if not intent_address:
                logger.info("Récupération de l'adresse du bridge Lighter via BridgeApi...")
                bridge_api = BridgeApi(self.api_client)
                bridges = self._run_async(bridge_api.bridges(l1_address=l1_addr))
                
                # Debug: afficher la structure de la réponse
                if bridges:
                    logger.debug(f"Bridges response type: {type(bridges)}")
                    if hasattr(bridges, 'bridges'):
                        logger.debug(f"Number of bridges: {len(bridges.bridges) if bridges.bridges else 0}")
                        for i, bridge in enumerate(bridges.bridges if bridges.bridges else []):
                            logger.debug(f"Bridge {i}: {bridge}")
                            if hasattr(bridge, 'source_chain_id'):
                                logger.debug(f"  source_chain_id: {bridge.source_chain_id} (type: {type(bridge.source_chain_id)})")
                            if hasattr(bridge, 'intent_address'):
                                logger.debug(f"  intent_address: {bridge.intent_address}")
                            if hasattr(bridge, 'id'):
                                logger.debug(f"  id: {bridge.id}")
                    elif isinstance(bridges, list):
                        logger.debug(f"Bridges is a list with {len(bridges)} items")
                        for i, bridge in enumerate(bridges):
                            logger.debug(f"Bridge {i}: {bridge}")
                
                if bridges and hasattr(bridges, 'bridges'):
                    for bridge in bridges.bridges:
                        # Vérifier si c'est un bridge Arbitrum
                        source_chain_id = str(bridge.source_chain_id) if hasattr(bridge, 'source_chain_id') else None
                        # Vérifier aussi si c'est un int
                        if hasattr(bridge, 'source_chain_id'):
                            if isinstance(bridge.source_chain_id, int):
                                source_chain_id = str(bridge.source_chain_id)
                            elif isinstance(bridge.source_chain_id, str):
                                source_chain_id = bridge.source_chain_id
                        
                        logger.debug(f"Checking bridge with source_chain_id: {source_chain_id}")
                        if source_chain_id == "42161" or source_chain_id == "421614" or source_chain_id == 42161 or source_chain_id == 421614:  # Arbitrum mainnet ou testnet
                            logger.info(f"Found Arbitrum bridge: {bridge}")
                            # Pour les dépôts externes, utiliser l'intent_address
                            if hasattr(bridge, 'intent_address') and bridge.intent_address:
                                intent_address = bridge.intent_address
                                logger.info(f"✅ Found intent_address for external deposit: {intent_address}")
                            # Sinon, utiliser l'ID du bridge comme adresse de contrat
                            if hasattr(bridge, 'id') and bridge.id:
                                bridge_address = bridge.id
                                logger.info(f"Found bridge address: {bridge_address}")
                            break
                elif isinstance(bridges, list):
                    # Si bridges est directement une liste
                    for bridge in bridges:
                        source_chain_id = str(bridge.source_chain_id) if hasattr(bridge, 'source_chain_id') else None
                        if source_chain_id == "42161" or source_chain_id == "421614" or source_chain_id == 42161 or source_chain_id == 421614:
                            if hasattr(bridge, 'intent_address') and bridge.intent_address:
                                intent_address = bridge.intent_address
                                logger.info(f"✅ Found intent_address for external deposit: {intent_address}")
                            if hasattr(bridge, 'id') and bridge.id:
                                bridge_address = bridge.id
                                logger.info(f"Found bridge address: {bridge_address}")
                            break
            
            if not intent_address and not bridge_address:
                # Adresse par défaut du bridge Lighter sur Arbitrum (si l'API ne la retourne pas)
                bridge_address = "0x10417734001162Ea139e8b044DFe28DbB8B28ad0"
                logger.warning(f"Bridge address not found via API, using default: {bridge_address}")
                logger.warning("⚠️  Le dépôt via contrat bridge peut échouer")
                logger.warning("   Pour un dépôt externe, Lighter nécessite une intent_address")
            
            # Connecter à Arbitrum
            w3 = Web3(Web3.HTTPProvider("https://arb1.arbitrum.io/rpc"))
            if not w3.is_connected():
                logger.error("Failed to connect to Arbitrum RPC")
                return {'status': 'error', 'message': 'Failed to connect to Arbitrum'}
            
            # Créer le compte depuis la clé privée
            account = Account.from_key(private_key)
            from_addr_raw = from_address or account.address
            # Convertir en format checksum pour web3
            from_addr = Web3.to_checksum_address(from_addr_raw)
            
            logger.info(f"Depositing ${amount:.2f} from Arbitrum ({from_addr}) to Lighter")
            
            # ABI pour USDC
            erc20_abi = [
                {
                    "constant": False,
                    "inputs": [
                        {"name": "_spender", "type": "address"},
                        {"name": "_value", "type": "uint256"}
                    ],
                    "name": "approve",
                    "outputs": [{"name": "", "type": "bool"}],
                    "type": "function"
                },
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
                },
                {
                    "constant": True,
                    "inputs": [
                        {"name": "_owner", "type": "address"},
                        {"name": "_spender", "type": "address"}
                    ],
                    "name": "allowance",
                    "outputs": [{"name": "", "type": "uint256"}],
                    "type": "function"
                }
            ]
            
            # Créer le contrat USDC (utilisé dans les deux cas)
            usdc_contract = w3.eth.contract(
                address=Web3.to_checksum_address(ARBITRUM_USDC),
                abi=erc20_abi
            )
            
            # Si on a une intent_address, utiliser un dépôt externe (transfert direct vers l'intent_address)
            if intent_address:
                logger.info(f"Using external deposit with intent_address: {intent_address}")
                # Pour un dépôt externe, on transfère directement les USDC vers l'intent_address
                # Pas besoin de contrat bridge, juste un transfert ERC20 standard
                intent_addr_checksum = Web3.to_checksum_address(intent_address)
                
                # Vérifier le solde
                balance = usdc_contract.functions.balanceOf(from_addr).call()
                balance_usd = balance / 1e6
                
                if balance_usd < amount:
                    logger.error(f"Insufficient USDC balance: ${balance_usd:.2f} < ${amount:.2f}")
                    return {'status': 'error', 'message': f'Insufficient balance: ${balance_usd:.2f}'}
                
                # Convertir le montant
                amount_wei = int(amount * 1e6)
                
                # Vérifier et approuver si nécessaire (pas besoin d'approbation pour un transfert direct)
                # Transférer directement les USDC vers l'intent_address
                logger.info(f"Transferring ${amount:.2f} USDC to intent_address {intent_address}...")
                
                # Utiliser la fonction transfer du contrat USDC (déjà défini plus haut)
                nonce = w3.eth.get_transaction_count(from_addr)
                gas_price = w3.eth.gas_price
                
                transfer_txn = usdc_contract.functions.transfer(
                    intent_addr_checksum,
                    amount_wei
                ).build_transaction({
                    'from': from_addr,
                    'nonce': nonce,
                    'gas': 100000,
                    'chainId': 42161,
                    'maxFeePerGas': gas_price,
                    'maxPriorityFeePerGas': int(gas_price * 0.1)
                })
                
                signed_transfer = account.sign_transaction(transfer_txn)
                transfer_raw = signed_transfer.raw_transaction if hasattr(signed_transfer, 'raw_transaction') else signed_transfer.rawTransaction
                transfer_hash = w3.eth.send_raw_transaction(transfer_raw)
                
                logger.info(f"Transfer transaction sent: {transfer_hash.hex()}")
                receipt = w3.eth.wait_for_transaction_receipt(transfer_hash, timeout=120)
                
                if receipt.status == 1:
                    bridge_type = "FAST" if is_next_fast else "SECURE"
                    logger.success(f"✅ External deposit successful: {transfer_hash.hex()}")
                    logger.info(f"⏳ Le dépôt sera crédité sur votre compte Lighter via bridge {bridge_type}")
                    logger.info("   (Le type de bridge est déterminé automatiquement par Lighter)")
                    return {
                        'status': 'success',
                        'message': 'External deposit initiated',
                        'transaction_hash': transfer_hash.hex(),
                        'amount': amount,
                        'intent_address': intent_address,
                        'bridge_type': bridge_type.lower(),
                        'is_fast': is_next_fast
                    }
                else:
                    logger.error(f"Transfer transaction failed: {transfer_hash.hex()}")
                    return {'status': 'error', 'message': 'Transfer transaction failed'}
            
            # Sinon, essayer avec le contrat bridge (méthode précédente)
            # ABI pour le bridge Lighter (fonction deposit standard)
            bridge_abi = [
                {
                    "constant": False,
                    "inputs": [
                        {"name": "token", "type": "address"},
                        {"name": "amount", "type": "uint256"},
                        {"name": "to", "type": "address"}
                    ],
                    "name": "deposit",
                    "outputs": [],
                    "type": "function"
                }
            ]
            
            # Vérifier le solde (from_addr est déjà en checksum, usdc_contract déjà défini)
            balance = usdc_contract.functions.balanceOf(from_addr).call()
            balance_usd = balance / 1e6
            
            if balance_usd < amount:
                logger.error(f"Insufficient USDC balance: ${balance_usd:.2f} < ${amount:.2f}")
                return {'status': 'error', 'message': f'Insufficient balance: ${balance_usd:.2f}'}
            
            # Convertir le montant
            amount_wei = int(amount * 1e6)
            
            # Vérifier et approuver si nécessaire
            bridge_addr_checksum = Web3.to_checksum_address(bridge_address)
            allowance = usdc_contract.functions.allowance(
                from_addr,
                bridge_addr_checksum
            ).call()
            
            if allowance < amount_wei:
                logger.info(f"Approving bridge to spend ${amount:.2f} USDC...")
                nonce = w3.eth.get_transaction_count(from_addr)
                gas_price = w3.eth.gas_price
                
                approve_txn = usdc_contract.functions.approve(
                    bridge_addr_checksum,
                    amount_wei
                ).build_transaction({
                    'from': from_addr,
                    'nonce': nonce,
                    'gas': 100000,
                    'chainId': 42161,
                    'maxFeePerGas': gas_price,
                    'maxPriorityFeePerGas': int(gas_price * 0.1)
                })
                
                signed_approve = account.sign_transaction(approve_txn)
                # Gérer les deux formats possibles (rawTransaction ou raw_transaction)
                approve_raw = signed_approve.raw_transaction if hasattr(signed_approve, 'raw_transaction') else signed_approve.rawTransaction
                approve_hash = w3.eth.send_raw_transaction(approve_raw)
                logger.info(f"Approval sent: {approve_hash.hex()}")
                w3.eth.wait_for_transaction_receipt(approve_hash, timeout=120)
            
            # Créer le contrat bridge
            bridge_contract = w3.eth.contract(
                address=bridge_addr_checksum,
                abi=bridge_abi
            )
            
            # Envoyer le dépôt
            nonce = w3.eth.get_transaction_count(from_addr)
            to_address_raw = self.l1_address or from_addr_raw  # Utiliser l'adresse brute pour to_address
            to_address = Web3.to_checksum_address(to_address_raw)  # Convertir en checksum
            
            gas_price = w3.eth.gas_price
            deposit_txn = bridge_contract.functions.deposit(
                Web3.to_checksum_address(ARBITRUM_USDC),
                amount_wei,
                to_address
            ).build_transaction({
                'from': from_addr,
                'nonce': nonce,
                'gas': 200000,
                'chainId': 42161,
                'maxFeePerGas': gas_price,
                'maxPriorityFeePerGas': int(gas_price * 0.1)
            })
            
            signed_deposit = account.sign_transaction(deposit_txn)
            # Gérer les deux formats possibles (rawTransaction ou raw_transaction)
            deposit_raw = signed_deposit.raw_transaction if hasattr(signed_deposit, 'raw_transaction') else signed_deposit.rawTransaction
            deposit_hash = w3.eth.send_raw_transaction(deposit_raw)
            
            logger.info(f"Deposit transaction sent: {deposit_hash.hex()}")
            receipt = w3.eth.wait_for_transaction_receipt(deposit_hash, timeout=120)
            
            if receipt.status == 1:
                bridge_type = "FAST" if is_next_fast else "SECURE"
                logger.success(f"✅ Deposit successful: {deposit_hash.hex()}")
                logger.info(f"⏳ Le dépôt sera crédité sur votre compte Lighter via bridge {bridge_type}")
                logger.info("   (Le type de bridge est déterminé automatiquement par Lighter)")
                return {
                    'status': 'success',
                    'message': 'Deposit initiated',
                    'transaction_hash': deposit_hash.hex(),
                    'amount': amount,
                    'bridge_type': bridge_type.lower(),
                    'is_fast': is_next_fast
                }
            else:
                # Essayer de récupérer le message d'erreur depuis les logs
                error_msg = "Transaction reverted"
                if receipt.logs:
                    logger.debug(f"Transaction logs: {receipt.logs}")
                
                # Vérifier si on peut récupérer le revert reason
                try:
                    tx = w3.eth.get_transaction(deposit_hash)
                    # Essayer de simuler la transaction pour obtenir le revert reason
                    try:
                        w3.eth.call({
                            'to': tx['to'],
                            'from': tx['from'],
                            'data': tx['input'],
                            'value': tx.get('value', 0),
                            'gas': tx['gas'],
                            'gasPrice': tx.get('gasPrice', tx.get('maxFeePerGas', 0))
                        }, receipt.blockNumber - 1)
                    except Exception as call_err:
                        error_msg = str(call_err)
                except Exception:
                    pass
                
                logger.error(f"Deposit transaction failed: {deposit_hash.hex()}")
                logger.error(f"Error: {error_msg}")
                logger.error(f"Transaction receipt: status={receipt.status}, gasUsed={receipt.gasUsed}")
                logger.warning("⚠️  Le dépôt via contrat bridge a échoué")
                logger.warning("   Lighter pourrait nécessiter un dépôt via leur interface web")
                logger.warning(f"   Veuillez déposer manuellement ${amount:.2f} USDC sur lighter.xyz")
                logger.warning(f"   Transaction hash: {deposit_hash.hex()}")
                return {
                    'status': 'error', 
                    'message': f'Deposit transaction failed: {error_msg}',
                    'transaction_hash': deposit_hash.hex()
                }
                
        except Exception as e:
            logger.error(f"Error depositing to Lighter: {e}")
            import traceback
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}
    
    def withdraw(self, amount: float, destination_address: str = None, fast: bool = True) -> Optional[Dict]:
        """
        Retire des USDC depuis Lighter vers Arbitrum
        
        Args:
            amount: Montant en USDC à retirer
            destination_address: Adresse de destination Arbitrum (requis pour fast withdraw)
            fast: True pour retrait fast, False pour retrait secure (normal)
            
        Returns:
            Dict avec status et détails ou None si échec
        """
        if not self.initialized:
            logger.error("Lighter client not initialized - cannot withdraw")
            return {'status': 'error', 'message': 'Lighter client not initialized'}
        
        if not self.signer_client:
            logger.error("Signer client not available for withdrawal")
            return {'status': 'error', 'message': 'Signer client not available'}
        
        try:
            if fast:
                # Retrait Fast
                logger.info(f"Initiating Lighter FAST withdrawal: ${amount:.2f} USDC")
                
                if not destination_address:
                    logger.error("destination_address required for fast withdrawal")
                    return {'status': 'error', 'message': 'destination_address required for fast withdrawal'}
                
                # Vérifier si on a la clé privée L1 pour signer le transfer
                if not hasattr(self, 'l1_private_key') or not self.l1_private_key:
                    logger.error("L1 private key required for fast withdrawal")
                    logger.error("   Ajoutez LIGHTER_L1_PRIVATE_KEY dans le fichier .env")
                    return {'status': 'error', 'message': 'L1 private key required for fast withdrawal'}
                
                # Étape 1: Obtenir les infos du pool fast withdraw
                auth_token, err = self.signer_client.create_auth_token_with_expiry()
                if err:
                    logger.error(f"Failed to create auth token: {err}")
                    return {'status': 'error', 'message': f'Auth token failed: {err}'}
                
                from lighter import InfoApi
                import json
                
                # Get fast withdraw pool info
                params = self.api_client.param_serialize(
                    method='GET',
                    resource_path='/api/v1/fastwithdraw/info',
                    query_params=[('account_index', self.account_index)],
                    header_params={'Authorization': auth_token}
                )
                response = self._run_async(self.api_client.call_api(*params))
                response_data = self._run_async(response.read())
                data = response_data if response_data else response.data
                
                if not data:
                    logger.error("Failed to get fast withdraw pool info")
                    return {'status': 'error', 'message': 'Failed to get fast withdraw pool info'}
                
                pool_info = json.loads(data.decode('utf-8'))
                if pool_info.get('code') != 200:
                    logger.error(f"Pool info failed: {pool_info.get('message')}")
                    return {'status': 'error', 'message': f"Pool info failed: {pool_info.get('message')}"}
                
                to_account = pool_info['to_account_index']
                withdraw_limit = pool_info.get('withdraw_limit', 0)
                logger.info(f"Fast withdraw pool: account={to_account}, limit=${withdraw_limit}")
                
                # Vérifier la limite
                if amount > float(withdraw_limit):
                    logger.error(f"❌ Montant (${amount:.2f}) supérieur à la limite (${withdraw_limit})")
                    logger.error("   Le retrait fast ne peut pas être effectué")
                    return {'status': 'error', 'message': f'Amount ${amount:.2f} exceeds fast withdraw limit ${withdraw_limit}'}
                
                # Étape 2: Obtenir les frais de transfert
                info_api = InfoApi(self.api_client)
                fee_info = self._run_async(info_api.transfer_fee_info(
                    account_index=self.account_index,
                    to_account_index=to_account,
                    auth=auth_token
                ))
                fee = fee_info.transfer_fee_usdc  # Déjà en int (USDC scale)
                fee_usd = fee / 1e6
                logger.info(f"Transfer fee: ${fee_usd:.2f} USDC")
                
                # Vérifier que le montant couvre les frais
                if amount <= fee_usd:
                    logger.error(f"❌ Montant (${amount:.2f}) inférieur ou égal aux frais (${fee_usd:.2f})")
                    logger.error("   Le retrait fast ne peut pas être effectué")
                    return {'status': 'error', 'message': f'Amount ${amount:.2f} is less than or equal to fee ${fee_usd:.2f}'}
                
                # Étape 3: Obtenir nonce et API key
                api_key_index, nonce = self.signer_client.nonce_manager.next_nonce()
                
                # Étape 4: Construire le memo (20 bytes address + 12 zeros = 32 bytes total)
                from web3 import Web3
                dest_addr_checksum = Web3.to_checksum_address(destination_address)
                addr_hex = dest_addr_checksum.lower().removeprefix("0x")
                addr_bytes = bytes.fromhex(addr_hex)
                if len(addr_bytes) != 20:
                    logger.error(f"Invalid address length: {len(addr_bytes)}")
                    return {'status': 'error', 'message': 'Invalid destination address'}
                
                memo_list = list(addr_bytes + b"\x00" * 12)
                memo_hex = ''.join(format(b, '02x') for b in memo_list)
                
                # Étape 5: Créer la transaction de transfer
                amount_usdc_int = int(amount * 1e6)  # Convertir en int avec scale USDC
                tx_type, tx_info_str, tx_hash, err = self.signer_client.sign_transfer(
                    eth_private_key=self.l1_private_key,
                    to_account_index=to_account,
                    asset_id=self.signer_client.ASSET_ID_USDC,
                    route_from=self.signer_client.ROUTE_PERP,
                    route_to=self.signer_client.ROUTE_PERP,
                    usdc_amount=amount_usdc_int,
                    fee=fee,
                    memo=memo_hex,
                    api_key_index=api_key_index,
                    nonce=nonce
                )
                
                if err:
                    logger.error(f"L2 signing failed: {err}")
                    return {'status': 'error', 'message': f'L2 signing failed: {err}'}
                
                # Étape 6: Soumettre le retrait fast
                params = self.api_client.param_serialize(
                    method='POST',
                    resource_path='/api/v1/fastwithdraw',
                    post_params=[
                        ('tx_info', tx_info_str),
                        ('to_address', dest_addr_checksum)
                    ],
                    header_params={
                        'Authorization': auth_token,
                        'Content-Type': 'application/x-www-form-urlencoded'
                    }
                )
                response = self._run_async(self.api_client.call_api(*params))
                response_data = self._run_async(response.read())
                data = response_data if response_data else response.data
                
                if not data:
                    logger.error("Failed to submit fast withdraw")
                    return {'status': 'error', 'message': 'Failed to submit fast withdraw'}
                
                result = json.loads(data.decode('utf-8'))
                
                if result.get('code') == 200:
                    tx_hash = result.get('tx_hash')
                    logger.success(f"✅ Lighter FAST withdrawal initiated: {tx_hash}")
                    return {
                        'status': 'success',
                        'message': 'Fast withdrawal initiated',
                        'tx_hash': tx_hash,
                        'withdraw_type': 'fast',
                        'pool_account': to_account,
                        'fee': fee_usd
                    }
                else:
                    error_msg = result.get('message', 'Unknown error')
                    logger.error(f"Fast withdraw failed: {error_msg}")
                    return {'status': 'error', 'message': f"Fast withdraw failed: {error_msg}"}
            
            else:
                # Retrait Secure (normal)
                logger.info(f"Initiating Lighter SECURE withdrawal: ${amount:.2f} USDC")
                
                # Appeler la méthode withdraw du signer_client
                # withdraw retourne: (Withdraw, RespSendTx, error)
                withdraw_obj, api_response, error = self._run_async(
                    self.signer_client.withdraw(
                        asset_id=self.signer_client.ASSET_ID_USDC,
                        route_type=self.signer_client.ROUTE_PERP,
                        amount=amount
                    )
                )
                
                if error:
                    logger.error(f"Lighter withdrawal failed: {error}")
                    return {'status': 'error', 'message': str(error)}
                
                # Extraire le tx_hash depuis api_response
                tx_hash = None
                if hasattr(api_response, 'tx_hash'):
                    tx_hash = api_response.tx_hash
                elif hasattr(api_response, 'txHash'):
                    tx_hash = api_response.txHash
                
                logger.success(f"✅ Lighter SECURE withdrawal initiated: {tx_hash}")
                return {
                    'status': 'success',
                    'message': 'Secure withdrawal initiated',
                    'tx_hash': tx_hash,
                    'withdraw_type': 'secure',
                    'withdraw_info': str(withdraw_obj) if withdraw_obj else None,
                    'response': str(api_response)
                }
            
        except Exception as e:
            logger.error(f"Error withdrawing from Lighter: {e}")
            import traceback
            traceback.print_exc()
            return {'status': 'error', 'message': str(e)}
    
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
        Place un ordre sur Lighter
        
        Args:
            symbol: Symbole (ex: "ETH", "BTC")
            side: 'buy' ou 'sell'
            size: Taille en unités de base
            order_type: 'market' ou 'limit'
            price: Prix limite (requis pour limit orders)
            reduce_only: True pour fermeture uniquement
            
        Returns:
            Réponse de l'exchange ou None
        """
        if not self.initialized:
            logger.error("Lighter client not initialized - cannot place orders")
            return None
            
        try:
            if not self.signer_client:
                logger.error("SignerClient not available - cannot place orders")
                return None
            
            market_index = self.get_market_index(symbol)
            is_ask = side.lower() == 'sell'
            
            # Convertir la taille en base_amount (Lighter utilise des entiers)
            # Récupérer le scale depuis le cache du marché
            base_amount_scale = 10000  # Valeur par défaut
            if market_index in self.markets_cache:
                base_amount_scale = self.markets_cache[market_index].get('base_amount_scale', 10000)
            
            base_amount = int(size * base_amount_scale)
            
            # Obtenir le prix si market order
            if order_type.lower() == 'market' or not price:
                ticker = self.get_ticker(symbol)
                if ticker:
                    # Pour market order sur Lighter, utiliser le mark price ou mid price
                    # Lighter a une limite de slippage stricte, donc utiliser un prix très proche
                    mark_price = ticker.get('last', 0)
                    bid = ticker.get('bid', 0)
                    ask = ticker.get('ask', 0)
                    
                    if mark_price == 0:
                        # Si pas de last price, utiliser le mid price
                        if bid > 0 and ask > 0:
                            mark_price = (bid + ask) / 2
                        elif ask > 0:
                            mark_price = ask
                        elif bid > 0:
                            mark_price = bid
                    
                    if mark_price == 0:
                        logger.error(f"Cannot get valid price for {symbol}")
                        return None
                    
                    # Pour market order, utiliser le prix bid/ask actuel avec une marge large (2-3%)
                    # pour garantir l'exécution immédiate. avg_execution_price est le prix maximum acceptable.
                    if is_ask:
                        # Vendre: utiliser bid avec une marge de sécurité de 2% en dessous
                        # pour garantir l'exécution même si le marché bouge
                        if bid > 0:
                            price = bid * 0.98  # 2% en dessous du bid pour garantir l'exécution
                        else:
                            price = mark_price * 0.98
                    else:
                        # Acheter: utiliser ask avec une marge de sécurité de 2% au-dessus
                        # pour garantir l'exécution même si le marché bouge
                        if ask > 0:
                            price = ask * 1.02  # 2% au-dessus de l'ask pour garantir l'exécution
                        else:
                            price = mark_price * 1.02
                    
                    logger.debug(f"Market order price for {symbol}: {price:.2f} (bid: ${bid:.2f}, ask: ${ask:.2f}, mark: ${mark_price:.2f})")
                else:
                    logger.error(f"Cannot get ticker for {symbol}")
                    return None
            
            logger.info(f"Placing Lighter order: {symbol} {'SELL' if is_ask else 'BUY'} {size} @ ${price:.2f}")
            
            # Pour les market orders, utiliser create_market_order avec avg_execution_price très large
            # obtenu directement depuis l'orderbook Lighter pour garantir l'exécution
            if order_type.lower() == 'market':
                # Obtenir le prix idéal directement depuis l'orderbook Lighter (plus fiable que notre cache)
                try:
                    order_book_orders = self._run_async(
                        self.order_api.order_book_orders(market_index, 1)
                    )
                    
                    if order_book_orders and hasattr(order_book_orders, 'bids') and hasattr(order_book_orders, 'asks'):
                        # Récupérer le meilleur bid/ask depuis l'orderbook
                        if is_ask and order_book_orders.bids:
                            # Pour SELL: utiliser le meilleur bid
                            ideal_price_str = order_book_orders.bids[0].price.replace(".", "")
                            ideal_price_cents = int(ideal_price_str)
                            ideal_price = ideal_price_cents / 100.0
                            # Utiliser un prix très bas (50% en dessous) pour garantir l'exécution
                            avg_execution_price_cents = int(ideal_price * 0.50 * 100)
                        elif not is_ask and order_book_orders.asks:
                            # Pour BUY: utiliser le meilleur ask
                            ideal_price_str = order_book_orders.asks[0].price.replace(".", "")
                            ideal_price_cents = int(ideal_price_str)
                            ideal_price = ideal_price_cents / 100.0
                            # Utiliser un prix très haut (50% au-dessus) pour garantir l'exécution
                            avg_execution_price_cents = int(ideal_price * 1.50 * 100)
                        else:
                            raise ValueError("Orderbook vide")
                        
                        logger.info(f"Utilisation de create_market_order avec avg_execution_price=${avg_execution_price_cents/100:.2f} (ideal=${ideal_price:.2f}, marge 50%)")
                        
                        # Vérifier et initialiser le nonce_manager si nécessaire
                        try:
                            if not hasattr(self.signer_client, 'nonce_manager') or self.signer_client.nonce_manager is None:
                                logger.error("nonce_manager non disponible, réinitialisation du SignerClient...")
                                self.signer_client = SignerClient(
                                    url=self.base_url,
                                    account_index=self.account_index,
                                    api_private_keys=self.api_private_keys
                                )
                                check_err = self.signer_client.check_client()
                                if check_err:
                                    raise Exception(f"SignerClient check failed: {check_err}")
                                logger.success("✅ SignerClient réinitialisé")
                            
                            # Obtenir explicitement le nonce depuis le nonce_manager
                            # Cela garantit que le nonce est correctement synchronisé
                            api_key_index, nonce = self.signer_client.nonce_manager.next_nonce()
                            logger.debug(f"Nonce obtenu: api_key_index={api_key_index}, nonce={nonce}")
                        except Exception as init_err:
                            logger.error(f"Erreur obtention nonce: {init_err}")
                            import traceback
                            logger.error(traceback.format_exc())
                            # Fallback: utiliser les valeurs par défaut et laisser le décorateur gérer
                            api_key_index = self.signer_client.DEFAULT_API_KEY_INDEX
                            nonce = self.signer_client.DEFAULT_NONCE
                            logger.warning("Utilisation des valeurs par défaut, le décorateur gérera le nonce")
                        
                        # Utiliser un client_order_index unique pour éviter les collisions
                        self._order_index_counter = (self._order_index_counter + 1) % 1000000
                        client_order_index = int(time.time() * 1000) % 1000000 + self._order_index_counter
                        client_order_index = client_order_index % 1000000
                        
                        # Passer explicitement le nonce et api_key_index obtenus
                        result = self._run_async(
                            self.signer_client.create_market_order(
                                market_index=market_index,
                                client_order_index=client_order_index,
                                base_amount=base_amount,
                                avg_execution_price=avg_execution_price_cents,
                                is_ask=is_ask,
                                reduce_only=reduce_only,
                                nonce=nonce,
                                api_key_index=api_key_index
                            )
                        )
                    else:
                        raise ValueError("Orderbook invalide")
                        
                except Exception as e:
                    logger.warning(f"Erreur lors de la récupération de l'orderbook: {e}, utilisation du fallback...")
                    # Fallback: utiliser create_market_order_limited_slippage avec un slippage très élevé
                    ticker = self.get_ticker(symbol)
                    if ticker:
                        bid = ticker.get('bid', 0)
                        ask = ticker.get('ask', 0)
                        if is_ask and bid > 0:
                            ideal_price_cents = int(bid * 100)
                        elif not is_ask and ask > 0:
                            ideal_price_cents = int(ask * 100)
                        else:
                            ideal_price_cents = int(price * 100)
                    else:
                        ideal_price_cents = int(price * 100)
                    
                    # Utiliser un slippage très élevé (50%) pour garantir l'exécution
                    logger.info(f"Fallback: utilisation de create_market_order_limited_slippage avec 50% slippage")
                    
                    # Obtenir explicitement le nonce depuis le nonce_manager
                    try:
                        api_key_index, nonce = self.signer_client.nonce_manager.next_nonce()
                    except Exception as nonce_err:
                        logger.error(f"Erreur obtention nonce: {nonce_err}")
                        api_key_index = self.signer_client.DEFAULT_API_KEY_INDEX
                        nonce = self.signer_client.DEFAULT_NONCE
                    
                    # Utiliser un client_order_index unique pour éviter les collisions
                    self._order_index_counter = (self._order_index_counter + 1) % 1000000
                    client_order_index = int(time.time() * 1000) % 1000000 + self._order_index_counter
                    client_order_index = client_order_index % 1000000
                    
                    result = self._run_async(
                        self.signer_client.create_market_order_limited_slippage(
                            market_index=market_index,
                            client_order_index=client_order_index,
                            base_amount=base_amount,
                            max_slippage=0.50,  # 50% de slippage pour garantir l'exécution
                            is_ask=is_ask,
                            reduce_only=reduce_only,
                            ideal_price=ideal_price_cents,
                            nonce=nonce,
                            api_key_index=api_key_index
                        )
                    )
            else:
                # Obtenir explicitement le nonce depuis le nonce_manager
                try:
                    api_key_index, nonce = self.signer_client.nonce_manager.next_nonce()
                except Exception as nonce_err:
                    logger.error(f"Erreur obtention nonce: {nonce_err}")
                    api_key_index = self.signer_client.DEFAULT_API_KEY_INDEX
                    nonce = self.signer_client.DEFAULT_NONCE
                
                # Utiliser un client_order_index unique pour éviter les collisions
                self._order_index_counter = (self._order_index_counter + 1) % 1000000
                client_order_index = int(time.time() * 1000) % 1000000 + self._order_index_counter
                client_order_index = client_order_index % 1000000
                
                # Convertir le prix en centimes
                price_cents = int(price * 100)
                
                result = self._run_async(
                    self.signer_client.create_order(
                        market_index=market_index,
                        client_order_index=client_order_index,
                        base_amount=base_amount,
                        price=price_cents,
                        is_ask=is_ask,
                        order_type=self.signer_client.ORDER_TYPE_LIMIT,
                        time_in_force=self.signer_client.ORDER_TIME_IN_FORCE_GOOD_TILL_TIME,
                        reduce_only=reduce_only,
                        nonce=nonce,
                        api_key_index=api_key_index
                    )
                )
            
            if result and len(result) >= 3:
                order_obj, api_response, error = result
                if error is None and api_response:
                    # Extraire le tx_hash depuis RespSendTx
                    tx_hash = None
                    if hasattr(api_response, 'tx_hash'):
                        tx_hash = api_response.tx_hash
                    elif hasattr(api_response, 'txHash'):
                        tx_hash = api_response.txHash
                    elif hasattr(api_response, 'tx_hashes') and api_response.tx_hashes:
                        tx_hash = api_response.tx_hashes[0] if isinstance(api_response.tx_hashes, list) else str(api_response.tx_hashes)
                    
                    logger.success(f"✅ Lighter order placed: {tx_hash}")
                    return {
                        'status': 'ok',
                        'order_id': tx_hash,
                        'tx_hash': tx_hash,
                        'response': api_response
                    }
                else:
                    error_str = str(error) if error else "Unknown error"
                    logger.error(f"Lighter order failed: {error_str}")
                    
                    # Vérifier si c'est l'erreur "invalid PublicKey" (code 21136)
                    if '21136' in error_str or 'invalid PublicKey' in error_str or 'update the sdk' in error_str:
                        logger.warning("⚠️  Erreur PublicKey invalide (code 21136) - problème de signature ou SDK obsolète")
                        logger.warning("   Vérifiez que le SDK Lighter est à jour et que les clés API sont correctes")
                        # Essayer de réinitialiser le SignerClient
                        try:
                            logger.info("Tentative de réinitialisation du SignerClient...")
                            self.signer_client = SignerClient(
                                url=self.base_url,
                                account_index=self.account_index,
                                api_private_keys=self.api_private_keys
                            )
                            self.signer_client.check_client()
                            logger.success("✅ SignerClient réinitialisé")
                        except Exception as reinit_err:
                            logger.error(f"Échec réinitialisation SignerClient: {reinit_err}")
                    
                    return {
                        'status': 'error',
                        'error': error_str
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Error placing Lighter order: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def cancel_order(self, symbol: str, order_index: int) -> bool:
        """
        Annule un ordre
        
        Args:
            symbol: Symbole
            order_index: Index de l'ordre à annuler
            
        Returns:
            True si succès
        """
        if not self.initialized:
            return False
            
        try:
            if not self.signer_client:
                return False
            
            market_index = self.get_market_index(symbol)
            
            # cancel_order retourne: (tx_info, api_response, error)
            result = self._run_async(
                self.signer_client.cancel_order(
                    market_index=market_index,
                    order_index=order_index
                )
            )
            
            if result and len(result) >= 3:
                _, _, error = result
                return error is None
            
            return False
            
        except Exception as e:
            logger.error(f"Error canceling Lighter order: {e}")
            return False
    
    def get_funding_rate(self, symbol: str) -> Optional[Dict]:
        """
        Récupère le funding rate actuel pour un symbole
        
        Args:
            symbol: Symbole (ex: "ETH", "BTC")
            
        Returns:
            Dict avec funding rate info
        """
        try:
            funding_rates = self._run_async(self.funding_api.funding_rates())
            
            market_id = self.get_market_index(symbol)
            
            if funding_rates and hasattr(funding_rates, 'funding_rates'):
                for fr in funding_rates.funding_rates:
                    if hasattr(fr, 'market_id') and int(fr.market_id) == market_id:
                        rate = float(fr.funding_rate) if hasattr(fr, 'funding_rate') else 0.0
                        return {
                            'symbol': symbol,
                            'rate': rate,
                            'next_funding': fr.next_funding_time if hasattr(fr, 'next_funding_time') else None,
                            'interval_hours': 1  # Lighter utilise 1h
                        }
            
            return None
            
        except Exception as e:
            logger.error(f"Error fetching Lighter funding rate for {symbol}: {e}")
            return None
    
    def get_all_funding_rates(self) -> Dict[str, Dict]:
        """
        Récupère tous les funding rates
        
        Returns:
            Dict {symbol: funding_info}
        """
        try:
            funding_rates = self._run_async(self.funding_api.funding_rates())
            
            result = {}
            
            if funding_rates and hasattr(funding_rates, 'funding_rates'):
                for fr in funding_rates.funding_rates:
                    market_id = int(fr.market_id) if hasattr(fr, 'market_id') else 0
                    
                    # Trouver le symbole
                    symbol = "UNKNOWN"
                    for sym, mid in self.market_index_by_symbol.items():
                        if mid == market_id:
                            symbol = sym
                            break
                    
                    rate = float(fr.funding_rate) if hasattr(fr, 'funding_rate') else 0.0
                    result[symbol] = {
                        'symbol': symbol,
                        'rate': rate,
                        'next_funding': fr.next_funding_time if hasattr(fr, 'next_funding_time') else None,
                        'interval_hours': 1
                    }
            
            logger.info(f"Fetched {len(result)} funding rates from Lighter")
            return result
            
        except Exception as e:
            logger.error(f"Error fetching all Lighter funding rates: {e}")
            return {}
    
    def ws_orderbook(self, ticker: str) -> bool:
        """
        Se connecte au WebSocket orderbook pour un ticker donné
        
        Args:
            ticker: Symbole du ticker (ex: "ETH", "BTC")
            
        Returns:
            True si la connexion est établie
        """
        if not self.initialized:
            return False
            
        try:
            market_id = self.get_market_index(ticker)
            
            # Si déjà connecté au même marché, ne rien faire
            if self.ws_connected and self.ws_market_id == market_id:
                logger.info(f"WebSocket déjà connecté au marché {ticker}")
                return True
            
            # Fermer la connexion précédente
            if self.ws_client:
                try:
                    self.ws_client.close()
                except:
                    pass
                self.ws_connected = False
            
            logger.info(f"🔌 Connexion WebSocket orderbook Lighter pour {ticker}...")
            
            def on_order_book_update(mid, order_book):
                try:
                    # order_book peut être un dict ou un objet avec attributs
                    if isinstance(order_book, dict):
                        bids = order_book.get('bids', [])
                        asks = order_book.get('asks', [])
                    else:
                        # Si c'est un objet, essayer d'accéder aux attributs
                        bids = getattr(order_book, 'bids', []) if hasattr(order_book, 'bids') else []
                        asks = getattr(order_book, 'asks', []) if hasattr(order_book, 'asks') else []
                    
                    if bids and asks:
                        # Les prix peuvent être des strings ou des floats
                        best_bid = float(bids[0].get('price', bids[0]) if isinstance(bids[0], dict) else bids[0])
                        best_ask = float(asks[0].get('price', asks[0]) if isinstance(asks[0], dict) else asks[0])
                        
                        # Convertir market_id en string pour le cache
                        market_id_str = str(mid)
                        self.orderbook_cache[market_id_str] = {
                            "bid": best_bid,
                            "ask": best_ask,
                            "last_update": time.time()
                        }
                        # Aussi stocker avec l'int pour compatibilité
                        self.orderbook_cache[int(mid)] = {
                            "bid": best_bid,
                            "ask": best_ask,
                            "last_update": time.time()
                        }
                        # Log retiré pour réduire la verbosité
                        # logger.debug(f"✅ Orderbook mis à jour pour market_id={mid}: bid={best_bid}, ask={best_ask}")
                except Exception as e:
                    logger.error(f"Error processing Lighter orderbook: {e}")
                    import traceback
                    logger.debug(traceback.format_exc())
            
            def on_account_update(account_id, account):
                # Optionnel: traiter les mises à jour de compte
                pass
            
            # Créer le client WebSocket
            # Extraire le host depuis base_url (ex: "https://mainnet.zklighter.elliot.ai" -> "mainnet.zklighter.elliot.ai")
            host = self.base_url.replace("https://", "").replace("http://", "")
            self.ws_client = WsClient(
                host=host,
                path="/stream",
                order_book_ids=[market_id],
                account_ids=[self.account_index],
                on_order_book_update=on_order_book_update,
                on_account_update=on_account_update
            )
            
            # Démarrer dans un thread
            def run_ws():
                self.ws_client.run()
            
            ws_thread = threading.Thread(target=run_ws, daemon=True)
            ws_thread.start()
            
            # Attendre la connexion
            time.sleep(2)
            self.ws_connected = True
            self.ws_market_id = market_id
            
            logger.success(f"✅ WebSocket orderbook Lighter démarré pour {ticker}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur connexion WebSocket Lighter: {e}")
            return False
    
    def ws_market_stats(self, ticker: str) -> bool:
        """
        Se connecte au WebSocket market_stats pour un ticker donné
        Récupère le mark_price et index_price en temps réel
        
        Args:
            ticker: Symbole du ticker (ex: "ETH", "BTC")
            
        Returns:
            True si la connexion est établie
        """
        if not self.initialized:
            return False
        
        try:
            import websocket
            
            market_id = self.get_market_index(ticker)
            
            # Si déjà abonné à ce symbole, ne rien faire
            if ticker in self.ws_market_stats_symbols:
                logger.debug(f"WebSocket market_stats déjà abonné à {ticker}")
                return True
            
            # Initialiser le WebSocket si pas encore fait
            if not self.ws_market_stats_connected:
                host = self.base_url.replace("https://", "").replace("http://", "")
                ws_url = f"wss://{host}/stream"
                
                logger.info(f"🔌 Initialisation WebSocket market_stats Lighter...")
                
                def on_message(ws, message):
                    try:
                        data = json.loads(message)
                        msg_type = data.get('type')
                        
                        if msg_type == 'connected':
                            logger.debug("WebSocket market_stats connecté, prêt pour abonnements")
                            self.ws_market_stats_connected = True
                        
                        elif msg_type == 'ping':
                            # Répondre au ping avec pong
                            ws.send(json.dumps({"type": "pong"}))
                        
                        elif msg_type in ['subscribed/market_stats', 'update/market_stats']:
                            # Extraire le market_id depuis le channel (ex: "market_stats:0" -> "0")
                            channel = data.get('channel', '')
                            if ':' in channel:
                                channel_market_id = int(channel.split(':')[1])
                            else:
                                channel_market_id = None
                            
                            # Récupérer les données market_stats
                            market_stats = data.get('market_stats', {})
                            
                            if market_stats and channel_market_id is not None:
                                mark_price_str = market_stats.get('mark_price', '0')
                                index_price_str = market_stats.get('index_price', '0')
                                last_trade_price_str = market_stats.get('last_trade_price', '0')
                                
                                mark_price = float(mark_price_str) if mark_price_str else 0
                                index_price = float(index_price_str) if index_price_str else 0
                                last_trade_price = float(last_trade_price_str) if last_trade_price_str else 0
                                
                                # Stocker dans le cache (avec market_id en int et en str pour compatibilité)
                                cache_data = {
                                    "mark_price": mark_price,
                                    "index_price": index_price,
                                    "last_trade_price": last_trade_price,
                                    "last_update": time.time()
                                }
                                self.market_stats_cache[channel_market_id] = cache_data
                                self.market_stats_cache[str(channel_market_id)] = cache_data
                                
                                # Log retiré pour réduire la verbosité
                                # logger.debug(f"✅ Market stats mis à jour pour market_id={channel_market_id}: mark_price={mark_price}")
                        
                    except Exception as e:
                        logger.debug(f"Erreur traitement message WebSocket market_stats: {e}")
                
                def on_error(ws, error):
                    logger.debug(f"WebSocket market_stats error: {error}")
                
                def on_close(ws, close_status_code, close_msg):
                    logger.info("WebSocket market_stats fermé")
                    self.ws_market_stats_connected = False
                
                def on_open(ws):
                    logger.debug("WebSocket market_stats ouvert")
                
                # Créer le client WebSocket
                self.ws_market_stats_client = websocket.WebSocketApp(
                    ws_url,
                    on_message=on_message,
                    on_error=on_error,
                    on_close=on_close,
                    on_open=on_open
                )
                
                # Démarrer dans un thread
                def run_ws():
                    self.ws_market_stats_client.run_forever()
                
                ws_thread = threading.Thread(target=run_ws, daemon=True)
                ws_thread.start()
                
                # Attendre la connexion
                time.sleep(1)
            
            # S'abonner au channel market_stats pour ce market_id
            if self.ws_market_stats_client and self.ws_market_stats_connected:
                subscribe_msg = {
                    "type": "subscribe",
                    "channel": f"market_stats/{market_id}"
                }
                self.ws_market_stats_client.send(json.dumps(subscribe_msg))
                self.ws_market_stats_symbols.add(ticker)
                logger.info(f"✅ WebSocket market_stats abonné à {ticker} (market_id={market_id})")
                
                # Attendre un peu pour recevoir les premières données
                time.sleep(1)
                return True
            else:
                logger.warning(f"⚠️  WebSocket market_stats pas prêt pour abonnement à {ticker}")
                return False
            
        except Exception as e:
            logger.error(f"Erreur connexion WebSocket market_stats Lighter: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    def get_market_stats_data(self, ticker: str) -> Optional[Dict[str, float]]:
        """
        Récupère les données market_stats depuis le cache WebSocket
        
        Args:
            ticker: Symbole du ticker (ex: "ETH", "BTC")
            
        Returns:
            Dict avec {"mark_price": float, "index_price": float} ou None si indisponible
        """
        try:
            market_id = self.get_market_index(ticker)
            
            # Vérifier le cache (essayer int et str)
            cache_data = self.market_stats_cache.get(market_id) or self.market_stats_cache.get(str(market_id))
            
            if cache_data:
                # Vérifier que les données ne sont pas trop anciennes (< 60 secondes)
                # Augmenté de 5s à 60s pour plus de robustesse en mode LIMIT
                age = time.time() - cache_data.get('last_update', 0)
                if age < 60:
                    return {
                        'mark_price': cache_data.get('mark_price', 0),
                        'index_price': cache_data.get('index_price', 0),
                        'last_trade_price': cache_data.get('last_trade_price', 0)
                    }
                else:
                    logger.debug(f"Market stats pour {ticker} trop anciens ({age:.1f}s > 60s)")
            else:
                logger.debug(f"Pas de market stats dans le cache pour {ticker} (market_id={market_id})")
                logger.debug(f"   Cache disponible: {list(self.market_stats_cache.keys())}")
            
            return None
            
        except Exception as e:
            logger.debug(f"Erreur récupération market stats depuis cache: {e}")
            return None
    
    def get_orderbook_data(self, ticker: str) -> Optional[Dict]:
        """
        Récupère les données de l'orderbook depuis le cache WebSocket
        
        Args:
            ticker: Symbole du ticker
            
        Returns:
            Dict avec {"bid": float, "ask": float} ou None
        """
        market_id = self.get_market_index(ticker)
        
        # Vérifier si le cache existe et est récent
        cache_data = self.orderbook_cache.get(market_id)
        if cache_data:
            # Vérifier que les données sont récentes (< 10 secondes)
            if time.time() - cache_data.get('last_update', 0) < 10:
                return {
                    "bid": cache_data['bid'],
                    "ask": cache_data['ask']
                }
            else:
                # Données trop anciennes, forcer une reconnexion
                logger.warning(f"Données orderbook Lighter trop anciennes pour {ticker}, reconnexion...")
                self.ws_connected = False
                self.ws_orderbook(ticker)
                time.sleep(1)
                # Réessayer après reconnexion
                cache_data = self.orderbook_cache.get(market_id)
                if cache_data and time.time() - cache_data.get('last_update', 0) < 10:
                    return {
                        "bid": cache_data['bid'],
                        "ask": cache_data['ask']
                    }
        
        # Si pas de cache ou données trop anciennes, essayer de reconnecter
        if not self.ws_connected:
            logger.info(f"Reconnexion WebSocket orderbook Lighter pour {ticker}...")
            self.ws_orderbook(ticker)
            time.sleep(2)
            cache_data = self.orderbook_cache.get(market_id)
            if cache_data:
                return {
                    "bid": cache_data['bid'],
                    "ask": cache_data['ask']
                }
        
        return None
    
    def close(self):
        """Ferme les connexions"""
        try:
            if self.ws_client:
                self.ws_client.close()
            if self.ws_positions_client:
                self.ws_positions_client.close()
            if self.api_client:
                self._run_async(self.api_client.close())
            if self.signer_client:
                self._run_async(self.signer_client.close())
        except:
            pass

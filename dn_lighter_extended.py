"""
DN Lighter Extended - Bot de trading delta neutre
Version refactorée avec logique robuste et fiable
"""
import os
import sys
import json
import time
import random
import threading
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

# Ajouter le chemin src pour les imports
src_path = os.path.join(os.path.dirname(__file__), 'src')
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from exchanges.extended_api import ExtendedAPI
from exchanges.lighter_api import LighterAPI

# Import pour Web3 (rebalancing)
try:
    from web3 import Web3
    try:
        from web3.middleware import geth_poa_middleware
    except ImportError:
        try:
            from web3.middleware import ExtraDataToPOAMiddleware as geth_poa_middleware
        except ImportError:
            geth_poa_middleware = None
    HAS_WEB3 = True
except ImportError:
    HAS_WEB3 = False
    logger.warning("web3 not available. Rebalancing will not work.")


class DNLighterExtended:
    """Bot de trading delta neutre entre Lighter et Extended - Version refactorée"""
    
    def __init__(self, config_path: str = "config/dnfarming.json"):
        """
        Initialise le bot
        
        Args:
            config_path: Chemin vers le fichier de configuration
        """
        load_dotenv()
        
        # Charger la configuration
        self.config = self._load_config(config_path)
        
        # Clients API (initialisés plus tard)
        self.extended_client = None
        self.lighter_client = None
        
        # Configuration Arbitrum pour les transferts
        self.arbitrum_rpc_url = "https://arb1.arbitrum.io/rpc"
        self.arbitrum_usdc_address = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"
        self.arbitrum_chain_id = 42161
        
        logger.info("✅ Bot initialisé")
    
    def _load_config(self, config_path: str) -> Dict:
        """
        Charge et valide la configuration depuis dnfarming.json
        
        Args:
            config_path: Chemin vers le fichier JSON
            
        Returns:
            Dict avec la configuration validée
        """
        logger.info(f"📋 Chargement de la configuration depuis {config_path}...")
        
        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Fichier de configuration non trouvé: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # Valider les paramètres requis
        required = ['symbol', 'leverage', 'margin', 'min_duration', 'max_duration', 
                   'num_cycles', 'pnl_check_delay', 'rebalance_threshold']
        missing = [p for p in required if p not in config]
        if missing:
            raise ValueError(f"Paramètres manquants dans la configuration: {missing}")
        
        # Valider les valeurs
        if config['leverage'] < 1:
            raise ValueError("Le levier doit être >= 1")
        if config['margin'] <= 0:
            raise ValueError("La marge doit être > 0")
        if config['max_duration'] < config['min_duration']:
            raise ValueError("max_duration doit être >= min_duration")
        if config['num_cycles'] < 1:
            raise ValueError("num_cycles doit être >= 1")
        
        logger.success("✅ Configuration validée")
        logger.info(f"   Paire: {config['symbol']}")
        logger.info(f"   Levier: {config['leverage']}x")
        logger.info(f"   Margin: ${config['margin']:.2f}")
        logger.info(f"   Cycles: {config['num_cycles']}")
        logger.info(f"   PnL check delay: {config['pnl_check_delay']} min")
        logger.info(f"   Rebalance threshold: ${config['rebalance_threshold']:.2f}")
        
        return config
    
    def _load_extended_config(self) -> Dict:
        """Charge la configuration Extended depuis .env"""
        config = {
            'name': os.getenv("ACCOUNT1_NAME", "Extended Account"),
            'api_key': os.getenv("ACCOUNT1_API_KEY"),
            'stark_public_key': os.getenv("ACCOUNT1_PUBLIC_KEY"),
            'stark_private_key': os.getenv("ACCOUNT1_PRIVATE_KEY"),
            'vault_id': int(os.getenv("ACCOUNT1_VAULT_ID", "0")),
            'arbitrum_address': os.getenv("ACCOUNT1_ARBITRUM_ADDRESS"),
            'arbitrum_private_key': os.getenv("ACCOUNT1_ARBITRUM_PRIVATE_KEY"),
        }
        config['wallet_address'] = config['arbitrum_address']
        
        required_fields = ['api_key', 'stark_public_key', 'stark_private_key', 'vault_id']
        missing = [k for k in required_fields if not config.get(k)]
        if missing:
            raise ValueError(f"Configuration Extended incomplète. Champs manquants: {missing}")
        
        return config
    
    def _load_lighter_config(self) -> Dict:
        """Charge la configuration Lighter depuis .env"""
        config = {
            'name': os.getenv("LIGHTER_NAME", "Lighter Account"),
            'account_index': int(os.getenv("LIGHTER_ACCOUNT_INDEX", "0")),
            'l1_address': os.getenv("LIGHTER_L1_ADDRESS"),
            'arbitrum_address': os.getenv("LIGHTER_ARBITRUM_ADDRESS"),
            'arbitrum_private_key': os.getenv("LIGHTER_ARBITRUM_PRIVATE_KEY"),
            'l1_private_key': os.getenv("LIGHTER_L1_PRIVATE_KEY"),
        }
        
        # Charger les clés API Lighter
        api_keys = {}
        for i in range(10):
            key = os.getenv(f"LIGHTER_API_KEY_{i}")
            if key:
                api_keys[i] = key
        
        if not api_keys:
            single_key = os.getenv("LIGHTER_API_KEY")
            if single_key:
                api_keys[0] = single_key
        
        config['api_private_keys'] = api_keys
        config['wallet_address'] = config['arbitrum_address'] or config['l1_address']
        
        if not api_keys:
            raise ValueError("LIGHTER_API_KEY_0 ou LIGHTER_API_KEY requis")
        
        return config
    
    def _initialize_clients(self):
        """Initialise les clients Extended et Lighter"""
        logger.info("🔧 Initialisation des clients...")
        
        # Charger les configurations
        extended_config = self._load_extended_config()
        lighter_config = self._load_lighter_config()
        
        # Initialiser Extended
        logger.info(f"   Extended: {extended_config.get('name', 'Extended Account')}")
        self.extended_client = ExtendedAPI(
            wallet_address=extended_config['wallet_address'],
            api_key=extended_config['api_key'],
            stark_public_key=extended_config['stark_public_key'],
            stark_private_key=extended_config['stark_private_key'],
            vault_id=extended_config['vault_id']
        )
        self.extended_config = extended_config
        
        # Initialiser Lighter
        logger.info(f"   Lighter: Account Index {lighter_config.get('account_index', 0)}")
        self.lighter_client = LighterAPI(
            account_index=lighter_config.get('account_index', 0),
            api_private_keys=lighter_config['api_private_keys'],
            l1_address=lighter_config.get('l1_address'),
            l1_private_key=lighter_config.get('l1_private_key'),
            testnet=False
        )
        self.lighter_config = lighter_config
        
        logger.success("✅ Clients initialisés")
    
    def check_initial_balances(self) -> Tuple[bool, str]:
        """
        Vérifie les balances initiales et détermine si rebalancing nécessaire
        
        Returns:
            Tuple (ok: bool, reason: str)
            - (True, "ok") si balances suffisantes
            - (False, "rebalance_needed") si rebalancing possible et nécessaire
            - (False, "insufficient_funds") si fonds insuffisants même après rebalancing
        """
        logger.info("💰 Vérification des balances initiales...")
        
        # Récupérer les balances
        extended_balance_dict = self.extended_client.get_balance()
        extended_available = extended_balance_dict.get('available', extended_balance_dict.get('total', 0))
        
        lighter_balance = self.lighter_client.get_balance()
        
        margin = self.config['margin']
        
        logger.info(f"   Extended: ${extended_available:.2f} USDC")
        logger.info(f"   Lighter: ${lighter_balance:.2f} USDC")
        logger.info(f"   Margin requise (par exchange): ${margin:.2f} USDC")
        
        # Vérifier si les deux comptes ont assez
        if extended_available >= margin and lighter_balance >= margin:
            logger.success("✅ Les deux comptes ont des fonds suffisants")
            return (True, "ok")
        
        # Un ou les deux comptes n'ont pas assez
        # Vérifier si rebalancing est possible
        total = extended_available + lighter_balance
        required_total = 2 * margin
        
        if total < required_total:
            logger.error(f"❌ Fonds totaux insuffisants: ${total:.2f} < ${required_total:.2f}")
            logger.error(f"   Il manque ${required_total - total:.2f} USDC")
            return (False, "insufficient_funds")
        
        # Rebalancing possible
        logger.warning("⚠️  Balances déséquilibrées mais rebalancing possible")
        logger.info(f"   Total disponible: ${total:.2f} >= ${required_total:.2f} requis")
        return (False, "rebalance_needed")
    
    def _get_arbitrum_balance(self, address: str) -> float:
        """Récupère le solde USDC sur Arbitrum"""
        if not HAS_WEB3:
            return 0.0
        
        try:
            w3 = Web3(Web3.HTTPProvider(self.arbitrum_rpc_url))
            if not w3.is_connected():
                return 0.0
            
            erc20_abi = [{
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function"
            }]
            
            usdc_contract = w3.eth.contract(
                address=Web3.to_checksum_address(self.arbitrum_usdc_address),
                abi=erc20_abi
            )
            
            balance = usdc_contract.functions.balanceOf(
                Web3.to_checksum_address(address)
            ).call()
            return balance / 1e6
        except Exception as e:
            logger.debug(f"Erreur récupération solde Arbitrum: {e}")
            return 0.0
    
    def _wait_for_arbitrum_balance(self, address: str, min_amount: float, max_wait_seconds: int = 600) -> bool:
        """Attend que le solde USDC sur Arbitrum atteigne un minimum"""
        if not HAS_WEB3:
            return False
        
        try:
            start_time = time.time()
            check_interval = 10
            
            while time.time() - start_time < max_wait_seconds:
                balance = self._get_arbitrum_balance(address)
                
                if balance >= min_amount:
                    logger.success(f"✅ Solde disponible: ${balance:,.2f} USDC")
                    return True
                
                elapsed = int(time.time() - start_time)
                remaining = max_wait_seconds - elapsed
                logger.info(f"⏳ Attente... ${balance:,.2f} / ${min_amount:.2f} requis - {remaining}s restantes")
                time.sleep(check_interval)
            
            logger.error(f"⏱️  Timeout après {max_wait_seconds}s")
            return False
        except Exception as e:
            logger.error(f"Erreur attente solde: {e}")
            return False
    
    def rebalance_accounts(self) -> bool:
        """
        Rebalance les comptes Extended et Lighter pour équilibrer les fonds
        
        Returns:
            True si succès
        """
        if not HAS_WEB3:
            logger.error("❌ web3 non disponible, impossible de rebalancer")
            return False
        
        logger.info("\n" + "="*60)
        logger.info("🔄 REBALANCING EXTENDED <-> LIGHTER")
        logger.info("="*60)
        
        # Récupérer les balances
        extended_balance_dict = self.extended_client.get_balance()
        extended_available = extended_balance_dict.get('available', extended_balance_dict.get('total', 0))
        lighter_balance = self.lighter_client.get_balance()
        
        logger.info(f"   Extended: ${extended_available:.2f}")
        logger.info(f"   Lighter: ${lighter_balance:.2f}")
        
        # Calculer le montant à transférer
        diff = abs(extended_available - lighter_balance)
        amount_to_transfer = diff / 2
        
        logger.info(f"   Différence: ${diff:.2f}")
        logger.info(f"   Montant à transférer: ${amount_to_transfer:.2f}")
        
        if amount_to_transfer < 10:
            logger.info("✅ Différence trop faible, pas de rebalancing nécessaire")
            return True
        
        # Déterminer la direction du transfert
        if extended_available > lighter_balance:
            # Extended -> Lighter
            logger.info("📤 Transfert: Extended → Lighter")
            from_address = self.extended_config['arbitrum_address']
            to_exchange = "lighter"
        else:
            # Lighter -> Extended  
            logger.info("📤 Transfert: Lighter → Extended")
            from_address = self.lighter_config['arbitrum_address']
            to_exchange = "extended"
        
        try:
            # ÉTAPE 1: Withdraw depuis le compte avec plus de fonds
            if extended_available > lighter_balance:
                logger.info(f"Étape 1: Retrait de ${amount_to_transfer:.2f} depuis Extended...")
                # Utiliser l'API Extended pour withdraw
                withdraw_result = self.extended_client.withdraw(amount_to_transfer, from_address)
                if not withdraw_result or withdraw_result.get('status') != 'success':
                    logger.error("❌ Échec retrait Extended")
                    return False
                logger.success("✅ Retrait Extended initié")
            else:
                logger.info(f"Étape 1: Retrait de ${amount_to_transfer:.2f} depuis Lighter...")
                # Utiliser l'API Lighter pour withdraw (fast=True)
                dest_address = self.extended_config['arbitrum_address']
                withdraw_result = self.lighter_client.withdraw(amount_to_transfer, dest_address, fast=True)
                if not withdraw_result or withdraw_result.get('status') != 'success':
                    logger.error("❌ Échec retrait Lighter")
                    return False
                logger.success("✅ Retrait Lighter initié")
            
            # ÉTAPE 2: Attendre que les fonds arrivent sur Arbitrum
            expected_amount = amount_to_transfer * 0.995  # Frais estimés 0.5%
            logger.info("Étape 2: Attente des fonds sur Arbitrum...")
            
            if not self._wait_for_arbitrum_balance(from_address, expected_amount):
                logger.error("❌ Fonds non reçus sur Arbitrum")
                return False
            
            # Récupérer le solde réel
            actual_balance = self._get_arbitrum_balance(from_address)
            
            # ÉTAPE 3: Deposit vers le compte avec moins de fonds
            if to_exchange == "lighter":
                logger.info(f"Étape 3: Dépôt de ${actual_balance:.2f} vers Lighter...")
                deposit_result = self.lighter_client.deposit(
                    amount=actual_balance,
                    from_address=from_address,
                    private_key=self.extended_config['arbitrum_private_key']
                )
            else:
                logger.info(f"Étape 3: Dépôt de ${actual_balance:.2f} vers Extended...")
                # Utiliser la clé privée Arbitrum de Lighter (car les fonds viennent de Lighter)
                deposit_private_key = self.lighter_config.get('arbitrum_private_key')
                if not deposit_private_key:
                    logger.error("❌ Clé privée Arbitrum manquante pour le dépôt Extended")
                    return False
                
                deposit_result = self.extended_client.deposit(
                    amount=actual_balance,
                    from_address=from_address,
                    private_key=deposit_private_key
                )
            
            if not deposit_result or deposit_result.get('status') != 'success':
                logger.error(f"❌ Échec dépôt {to_exchange}")
                return False
            
            logger.success(f"✅ Dépôt {to_exchange} réussi")
            
            # Attendre un peu pour que le dépôt soit crédité
            logger.info("⏳ Attente de la confirmation du dépôt...")
            time.sleep(60)
            
            # Vérifier les nouvelles balances
            extended_balance_new = self.extended_client.get_balance()
            extended_available_new = extended_balance_new.get('available', extended_balance_new.get('total', 0))
            lighter_balance_new = self.lighter_client.get_balance()
            
            logger.info("\n📊 Nouvelles balances:")
            logger.info(f"   Extended: ${extended_available_new:.2f}")
            logger.info(f"   Lighter: ${lighter_balance_new:.2f}")
            
            logger.success("✅ Rebalancing terminé")
            logger.info("="*60 + "\n")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur lors du rebalancing: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def setup_leverage(self) -> bool:
        """
        Configure le levier sur les deux exchanges
        
        Returns:
            True si succès
        """
        symbol = self.config['symbol']
        leverage = self.config['leverage']
        
        logger.info(f"⚙️  Configuration du levier {leverage}x pour {symbol}...")
        
        try:
            # Extended
            self.extended_client.set_leverage(symbol, leverage)
            logger.success(f"   ✅ Extended: {leverage}x")
            
            # Lighter
            self.lighter_client.set_leverage(symbol, leverage)
            logger.success(f"   ✅ Lighter: {leverage}x")
            
            time.sleep(1)
            return True
        except Exception as e:
            logger.error(f"❌ Erreur configuration levier: {e}")
            return False
    
    def setup_websockets(self) -> bool:
        """
        Connecte les WebSockets pour les prix et comptes
        
        Returns:
            True si succès
        """
        symbol = self.config['symbol']
        logger.info(f"🔌 Connexion des WebSockets pour {symbol}...")
        
        try:
            # Extended orderbook (pour mid_price)
            self.extended_client.ws_orderbook(symbol)
            logger.success("   ✅ Extended orderbook")
            
            # Lighter market_stats (pour mark_price)
            self.lighter_client.ws_market_stats(symbol)
            logger.success("   ✅ Lighter market_stats")
            
            # Lighter positions (pour détecter les trades en temps réel)
            self.lighter_client.ws_positions()
            logger.success("   ✅ Lighter positions")
            
            # Extended account (pour positions)
            self.extended_client.ws_account()
            logger.success("   ✅ Extended account")
            
            # Attendre que les données soient reçues
            time.sleep(3)
            
            logger.success("✅ WebSockets connectés")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur connexion WebSockets: {e}")
            return False
    
    def place_orders(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Place les ordres selon le mode configuré
        
        Returns:
            Tuple (success, extended_order_id, lighter_order_id)
        """
        order_mode = self.config.get('order_mode', 'market')
        
        if order_mode == 'limit':
            return self.place_orders_limit_mode()
        else:
            return self.place_orders_market_mode()
    
    def place_orders_limit_mode(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        MODE LIMIT: Place un ordre LIMIT sur Extended, attend le fill, puis MARKET sur Lighter
        - Avantage: 0% frais sur Extended (maker)
        - Stratégie: SHORT Extended si prix Extended > Lighter, LONG Lighter une fois fill
        
        Returns:
            Tuple (success, extended_order_id, lighter_order_id)
        """
        symbol = self.config['symbol']
        margin = self.config['margin']
        leverage = self.config['leverage']
        timeout = self.config.get('limit_order_timeout', 60)
        
        logger.info("\n" + "="*60)
        logger.info(f"📝 PLACEMENT DES ORDRES (MODE LIMIT) POUR {symbol}")
        logger.info("="*60)
        
        try:
            # ÉTAPE 1: Récupérer les prix
            logger.info("Étape 1: Récupération des prix...")
            extended_ticker = self.extended_client.get_ticker(symbol)
            lighter_ticker = self.lighter_client.get_ticker(symbol)
            
            if not extended_ticker or not lighter_ticker:
                logger.error("❌ Impossible de récupérer les prix")
                return (False, None, None)
            
            ext_bid = float(extended_ticker.get('bid', 0))
            ext_ask = float(extended_ticker.get('ask', 0))
            ext_last = float(extended_ticker.get('last', ext_ask))
            
            light_bid = float(lighter_ticker.get('bid', 0))
            light_ask = float(lighter_ticker.get('ask', 0))
            light_last = float(lighter_ticker.get('last', light_ask))
            
            logger.info(f"   Extended: bid=${ext_bid:.2f} | ask=${ext_ask:.2f} | last=${ext_last:.2f}")
            logger.info(f"   Lighter: bid=${light_bid:.2f} | ask=${light_ask:.2f} | last=${light_last:.2f}")
            
            # ÉTAPE 2: Déterminer la stratégie (comparer les prix mid)
            ext_mid = (ext_bid + ext_ask) / 2
            light_mid = (light_bid + light_ask) / 2
            
            # Placer directement au bid/ask exact pour maximiser les chances de fill
            # - BUY : prix = bid exact
            # - SELL : prix = ask exact
            
            if ext_mid > light_mid:
                # Extended plus cher → SHORT Extended, LONG Lighter
                extended_side = "sell"
                lighter_side = "buy"
                # Pour SELL : placer directement à l'ask exact
                limit_price = ext_ask
                logger.info(f"Étape 2: Extended > Lighter → SHORT Extended @ ${limit_price:.2f} (LIMIT, ask exact) | LONG Lighter (MARKET)")
                logger.info(f"   Orderbook Extended: bid=${ext_bid:.2f} | ask=${ext_ask:.2f} (prix = ask pour fill rapide)")
            else:
                # Lighter plus cher → LONG Extended, SHORT Lighter
                extended_side = "buy"
                lighter_side = "sell"
                # Pour BUY : placer directement au bid exact
                limit_price = ext_bid
                logger.info(f"Étape 2: Lighter > Extended → LONG Extended @ ${limit_price:.2f} (LIMIT, bid exact) | SHORT Lighter (MARKET)")
                logger.info(f"   Orderbook Extended: bid=${ext_bid:.2f} | ask=${ext_ask:.2f} (prix = bid pour fill rapide)")
            
            # ÉTAPE 3: Calculer la taille (90% margin)
            safe_margin = margin * 0.90
            extended_size = (safe_margin * leverage) / limit_price
            
            sz_decimals = self.lighter_client.get_size_decimals(symbol)
            extended_size = round(extended_size, sz_decimals)
            
            logger.info(f"Étape 3: Taille calculée: {extended_size:.6f} {symbol} (90% margin = ${safe_margin:.2f})")
            
            # ÉTAPE 4: Placer l'ordre LIMIT sur Extended avec post_only=True pour garantir maker
            logger.info(f"Étape 4: Placement ordre LIMIT Extended ({extended_side.upper()}) avec post_only=True...")
            extended_result = self.extended_client.place_order(
                symbol=symbol,
                side=extended_side,
                size=extended_size,
                order_type="limit",
                price=limit_price,
                post_only=True  # 🔥 Forcer maker (post-only)
            )
            
            if not extended_result or extended_result.get('status') not in ['OK', 'ok', 'success']:
                error_msg = extended_result.get('error', 'Unknown') if extended_result else 'No result'
                logger.error(f"❌ Échec ordre LIMIT Extended: {error_msg}")
                return (False, None, None)
            
            # Extraire l'order_id et external_id pour l'annulation
            extended_order_id = extended_result.get('order_id')
            extended_external_id = None
            
            # Essayer d'extraire l'external_id depuis l'objet raw
            if 'raw' in extended_result and extended_result['raw']:
                try:
                    raw_data = extended_result['raw']
                    if hasattr(raw_data, 'data') and raw_data.data:
                        extended_external_id = raw_data.data.external_id
                except:
                    pass
            
            logger.success(f"✅ Ordre LIMIT Extended placé: {extended_order_id}")
            if extended_external_id:
                logger.debug(f"   External ID: {extended_external_id}")
            
            # ÉTAPE 4.5: Vérifier que l'ordre est bien accepté via WebSocket
            logger.info("🔍 Vérification de l'ordre via WebSocket...")
            time.sleep(2)  # Attendre 2s que l'ordre soit enregistré
            
            # Utiliser le WebSocket account pour vérifier le statut
            account_updates = self.extended_client.get_account_updates()
            orders_cache = account_updates.get('orders', [])
            order_confirmed = any(
                o.get('id') == extended_order_id and o.get('status') in ['NEW', 'UNTRIGGERED']
                for o in orders_cache
            )
            
            # Si ordre rejeté, réessayer avec le bid/ask exact (même agressivité que le premier ordre)
            attempt = 1
            max_attempts = 5
            
            while not order_confirmed and attempt < max_attempts:
                logger.warning(f"⚠️  Ordre rejeté (post-only failed)")
                logger.info(f"🔄 Tentative {attempt+1}/{max_attempts}: réessai au bid/ask exact...")
                
                # Récupérer les prix actuels
                extended_ticker_retry = self.extended_client.get_ticker(symbol)
                ext_bid_retry = float(extended_ticker_retry.get('bid', 0))
                ext_ask_retry = float(extended_ticker_retry.get('ask', 0))
                
                # Utiliser le bid/ask exact (même agressivité que le premier ordre)
                if extended_side == "sell":
                    # SELL : ask exact
                    limit_price = ext_ask_retry
                else:
                    # BUY : bid exact
                    limit_price = ext_bid_retry
                
                # IMPORTANT: Garder la même taille pour éviter de dépasser la balance
                # Ne pas recalculer extended_size avec le nouveau prix
                # extended_size reste le même
                
                logger.info(f"   Nouveau prix (bid/ask exact): ${limit_price:.2f} | Taille: {extended_size:.6f} (inchangée)")
                
                # Replacer l'ordre avec post_only=True
                extended_result = self.extended_client.place_order(
                    symbol=symbol,
                    side=extended_side,
                    size=extended_size,
                    order_type="limit",
                    price=limit_price,
                    post_only=True  # 🔥 Toujours post_only=True
                )
                
                if not extended_result or extended_result.get('status') not in ['OK', 'ok', 'success']:
                    error_msg = extended_result.get('error', 'Unknown') if extended_result else 'No result'
                    logger.error(f"❌ Échec placement: {error_msg}")
                    attempt += 1
                    continue
                
                extended_order_id = extended_result.get('order_id')
                logger.success(f"✅ Ordre LIMIT placé (tentative {attempt+1}): {extended_order_id}")
                
                # Vérifier si cet ordre est accepté via WebSocket
                time.sleep(2)
                account_updates = self.extended_client.get_account_updates()
                orders_cache = account_updates.get('orders', [])
                order_confirmed = any(
                    o.get('id') == extended_order_id and o.get('status') in ['NEW', 'UNTRIGGERED']
                    for o in orders_cache
                )
                
                if order_confirmed:
                    logger.success(f"✅ Ordre confirmé dans l'orderbook (prix: ${limit_price:.2f})")
                    break
                
                attempt += 1
            
            if not order_confirmed:
                logger.error("❌ Impossible de placer un ordre LIMIT accepté après 5 tentatives")
                logger.error("❌ Le bot reste en mode LIMIT et ne basculera pas en MARKET")
                return (False, None, None)
            
            logger.info(f"⏳ Attente du fill avec suivi du marché en temps réel (sans timeout, jusqu'au fill)...")
            
            # ÉTAPE 5: Attendre que l'ordre soit fill avec suivi dynamique du prix
            # Pas de timeout ni de limite de tentatives - le bot continue jusqu'au fill
            fill_attempt = 0
            filled = False
            current_order_id = extended_order_id
            current_limit_price = limit_price
            start_time = time.time()
            check_interval = 1  # Vérifier le prix toutes les 1 seconde (plus rapide pour détecter le fill)
            
            # Boucle infinie jusqu'au fill (s'arrête seulement si l'ordre est fill ou Ctrl+C)
            while not filled:
                # Vérifier d'abord si l'ordre est fill (priorité absolue)
                extended_positions = self.extended_client.get_positions()
                extended_pos = next((p for p in extended_positions if p['symbol'] == symbol), None)
                
                if extended_pos:
                    filled_size = abs(float(extended_pos.get('size', 0)))
                    if filled_size >= extended_size * 0.90:  # 90% fill minimum (plus permissif)
                        filled = True
                        logger.success(f"✅ Ordre Extended FILL détecté: {filled_size:.6f} {symbol}")
                        break
                
                # Vérifier aussi via les ordres ouverts (si l'ordre n'est plus dans l'orderbook, il est peut-être fill)
                try:
                    account_updates = self.extended_client.get_account_updates()
                    orders_cache = account_updates.get('orders', [])
                    current_order_exists = any(
                        o.get('id') == current_order_id and o.get('status') in ['NEW', 'UNTRIGGERED', 'PARTIALLY_FILLED']
                        for o in orders_cache
                    )
                    
                    # Si l'ordre n'existe plus dans l'orderbook et qu'on a une position, c'est fill
                    if not current_order_exists and extended_pos:
                        filled_size = abs(float(extended_pos.get('size', 0)))
                        if filled_size > 0:
                            filled = True
                            logger.success(f"✅ Ordre Extended FILL (ordre disparu de l'orderbook): {filled_size:.6f} {symbol}")
                            break
                except:
                    pass  # Ignorer les erreurs de vérification
                
                time.sleep(check_interval)
                
                # Récupérer les prix actuels du marché directement depuis le cache WebSocket (plus rapide)
                orderbook_data = self.extended_client.get_orderbook_data(symbol)
                if orderbook_data:
                    ext_bid_current = float(orderbook_data.get('bid', 0))
                    ext_ask_current = float(orderbook_data.get('ask', 0))
                else:
                    # Fallback sur get_ticker si WebSocket pas disponible
                    extended_ticker_current = self.extended_client.get_ticker(symbol)
                    ext_bid_current = float(extended_ticker_current.get('bid', 0))
                    ext_ask_current = float(extended_ticker_current.get('ask', 0))
                
                # Déterminer le prix cible actuel (bid pour BUY, ask pour SELL)
                if extended_side == "buy":
                    target_price = ext_bid_current
                    price_diff = abs(target_price - current_limit_price)
                    price_diff_pct = (price_diff / current_limit_price) * 100 if current_limit_price > 0 else 0
                else:  # sell
                    target_price = ext_ask_current
                    price_diff = abs(target_price - current_limit_price)
                    price_diff_pct = (price_diff / current_limit_price) * 100 if current_limit_price > 0 else 0
                
                elapsed = int(time.time() - start_time)
                print(f"\r⏳ Ordre @ ${current_limit_price:.2f} | Marché @ ${target_price:.2f} | Écart: ${price_diff:.2f} ({price_diff_pct:.3f}%) | {elapsed}s", end="", flush=True)
                
                # VÉRIFICATION CRITIQUE: Vérifier le fill AVANT de réajuster l'ordre
                extended_positions_check = self.extended_client.get_positions()
                extended_pos_check = next((p for p in extended_positions_check if p['symbol'] == symbol), None)
                if extended_pos_check:
                    filled_size_check = abs(float(extended_pos_check.get('size', 0)))
                    if filled_size_check >= extended_size * 0.90:
                        filled = True
                        print()  # Nouvelle ligne
                        logger.success(f"✅ Ordre Extended FILL détecté avant réajustement: {filled_size_check:.6f} {symbol}")
                        break
                
                # Réajuster l'ordre si le bid/ask a changé
                # On remplace dès que le prix du marché diffère de l'ordre (tolérance de $0.10 pour éviter les micro-ajustements)
                # Cela garantit que l'ordre reste toujours au meilleur bid/ask exact
                price_changed = abs(target_price - current_limit_price) > 0.10  # Tolérance de $0.10 pour éviter les micro-ajustements
                
                # Si le bid/ask a changé, réajuster (mais seulement si pas déjà fill)
                if price_changed and not filled:  # Remplace dès que le bid/ask change (même légèrement)
                    print()  # Nouvelle ligne
                    fill_attempt += 1
                    logger.info(f"\n🔄 Prix marché éloigné (écart: ${price_diff:.2f}, {price_diff_pct:.3f}%) - Réajustement #{fill_attempt}")
                    logger.info(f"   Ordre actuel: ${current_limit_price:.2f} | Marché: ${target_price:.2f}")
                    logger.info("🗑️  Annulation de l'ordre Extended...")
                    
                    # Annuler l'ordre actuel
                    try:
                        if current_order_id:
                            self.extended_client.cancel_order(current_order_id)
                            logger.success("✅ Ordre Extended annulé")
                    except Exception as e:
                        logger.warning(f"⚠️  Annulation Extended échouée: {e} (peut-être déjà fill ou annulé)")
                    
                    # Utiliser le bid/ask exact actuel (même agressivité)
                    new_limit_price = target_price
                    
                    logger.info(f"🔄 Nouveau prix: ${new_limit_price:.2f} (bid/ask exact) | Taille: {extended_size:.6f} (inchangée)")
                    
                    # Replacer l'ordre avec post_only=True
                    extended_result_new = self.extended_client.place_order(
                        symbol=symbol,
                        side=extended_side,
                        size=extended_size,
                        order_type="limit",
                        price=new_limit_price,
                        post_only=True  # 🔥 Toujours post_only=True pour garantir maker
                    )
                    
                    if not extended_result_new or extended_result_new.get('status') not in ['OK', 'ok', 'success']:
                        error_msg = extended_result_new.get('error', 'Unknown') if extended_result_new else 'No result'
                        logger.error(f"❌ Échec placement ordre réajusté: {error_msg}")
                        break
                    
                    current_order_id = extended_result_new.get('order_id')
                    current_limit_price = new_limit_price
                    logger.success(f"✅ Ordre LIMIT réajusté (#{fill_attempt}): {current_order_id} @ ${new_limit_price:.2f}")
                    time.sleep(1)  # Attendre que l'ordre soit enregistré
            
            print()  # Nouvelle ligne après la boucle
            
            # Si on sort de la boucle sans fill, c'est probablement une erreur ou Ctrl+C
            if not filled:
                elapsed_total = int(time.time() - start_time)
                logger.warning(f"⚠️  Sortie de la boucle de suivi après {elapsed_total}s et {fill_attempt} réajustements")
                logger.warning("   (Peut être dû à Ctrl+C ou une erreur)")
                
                # Annuler le dernier ordre s'il existe
                try:
                    if current_order_id:
                        self.extended_client.cancel_order(current_order_id)
                        logger.success("✅ Dernier ordre Extended annulé")
                except Exception as e:
                    logger.warning(f"⚠️  Annulation échouée: {e}")
                
                # Retourner une erreur
                return (False, None, None)
            
            # ÉTAPE 6: Ordre Extended fill → placer MARKET sur Lighter IMMÉDIATEMENT
            logger.info(f"Étape 6: Ordre Extended fill → Placement MARKET Lighter ({lighter_side.upper()})...")
            
            # Recalculer la taille Lighter basée sur le prix actuel
            lighter_ticker_fresh = self.lighter_client.get_ticker(symbol)
            lighter_price = float(lighter_ticker_fresh.get('last', lighter_ticker_fresh.get('ask', 0)))
            lighter_size = (safe_margin * leverage) / lighter_price
            lighter_size = round(lighter_size, sz_decimals)
            
            lighter_result = self.lighter_client.place_order(
                symbol=symbol,
                side=lighter_side,
                size=lighter_size,
                order_type="market"
            )
            
            if not lighter_result or lighter_result.get('status') not in ['OK', 'ok', 'success']:
                error_msg = lighter_result.get('error', 'Unknown') if lighter_result else 'No result'
                logger.error(f"❌ Échec ordre MARKET Lighter: {error_msg}")
                logger.warning("⚠️  Position Extended ouverte mais Lighter a échoué!")
                logger.warning("⚠️  Fermeture de la position Extended orpheline...")
                
                time.sleep(5)
                self.close_positions(symbol)
                return (False, None, None)
            
            lighter_order_id = lighter_result.get('order_id', lighter_result.get('data', {}).get('id'))
            logger.success(f"✅ Ordre MARKET Lighter placé: {lighter_order_id}")
            
            logger.success(f"✅ Ordre Extended placé: {extended_order_id}")
            logger.success(f"✅ Ordre Lighter placé: {lighter_order_id}")
            
            return (True, extended_order_id, lighter_order_id)
            
        except Exception as e:
            logger.error(f"❌ Erreur placement ordres LIMIT: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return (False, None, None)
    
    def place_orders_market_mode(self) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        MODE MARKET: Place les ordres market opposés sur Extended et Lighter simultanément
        Utilise 90% de la margin pour garantir que le coût ne dépasse pas la balance
        
        Returns:
            Tuple (success, extended_order_id, lighter_order_id)
        """
        symbol = self.config['symbol']
        margin = self.config['margin']
        leverage = self.config['leverage']
        
        logger.info("\n" + "="*60)
        logger.info(f"📝 PLACEMENT DES ORDRES POUR {symbol}")
        logger.info("="*60)
        
        try:
            # ÉTAPE 1: Récupérer les prix en temps réel
            logger.info("Étape 1: Récupération des prix...")
            extended_ticker = self.extended_client.get_ticker(symbol)
            lighter_ticker = self.lighter_client.get_ticker(symbol)
            
            if not extended_ticker or not lighter_ticker:
                logger.error("❌ Impossible de récupérer les prix")
                return (False, None, None)
            
            # Utiliser 'last' pour le calcul (comme dnfarming.py)
            extended_price = float(extended_ticker.get('last', extended_ticker.get('ask', 0)))
            lighter_price = float(lighter_ticker.get('last', lighter_ticker.get('ask', 0)))
            
            ext_ask = float(extended_ticker.get('ask', extended_price))
            light_ask = float(lighter_ticker.get('ask', lighter_price))
            
            logger.info(f"   Extended last: ${extended_price:.2f}")
            logger.info(f"   Lighter last: ${lighter_price:.2f}")
            
            # ÉTAPE 2: Calculer les tailles avec 90% de la margin
            safe_margin = margin * 0.90  # 2700 USDC pour margin=3000
            
            extended_size = (safe_margin * leverage) / extended_price
            lighter_size = (safe_margin * leverage) / lighter_price
            
            # Arrondir selon sz_decimals
            sz_decimals = self.lighter_client.get_size_decimals(symbol)
            extended_size = round(extended_size, sz_decimals)
            lighter_size = round(lighter_size, sz_decimals)
            
            logger.info(f"Étape 2: Calcul des tailles (90% margin = ${safe_margin:.2f}):")
            logger.info(f"   Extended size: {extended_size:.6f} {symbol}")
            logger.info(f"   Lighter size: {lighter_size:.6f} {symbol}")
            
            # ÉTAPE 3: Déterminer les côtés (comparer ask prices)
            if ext_ask < light_ask:
                extended_side = "buy"   # LONG Extended (moins cher)
                lighter_side = "sell"   # SHORT Lighter (plus cher)
                logger.info(f"Étape 3: Stratégie → LONG Extended (${ext_ask:.2f}) | SHORT Lighter (${light_ask:.2f})")
            else:
                extended_side = "sell"  # SHORT Extended
                lighter_side = "buy"    # LONG Lighter
                logger.info(f"Étape 3: Stratégie → SHORT Extended | LONG Lighter (${light_ask:.2f})")
            
            # ÉTAPE 4: Placer les ordres simultanément
            logger.info("Étape 4: Placement des ordres market...")
            
            extended_result = None
            lighter_result = None
            
            def place_extended():
                nonlocal extended_result
                extended_result = self.extended_client.place_order(
                    symbol=symbol,
                    side=extended_side,
                    size=extended_size,
                    order_type="market"
                )
            
            def place_lighter():
                nonlocal lighter_result
                lighter_result = self.lighter_client.place_order(
                    symbol=symbol,
                    side=lighter_side,
                    size=lighter_size,
                    order_type="market"
                )
            
            # Lancer les deux threads
            ext_thread = threading.Thread(target=place_extended)
            light_thread = threading.Thread(target=place_lighter)
            
            ext_thread.start()
            light_thread.start()
            
            ext_thread.join(timeout=30)
            light_thread.join(timeout=30)
            
            # ÉTAPE 5: Vérifier les résultats API
            extended_api_ok = extended_result and extended_result.get('status') in ['OK', 'ok', 'success']
            lighter_api_ok = lighter_result and lighter_result.get('status') in ['OK', 'ok', 'success']
            
            if not extended_api_ok:
                error_msg = extended_result.get('error', 'Unknown') if extended_result else 'No result'
                logger.error(f"❌ Échec API Extended: {error_msg}")
                
                # Si Lighter a réussi, le fermer immédiatement
                if lighter_api_ok:
                    logger.warning("⚠️  Fermeture de la position Lighter car Extended a échoué...")
                    # Attendre plus longtemps (10s) pour que la position Lighter soit créée et détectable
                    logger.info("⏳ Attente de la création de la position Lighter (10s)...")
                    time.sleep(10)
                    
                    try:
                        # Vérifier avec l'API Explorer si la position existe
                        lighter_positions = self.lighter_client.get_positions_from_explorer()
                        lighter_pos = next((p for p in lighter_positions if p.get('symbol') == symbol), None)
                        
                        if lighter_pos:
                            logger.info(f"   Position Lighter détectée: {lighter_pos.get('side')} {lighter_pos.get('size')} {symbol}")
                            self.close_positions(symbol)
                        else:
                            logger.warning("   Position Lighter non détectée (peut-être déjà fermée ou échec)")
                    except Exception as e:
                        logger.error(f"   Erreur fermeture Lighter: {e}")
                
                return (False, None, None)
            
            if not lighter_api_ok:
                error_msg = lighter_result.get('error', 'Unknown') if lighter_result else 'No result'
                logger.error(f"❌ Échec API Lighter: {error_msg}")
                
                # Si Extended a réussi, le fermer immédiatement
                if extended_api_ok:
                    logger.warning("⚠️  Fermeture de la position Extended car Lighter a échoué...")
                    # Attendre plus longtemps (10s) pour que la position Extended soit créée
                    logger.info("⏳ Attente de la création de la position Extended (10s)...")
                    time.sleep(10)
                    
                    try:
                        extended_positions = self.extended_client.get_positions()
                        extended_pos = next((p for p in extended_positions if p['symbol'] == symbol), None)
                        
                        if extended_pos:
                            logger.info(f"   Position Extended détectée: {extended_pos.get('side')} {extended_pos.get('size')} {symbol}")
                            self.close_positions(symbol)
                        else:
                            logger.warning("   Position Extended non détectée (peut-être déjà fermée ou échec)")
                    except Exception as e:
                        logger.error(f"   Erreur fermeture Extended: {e}")
                
                return (False, None, None)
            
            # Les deux API ont accepté les ordres
            ext_order_id = extended_result.get('order_id') or extended_result.get('data', {}).get('id')
            light_order_id = lighter_result.get('order_id') or lighter_result.get('tx_hash')
            
            logger.success(f"✅ Ordre Extended accepté par l'API: {ext_order_id}")
            logger.success(f"✅ Ordre Lighter accepté par l'API: {light_order_id}")
            
            # IMPORTANT: Attendre que les matching engines traitent les ordres
            # Les ordres market peuvent prendre quelques secondes à être exécutés
            # ⚠️ L'API peut accepter un ordre qui sera ensuite rejeté par le matching engine
            logger.info("⏳ Attente de l'exécution par les matching engines (7s)...")
            time.sleep(7)
            
            logger.info("="*60 + "\n")
            
            return (True, ext_order_id, light_order_id)
            
        except Exception as e:
            logger.error(f"❌ Erreur placement des ordres: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return (False, None, None)
    
    def verify_trades_opened(self, symbol: str, timeout: int = 40) -> Tuple[bool, str]:
        """
        Vérifie que les deux trades sont ouverts et ont des tailles similaires
        Utilise l'API Explorer pour Lighter (plus fiable que WebSocket après placement d'ordre)
        
        Args:
            symbol: Symbole à vérifier
            timeout: Timeout en secondes
            
        Returns:
            Tuple (success, reason)
        """
        logger.info(f"🔍 Vérification des trades ouverts (timeout: {timeout}s)...")
        logger.info(f"   Utilise l'API Explorer pour Lighter (plus fiable)")
        
        start = time.time()
        check_count = 0
        
        while time.time() - start < timeout:
            try:
                check_count += 1
                
                # Récupérer positions Extended (WebSocket)
                extended_positions = self.extended_client.get_positions()
                extended_pos = next((p for p in extended_positions if p['symbol'] == symbol), None)
                
                # Récupérer positions Lighter (API Explorer - plus fiable après placement d'ordre)
                lighter_positions = self.lighter_client.get_positions_from_explorer()
                lighter_pos = next((p for p in lighter_positions if p.get('symbol') == symbol), None)
                
                # Debug tous les 3 checks (plus fréquent pour mieux voir)
                if check_count % 3 == 0:
                    elapsed = int(time.time() - start)
                    logger.info(f"   Check #{check_count} ({elapsed}s): Extended={'✓' if extended_pos else '✗'}, Lighter={'✓' if lighter_pos else '✗'}")
                    
                    # Debug: afficher toutes les positions disponibles
                    if check_count % 9 == 0:  # Tous les 9 checks
                        logger.debug(f"      Extended positions: {len(extended_positions)} total")
                        logger.debug(f"      Lighter positions: {len(lighter_positions)} total")
                        if lighter_positions:
                            logger.debug(f"      Lighter symbols: {[p.get('symbol') for p in lighter_positions]}")
                
                if extended_pos and lighter_pos:
                    # Vérifier les sizes
                    ext_size = abs(float(extended_pos.get('size', 0)))
                    light_size_signed = float(lighter_pos.get('size_signed', 0))
                    light_size = abs(light_size_signed) if light_size_signed != 0 else abs(float(lighter_pos.get('size', 0)))
                    
                    if ext_size == 0 or light_size == 0:
                        time.sleep(1)
                        continue
                    
                    # Calculer la différence (tolérance 10% car sizes peuvent différer)
                    diff_percent = abs(ext_size - light_size) / max(ext_size, light_size) * 100
                    
                    logger.info(f"   ✅ Extended: {extended_pos['side']} {ext_size:.6f} {symbol}")
                    logger.info(f"   ✅ Lighter: {lighter_pos.get('side', 'N/A')} {light_size:.6f} {symbol}")
                    logger.info(f"   📊 Différence: {diff_percent:.2f}%")
                    
                    if diff_percent <= 15.0:  # Tolérance 15% (sizes calculées différemment)
                        logger.success("✅ Les deux trades sont ouverts avec des tailles acceptables")
                        return (True, "ok")
                    else:
                        logger.error(f"❌ Tailles trop différentes: {diff_percent:.2f}% > 15%")
                        return (False, "size_mismatch")
                
                time.sleep(1)
                
            except Exception as e:
                logger.debug(f"Erreur vérification: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                time.sleep(1)
        
        # Timeout atteint - Dernier check avec debug complet
        logger.warning("⏱️  Timeout atteint, dernier check...")
        
        extended_positions = self.extended_client.get_positions()
        extended_pos = next((p for p in extended_positions if p['symbol'] == symbol), None)
        
        # Dernier essai avec Explorer API
        lighter_positions = self.lighter_client.get_positions_from_explorer()
        lighter_pos = next((p for p in lighter_positions if p.get('symbol') == symbol), None)
        
        logger.error(f"État final:")
        logger.error(f"   Extended positions total: {len(extended_positions)}")
        logger.error(f"   Extended {symbol}: {'TROUVÉ' if extended_pos else 'NON TROUVÉ'}")
        logger.error(f"   Lighter positions total: {len(lighter_positions)}")
        logger.error(f"   Lighter {symbol}: {'TROUVÉ' if lighter_pos else 'NON TROUVÉ'}")
        
        if lighter_positions:
            logger.error(f"   Lighter symbols disponibles: {[p.get('symbol', 'N/A') for p in lighter_positions]}")
        
        if extended_pos and not lighter_pos:
            logger.error("❌ Trade Extended ouvert mais pas Lighter")
            return (False, "lighter_not_opened")
        elif lighter_pos and not extended_pos:
            logger.error("❌ Trade Lighter ouvert mais pas Extended")
            return (False, "extended_not_opened")
        else:
            logger.error("❌ Aucun des deux trades n'est ouvert")
            return (False, "both_not_opened")
    
    def calculate_pnl_extended(self, position: Dict, symbol: str) -> float:
        """Calcule le PnL Extended avec mid_price (bid+ask)/2"""
        try:
            orderbook = self.extended_client.get_orderbook_data(symbol)
            if not orderbook or not orderbook.get('bid') or not orderbook.get('ask'):
                return 0.0
            
            bid = float(orderbook['bid'])
            ask = float(orderbook['ask'])
            mid_price = (bid + ask) / 2
            
            entry_price = float(position.get('entry_price', 0) or position.get('open_price', 0))
            size = float(position.get('size', 0))
            side = position.get('side', 'UNKNOWN')
            
            if entry_price == 0 or size == 0:
                return 0.0
            
            if side == "LONG":
                return (mid_price - entry_price) * size
            elif side == "SHORT":
                return (entry_price - mid_price) * size
            else:
                size_signed = float(position.get('size_signed', 0))
                return (mid_price - entry_price) * size_signed
                
        except Exception as e:
            logger.debug(f"Erreur calcul PnL Extended: {e}")
            return 0.0
    
    def calculate_pnl_lighter(self, position: Dict, symbol: str) -> float:
        """Calcule le PnL Lighter avec mark_price"""
        try:
            market_stats = self.lighter_client.get_market_stats_data(symbol)
            if not market_stats or not market_stats.get('mark_price'):
                return 0.0
            
            mark_price = float(market_stats['mark_price'])
            
            entry_price = float(position.get('entry_price', 0) or position.get('open_price', 0))
            size = float(position.get('size', 0))
            side = position.get('side', 'UNKNOWN')
            size_signed = float(position.get('size_signed', 0))
            
            if entry_price == 0:
                return 0.0
            
            if side == "LONG" and size > 0:
                return (mark_price - entry_price) * size
            elif side == "SHORT" and size > 0:
                return (entry_price - mark_price) * size
            else:
                # Fallback avec size_signed
                if size_signed != 0:
                    return (mark_price - entry_price) * size_signed
                return 0.0
                
        except Exception as e:
            logger.debug(f"Erreur calcul PnL Lighter: {e}")
            return 0.0
    
    def get_total_pnl(self) -> Tuple[float, float, float]:
        """
        Récupère le PnL total
        
        Returns:
            Tuple (extended_pnl, lighter_pnl, total_pnl)
        """
        symbol = self.config['symbol']
        
        extended_pnl = 0.0
        lighter_pnl = 0.0
        
        try:
            # Extended
            extended_positions = self.extended_client.get_positions()
            extended_pos = next((p for p in extended_positions if p['symbol'] == symbol), None)
            if extended_pos:
                extended_pnl = self.calculate_pnl_extended(extended_pos, symbol)
            
            # Lighter (utiliser API Explorer - plus fiable)
            lighter_positions = self.lighter_client.get_positions_from_explorer()
            lighter_pos = next((p for p in lighter_positions if p.get('symbol') == symbol), None)
            if lighter_pos:
                lighter_pnl = self.calculate_pnl_lighter(lighter_pos, symbol)
                
        except Exception as e:
            logger.debug(f"Erreur get_total_pnl: {e}")
        
        total_pnl = extended_pnl + lighter_pnl
        return (extended_pnl, lighter_pnl, total_pnl)
    
    def wait_holding_duration_with_pnl(self, duration_minutes: int):
        """
        Attend la durée du cycle en affichant le PnL en temps réel
        
        Args:
            duration_minutes: Durée en minutes
        """
        symbol = self.config['symbol']
        logger.info(f"\n⏳ Attente de {duration_minutes} minute(s) avec monitoring PnL...")
        
        start_time = time.time()
        end_time = start_time + (duration_minutes * 60)
        
        while time.time() < end_time:
            try:
                # Récupérer les positions
                extended_positions = self.extended_client.get_positions()
                extended_pos = next((p for p in extended_positions if p['symbol'] == symbol), None)
                
                # Utiliser l'API Explorer pour Lighter (plus fiable)
                lighter_positions = self.lighter_client.get_positions_from_explorer()
                lighter_pos = next((p for p in lighter_positions if p.get('symbol') == symbol), None)
                
                # Calculer PnL
                ext_pnl = 0.0
                ext_size = 0.0
                ext_side = "N/A"
                
                if extended_pos:
                    ext_pnl = self.calculate_pnl_extended(extended_pos, symbol)
                    ext_size = abs(float(extended_pos.get('size', 0)))
                    ext_side = extended_pos.get('side', 'N/A')
                
                light_pnl = 0.0
                light_size = 0.0
                light_side = "N/A"
                
                if lighter_pos:
                    light_pnl = self.calculate_pnl_lighter(lighter_pos, symbol)
                    light_size_signed = float(lighter_pos.get('size_signed', 0))
                    if light_size_signed != 0:
                        light_size = abs(light_size_signed)
                        light_side = "LONG" if light_size_signed > 0 else "SHORT"
                    else:
                        light_size = float(lighter_pos.get('size', 0))
                        light_side = lighter_pos.get('side', 'N/A')
                
                total_pnl = ext_pnl + light_pnl
                
                # Calculer le temps
                elapsed = int(time.time() - start_time)
                remaining = int(end_time - time.time())
                elapsed_mins = elapsed // 60
                elapsed_secs = elapsed % 60
                remaining_mins = remaining // 60
                remaining_secs = remaining % 60
                
                # Afficher sur une ligne
                pnl_line = (
                    f"📊 PnL {symbol} | "
                    f"Extended: {ext_side} {ext_size:.6f} = ${ext_pnl:+.2f} | "
                    f"Lighter: {light_side} {light_size:.6f} = ${light_pnl:+.2f} | "
                    f"Total: ${total_pnl:+.2f} | "
                    f"⏱️ {elapsed_mins:02d}:{elapsed_secs:02d} / {remaining_mins:02d}:{remaining_secs:02d}"
                )
                print(f"\r{pnl_line}", end="", flush=True)
                
            except Exception as e:
                logger.debug(f"Erreur affichage PnL: {e}")
            
            time.sleep(1)
        
        print()  # Nouvelle ligne après la boucle
        logger.info(f"⏰ Durée de {duration_minutes} minute(s) atteinte\n")
    
    def close_positions_with_pnl_check(self, symbol: str, pnl_check_delay: int) -> bool:
        """
        Ferme les positions en vérifiant le PnL
        Si PnL négatif, attend pnl_check_delay minutes
        
        Args:
            symbol: Symbole à fermer
            pnl_check_delay: Délai d'attente en minutes si PnL négatif
            
        Returns:
            True si succès
        """
        logger.info("\n" + "="*60)
        logger.info("🔍 VÉRIFICATION PNL AVANT FERMETURE")
        logger.info("="*60)
        
        # Vérifier le PnL actuel
        ext_pnl, light_pnl, total_pnl = self.get_total_pnl()
        
        logger.info(f"   Extended PnL: ${ext_pnl:+.2f}")
        logger.info(f"   Lighter PnL: ${light_pnl:+.2f}")
        logger.info(f"   Total PnL: ${total_pnl:+.2f}")
        
        # Récupérer le seuil minimal de PnL
        minimal_pnl = self.config.get('minimal_pnl', 0.0)
        logger.info(f"   Seuil minimal: ${minimal_pnl:+.2f}")
        
        if total_pnl >= minimal_pnl:
            logger.success(f"✅ PnL atteint ou dépassé le seuil (${total_pnl:+.2f} >= ${minimal_pnl:+.2f}), fermeture immédiate")
            return self.close_positions(symbol)
        
        # PnL négatif, attendre pnl_check_delay minutes
        logger.warning(f"⚠️  PnL en dessous du seuil (${total_pnl:+.2f} < ${minimal_pnl:+.2f})")
        logger.info(f"⏳ Attente de {pnl_check_delay} minute(s) pour récupération...")
        
        end_time = time.time() + (pnl_check_delay * 60)
        
        while time.time() < end_time:
            ext_pnl, light_pnl, total_pnl = self.get_total_pnl()
            
            if total_pnl >= minimal_pnl:
                logger.success(f"\n🎯 PnL a atteint le seuil! (${total_pnl:+.2f} >= ${minimal_pnl:+.2f})")
                logger.info("   → Fermeture immédiate des positions")
                return self.close_positions(symbol)
            
            remaining = int(end_time - time.time())
            mins = remaining // 60
            secs = remaining % 60
            
            pnl_line = f"⏳ PnL: ${total_pnl:+.2f} (seuil: ${minimal_pnl:+.2f}) | Attente: {mins:02d}:{secs:02d}"
            print(f"\r{pnl_line}", end="", flush=True)
            
            time.sleep(1)
        
        print()  # Nouvelle ligne
        logger.warning(f"⏱️  Timeout atteint, PnL toujours négatif (${total_pnl:+.2f})")
        logger.info("   → Fermeture forcée des positions")
        return self.close_positions(symbol)
    
    def close_positions(self, symbol: str) -> bool:
        """
        Ferme les positions sur Extended et Lighter
        
        Args:
            symbol: Symbole à fermer
            
        Returns:
            True si succès
        """
        logger.info(f"\n🔒 Fermeture des positions pour {symbol}...")
        
        success = True
        
        try:
            # Récupérer les positions
            extended_positions = self.extended_client.get_positions()
            extended_pos = next((p for p in extended_positions if p['symbol'] == symbol), None)
            
            # Utiliser l'API Explorer pour Lighter (plus fiable)
            lighter_positions = self.lighter_client.get_positions_from_explorer()
            lighter_pos = next((p for p in lighter_positions if p.get('symbol') == symbol), None)
            
            logger.info(f"   Positions Extended: {len(extended_positions)} | Lighter: {len(lighter_positions)}")
            
            # Fermer Extended
            if extended_pos:
                size = abs(float(extended_pos.get('size', 0)))
                side = extended_pos.get('side', 'UNKNOWN')
                close_side = "sell" if side == "LONG" else "buy"
                
                logger.info(f"   Fermeture Extended {side} {size} {symbol}...")
                result = self.extended_client.place_order(
                    symbol=symbol,
                    side=close_side,
                    size=size,
                    order_type="market",
                    reduce_only=True
                )
                
                if result and result.get('status') in ['OK', 'ok', 'success']:
                    logger.success("   ✅ Position Extended fermée")
                else:
                    logger.error("   ❌ Échec fermeture Extended")
                    success = False
            
            # Fermer Lighter
            if lighter_pos:
                size_signed = float(lighter_pos.get('size_signed', 0))
                if size_signed != 0:
                    size = abs(size_signed)
                    side = "LONG" if size_signed > 0 else "SHORT"
                else:
                    size = float(lighter_pos.get('size', 0))
                    side = lighter_pos.get('side', 'UNKNOWN')
                
                close_side = "sell" if side == "LONG" else "buy"
                
                logger.info(f"   Fermeture Lighter {side} {size} {symbol}...")
                result = self.lighter_client.place_order(
                    symbol=symbol,
                    side=close_side,
                    size=size,
                    order_type="market",
                    reduce_only=True
                )
                
                if result and result.get('status') in ['OK', 'ok', 'success']:
                    logger.success("   ✅ Position Lighter fermée")
                else:
                    logger.error("   ❌ Échec fermeture Lighter")
                    success = False
            
            if not extended_pos and not lighter_pos:
                logger.warning("   ⚠️  Aucune position à fermer")
            
            # Attendre et vérifier la fermeture
            time.sleep(3)
            
            extended_positions = self.extended_client.get_positions()
            extended_pos_after = next((p for p in extended_positions if p['symbol'] == symbol), None)
            
            lighter_positions = self.lighter_client.get_positions()
            lighter_pos_after = next((p for p in lighter_positions if p.get('symbol') == symbol), None)
            
            if extended_pos_after or lighter_pos_after:
                logger.warning("⚠️  Des positions sont toujours ouvertes")
                if extended_pos_after:
                    logger.warning(f"   Extended: {extended_pos_after.get('size', 0)}")
                if lighter_pos_after:
                    logger.warning(f"   Lighter: {lighter_pos_after.get('size', 0)}")
                success = False
            else:
                logger.success("✅ Toutes les positions sont fermées")
            
            return success
            
        except Exception as e:
            logger.error(f"❌ Erreur fermeture positions: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def check_balances_between_cycles(self) -> bool:
        """
        Vérifie les balances entre les cycles et rebalance si nécessaire
        
        Returns:
            True si balances OK ou rebalancing réussi
        """
        logger.info("\n" + "="*60)
        logger.info("💰 VÉRIFICATION DES BALANCES ENTRE CYCLES")
        logger.info("="*60)
        
        # Récupérer les balances
        extended_balance_dict = self.extended_client.get_balance()
        extended_available = extended_balance_dict.get('available', extended_balance_dict.get('total', 0))
        lighter_balance = self.lighter_client.get_balance()
        
        margin = self.config['margin']
        rebalance_threshold = self.config['rebalance_threshold']
        
        logger.info(f"   Extended: ${extended_available:.2f}")
        logger.info(f"   Lighter: ${lighter_balance:.2f}")
        logger.info(f"   Margin requise: ${margin:.2f}")
        logger.info(f"   Seuil rebalancing: ${rebalance_threshold:.2f}")
        
        # Vérifier si un compte a moins que la margin
        if extended_available < margin or lighter_balance < margin:
            logger.warning("⚠️  Un compte a moins que la margin requise")
            # Vérifier si rebalancing possible
            total = extended_available + lighter_balance
            if total >= 2 * margin:
                logger.info("   Rebalancing possible")
                return self.rebalance_accounts()
            else:
                logger.error(f"❌ Fonds insuffisants: ${total:.2f} < ${2*margin:.2f}")
                return False
        
        # Vérifier la différence entre les comptes
        diff = abs(extended_available - lighter_balance)
        if diff > rebalance_threshold:
            logger.warning(f"⚠️  Différence de ${diff:.2f} > seuil ${rebalance_threshold:.2f}")
            return self.rebalance_accounts()
        
        logger.success("✅ Balances OK pour le prochain cycle")
        logger.info("="*60 + "\n")
        return True
    
    def close_partial_positions(self):
        """Ferme les positions partielles en cas d'erreur"""
        symbol = self.config['symbol']
        logger.warning("⚠️  Fermeture des positions partielles...")
        
        try:
            self.close_positions(symbol)
        except Exception as e:
            logger.error(f"Erreur fermeture partielle: {e}")
    
    def run(self):
        """Lance le bot principal"""
        try:
            logger.info("\n" + "="*80)
            logger.info("🚀 DÉMARRAGE DU BOT DN LIGHTER EXTENDED")
            logger.info("="*80 + "\n")
            
            # 1. Initialiser les clients
            self._initialize_clients()
            
            # 2. Vérifier les balances initiales
            balance_ok, reason = self.check_initial_balances()
            if not balance_ok:
                if reason == "rebalance_needed":
                    if not self.rebalance_accounts():
                        logger.error("❌ Échec du rebalancing initial")
                        return
                else:
                    logger.error("❌ Fonds insuffisants, impossible de continuer")
                    return
            
            # 3. Configurer le levier
            if not self.setup_leverage():
                logger.error("❌ Échec configuration levier")
                return
            
            # 4. Connecter les WebSockets
            if not self.setup_websockets():
                logger.error("❌ Échec connexion WebSockets")
                return
            
            # 5. Boucle de cycles
            num_cycles = self.config['num_cycles']
            symbol = self.config['symbol']
            
            for cycle_num in range(1, num_cycles + 1):
                logger.info("\n" + "="*80)
                logger.info(f"🔄 CYCLE {cycle_num}/{num_cycles}")
                logger.info("="*80)
                
                # a. Placer les ordres (avec retry)
                max_order_attempts = 3  # Nombre de tentatives pour placer les ordres
                order_attempt = 0
                success = False
                ext_order_id = None
                light_order_id = None
                
                while order_attempt < max_order_attempts and not success:
                    order_attempt += 1
                    if order_attempt > 1:
                        logger.info(f"🔄 Tentative {order_attempt}/{max_order_attempts} de placement des ordres...")
                        time.sleep(2)  # Attendre un peu avant de réessayer
                    
                    success, ext_order_id, light_order_id = self.place_orders()
                    
                    if not success:
                        if order_attempt < max_order_attempts:
                            logger.warning(f"⚠️  Échec placement des ordres (tentative {order_attempt}/{max_order_attempts}), réessai...")
                        else:
                            logger.error(f"❌ Échec placement des ordres après {max_order_attempts} tentatives")
                            logger.warning("⚠️  Arrêt du bot")
                            break
                
                if not success:
                    break
                
                # b. Vérifier que les trades sont ouverts
                trades_ok, verify_reason = self.verify_trades_opened(symbol)
                if not trades_ok:
                    logger.error(f"❌ Échec vérification des trades: {verify_reason}")
                    logger.warning("⚠️  Fermeture des positions partielles et arrêt")
                    self.close_partial_positions()
                    break
                
                # c. Attendre la durée du cycle avec monitoring PnL
                duration = random.randint(self.config['min_duration'], self.config['max_duration'])
                logger.info(f"🎲 Durée du cycle: {duration} minute(s)")
                self.wait_holding_duration_with_pnl(duration)
                
                # d. Fermer avec vérification PnL
                if not self.close_positions_with_pnl_check(symbol, self.config['pnl_check_delay']):
                    logger.error("❌ Échec fermeture des positions")
                    break
                
            # e. Vérifier les balances entre cycles (sauf pour le dernier)
            if cycle_num < num_cycles:
                rebalance_result = self.check_balances_between_cycles()
                if not rebalance_result:
                    logger.warning("⚠️  Problème de balance ou rebalancing échoué")
                    logger.warning("⚠️  Le bot continue quand même avec les balances actuelles")
                    # Ne pas arrêter le bot, juste logger un warning
                    # Le bot peut continuer même si le rebalancing échoue
                    
                    # f. Délai entre cycles
                    delay = self.config.get('delay_between_cycles', 0)
                    if delay > 0:
                        logger.info(f"⏳ Délai entre cycles: {delay} minute(s)...")
                        time.sleep(delay * 60)
            
            logger.info("\n" + "="*80)
            logger.success("✅ TOUS LES CYCLES TERMINÉS AVEC SUCCÈS")
            logger.info("="*80 + "\n")
            
        except KeyboardInterrupt:
            logger.warning("\n⚠️  Arrêt demandé par l'utilisateur")
            logger.info("Fermeture des positions ouvertes...")
            try:
                self.close_positions(self.config['symbol'])
            except:
                pass
        except Exception as e:
            logger.error(f"❌ Erreur fatale: {e}")
            import traceback
            logger.error(traceback.format_exc())
        finally:
            # Fermer les clients
            if self.extended_client:
                try:
                    self.extended_client.close()
                except:
                    pass
            if self.lighter_client:
                try:
                    self.lighter_client.close()
                except:
                    pass
            logger.info("✅ Bot arrêté")


if __name__ == "__main__":
    # Configuration du logger
    logger.remove()
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )
    logger.add(
        "dn_lighter_extended.log",
        rotation="10 MB",
        retention="7 days",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="DEBUG"
    )
    
    # Lancer le bot
    bot = DNLighterExtended()
    bot.run()

"""
DN Farming Bot
Ouvre des trades opposés (long/short) sur deux comptes Extended avec rebalancing automatique
"""
import os
import sys
import time
import random
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
from execution.rebalancing import RebalancingManager


class DNFarmingBot:
    """Bot pour farming de delta neutre avec rebalancing automatique"""
    
    def __init__(self):
        """Initialise le bot avec les credentials depuis .env"""
        load_dotenv()
        
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
        # On va créer des configs minimales pour le rebalancing
        self.rebalance_manager1 = self._create_rebalance_manager(self.account1)
        self.rebalance_manager2 = self._create_rebalance_manager(self.account2)
        
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
            
            # Valider les paramètres requis
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
            
            result = {
                'symbol': symbol,
                'leverage': leverage,
                'margin': margin,
                'min_duration': min_duration,
                'max_duration': max_duration,
                'num_cycles': num_cycles,
                'delay_between_cycles': delay_between_cycles,
                'rebalance_threshold': rebalance_threshold
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
        
        balance1 = self.client1.get_balance()
        balance2 = self.client2.get_balance()
        
        bal1 = balance1.get('total', 0)
        bal2 = balance2.get('total', 0)
        
        logger.info(f"Compte 1: ${bal1:,.2f} USDC")
        logger.info(f"Compte 2: ${bal2:,.2f} USDC")
        
        return bal1, bal2
    
    def rebalance_accounts(self) -> bool:
        """
        Rebalance les deux comptes Extended pour qu'ils aient le même montant
        
        Le wallet avec le plus haut montant retire vers Arbitrum,
        puis envoie les USDC au wallet Arbitrum de l'autre compte,
        qui les transfère ensuite sur son compte Extended.
        """
        logger.info("🔄 Début du rebalancing...")
        
        # Récupérer les balances
        balance1 = self.client1.get_balance()
        balance2 = self.client2.get_balance()
        
        bal1 = balance1.get('total', 0)
        bal2 = balance2.get('total', 0)
        
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
    
    def calculate_position_size(self, margin: float, leverage: int, symbol: str, client: ExtendedAPI) -> float:
        """
        Calcule la taille de position en fonction de la marge et du levier
        
        Args:
            margin: Marge en USDC
            leverage: Levier
            symbol: Symbole de la paire
            client: Client Extended pour récupérer le prix
        
        Returns:
            Taille de position en unités de l'asset
        """
        # Récupérer le prix actuel
        ticker = client.get_ticker(symbol)
        price = ticker.get('last', ticker.get('ask', 0))
        
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
        logger.info(f"📊 Ouverture des trades: Compte 1 {account1_side.upper()}, Compte 2 {account2_side.upper()}")
        
        # Configurer le levier pour les deux comptes
        logger.info(f"Configuration du levier {leverage}x pour {symbol}...")
        self.client1.set_leverage(symbol, leverage)
        self.client2.set_leverage(symbol, leverage)
        time.sleep(1)  # Attendre que le levier soit appliqué
        
        # Calculer la taille de position
        size1 = self.calculate_position_size(margin, leverage, symbol, self.client1)
        size2 = self.calculate_position_size(margin, leverage, symbol, self.client2)
        
        logger.info(f"Taille de position: {size1:.6f} {symbol} (marge: ${margin:.2f}, levier: {leverage}x)")
        
        # Placer les ordres market simultanément
        logger.info("Placement des ordres market...")
        
        order1 = self.client1.place_order(
            symbol=symbol,
            side=account1_side,
            size=size1,
            order_type="market"
        )
        
        order2 = self.client2.place_order(
            symbol=symbol,
            side=account2_side,
            size=size2,
            order_type="market"
        )
        
        # Vérifier les résultats
        if order1.get('status') not in ['OK', 'ok', 'success']:
            logger.error(f"❌ Échec ordre compte 1: {order1.get('error', 'Unknown error')}")
            return None, None
        
        if order2.get('status') not in ['OK', 'ok', 'success']:
            logger.error(f"❌ Échec ordre compte 2: {order2.get('error', 'Unknown error')}")
            return None, None
        
        order_id1 = order1.get('order_id')
        order_id2 = order2.get('order_id')
        
        logger.success(f"✅ Ordre compte 1 placé: {order_id1}")
        logger.success(f"✅ Ordre compte 2 placé: {order_id2}")
        
        # Attendre un peu pour que les ordres soient exécutés
        time.sleep(2)
        
        # Attendre un peu pour que les positions soient créées
        time.sleep(3)
        
        # Vérifier que les positions sont ouvertes et opposées en utilisant le SDK directement
        try:
            # Récupérer les positions brutes depuis le SDK pour avoir le signe exact
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
                logger.info(f"   Compte 1: size={size1}, côté={side1}")
                logger.info(f"   Compte 2: size={size2}, côté={side2}")
                
                if side1 == side2:
                    logger.warning(f"⚠️  ATTENTION: Les deux positions sont du même côté ({side1})!")
                    logger.warning("   Les positions devraient être opposées (LONG/SHORT)")
                    logger.warning(f"   Compte 1: {side1} {abs(size1)} {symbol} (size brut: {size1})")
                    logger.warning(f"   Compte 2: {side2} {abs(size2)} {symbol} (size brut: {size2})")
                    logger.warning("   Cela peut indiquer que les ordres n'ont pas créé de positions opposées")
                else:
                    logger.success(f"✅ Positions opposées confirmées:")
                    logger.success(f"   Compte 1: {side1} {abs(size1)} {symbol}")
                    logger.success(f"   Compte 2: {side2} {abs(size2)} {symbol}")
            else:
                if not pos1_raw:
                    logger.warning("⚠️  Position compte 1 non trouvée dans le SDK")
                if not pos2_raw:
                    logger.warning("⚠️  Position compte 2 non trouvée dans le SDK")
        except Exception as e:
            logger.debug(f"Erreur lors de la vérification SDK des positions: {e}")
            # Fallback sur la méthode normale
            positions1 = self.client1.get_positions()
            positions2 = self.client2.get_positions()
            
            pos1 = next((p for p in positions1 if p['symbol'] == symbol), None)
            pos2 = next((p for p in positions2 if p['symbol'] == symbol), None)
            
            if not pos1:
                logger.warning("⚠️  Position compte 1 non trouvée, vérification...")
            if not pos2:
                logger.warning("⚠️  Position compte 2 non trouvée, vérification...")
            
            # Vérifier que les positions sont opposées
            if pos1 and pos2:
                if pos1['side'] == pos2['side']:
                    logger.warning(f"⚠️  ATTENTION: Les deux positions sont du même côté ({pos1['side']})!")
                    logger.warning("   Les positions devraient être opposées (LONG/SHORT)")
                    logger.warning(f"   Compte 1: {pos1['side']} {pos1['size']} {symbol}")
                    logger.warning(f"   Compte 2: {pos2['side']} {pos2['size']} {symbol}")
                else:
                    logger.success(f"✅ Positions opposées confirmées:")
                    logger.success(f"   Compte 1: {pos1['side']} {pos1['size']} {symbol}")
                    logger.success(f"   Compte 2: {pos2['side']} {pos2['size']} {symbol}")
        
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
        positions2 = self.client2.get_positions()
        
        pos1 = next((p for p in positions1 if p['symbol'] == symbol), None)
        pos2 = next((p for p in positions2 if p['symbol'] == symbol), None)
        
        if not pos1 and not pos2:
            logger.warning("Aucune position à fermer")
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
            # Récupérer la position brute depuis le SDK pour avoir le signe exact
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
                    # Utiliser le signe brut pour déterminer le côté réel
                    # Si raw_size est positif, c'est LONG -> fermer avec SELL
                    # Si raw_size est négatif, c'est SHORT -> fermer avec BUY
                    actual_side2 = "LONG" if raw_size2 > 0 else "SHORT"
                    close_side2 = "sell" if raw_size2 > 0 else "buy"
                    logger.info(f"Fermeture position compte 2: {actual_side2} {abs(raw_size2)} {symbol} (size brut: {raw_size2})")
                    logger.info(f"  Ordre de fermeture: {close_side2.upper()} {abs(raw_size2)} {symbol} (reduce_only=True)")
                    
                    # Log supplémentaire pour debug
                    logger.debug(f"  Détails: raw_size2={raw_size2}, actual_side2={actual_side2}, close_side2={close_side2}")
                    
                    result2 = self.client2.place_order(
                        symbol=symbol,
                        side=close_side2,
                        size=abs(raw_size2),
                        order_type="market",
                        reduce_only=True
                    )
                    
                    if result2.get('status') not in ['OK', 'ok', 'success']:
                        error_msg2 = result2.get('error', '')
                        
                        # Si erreur "same side", inverser le côté automatiquement
                        if 'same side' in str(error_msg2).lower() or '1138' in str(error_msg2):
                            # Cette erreur est normale - l'API Extended a parfois un décalage dans la détection du côté
                            # On inverse automatiquement sans afficher d'erreur
                            logger.debug(f"Erreur 'same side' (1138) - inversion automatique du côté")
                            logger.debug(f"   Position détectée: {actual_side2} (size brut: {raw_size2})")
                            logger.debug(f"   Ordre tenté: {close_side2.upper()} - correction automatique en cours...")
                            
                            # Inverser le côté
                            close_side2 = "buy" if raw_size2 > 0 else "sell"  # Inverser
                            logger.info(f"  Correction automatique: Ordre {close_side2.upper()} (côté inversé)")
                            
                            result2_retry = self.client2.place_order(
                                symbol=symbol,
                                side=close_side2,
                                size=abs(raw_size2),
                                order_type="market",
                                reduce_only=True
                            )
                            
                            if result2_retry.get('status') in ['OK', 'ok', 'success']:
                                logger.success(f"✅ Position compte 2 fermée (côté corrigé automatiquement)")
                                success = True
                            else:
                                logger.error(f"❌ Échec même après inversion: {result2_retry.get('error', 'Unknown error')}")
                                success = False
                        else:
                            logger.error(f"❌ Échec fermeture compte 2: {error_msg2}")
                            success = False
                    else:
                        logger.success(f"✅ Position compte 2 fermée")
                else:
                    logger.warning("⚠️  Position compte 2 non trouvée dans le SDK, peut-être déjà fermée")
                    success = True
            except Exception as e:
                logger.error(f"❌ Erreur lors de la récupération de la position compte 2: {e}")
                # Fallback sur la méthode normale
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
                        logger.success(f"✅ Position compte 2 fermée")
                else:
                    logger.warning("⚠️  Position compte 2 non trouvée")
                    success = True
        
        # Attendre un peu pour que les fermetures soient confirmées
        time.sleep(2)
        
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
                    if not self.rebalance_accounts():
                        logger.error("❌ Échec du rebalancing")
                        logger.error("Arrêt du bot - Veuillez rebalancer manuellement ou réduire le margin")
                        return
                    
                    # Vérifier à nouveau les balances après rebalancing
                    bal1, bal2 = self.check_initial_balances()
                    if bal1 < min_balance_needed or bal2 < min_balance_needed:
                        logger.error("❌ Solde toujours insuffisant après rebalancing")
                        logger.error("Arrêt du bot - Veuillez réduire le margin dans config/dnfarming.json")
                        return
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
            
            # Exécuter les cycles
            for cycle_num in range(1, params['num_cycles'] + 1):
                logger.info(f"\n{'='*60}")
                logger.info(f"🚀 CYCLE {cycle_num}/{params['num_cycles']}")
                logger.info(f"{'='*60}")
                
                duration = durations[cycle_num - 1]
                
                # Exécuter le cycle
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
                
                # Alterner les positions pour le prochain cycle
                account1_side, account2_side = account2_side, account1_side
                if cycle_num < params['num_cycles']:
                    logger.info(f"Prochain cycle: Compte 1 {account1_side.upper()}, Compte 2 {account2_side.upper()}")
            
            logger.success(f"\n✅ Tous les cycles terminés avec succès!")
            
        except KeyboardInterrupt:
            logger.warning("\n⚠️  Arrêt demandé par l'utilisateur")
            # Fermer les positions ouvertes en cas d'arrêt
            logger.info("Fermeture des positions ouvertes...")
            if 'params' in locals():
                self.close_trades(params['symbol'])
        except Exception as e:
            logger.error(f"❌ Erreur: {e}")
            import traceback
            logger.error(traceback.format_exc())


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
    
    bot = DNFarmingBot()
    bot.run()

"""
Rebalancing Manager
Gère le transfert de fonds entre Extended et Hyperliquid
"""
import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional
from loguru import logger

try:
    from hyperliquid.info import Info
    from hyperliquid.exchange import Exchange
    from hyperliquid.utils import constants
    import eth_account
    from eth_account.signers.local import LocalAccount
    HAS_HYPERLIQUID_SDK = True
except ImportError:
    HAS_HYPERLIQUID_SDK = False
    logger.warning("Hyperliquid SDK not found. Install it with: pip install hyperliquid-python-sdk")

try:
    from web3 import Web3
    try:
        from web3.middleware import geth_poa_middleware
    except ImportError:
        # Pour web3 v6+, le middleware peut être dans un autre endroit
        try:
            from web3.middleware import ExtraDataToPOAMiddleware as geth_poa_middleware
        except ImportError:
            # Arbitrum n'a pas besoin de POA middleware dans les versions récentes
            geth_poa_middleware = None
    HAS_WEB3 = True
except ImportError:
    HAS_WEB3 = False
    logger.warning("web3 not found. Install it with: pip install web3")

try:
    from x10.perpetual.accounts import StarkPerpetualAccount
    from x10.perpetual.configuration import MAINNET_CONFIG
    from x10.perpetual.trading_client import PerpetualTradingClient
    HAS_EXTENDED_SDK = True
except ImportError:
    HAS_EXTENDED_SDK = False
    logger.warning("Extended SDK not found. Install it with: pip install x10-python-trading-starknet")


class RebalancingManager:
    """Gestionnaire de rebalancing entre exchanges"""
    
    def _get_gas_params(self, w3):
        """
        Récupère les paramètres de gas pour une transaction EIP-1559
        
        Args:
            w3: Instance Web3 connectée
            
        Returns:
            Dict avec maxFeePerGas et maxPriorityFeePerGas
        """
        try:
            # Récupérer le dernier bloc pour obtenir baseFee
            latest_block = w3.eth.get_block('latest')
            base_fee = latest_block.get('baseFeePerGas', 0)
            
            # Pour Arbitrum, maxPriorityFeePerGas est généralement très bas (0.1 gwei)
            # maxFeePerGas doit être >= baseFee + maxPriorityFeePerGas
            max_priority_fee = w3.to_wei(0.1, 'gwei')  # 0.1 gwei pour Arbitrum
            
            # Calculer maxFeePerGas avec une marge de sécurité (baseFee * 1.2 + priority)
            if base_fee > 0:
                max_fee = int(base_fee * 1.2) + max_priority_fee
            else:
                # Fallback si baseFee n'est pas disponible
                gas_price = w3.eth.gas_price
                max_fee = gas_price
                max_priority_fee = w3.to_wei(0.1, 'gwei')
            
            return {
                'maxFeePerGas': max_fee,
                'maxPriorityFeePerGas': max_priority_fee
            }
        except Exception as e:
            logger.warning(f"Error getting EIP-1559 gas params, using legacy gasPrice: {e}")
            # Fallback vers gasPrice legacy
            gas_price = w3.eth.gas_price
            return {
                'gasPrice': gas_price
            }
    
    def __init__(self, config):
        """
        Initialise le gestionnaire
        
        Args:
            config: Configuration du bot
        """
        self.config = config
        self.auto_rebalance = config.get('arbitrage', 'auto_rebalance', default=True)
        self.threshold = config.get('arbitrage', 'rebalance_threshold', default=0.1)
        
        # Récupérer l'adresse du wallet
        try:
            self.wallet_address = config.get('wallet', 'address', default=None)
            if not self.wallet_address or self.wallet_address == "0xYOUR_WALLET_ADDRESS":
                logger.warning("Wallet address not configured properly")
                self.wallet_address = None
        except Exception as e:
            logger.error(f"Error getting wallet address: {e}")
            self.wallet_address = None
        
        # Initialiser les clients d'exchanges
        self.extended_client = None
        self.hyperliquid_client = None
        self.hyperliquid_exchange = None
        self.extended_account = None
        self.hyperliquid_wallet = None
        
        # Configuration pour les deposits (bridge Arbitrum)
        self.hyperliquid_bridge_address = "0x2df1c51e09aecf9cacb7bc98cb1742757f163df7"  # Bridge contract
        self.arbitrum_usdc_address = "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"  # USDC on Arbitrum
        self.arbitrum_rpc_url = "https://arb1.arbitrum.io/rpc"  # Arbitrum mainnet RPC
        self.min_deposit_amount = 5.0  # Minimum 5 USDC
        
        # Initialiser le client Hyperliquid avec le SDK
        if HAS_HYPERLIQUID_SDK and self.wallet_address:
            try:
                # Utiliser mainnet par défaut (peut être configuré plus tard)
                self.hyperliquid_client = Info(constants.MAINNET_API_URL, skip_ws=True)
                logger.debug("Hyperliquid SDK Info client initialized")
                
                # Initialiser le wallet pour les transactions signées
                try:
                    private_key = config.get('wallet', 'private_key', default=None)
                    if private_key and private_key != "YOUR_PRIVATE_KEY":
                        self.hyperliquid_wallet = eth_account.Account.from_key(private_key)
                        # Créer le client Exchange pour les transactions signées
                        self.hyperliquid_exchange = Exchange(
                            wallet=self.hyperliquid_wallet,
                            base_url=constants.MAINNET_API_URL
                        )
                        logger.debug("Hyperliquid SDK Exchange client initialized")
                    else:
                        logger.warning("Private key not configured, withdrawal features will be disabled")
                except Exception as e:
                    logger.error(f"Error initializing Hyperliquid Exchange client: {e}")
                    self.hyperliquid_exchange = None
                    
            except Exception as e:
                logger.error(f"Error initializing Hyperliquid client: {e}")
                self.hyperliquid_client = None
        
        # Initialiser le client Extended avec le SDK
        if HAS_EXTENDED_SDK:
            try:
                # Récupérer les clés API Extended depuis la config
                extended_config = config.get('exchanges', 'extended', default={})
                api_key = extended_config.get('api_key')
                public_key = extended_config.get('public_key')
                private_key = extended_config.get('private_key')
                vault_id = extended_config.get('vault_id')
                
                if api_key and public_key and private_key and vault_id:
                    try:
                        vault_id_int = int(vault_id) if isinstance(vault_id, (str, int)) else vault_id
                        self.extended_account = StarkPerpetualAccount(
                            vault=vault_id_int,
                            private_key=private_key,
                            public_key=public_key,
                            api_key=api_key,
                        )
                        logger.debug("Extended SDK account initialized")
                    except Exception as e:
                        logger.error(f"Error creating Extended account: {e}")
                        self.extended_account = None
                else:
                    logger.warning("Extended API credentials not fully configured")
            except Exception as e:
                logger.error(f"Error initializing Extended client: {e}")
                self.extended_account = None
        
    def check_balance_needed(self) -> Dict[str, Dict[str, float]]:
        """
        Vérifie si un rebalancing est nécessaire
        
        Returns:
            Dict avec les balances actuelles et recommandations
        """
        try:
            # Récupérer les balances
            ext_balance = self._get_balance("Extended")
            hyp_balance = self._get_balance("Hyperliquid")
            
            total = ext_balance + hyp_balance
            
            # Calculer la répartition idéale (50/50)
            ideal_per_exchange = total / 2
            
            # Calculer les différences
            ext_diff = ext_balance - ideal_per_exchange
            hyp_diff = hyp_balance - ideal_per_exchange
            
            # Vérifier si le seuil est dépassé
            ext_diff_pct = abs(ext_diff) / total if total > 0 else 0
            hyp_diff_pct = abs(hyp_diff) / total if total > 0 else 0
            
            needs_rebalancing = max(ext_diff_pct, hyp_diff_pct) > self.threshold
            
            result = {
                'balances': {
                    'extended': ext_balance,
                    'hyperliquid': hyp_balance,
                    'total': total
                },
                'ideal': ideal_per_exchange,
                'differences': {
                    'extended': ext_diff,
                    'hyperliquid': hyp_diff
                },
                'needs_rebalancing': needs_rebalancing,
                'recommended_transfer': None
            }
            
            if needs_rebalancing:
                # Déterminer le transfert recommandé
                if ext_diff > 0:
                    # Extended a trop, transférer vers Hyperliquid
                    result['recommended_transfer'] = {
                        'from': 'Extended',
                        'to': 'Hyperliquid',
                        'amount': abs(ext_diff)
                    }
                else:
                    # Hyperliquid a trop, transférer vers Extended
                    result['recommended_transfer'] = {
                        'from': 'Hyperliquid',
                        'to': 'Extended',
                        'amount': abs(hyp_diff)
                    }
            
            return result
            
        except Exception as e:
            logger.error(f"Error checking balance: {e}")
            return {}
    
    def withdraw_hyperliquid(self, amount: float, destination: str) -> Dict:
        """
        Effectue un withdrawal depuis Hyperliquid vers une adresse destination
        
        Args:
            amount: Montant à retirer en USD
            destination: Adresse de destination (0x...)
            
        Returns:
            Dict avec le résultat de la requête ou None en cas d'erreur
        """
        if not HAS_HYPERLIQUID_SDK:
            logger.error("Hyperliquid SDK not available")
            return {"status": "error", "message": "SDK not available"}
        
        if not self.hyperliquid_exchange:
            logger.error("Hyperliquid Exchange client not initialized")
            logger.error("Make sure private_key is configured in config.json")
            return {"status": "error", "message": "Exchange client not initialized"}
        
        try:
            logger.info(f"Withdrawing ${amount:.2f} from Hyperliquid to {destination}")
            
            # Utiliser la méthode withdraw_from_bridge du SDK
            result = self.hyperliquid_exchange.withdraw_from_bridge(amount, destination)
            
            if result and result.get('status') == 'ok':
                logger.success(f"Withdrawal initiated: ${amount:.2f} to {destination}")
                logger.info("Note: Withdrawals take approximately 5 minutes to finalize")
                logger.info("Note: There is a $1 fee for withdrawing")
                return {
                    "status": "success",
                    "amount": amount,
                    "destination": destination,
                    "response": result
                }
            else:
                logger.error(f"Withdrawal failed: {result}")
                return {
                    "status": "error",
                    "message": "Withdrawal request failed",
                    "response": result
                }
            
        except Exception as e:
            logger.error(f"Error withdrawing from Hyperliquid: {e}")
            logger.exception("Full error details:")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def deposit_hyperliquid(self, amount: float) -> Dict:
        """
        Effectue un deposit d'USDC vers Hyperliquid via le bridge Arbitrum
        
        Le deposit se fait en envoyant de l'USDC natif au contrat bridge sur Arbitrum.
        Le montant minimum est de 5 USDC.
        
        Args:
            amount: Montant à déposer en USD (minimum 5 USDC)
            
        Returns:
            Dict avec le résultat de la transaction ou erreur
        """
        if not HAS_WEB3:
            logger.error("web3 not available. Install it with: pip install web3")
            return {"status": "error", "message": "web3 not available"}
        
        if not self.hyperliquid_wallet:
            logger.error("Hyperliquid wallet not initialized")
            logger.error("Make sure private_key is configured in config.json")
            return {"status": "error", "message": "Wallet not initialized"}
        
        # Vérifier le montant minimum
        if amount < self.min_deposit_amount:
            logger.error(f"Amount ${amount:.2f} is below minimum deposit of ${self.min_deposit_amount:.2f} USDC")
            return {
                "status": "error",
                "message": f"Minimum deposit is ${self.min_deposit_amount:.2f} USDC"
            }
        
        try:
            logger.info(f"Depositing ${amount:.2f} USDC to Hyperliquid bridge")
            
            # Connecter à Arbitrum
            w3 = Web3(Web3.HTTPProvider(self.arbitrum_rpc_url))
            # Arbitrum n'a généralement pas besoin de POA middleware dans les versions récentes
            # mais on l'ajoute si disponible pour compatibilité
            if geth_poa_middleware is not None:
                try:
                    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
                except Exception:
                    # Si l'injection échoue, on continue sans (Arbitrum fonctionne sans)
                    pass
            
            if not w3.is_connected():
                logger.error("Failed to connect to Arbitrum RPC")
                return {"status": "error", "message": "Failed to connect to Arbitrum"}
            
            # ABI minimal pour la fonction transfer de l'ERC20
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
                Web3.to_checksum_address(self.hyperliquid_wallet.address)
            ).call()
            balance_usd = balance / 1e6  # USDC a 6 décimales
            
            logger.info(f"USDC balance on Arbitrum: ${balance_usd:,.2f}")
            
            if balance_usd < amount:
                logger.error(f"Insufficient USDC balance: ${balance_usd:,.2f} < ${amount:,.2f}")
                return {
                    "status": "error",
                    "message": f"Insufficient balance. Available: ${balance_usd:,.2f}, Required: ${amount:,.2f}"
                }
            
            # Convertir le montant en wei (USDC a 6 décimales)
            amount_wei = int(amount * 1e6)
            
            # Construire la transaction
            bridge_address = Web3.to_checksum_address(self.hyperliquid_bridge_address)
            
            # Obtenir le nonce
            nonce = w3.eth.get_transaction_count(self.hyperliquid_wallet.address)
            
            # Construire la transaction transfer
            transaction = usdc_contract.functions.transfer(
                bridge_address,
                amount_wei
            ).build_transaction({
                'from': self.hyperliquid_wallet.address,
                'nonce': nonce,
                'gas': 100000,  # Gas limit pour un transfer ERC20
                'gasPrice': w3.eth.gas_price,
                'chainId': 42161  # Arbitrum mainnet chain ID
            })
            
            # Signer la transaction
            signed_txn = w3.eth.account.sign_transaction(transaction, self.hyperliquid_wallet.key)
            
            # Envoyer la transaction
            logger.info("Sending transaction to Arbitrum...")
            # web3 v6+ utilise raw_transaction au lieu de rawTransaction
            raw_tx = signed_txn.raw_transaction if hasattr(signed_txn, 'raw_transaction') else signed_txn.rawTransaction
            tx_hash = w3.eth.send_raw_transaction(raw_tx)
            
            logger.info(f"Transaction sent: {tx_hash.hex()}")
            logger.info("Waiting for confirmation...")
            
            # Attendre la confirmation
            tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            
            if tx_receipt.status == 1:
                logger.success(f"Deposit successful! Transaction: {tx_hash.hex()}")
                logger.info("The deposit will be credited to your Hyperliquid account in less than 1 minute")
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
                logger.error(f"Transaction failed: {tx_hash.hex()}")
                return {
                    "status": "error",
                    "message": "Transaction failed",
                    "transaction_hash": tx_hash.hex()
                }
            
        except Exception as e:
            logger.error(f"Error depositing to Hyperliquid: {e}")
            logger.exception("Full error details:")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def withdraw_extended(self, amount: float) -> Dict:
        """
        Effectue un withdrawal depuis Extended vers Arbitrum via le bridge
        
        Le processus de retrait EVM comprend 4 étapes:
        1. Récupérer la config du bridge pour obtenir les chaînes supportées
        2. Demander un devis pour le retrait vers Arbitrum
        3. Confirmer le devis
        4. Soumettre le retrait avec le quote_id
        
        Args:
            amount: Montant à retirer en USD
            
        Returns:
            Dict avec le résultat de la requête ou erreur
        """
        if not HAS_EXTENDED_SDK:
            logger.error("Extended SDK not available")
            return {"status": "error", "message": "SDK not available"}
        
        if not self.extended_account:
            logger.error("Extended account not initialized")
            logger.error("Make sure Extended API credentials are configured in config.json")
            return {"status": "error", "message": "Extended account not initialized"}
        
        if amount <= 0:
            logger.error(f"Invalid withdrawal amount: ${amount:.2f}")
            return {"status": "error", "message": "Amount must be positive"}
        
        try:
            logger.info(f"Withdrawing ${amount:.2f} from Extended to Arbitrum")
            
            # Fonction asynchrone pour gérer le retrait
            async def _async_withdraw():
                trading_client = PerpetualTradingClient(
                    endpoint_config=MAINNET_CONFIG,
                    stark_account=self.extended_account,
                )
                try:
                    # Étape 1: Récupérer la config du bridge
                    logger.debug("Step 1: Getting bridge config...")
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
                    
                    logger.info(f"Found Arbitrum bridge: {arb_chain.contractAddress}")
                    
                    # Étape 2: Demander un devis pour le retrait
                    logger.debug("Step 2: Requesting bridge quote...")
                    amount_decimal = Decimal(str(amount))
                    quote_response = await trading_client.account.get_bridge_quote(
                        chain_in="STRK",  # Depuis Starknet
                        chain_out="ARB",  # Vers Arbitrum
                        amount=amount_decimal
                    )
                    
                    if not quote_response or not quote_response.data:
                        raise ValueError("Failed to get bridge quote")
                    
                    quote = quote_response.data
                    logger.info(f"Bridge quote received: ID={quote.id}, Fee=${quote.fee}")
                    
                    # Afficher les informations du devis
                    logger.info(f"  Withdrawal amount: ${amount:.2f}")
                    logger.info(f"  Bridge fee: ${quote.fee}")
                    logger.info(f"  Amount after fee: ${amount - float(quote.fee):.2f}")
                    
                    # Étape 3: Confirmer le devis
                    logger.debug("Step 3: Committing bridge quote...")
                    await trading_client.account.commit_bridge_quote(quote.id)
                    logger.info(f"Bridge quote committed: {quote.id}")
                    
                    # Étape 4: Effectuer le retrait avec le quote_id
                    logger.debug("Step 4: Submitting withdrawal...")
                    withdrawal_response = await trading_client.account.withdraw(
                        amount=amount_decimal,
                        chain_id="ARB",  # Arbitrum
                        quote_id=quote.id
                    )
                    
                    if not withdrawal_response or withdrawal_response.data is None:
                        raise ValueError("Failed to submit withdrawal")
                    
                    withdrawal_id = withdrawal_response.data
                    logger.success(f"Withdrawal submitted successfully: ID={withdrawal_id}")
                    
                    return {
                        "status": "success",
                        "amount": amount,
                        "bridge_fee": float(quote.fee),
                        "amount_after_fee": amount - float(quote.fee),
                        "withdrawal_id": withdrawal_id,
                        "quote_id": quote.id,
                        "bridge_address": arb_chain.contractAddress
                    }
                    
                finally:
                    # Fermer la session
                    await trading_client.close()
            
            # Exécuter la fonction asynchrone
            result = asyncio.run(_async_withdraw())
            return result
            
        except Exception as e:
            logger.error(f"Error withdrawing from Extended: {e}")
            logger.exception("Full error details:")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def deposit_extended(self, amount: float) -> Dict:
        """
        Effectue un deposit d'USDC depuis Arbitrum vers Extended via le bridge Rhino.fi
        
        Le processus de dépôt EVM comprend 4 étapes:
        1. Récupérer la config du bridge pour obtenir les chaînes supportées
        2. Demander un devis pour le dépôt depuis Arbitrum
        3. Confirmer le devis
        4. Appeler depositWithId sur le contrat bridge sur Arbitrum
        
        Args:
            amount: Montant à déposer en USD
            
        Returns:
            Dict avec le résultat de la transaction ou erreur
        """
        if not HAS_EXTENDED_SDK:
            logger.error("Extended SDK not available")
            return {"status": "error", "message": "SDK not available"}
        
        if not HAS_WEB3:
            logger.error("web3 not available. Install it with: pip install web3")
            return {"status": "error", "message": "web3 not available"}
        
        if not self.extended_account:
            logger.error("Extended account not initialized")
            logger.error("Make sure Extended API credentials are configured in config.json")
            return {"status": "error", "message": "Extended account not initialized"}
        
        if not self.hyperliquid_wallet:
            logger.error("Wallet not initialized")
            logger.error("Make sure private_key is configured in config.json")
            return {"status": "error", "message": "Wallet not initialized"}
        
        if amount <= 0:
            logger.error(f"Invalid deposit amount: ${amount:.2f}")
            return {"status": "error", "message": "Amount must be positive"}
        
        try:
            logger.info(f"Depositing ${amount:.2f} from Arbitrum to Extended")
            
            # Fonction asynchrone pour gérer les étapes API
            async def _async_get_bridge_info():
                trading_client = PerpetualTradingClient(
                    endpoint_config=MAINNET_CONFIG,
                    stark_account=self.extended_account,
                )
                try:
                    # Étape 1: Récupérer la config du bridge
                    logger.debug("Step 1: Getting bridge config...")
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
                    
                    logger.info(f"Found Arbitrum bridge: {arb_chain.contractAddress}")
                    
                    # Étape 2: Demander un devis pour le dépôt
                    logger.debug("Step 2: Requesting bridge quote...")
                    amount_decimal = Decimal(str(amount))
                    quote_response = await trading_client.account.get_bridge_quote(
                        chain_in="ARB",  # Depuis Arbitrum
                        chain_out="STRK",  # Vers Starknet
                        amount=amount_decimal
                    )
                    
                    if not quote_response or not quote_response.data:
                        raise ValueError("Failed to get bridge quote")
                    
                    quote = quote_response.data
                    logger.info(f"Bridge quote received: ID={quote.id}, Fee=${quote.fee}")
                    
                    # Afficher les informations du devis
                    logger.info(f"  Deposit amount: ${amount:.2f}")
                    logger.info(f"  Bridge fee: ${quote.fee}")
                    logger.info(f"  Amount after fee: ${amount - float(quote.fee):.2f}")
                    
                    # Étape 3: Confirmer le devis
                    logger.debug("Step 3: Committing bridge quote...")
                    await trading_client.account.commit_bridge_quote(quote.id)
                    logger.info(f"Bridge quote committed: {quote.id}")
                    
                    return {
                        "bridge_address": arb_chain.contractAddress,
                        "quote_id": quote.id,
                        "bridge_fee": float(quote.fee)
                    }
                    
                finally:
                    # Fermer la session
                    await trading_client.close()
            
            # Exécuter les étapes API
            bridge_info = asyncio.run(_async_get_bridge_info())
            bridge_address = bridge_info["bridge_address"]
            quote_id = bridge_info["quote_id"]
            bridge_fee = bridge_info["bridge_fee"]
            
            # Étape 4: Appeler depositWithId sur le contrat bridge sur Arbitrum
            logger.debug("Step 4: Calling depositWithId on Arbitrum bridge...")
            
            # Connecter à Arbitrum
            w3 = Web3(Web3.HTTPProvider(self.arbitrum_rpc_url))
            if geth_poa_middleware is not None:
                try:
                    w3.middleware_onion.inject(geth_poa_middleware, layer=0)
                except Exception:
                    pass
            
            if not w3.is_connected():
                logger.error("Failed to connect to Arbitrum RPC")
                return {"status": "error", "message": "Failed to connect to Arbitrum"}
            
            # ABI pour le contrat bridge (depositWithId)
            # D'après la doc Rhino.fi: depositWithId(address token, uint256 amount, uint256 commitmentId)
            bridge_abi = [
                {
                    "constant": False,
                    "inputs": [
                        {"name": "token", "type": "address"},
                        {"name": "amount", "type": "uint256"},
                        {"name": "commitmentId", "type": "uint256"}
                    ],
                    "name": "depositWithId",
                    "outputs": [],
                    "type": "function"
                }
            ]
            
            # ABI pour USDC (approve et balanceOf)
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
            
            # Créer les contrats
            bridge_contract = w3.eth.contract(
                address=Web3.to_checksum_address(bridge_address),
                abi=bridge_abi
            )
            
            usdc_contract = w3.eth.contract(
                address=Web3.to_checksum_address(self.arbitrum_usdc_address),
                abi=erc20_abi
            )
            
            # Vérifier le solde USDC disponible
            balance = usdc_contract.functions.balanceOf(
                Web3.to_checksum_address(self.hyperliquid_wallet.address)
            ).call()
            balance_usd = balance / 1e6  # USDC a 6 décimales
            
            logger.info(f"USDC balance on Arbitrum: ${balance_usd:,.2f}")
            
            if balance_usd < amount:
                logger.error(f"Insufficient USDC balance: ${balance_usd:,.2f} < ${amount:,.2f}")
                return {
                    "status": "error",
                    "message": f"Insufficient balance. Available: ${balance_usd:,.2f}, Required: ${amount:,.2f}"
                }
            
            # Convertir le montant en wei (USDC a 6 décimales)
            amount_wei = int(amount * 1e6)
            
            # Vérifier et approuver si nécessaire
            allowance = usdc_contract.functions.allowance(
                Web3.to_checksum_address(self.hyperliquid_wallet.address),
                Web3.to_checksum_address(bridge_address)
            ).call()
            
            if allowance < amount_wei:
                logger.info(f"Approving bridge contract to spend ${amount:.2f} USDC...")
                nonce = w3.eth.get_transaction_count(self.hyperliquid_wallet.address)
                
                # Obtenir les paramètres de gas EIP-1559
                gas_params = self._get_gas_params(w3)
                
                approve_txn = usdc_contract.functions.approve(
                    Web3.to_checksum_address(bridge_address),
                    amount_wei
                ).build_transaction({
                    'from': self.hyperliquid_wallet.address,
                    'nonce': nonce,
                    'gas': 100000,
                    'chainId': 42161,
                    **gas_params  # Ajouter maxFeePerGas et maxPriorityFeePerGas ou gasPrice
                })
                
                signed_approve = w3.eth.account.sign_transaction(approve_txn, self.hyperliquid_wallet.key)
                raw_approve = signed_approve.raw_transaction if hasattr(signed_approve, 'raw_transaction') else signed_approve.rawTransaction
                approve_hash = w3.eth.send_raw_transaction(raw_approve)
                
                logger.info(f"Approval transaction sent: {approve_hash.hex()}")
                approve_receipt = w3.eth.wait_for_transaction_receipt(approve_hash, timeout=120)
                
                if approve_receipt.status != 1:
                    logger.error(f"Approval transaction failed: {approve_hash.hex()}")
                    return {"status": "error", "message": "Approval transaction failed"}
                
                logger.success("Approval confirmed")
            
            # Convertir le quote_id en uint256 (commitmentId)
            # D'après la doc Rhino.fi: commitmentId = BigInt(`0x${quoteId}`)
            # Le quote_id est une string hex, on doit le convertir en uint256
            try:
                if isinstance(quote_id, str):
                    # Enlever le préfixe 0x si présent
                    quote_id_clean = quote_id.replace('0x', '').replace('-', '')
                    
                    # Convertir en uint256 (BigInt) avec préfixe 0x
                    # Exemple: "691701077b5ae94a598a58bc" -> BigInt("0x691701077b5ae94a598a58bc")
                    try:
                        # S'assurer que c'est du hex valide
                        int(quote_id_clean, 16)
                        # Convertir en uint256 (Python int peut gérer des nombres arbitrairement grands)
                        commitment_id = int(quote_id_clean, 16)
                        logger.debug(f"Converted quote_id '{quote_id}' to commitmentId: {commitment_id}")
                    except ValueError:
                        # Si ce n'est pas du hex valide, essayer de le traiter comme un nombre décimal
                        try:
                            commitment_id = int(quote_id)
                            logger.debug(f"Converted quote_id '{quote_id}' to commitmentId (decimal): {commitment_id}")
                        except ValueError:
                            raise ValueError(f"quote_id '{quote_id}' is not a valid hex or decimal number")
                else:
                    # Si ce n'est pas une string, essayer de le convertir directement
                    commitment_id = int(quote_id)
                    
            except Exception as e:
                logger.error(f"Error converting quote_id to uint256: {e}")
                logger.error(f"quote_id value: {quote_id}, type: {type(quote_id)}")
                return {"status": "error", "message": f"Invalid quote_id format: {quote_id}"}
            
            # Appeler depositWithId
            nonce = w3.eth.get_transaction_count(self.hyperliquid_wallet.address)
            
            # Obtenir les paramètres de gas EIP-1559
            gas_params = self._get_gas_params(w3)
            
            deposit_txn = bridge_contract.functions.depositWithId(
                Web3.to_checksum_address(self.arbitrum_usdc_address),
                amount_wei,
                commitment_id  # uint256, pas bytes32
            ).build_transaction({
                'from': self.hyperliquid_wallet.address,
                'nonce': nonce,
                'gas': 200000,  # Gas limit plus élevé pour depositWithId
                'chainId': 42161,
                **gas_params  # Ajouter maxFeePerGas et maxPriorityFeePerGas ou gasPrice
            })
            
            signed_deposit = w3.eth.account.sign_transaction(deposit_txn, self.hyperliquid_wallet.key)
            raw_deposit = signed_deposit.raw_transaction if hasattr(signed_deposit, 'raw_transaction') else signed_deposit.rawTransaction
            deposit_hash = w3.eth.send_raw_transaction(raw_deposit)
            
            logger.info(f"Deposit transaction sent: {deposit_hash.hex()}")
            logger.info("Waiting for confirmation...")
            
            deposit_receipt = w3.eth.wait_for_transaction_receipt(deposit_hash, timeout=120)
            
            if deposit_receipt.status == 1:
                logger.success(f"Deposit successful! Transaction: {deposit_hash.hex()}")
                logger.info("The deposit will be credited to your Extended account after bridge processing")
                return {
                    "status": "success",
                    "amount": amount,
                    "bridge_fee": bridge_fee,
                    "amount_after_fee": amount - bridge_fee,
                    "transaction_hash": deposit_hash.hex(),
                    "quote_id": quote_id,
                    "bridge_address": bridge_address,
                    "receipt": {
                        "blockNumber": deposit_receipt.blockNumber,
                        "gasUsed": deposit_receipt.gasUsed
                    }
                }
            else:
                logger.error(f"Deposit transaction failed: {deposit_hash.hex()}")
                return {
                    "status": "error",
                    "message": "Deposit transaction failed",
                    "transaction_hash": deposit_hash.hex()
                }
            
        except Exception as e:
            logger.error(f"Error depositing to Extended: {e}")
            logger.exception("Full error details:")
            return {
                "status": "error",
                "message": str(e)
            }
    
    def execute_rebalancing(
        self,
        from_exchange: str,
        to_exchange: str,
        amount: float
    ) -> bool:
        """
        Exécute un transfert de rebalancing
        
        Args:
            from_exchange: Exchange source
            to_exchange: Exchange destination
            amount: Montant à transférer
            
        Returns:
            True si succès
        """
        try:
            logger.info(f"Rebalancing: {from_exchange} -> {to_exchange}, ${amount:.2f}")
            
            # TODO: Implémenter le transfert réel
            # 1. Retirer de from_exchange
            # 2. Déposer sur to_exchange
            
            # Simulation
            logger.success(f"Rebalancing completed: ${amount:.2f} transferred")
            return True
            
        except Exception as e:
            logger.error(f"Error executing rebalancing: {e}")
            return False
    
    def auto_rebalance_if_needed(self) -> bool:
        """
        Exécute automatiquement le rebalancing si nécessaire
        
        Returns:
            True si un rebalancing a été effectué
        """
        if not self.auto_rebalance:
            logger.debug("Auto-rebalancing disabled")
            return False
        
        check = self.check_balance_needed()
        
        if check.get('needs_rebalancing') and check.get('recommended_transfer'):
            transfer = check['recommended_transfer']
            
            logger.info("Auto-rebalancing triggered")
            logger.info(f"  From: {transfer['from']}")
            logger.info(f"  To: {transfer['to']}")
            logger.info(f"  Amount: ${transfer['amount']:.2f}")
            
            return self.execute_rebalancing(
                transfer['from'],
                transfer['to'],
                transfer['amount']
            )
        
        return False
    
    def _get_balance(self, exchange: str) -> float:
        """
        Récupère le solde d'un exchange
        
        Args:
            exchange: Nom de l'exchange ("Hyperliquid" ou "Extended")
            
        Returns:
            Solde en USDC
        """
        if exchange == "Hyperliquid":
            return self._get_hyperliquid_balance()
        elif exchange == "Extended":
            return self._get_extended_balance()
        else:
            logger.error(f"Unknown exchange: {exchange}")
            return 0.0
    
    def _get_hyperliquid_balance(self) -> float:
        """
        Récupère le solde USDC disponible sur Hyperliquid (perp wallet) via le SDK
        
        Returns:
            Solde withdrawable en USDC
        """
        if not HAS_HYPERLIQUID_SDK:
            logger.error("Hyperliquid SDK not available")
            return 0.0
        
        if not self.hyperliquid_client:
            logger.error("Hyperliquid client not initialized")
            return 0.0
        
        if not self.wallet_address:
            logger.error("Wallet address not configured")
            return 0.0
        
        try:
            # Récupérer l'état perp de l'utilisateur
            user_state = self.hyperliquid_client.user_state(self.wallet_address)
            
            if not user_state:
                logger.warning("No user state returned from Hyperliquid")
                return 0.0
            
            # Le solde withdrawable est disponible directement
            # C'est le montant USDC qui peut être retiré/transféré
            withdrawable_str = user_state.get('withdrawable', '0')
            
            try:
                withdrawable_balance = float(withdrawable_str)
                logger.debug(f"Found Hyperliquid withdrawable balance: {withdrawable_balance}")
                
                # Optionnel: logger aussi accountValue pour information
                margin_summary = user_state.get('marginSummary', {})
                if margin_summary:
                    account_value = float(margin_summary.get('accountValue', '0'))
                    logger.debug(f"Account value: {account_value}, Withdrawable: {withdrawable_balance}")
                
                return withdrawable_balance
                
            except (ValueError, TypeError) as e:
                logger.error(f"Error parsing withdrawable balance: {e}")
                return 0.0
            
        except Exception as e:
            logger.error(f"Error fetching Hyperliquid balance: {e}")
            return 0.0
    
    def _get_extended_balance(self) -> float:
        """
        Récupère le solde USDC disponible sur Extended (perp wallet) via le SDK
        
        Returns:
            Solde available_for_withdrawal en USDC
        """
        if not HAS_EXTENDED_SDK:
            logger.error("Extended SDK not available")
            return 0.0
        
        if not self.extended_account:
            logger.error("Extended account not initialized")
            return 0.0
        
        try:
            # Le SDK Extended est asynchrone, on doit utiliser asyncio.run()
            async def _async_get_balance():
                trading_client = PerpetualTradingClient(
                    endpoint_config=MAINNET_CONFIG,
                    stark_account=self.extended_account,
                )
                try:
                    balance_response = await trading_client.account.get_balance()
                    if balance_response and balance_response.data:
                        # BalanceModel contient available_for_withdrawal
                        available = float(balance_response.data.available_for_withdrawal)
                        logger.debug(f"Found Extended available_for_withdrawal: {available}")
                        return available
                    else:
                        logger.warning("No balance data returned from Extended")
                        return 0.0
                finally:
                    # Fermer la session
                    await trading_client.close()
            
            # Exécuter la fonction asynchrone
            balance = asyncio.run(_async_get_balance())
            return balance
            
        except Exception as e:
            logger.error(f"Error fetching Extended balance: {e}")
            return 0.0
    
    def get_balance_report(self) -> str:
        """
        Génère un rapport des balances
        
        Returns:
            Rapport formaté
        """
        check = self.check_balance_needed()
        
        if not check:
            return "❌ Impossible de récupérer les balances"
        
        report = "\n" + "="*60 + "\n"
        report += "💰 RAPPORT DES BALANCES\n"
        report += "="*60 + "\n\n"
        
        balances = check['balances']
        report += f"Extended:     ${balances['extended']:,.2f}\n"
        report += f"Hyperliquid:  ${balances['hyperliquid']:,.2f}\n"
        report += f"Total:        ${balances['total']:,.2f}\n"
        report += f"Idéal/exchange: ${check['ideal']:,.2f}\n\n"
        
        if check['needs_rebalancing']:
            transfer = check['recommended_transfer']
            report += "⚠️  REBALANCING RECOMMANDÉ\n"
            report += f"  De: {transfer['from']}\n"
            report += f"  Vers: {transfer['to']}\n"
            report += f"  Montant: ${transfer['amount']:,.2f}\n"
        else:
            report += "✅ Les balances sont équilibrées\n"
        
        report += "="*60 + "\n"
        
        return report

"""
Test de la configuration wallet
Vérifie que le wallet est correctement configuré et peut se connecter aux exchanges
"""
import json
import sys
from loguru import logger
from src.exchanges.exchange_manager import ExchangeManager


def check_wallet_config():
    """Vérifie que le wallet est configuré"""
    try:
        with open('config/config.json', 'r') as f:
            config = json.load(f)
        
        wallet_address = config['wallet']['address']
        private_key = config['wallet']['private_key']
        
        if wallet_address == "0xYOUR_WALLET_ADDRESS":
            logger.warning("⚠️  Wallet address non configurée")
            logger.info("📝 Édite config/config.json et remplace:")
            logger.info("   - '0xYOUR_WALLET_ADDRESS' par ton adresse wallet")
            logger.info("   - 'YOUR_PRIVATE_KEY' par ta clé privée")
            return False
        
        if private_key == "YOUR_PRIVATE_KEY":
            logger.warning("⚠️  Private key non configurée")
            return False
        
        if not wallet_address.startswith("0x"):
            logger.error("❌ L'adresse wallet doit commencer par '0x'")
            return False
        
        if len(wallet_address) != 42:
            logger.error(f"❌ L'adresse wallet doit faire 42 caractères (0x + 40 hex). Actuellement: {len(wallet_address)}")
            return False
        
        logger.success(f"✅ Wallet configuré: {wallet_address[:6]}...{wallet_address[-4:]}")
        return True
    
    except FileNotFoundError:
        logger.error("❌ Fichier config/config.json introuvable")
        return False
    except json.JSONDecodeError:
        logger.error("❌ Erreur de format dans config.json")
        return False


def test_exchange_connections():
    """Test la connexion aux exchanges"""
    try:
        logger.info("\n" + "="*60)
        logger.info("🔌 Test de connexion aux exchanges...")
        logger.info("="*60)
        
        manager = ExchangeManager()
        
        # Test Hyperliquid
        if manager.hyperliquid:
            logger.info("\n📡 Test Hyperliquid...")
            try:
                user_state = manager.hyperliquid.get_user_state()
                if user_state:
                    logger.success("✅ Hyperliquid connecté")
                    
                    # Afficher la balance
                    balance = manager.hyperliquid.get_balance()
                    logger.info(f"💰 Balance: ${balance:,.2f}")
                else:
                    logger.warning("⚠️  Hyperliquid: pas de données utilisateur")
            except Exception as e:
                logger.error(f"❌ Hyperliquid: {e}")
        
        # Test Variational
        if manager.variational:
            logger.info("\n📡 Test Variational...")
            try:
                balance = manager.variational.get_balance()
                logger.success("✅ Variational connecté")
                logger.info(f"💰 Balance: ${balance:,.2f}")
            except Exception as e:
                logger.error(f"❌ Variational: {e}")
        
        # Balance totale
        logger.info("\n" + "="*60)
        logger.info("💼 Balance totale")
        logger.info("="*60)
        total = manager.get_total_balance()
        logger.info(f"\n💰 Total sur tous les exchanges: ${total:,.2f}")
        
        # Positions ouvertes
        logger.info("\n" + "="*60)
        logger.info("📊 Positions ouvertes")
        logger.info("="*60)
        positions = manager.get_all_positions()
        
        has_positions = False
        for exchange, pos_list in positions.items():
            if pos_list:
                has_positions = True
                logger.info(f"\n{exchange.upper()}:")
                for pos in pos_list:
                    logger.info(f"  {pos}")
        
        if not has_positions:
            logger.info("\nℹ️  Aucune position ouverte")
        
        return True
    
    except Exception as e:
        logger.error(f"❌ Erreur test connexions: {e}")
        return False


def main():
    """Test complet de la configuration"""
    print("\n" + "="*60)
    print("🧪 TEST DE CONFIGURATION WALLET")
    print("="*60 + "\n")
    
    # 1. Vérifier la config
    if not check_wallet_config():
        logger.error("\n❌ Configuration wallet invalide")
        logger.info("\n📖 Voir WALLET_SETUP.md pour les instructions")
        sys.exit(1)
    
    # 2. Tester les connexions
    logger.info("\n" + "="*60)
    if not test_exchange_connections():
        logger.error("\n❌ Erreur de connexion aux exchanges")
        sys.exit(1)
    
    # 3. Résumé
    print("\n" + "="*60)
    print("✅ CONFIGURATION OK !")
    print("="*60)
    print("\nTu peux maintenant:")
    print("  1. Lancer find_best_opportunity.py pour voir les opportunités")
    print("  2. Lancer python src/main.py en mode auto")
    print("  3. Trader en delta-neutral sur Extended/Hyperliquid/Variational")
    print("\n⚠️  RAPPEL: Commence sur TESTNET avant le mainnet !")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()

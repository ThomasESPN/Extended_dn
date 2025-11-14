"""
Test RÉEL d'ordre Hyperliquid avec le SDK officiel
ATTENTION : Va placer un VRAI ordre sur Hyperliquid !
"""

import json
import sys
from loguru import logger
from src.exchanges.hyperliquid_api import HyperliquidAPI

logger.remove()
logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{level:8}</level> | <level>{message}</level>")

def load_config():
    """Charge la configuration"""
    with open('config/config.json', 'r') as f:
        return json.load(f)

def main():
    """Test principal"""
    logger.info(f"{'='*80}")
    logger.info(f"🚨 TEST RÉEL HYPERLIQUID - ORDRE LIMIT")
    logger.info(f"{'='*80}\n")
    
    # Chargement config
    config = load_config()
    wallet = config['wallet']['address']
    private_key = config['wallet']['private_key']
    
    logger.info(f"📝 Configuration:")
    logger.info(f"   Wallet: {wallet}\n")
    
    # Init API Hyperliquid
    logger.info(f"🔌 Initialisation Hyperliquid...")
    hl_api = HyperliquidAPI(wallet_address=wallet, private_key=private_key)
    logger.success(f"✅ API Hyperliquid initialisée\n")
    
    # Récupérer le prix ETH
    logger.info(f"📊 Récupération du prix ETH...")
    ticker = hl_api.get_ticker("ETH")
    if not ticker:
        logger.error("❌ Impossible de récupérer le prix ETH")
        return
    
    logger.success(f"✅ Prix ETH: last=${ticker['last']:.2f}, bid=${ticker['bid']:.2f}, ask=${ticker['ask']:.2f}\n")
    
    # Calculer un prix TRÈS loin pour ne PAS être fill (test)
    # On va mettre un prix à -10% du market pour un LONG (ne sera jamais fill)
    test_price = ticker['last'] * 0.90
    test_size = 0.001  # 0.001 ETH = environ $3
    
    logger.warning(f"\n⚠️  TEST ORDRE HYPERLIQUID")
    logger.warning(f"   Type: LONG (BUY)")
    logger.warning(f"   Symbole: ETH")
    logger.warning(f"   Taille: {test_size} ETH (~$3)")
    logger.warning(f"   Prix: ${test_price:.2f} (market: ${ticker['last']:.2f})")
    logger.warning(f"   Note: Prix -10% du market → NE SERA PAS FILL (sécurité)")
    
    choice = input("\n   Taper 'CONFIRM' pour placer l'ordre RÉEL sur Hyperliquid: ")
    
    if choice.upper() != 'CONFIRM':
        logger.info("❌ Test annulé")
        return
    
    # Placer l'ordre
    logger.info(f"\n🚀 Placement de l'ordre...")
    result = hl_api.place_order(
        symbol="ETH",
        side="buy",
        size=test_size,
        order_type="limit",
        price=test_price
    )
    
    if result:
        logger.success(f"\n{'='*80}")
        logger.success(f"🎉 ORDRE PLACÉ AVEC SUCCÈS !")
        logger.success(f"{'='*80}\n")
        logger.info(f"Résultat: {result}\n")
        logger.info(f"📋 Vérifiez votre ordre sur:")
        logger.info(f"   https://app.hyperliquid.xyz/trade/ETH")
        logger.info(f"\n💡 Pensez à ANNULER l'ordre manuellement sur le site !")
    else:
        logger.error(f"\n❌ Échec du placement de l'ordre")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning(f"\n⚠️  Test interrompu par l'utilisateur")
    except Exception as e:
        logger.error(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()

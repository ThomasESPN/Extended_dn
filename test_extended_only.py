"""
Test Extended API uniquement (sans Hyperliquid)
"""
import json
import sys
from pathlib import Path

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.exchanges.extended_api import ExtendedAPI


def main():
    logger.info("="*80)
    logger.info("🧪 TEST EXTENDED UNIQUEMENT")
    logger.info("="*80)
    
    # Load config
    config_path = Path(__file__).parent / "config" / "config.json"
    with open(config_path) as f:
        config = json.load(f)
    
    wallet = config["wallet"]["address"]
    extended_config = config["extended"]
    
    logger.info(f"\n📝 Configuration:")
    logger.info(f"   Wallet: {wallet}")
    logger.info(f"   Vault: {extended_config['vault_id']}")
    
    # Initialize Extended API
    logger.info("\n🔌 Initialisation Extended API...")
    extended = ExtendedAPI(
        wallet_address=wallet,
        api_key=extended_config["api_key"],
        stark_public_key=extended_config["stark_public_key"],
        stark_private_key=extended_config["stark_private_key"],
        vault_id=extended_config["vault_id"],
        client_id=extended_config.get("client_id")
    )
    
    if not extended.trading_client:
        logger.error("❌ Extended client failed to initialize")
        return
    
    logger.success("✅ Extended API initialized")
    
    # Test market data
    logger.info("\n📊 Test données marché...")
    symbol = "ETH"
    ticker = extended.get_ticker(symbol)
    logger.info(f"   {symbol} - bid: {ticker['bid']}, ask: {ticker['ask']}")
    
    # Calculate test order size
    mid_price = (ticker['bid'] + ticker['ask']) / 2
    test_usd = 31.0  # 31 USD = 0.01 ETH @ 3100
    test_size = test_usd / mid_price
    
    # Round to 0.01 (min size for Extended ETH)
    test_size = max(0.01, round(test_size, 2))
    
    logger.info(f"\n💰 Ordre test:")
    logger.info(f"   Taille: {test_size} {symbol} (≈${test_size * mid_price:.2f})")
    logger.info(f"   Prix: {ticker['ask'] * 1.0005:.2f} (ask + 0.05%)")
    
    # Ask confirmation
    response = input("\n⚠️  Placer cet ordre RÉEL sur Extended ? (YES pour continuer): ")
    if response.upper() != "YES":
        logger.info("❌ Test annulé")
        return
    
    # Place order
    logger.info("\n🚀 Placement de l'ordre...")
    result = extended.place_order(
        symbol=symbol,
        side="buy",
        size=test_size,
        price=ticker['ask'] * 1.0005,  # +0.05% pour fill immédiat
        order_type="limit"
    )
    
    logger.info(f"\n📋 Résultat:")
    logger.info(f"   Status: {result.get('status')}")
    logger.info(f"   Order ID: {result.get('order_id')}")
    logger.info(f"   Size: {result.get('size')} {symbol}")
    logger.info(f"   Price: ${result.get('price')}")
    
    if result.get('status') in ['OK', 'timeout', 'pending']:
        logger.success("\n✅ Ordre Extended placé (vérifier sur UI si timeout)")
    else:
        logger.error(f"\n❌ Erreur: {result.get('error')}")
    
    logger.info("\n" + "="*80)
    logger.info("🏁 Test terminé - Vérifiez https://app.extended.exchange")
    logger.info("="*80)


if __name__ == "__main__":
    main()

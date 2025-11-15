"""
EMERGENCY: Close unhedged Extended position
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

sys.path.insert(0, str(Path(__file__).parent))

from src.exchanges.extended_api import ExtendedAPI


def main():
    logger.info("🚨 EMERGENCY CLOSE UNHEDGED POSITION")
    
    # Load config
    config_path = Path(__file__).parent / "config" / "config.json"
    with open(config_path) as f:
        config = json.load(f)
    
    wallet = config["wallet"]["address"]
    extended_config = config["extended"]
    
    # Initialize API
    extended = ExtendedAPI(
        wallet_address=wallet,
        api_key=extended_config["api_key"],
        stark_public_key=extended_config["stark_public_key"],
        stark_private_key=extended_config["stark_private_key"],
        vault_id=extended_config["vault_id"],
        client_id=extended_config.get("client_id")
    )
    
    if not extended.trading_client:
        logger.error("❌ Extended failed to initialize")
        return
    
    # Get positions
    logger.info("\n📊 Positions actuelles sur Extended:")
    positions = extended.get_positions()
    
    if not positions:
        logger.success("✅ Aucune position ouverte")
        return
    
    for pos in positions:
        symbol = pos.get('symbol', 'UNKNOWN')
        size = pos.get('size', 0)
        side = pos.get('side', 'UNKNOWN')
        entry_price = pos.get('entry_price', 0)
        
        logger.warning(f"\n   Position: {symbol}")
        logger.warning(f"   Side: {side}")
        logger.warning(f"   Size: {size}")
        logger.warning(f"   Entry: ${entry_price:.2f}")
        
        # Ask confirmation
        confirm = input(f"\n⚠️  Fermer cette position {symbol} en MARKET? (yes/no): ").strip().lower()
        if confirm == "yes":
            # Determine close side
            close_side = "sell" if side.upper() == "LONG" else "buy"
            
            logger.info(f"\n📝 Fermeture {symbol} {side} (taille: {size})...")
            result = extended.place_order(
                symbol=symbol,
                side=close_side,
                size=abs(float(size)),
                order_type="market"
            )
            
            if result and result.get('order_id'):
                logger.success(f"   ✅ Position {symbol} fermée!")
            else:
                logger.error(f"   ❌ Échec fermeture: {result}")
        else:
            logger.info(f"   → Position {symbol} conservée")


if __name__ == "__main__":
    main()

"""
Script pour fermer TOUTES les positions ouvertes sur Extended et Hyperliquid
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
from src.exchanges.hyperliquid_api import HyperliquidAPI


def main():
    logger.info("="*100)
    logger.info("🧹 FERMETURE DE TOUTES LES POSITIONS")
    logger.info("="*100)
    
    # Load config
    config_path = Path(__file__).parent / "config" / "config.json"
    with open(config_path) as f:
        config = json.load(f)
    
    wallet = config["wallet"]["address"]
    private_key = config["wallet"]["private_key"]
    extended_config = config["extended"]
    
    # Initialize APIs
    extended = ExtendedAPI(
        wallet_address=wallet,
        api_key=extended_config["api_key"],
        stark_public_key=extended_config["stark_public_key"],
        stark_private_key=extended_config["stark_private_key"],
        vault_id=extended_config["vault_id"],
        client_id=extended_config.get("client_id")
    )
    
    hyperliquid = HyperliquidAPI(
        wallet_address=wallet,
        private_key=private_key
    )
    
    # 1. Annuler tous les ordres ouverts
    logger.info("\n❌ Annulation de tous les ordres ouverts...")
    
    logger.info("   Extended...")
    try:
        extended_orders = extended.get_open_orders()
        for order in extended_orders:
            logger.info(f"      Annulation ordre {order['symbol']}: {order['order_id']}")
            extended.cancel_order(order['order_id'])
    except Exception as e:
        logger.error(f"   Erreur Extended: {e}")
    
    logger.info("   Hyperliquid...")
    try:
        hyperliquid.cancel_all_orders()
    except Exception as e:
        logger.error(f"   Erreur Hyperliquid: {e}")
    
    # 2. Fermer toutes les positions
    logger.info("\n📊 Fermeture de toutes les positions...")
    
    logger.info("\n   Extended...")
    try:
        extended_positions = extended.get_positions()
        for pos in extended_positions:
            symbol = pos['symbol']
            size = abs(float(pos['size']))
            side = "sell" if float(pos['size']) > 0 else "buy"
            
            logger.info(f"      Fermeture {symbol}: {side.upper()} {size}")
            result = extended.place_order(
                symbol=symbol,
                side=side,
                size=size,
                order_type="market"
            )
            
            if result and result.get('order_id'):
                logger.success(f"      ✅ {symbol} fermé")
            else:
                logger.error(f"      ❌ Échec {symbol}")
    except Exception as e:
        logger.error(f"   Erreur Extended: {e}")
    
    logger.info("\n   Hyperliquid...")
    try:
        hyperliquid_positions = hyperliquid.get_open_positions()
        for pos in hyperliquid_positions:
            pos_data = pos.get('position', {})
            symbol = pos_data.get('coin')
            size = abs(float(pos_data.get('szi', 0)))
            
            if size > 0:
                side = "buy" if float(pos_data.get('szi', 0)) < 0 else "sell"
                
                logger.info(f"      Fermeture {symbol}: {side.upper()} {size}")
                result = hyperliquid.place_order(
                    symbol=symbol,
                    side=side,
                    size=size,
                    order_type="market"
                )
                
                if result and result.get('status') == 'ok':
                    logger.success(f"      ✅ {symbol} fermé")
                else:
                    logger.error(f"      ❌ Échec {symbol}")
    except Exception as e:
        logger.error(f"   Erreur Hyperliquid: {e}")
    
    logger.info("\n" + "="*100)
    logger.success("✅ NETTOYAGE TERMINÉ")
    logger.info("="*100)


if __name__ == "__main__":
    main()

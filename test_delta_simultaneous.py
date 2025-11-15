"""
Test Delta-Neutral avec placement SIMULTANÉ des 2 ordres
- Place Extended LONG + Hyperliquid SHORT en même temps
- Si aucun fill → Réajuste prix MAKER (pas TAKER)
- Si 1 seul fill → Adapte l'autre au prix fill avec écart minimum
"""

import json
import time
from loguru import logger
from src.exchanges.extended_api import ExtendedAPI
from src.exchanges.hyperliquid_api import HyperliquidAPI

def check_fill_status(extended, hyperliquid, symbol, extended_order_id, hyperliquid_order_id):
    """
    Vérifie le statut des 2 ordres (filled, resting, rejected)
    
    Returns:
        dict: {
            "extended": {"status": "filled|resting|rejected", "price": float|None},
            "hyperliquid": {"status": "filled|resting|rejected", "price": float|None}
        }
    """
    result = {
        "extended": {"status": "unknown", "price": None, "size": 0},
        "hyperliquid": {"status": "unknown", "price": None, "size": 0}
    }
    
    # Check Extended
    if extended_order_id:
        positions = extended.get_positions()
        position = next((p for p in positions if p.get('symbol') == symbol), None)
        
        if position:
            result["extended"]["status"] = "filled"
            result["extended"]["price"] = position.get('entry_price')
            result["extended"]["size"] = position.get('size')
        else:
            open_orders = extended.get_open_orders(symbol)
            order = next((o for o in open_orders if o.get('order_id') == extended_order_id), None)
            
            if order:
                result["extended"]["status"] = "resting"
                result["extended"]["price"] = order.get('price')
            else:
                result["extended"]["status"] = "rejected"
    
    # Check Hyperliquid
    if hyperliquid_order_id:
        fills = hyperliquid.get_user_fills(limit=10)
        recent_fill = next((f for f in fills if f.get('oid') == hyperliquid_order_id), None)
        
        if recent_fill:
            result["hyperliquid"]["status"] = "filled"
            result["hyperliquid"]["price"] = recent_fill.get('price')
            result["hyperliquid"]["size"] = recent_fill.get('size')
        else:
            open_orders = hyperliquid.get_open_orders()
            order = next((o for o in open_orders if o.get('oid') == hyperliquid_order_id), None)
            
            if order:
                result["hyperliquid"]["status"] = "resting"
                result["hyperliquid"]["price"] = order.get('limitPx')
            else:
                result["hyperliquid"]["status"] = "rejected"
    
    return result

def main():
    logger.info("="*100)
    logger.info("🧪 TEST DELTA-NEUTRAL - PLACEMENT SIMULTANÉ")
    logger.info("="*100)
    
    # Load config
    config_path = "config/config.json"
    with open(config_path) as f:
        config = json.load(f)
    
    wallet = config["wallet"]["address"]
    private_key = config["wallet"]["private_key"]
    extended_config = config["extended"]
    target_usd = config["auto_trading"]["position_size_usd"]
    
    logger.info(f"\n📝 Configuration:")
    logger.info(f"   Wallet: {wallet}")
    logger.info(f"   Margin: ${target_usd}")
    
    # Initialize APIs
    logger.info("\n🔌 Initialisation des APIs...")
    
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
    
    if not extended.trading_client:
        logger.error("❌ Extended failed to initialize")
        return
    
    logger.success("✅ Les deux APIs sont initialisées")
    
    # Symbole
    symbol = "ZORA"
    logger.info(f"\n🎯 Symbole: {symbol}")
    
    logger.info(f"\n{'='*100}")
    logger.info(f"🎯 PHASE 1: CALCUL TAILLE ET PRIX")
    logger.info(f"{'='*100}")
    
    # Get market data
    logger.info(f"\n📊 Récupération des prix et metadata...")
    
    extended_ticker = extended.get_ticker(symbol)
    hyperliquid_ticker = hyperliquid.get_ticker(symbol)
    
    logger.success(f"✅ Extended {symbol}: bid={extended_ticker['bid']:.5f}, ask={extended_ticker['ask']:.5f}")
    logger.success(f"✅ Hyperliquid {symbol}: bid={hyperliquid_ticker['bid']:.5f}, ask={hyperliquid_ticker['ask']:.5f}")
    
    # Récupération metadata
    extended_leverage = extended.get_max_leverage(symbol)
    hyperliquid_leverage = hyperliquid.get_max_leverage(symbol)
    extended_decimals = extended.get_size_decimals(symbol)
    hyperliquid_decimals = hyperliquid.get_size_decimals(symbol)
    
    compatible_leverage = min(extended_leverage, hyperliquid_leverage, 10)
    size_decimals = min(extended_decimals, hyperliquid_decimals)
    
    logger.info(f"   Extended: {extended_leverage}x leverage, {extended_decimals} decimals")
    logger.info(f"   Hyperliquid: {hyperliquid_leverage}x leverage, {hyperliquid_decimals} decimals")
    logger.info(f"   ✅ Compatible: {compatible_leverage}x leverage, {size_decimals} decimals")
    
    # Calculate size
    avg_price = (extended_ticker['ask'] + hyperliquid_ticker['bid']) / 2
    notional_usd = target_usd * compatible_leverage
    target_size = notional_usd / avg_price
    target_size = round(target_size, size_decimals)
    
    logger.info(f"\n💰 Calcul des tailles:")
    logger.info(f"   Margin: ${target_usd} USD")
    logger.info(f"   Leverage: {compatible_leverage}x")
    logger.info(f"   Notional: ${notional_usd} USD")
    logger.info(f"   Prix moyen: ${avg_price:.6f}")
    logger.info(f"   Size: {target_size} {symbol}")
    
    # Prix global mid
    global_mid = (
        (extended_ticker['bid'] + extended_ticker['ask']) / 2 +
        (hyperliquid_ticker['bid'] + hyperliquid_ticker['ask']) / 2
    ) / 2
    
    logger.info(f"\n📊 Prix mid global: ${global_mid:.6f}")
    
    logger.info(f"\n🚀 Lancement automatique dans 3 secondes...")
    time.sleep(3)
    
    # ==========================================
    # PLACEMENT SIMULTANÉ
    # ==========================================
    
    max_attempts = 5  # Maximum 5 tentatives
    
    for attempt in range(1, max_attempts + 1):
        logger.info(f"\n{'='*100}")
        logger.info(f"📝 TENTATIVE #{attempt} - PLACEMENT SIMULTANÉ")
        logger.info(f"{'='*100}")
        
        # Calculer offset progressif (0.01% → 0.05% → 0.1% → 0.2% → 0.5%)
        offset_pct = 0.01 * (2 ** (attempt - 1))  # Exponentiel
        offset_pct = min(offset_pct, 0.5)  # Max 0.5%
        
        # Prix pour chaque exchange
        extended_price = global_mid * (1 - offset_pct / 100)  # BUY = mid - offset
        hyperliquid_price = global_mid * (1 + offset_pct / 100)  # SELL = mid + offset
        
        extended_price = round(extended_price, 6)
        hyperliquid_price = round(hyperliquid_price, 6)
        
        logger.info(f"\n💵 Prix avec offset {offset_pct:.3f}%:")
        logger.info(f"   Extended BUY:  ${extended_price:.6f}")
        logger.info(f"   Hyperliquid SELL: ${hyperliquid_price:.6f}")
        logger.info(f"   Spread: {abs(hyperliquid_price - extended_price) / global_mid * 100:.4f}%")
        
        # PLACER LES 2 ORDRES EN PARALLÈLE
        logger.info(f"\n🚀 Placement simultané...")
        
        extended_result = extended.place_order(
            symbol=symbol,
            side="buy",
            size=target_size,
            order_type="limit",
            price=extended_price
        )
        
        hyperliquid_result = hyperliquid.place_order(
            symbol=symbol,
            side="sell",
            size=target_size,
            order_type="limit",
            price=hyperliquid_price
        )
        
        extended_order_id = extended_result.get('order_id') if extended_result else None
        hyperliquid_order_id = hyperliquid_result.get('order_id') if hyperliquid_result else None
        
        if not extended_order_id and not hyperliquid_order_id:
            logger.error("❌ Les 2 ordres ont échoué immédiatement!")
            logger.info(f"   Extended: {extended_result}")
            logger.info(f"   Hyperliquid: {hyperliquid_result}")
            continue
        
        logger.info(f"   Extended order_id: {extended_order_id}")
        logger.info(f"   Hyperliquid order_id: {hyperliquid_order_id}")
        
        # Attendre 5s et checker status
        logger.info(f"\n⏳ Attente 5 secondes pour vérifier les fills...")
        time.sleep(5)
        
        status = check_fill_status(extended, hyperliquid, symbol, extended_order_id, hyperliquid_order_id)
        
        logger.info(f"\n📊 Status après 5s:")
        logger.info(f"   Extended: {status['extended']['status']} @ ${status['extended']['price'] or 'N/A'}")
        logger.info(f"   Hyperliquid: {status['hyperliquid']['status']} @ ${status['hyperliquid']['price'] or 'N/A'}")
        
        # CAS 1: Les 2 sont filled ✅
        if status["extended"]["status"] == "filled" and status["hyperliquid"]["status"] == "filled":
            logger.success("\n✅ ✅ LES 2 ORDRES SONT FILLED!")
            logger.success(f"   Extended LONG: {status['extended']['size']} @ ${status['extended']['price']}")
            logger.success(f"   Hyperliquid SHORT: {status['hyperliquid']['size']} @ ${status['hyperliquid']['price']}")
            
            spread = abs(status['hyperliquid']['price'] - status['extended']['price'])
            spread_pct = spread / global_mid * 100
            logger.success(f"   Spread final: ${spread:.6f} ({spread_pct:.4f}%)")
            break
        
        # CAS 2: Aucun filled → Cancel et retry avec prix plus agressif
        elif status["extended"]["status"] == "resting" and status["hyperliquid"]["status"] == "resting":
            logger.warning(f"\n⚠️  Aucun ordre filled (les 2 resting)")
            logger.info(f"   🔄 Cancel et retry avec offset plus agressif...")
            
            # Cancel les 2
            if extended_order_id:
                extended.cancel_order(extended_order_id)
            if hyperliquid_order_id:
                hyperliquid.cancel_order(hyperliquid_order_id)
            
            time.sleep(1)
            continue
        
        # CAS 3: UN SEUL filled → Adapter l'autre
        elif status["extended"]["status"] == "filled" and status["hyperliquid"]["status"] != "filled":
            logger.warning(f"\n⚠️  Extended filled mais pas Hyperliquid!")
            logger.info(f"   🎯 Adaptation: Place Hyperliquid au prix Extended + écart minimum")
            
            # Cancel Hyperliquid resting
            if hyperliquid_order_id and status["hyperliquid"]["status"] == "resting":
                hyperliquid.cancel_order(hyperliquid_order_id)
                time.sleep(1)
            
            # Nouveau prix = prix Extended + 0.01%
            adapted_price = status["extended"]["price"] * 1.0001
            adapted_price = round(adapted_price, 6)
            
            logger.info(f"   Nouveau prix Hyperliquid SHORT: ${adapted_price:.6f}")
            
            hyperliquid_result = hyperliquid.place_order(
                symbol=symbol,
                side="sell",
                size=target_size,
                order_type="limit",
                price=adapted_price
            )
            
            # Attendre 3s
            time.sleep(3)
            
            # Si toujours pas filled → MARKET pour urgence hedge
            fills = hyperliquid.get_user_fills(limit=5)
            filled = any(f.get('symbol') == symbol for f in fills)
            
            if filled:
                logger.success("✅ Hyperliquid filled après adaptation!")
                break
            else:
                logger.error("❌ Toujours pas filled après 3s → MARKET hedge urgence")
                hyperliquid.place_order(
                    symbol=symbol,
                    side="sell",
                    size=target_size,
                    order_type="market"
                )
                time.sleep(2)
                break
        
        elif status["hyperliquid"]["status"] == "filled" and status["extended"]["status"] != "filled":
            logger.warning(f"\n⚠️  Hyperliquid filled mais pas Extended!")
            logger.info(f"   🎯 Adaptation: Place Extended au prix Hyperliquid - écart minimum")
            
            # Cancel Extended resting
            if extended_order_id and status["extended"]["status"] == "resting":
                extended.cancel_order(extended_order_id)
                time.sleep(1)
            
            # Nouveau prix = prix Hyperliquid - 0.01%
            adapted_price = status["hyperliquid"]["price"] * 0.9999
            adapted_price = round(adapted_price, 6)
            
            logger.info(f"   Nouveau prix Extended BUY: ${adapted_price:.6f}")
            
            extended_result = extended.place_order(
                symbol=symbol,
                side="buy",
                size=target_size,
                order_type="limit",
                price=adapted_price
            )
            
            # Attendre 3s
            time.sleep(3)
            
            # Si toujours pas filled → MARKET pour urgence hedge
            positions = extended.get_positions()
            filled = any(p.get('symbol') == symbol for p in positions)
            
            if filled:
                logger.success("✅ Extended filled après adaptation!")
                break
            else:
                logger.error("❌ Toujours pas filled après 3s → MARKET hedge urgence")
                extended.place_order(
                    symbol=symbol,
                    side="buy",
                    size=target_size,
                    order_type="market"
                )
                time.sleep(2)
                break
    
    else:
        logger.error(f"\n❌ Échec après {max_attempts} tentatives")
        return
    
    # ==========================================
    # PHASE 2: MONITORING
    # ==========================================
    
    logger.info(f"\n{'='*100}")
    logger.info("📊 PHASE 2: MONITORING POSITION (10 secondes)")
    logger.info(f"{'='*100}")
    
    time.sleep(10)
    
    # ==========================================
    # PHASE 3: FERMETURE
    # ==========================================
    
    logger.info(f"\n{'='*100}")
    logger.info("🔄 PHASE 3: FERMETURE POSITIONS")
    logger.info(f"{'='*100}")
    
    # Get positions
    extended_positions = extended.get_positions()
    hyperliquid_positions = hyperliquid.get_positions()
    
    for pos in extended_positions:
        if pos.get('symbol') == symbol:
            logger.info(f"\n🔄 Fermeture Extended {symbol}...")
            close_result = extended.close_position(symbol)
            logger.info(f"   Result: {close_result}")
    
    for pos in hyperliquid_positions:
        if pos.get('symbol') == symbol:
            logger.info(f"\n🔄 Fermeture Hyperliquid {symbol}...")
            close_result = hyperliquid.close_position(symbol)
            logger.info(f"   Result: {close_result}")
    
    logger.success(f"\n✅ Test terminé!")

if __name__ == "__main__":
    main()

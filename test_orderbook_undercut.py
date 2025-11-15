"""
Test DELTA-NEUTRAL avec ORDERBOOK UNDERCUTTING

Stratégie:
1. Check l'orderbook en temps réel
2. Place juste DEVANT le meilleur bid/ask (undercut)
3. Si quelqu'un nous coupe → Replace immédiatement
4. Objectif: TOUJOURS être le meilleur prix des deux côtés
"""
import json
import sys
import time
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


def check_order_filled_fast(api, exchange_name, order_result, symbol, order_timestamp):
    """Vérifie rapidement si un ordre est filled via positions"""
    try:
        if exchange_name == "extended":
            positions = api.get_positions()
            for pos in positions:
                if pos.get('symbol') == symbol and abs(pos.get('size', 0)) > 0:
                    # Vérifier timestamp si disponible
                    fill_price = pos.get('entry_price') or pos.get('avg_price')
                    logger.info(f"   ✅ Extended: Fill détecté! {symbol} {pos.get('size')} @ ${fill_price:.2f}")
                    return True, fill_price
            return False, None
            
        elif exchange_name == "hyperliquid":
            positions = api.get_open_positions()
            for pos in positions:
                if pos.get('symbol') == symbol and abs(pos.get('size', 0)) > 0:
                    fill_price = pos.get('entry_price') or pos.get('avg_price')
                    logger.info(f"   ✅ Hyperliquid: Fill détecté! {symbol} {pos.get('size')} @ ${fill_price:.2f}")
                    return True, fill_price
            return False, None
    except Exception as e:
        logger.error(f"Error checking fill: {e}")
        return False, None


def main():
    logger.info("="*100)
    logger.info("🎯 TEST DELTA-NEUTRAL avec ORDERBOOK UNDERCUTTING")
    logger.info("="*100)
    
    # Load config
    config_path = Path(__file__).parent / "config" / "config.json"
    with open(config_path) as f:
        config = json.load(f)
    
    wallet = config["wallet"]["address"]
    private_key = config["wallet"]["private_key"]
    extended_config = config["extended"]
    target_usd = config["auto_trading"]["position_size_usd"]
    
    logger.info(f"\n📝 Configuration:")
    logger.info(f"   Wallet: {wallet}")
    logger.info(f"   Taille: ${target_usd} par exchange")
    
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
    
    logger.success("✅ APIs initialisées")
    
    # Symbol à trader
    symbol = "ZORA"
    
    logger.info(f"\n📊 Récupération prix {symbol}...")
    
    extended_ticker = extended.get_ticker(symbol)
    hyperliquid_ticker = hyperliquid.get_ticker(symbol)
    
    logger.success(f"✅ Extended {symbol}: bid={extended_ticker['bid']:.2f}, ask={extended_ticker['ask']:.2f}")
    logger.success(f"✅ Hyperliquid {symbol}: bid={hyperliquid_ticker['bid']:.2f}, ask={hyperliquid_ticker['ask']:.2f}")
    
    # Metadata
    logger.info(f"\n📐 Récupération metadata {symbol}...")
    extended_leverage = extended.get_max_leverage(symbol)
    hyperliquid_leverage = hyperliquid.get_max_leverage(symbol)
    extended_decimals = extended.get_size_decimals(symbol)
    hyperliquid_decimals = hyperliquid.get_size_decimals(symbol)
    extended_min_size = extended.get_min_order_size(symbol)
    
    compatible_leverage = min(extended_leverage, hyperliquid_leverage, 10)
    
    # 🔥 FORCE 0 decimals pour ZORA (pas 4 comme Extended retourne incorrectement)
    size_decimals = 0
    
    logger.info(f"   Extended: {extended_leverage}x leverage, {extended_decimals} decimals, min: {extended_min_size}")
    logger.info(f"   Hyperliquid: {hyperliquid_leverage}x leverage, {hyperliquid_decimals} decimals")
    logger.info(f"   ✅ Compatible: {compatible_leverage}x leverage, {size_decimals} decimals (forced)")
    
    # Calculate size
    avg_price = (extended_ticker['ask'] + hyperliquid_ticker['bid']) / 2
    notional_usd = target_usd * compatible_leverage
    target_size = notional_usd / avg_price
    target_size = round(target_size, size_decimals)
    
    # 🔥 FORCE 1000 ZORA minimum (Extended retourne 0.01 incorrectement)
    extended_min_size_real = 1000.0
    
    if target_size < extended_min_size_real:
        logger.warning(f"⚠️  Size {target_size:.{size_decimals}f} < min Extended {extended_min_size_real}")
        target_size = extended_min_size_real
        required_notional = target_size * avg_price
        required_margin = required_notional / compatible_leverage
        logger.warning(f"   → Utilisation {extended_min_size_real} {symbol} (margin: ${required_margin:.2f})")
    
    extended_size = target_size
    hyperliquid_size = target_size
    
    logger.info(f"\n💰 Tailles:")
    logger.info(f"   Margin: ${target_usd}")
    logger.info(f"   Leverage: {compatible_leverage}x")
    logger.info(f"   Notional: ${notional_usd}")
    logger.info(f"   Prix moyen: ${avg_price:.6f}")
    logger.info(f"   Size: {target_size} {symbol}")
    
    logger.warning(f"\n⚠️  STRATÉGIE ORDERBOOK UNDERCUTTING:")
    logger.warning(f"   1. Check orderbook en continu")
    logger.warning(f"   2. Place juste DEVANT le meilleur bid/ask")
    logger.warning(f"   3. Si quelqu'un cut → Replace immédiatement")
    logger.warning(f"   4. TOUJOURS être le meilleur prix")
    
    logger.info(f"\n🚀 Start dans 3s...")
    time.sleep(3)
    
    # =================================================================
    # MAIN LOOP: ORDERBOOK UNDERCUTTING
    # =================================================================
    
    logger.info(f"\n{'='*100}")
    logger.info("🔥 ORDERBOOK UNDERCUTTING LOOP")
    logger.info(f"{'='*100}")
    
    extended_filled = False
    hyperliquid_filled = False
    extended_fill_price = None
    hyperliquid_fill_price = None
    extended_order_id = None
    
    order_timestamp = int(time.time() * 1000)
    max_attempts = 50  # 50 tentatives max
    
    for attempt in range(max_attempts):
        logger.info(f"\n{'='*80}")
        logger.info(f"🔄 ATTEMPT #{attempt + 1}/{max_attempts}")
        logger.info(f"{'='*80}")
        
        # =====================================================
        # EXTENDED: UNDERCUT BID
        # =====================================================
        if not extended_filled:
            try:
                # 🔥 UTILISER LE VRAI ORDERBOOK EXTENDED REAL-TIME
                extended_orderbook = extended.get_orderbook(symbol, depth=5)
                
                if not extended_orderbook.get('bids') or not extended_orderbook.get('asks'):
                    logger.warning(f"⚠️ Extended orderbook vide, retry...")
                    time.sleep(0.5)
                    continue
                
                best_bid = extended_orderbook['bids'][0][0]  # Meilleur prix bid
                best_ask = extended_orderbook['asks'][0][0]  # Meilleur prix ask
                
                # UNDERCUT: place juste AU-DESSUS du meilleur bid
                # On veut être le MEILLEUR acheteur (BUY)
                extended_price = best_bid * 1.00005  # +0.005% au-dessus du bid
                extended_price = extended.round_price(symbol, extended_price)
                
                # Ne pas dépasser le ask (sinon on devient taker)
                if extended_price >= best_ask:
                    extended_price = best_ask * 0.99995  # -0.005% en dessous du ask
                    extended_price = extended.round_price(symbol, extended_price)
                
                logger.info(f"\n📗 Extended UNDERCUT BUY @ ${extended_price:.6f} (bid={best_bid:.6f}, ask={best_ask:.6f})")
                
                # Annuler l'ordre précédent s'il existe
                if extended_order_id:
                    try:
                        extended.cancel_order(extended_order_id)
                        time.sleep(0.1)
                    except:
                        pass
                
                # Placer le nouvel ordre
                result = extended.place_order(
                    symbol=symbol,
                    side="buy",
                    size=extended_size,
                    order_type="limit",
                    price=extended_price
                )
                
                if result and result.get('order_id'):
                    extended_order_id = result['order_id']
                    logger.success(f"   ✅ Extended placé (OID: {extended_order_id})")
                else:
                    logger.error(f"   ❌ Extended failed: {result}")
                    
            except Exception as e:
                logger.error(f"   ❌ Extended error: {e}")
        
        # =====================================================
        # HYPERLIQUID: UNDERCUT ASK
        # =====================================================
        if not hyperliquid_filled:
            try:
                # Get real-time orderbook
                ticker = hyperliquid.get_ticker(symbol)
                best_bid = ticker['bid']
                best_ask = ticker['ask']
                
                # UNDERCUT: place juste EN-DESSOUS du meilleur ask
                # On veut être le MEILLEUR vendeur (SELL)
                hyperliquid_price = best_ask * 0.99995  # -0.005% en dessous du ask
                hyperliquid_price = round(float(f"{hyperliquid_price:.5g}"), 6)
                
                # Ne pas descendre sous le bid (sinon on devient taker)
                if hyperliquid_price <= best_bid:
                    hyperliquid_price = best_bid * 1.00005  # +0.005% au-dessus du bid
                    hyperliquid_price = round(float(f"{hyperliquid_price:.5g}"), 6)
                
                logger.info(f"\n📕 Hyperliquid UNDERCUT SELL @ ${hyperliquid_price:.6f} (bid={best_bid:.6f}, ask={best_ask:.6f})")
                
                # Annuler l'ordre précédent
                try:
                    hyperliquid.cancel_all_orders(symbol)
                    time.sleep(0.1)
                except:
                    pass
                
                # Placer le nouvel ordre
                result = hyperliquid.place_order(
                    symbol=symbol,
                    side="sell",
                    size=hyperliquid_size,
                    order_type="limit",
                    post_only=True,
                    price=hyperliquid_price
                )
                
                if result and result.get('status') == 'ok':
                    logger.success(f"   ✅ Hyperliquid placé")
                else:
                    logger.error(f"   ❌ Hyperliquid failed: {result}")
                    
            except Exception as e:
                logger.error(f"   ❌ Hyperliquid error: {e}")
        
        # =====================================================
        # CHECK FILLS
        # =====================================================
        time.sleep(0.5)  # Wait avant check
        
        if not extended_filled:
            filled, price = check_order_filled_fast(extended, "extended", {"order_id": extended_order_id}, symbol, order_timestamp)
            if filled and price:
                extended_filled = True
                extended_fill_price = price
                logger.success(f"\n🎉 EXTENDED FILLED @ ${price:.6f}")
        
        if not hyperliquid_filled:
            filled, price = check_order_filled_fast(hyperliquid, "hyperliquid", {}, symbol, order_timestamp)
            if filled and price:
                hyperliquid_filled = True
                hyperliquid_fill_price = price
                logger.success(f"\n🎉 HYPERLIQUID FILLED @ ${price:.6f}")
        
        # Si les deux filled → SUCCESS!
        if extended_filled and hyperliquid_filled:
            logger.success("\n✅✅ DELTA-NEUTRAL PARFAIT!")
            break
        
        # Si UN filled → SPAM l'autre agressivement
        if extended_filled and not hyperliquid_filled:
            logger.warning(f"\n⚠️  ASYMÉTRIQUE: Extended filled, SPAM Hyperliquid!")
            
            # Cancel existing
            try:
                hyperliquid.cancel_all_orders(symbol)
                time.sleep(0.1)
            except:
                pass
            
            # Place agressivement au prix Extended
            spam_price = extended_fill_price * 1.00001  # +0.001% au-dessus
            spam_price = round(float(f"{spam_price:.5g}"), 6)
            
            logger.info(f"   🔥 SPAM Hyperliquid @ ${spam_price:.6f}...")
            result = hyperliquid.place_order(
                symbol=symbol,
                side="sell",
                size=hyperliquid_size,
                order_type="limit",
                post_only=False,  # Accept TAKER
                price=spam_price
            )
            
            if result and result.get('status') == 'ok':
                logger.success(f"      ✅ Placé")
                time.sleep(0.5)
                filled, price = check_order_filled_fast(hyperliquid, "hyperliquid", result, symbol, order_timestamp)
                if filled and price:
                    hyperliquid_filled = True
                    hyperliquid_fill_price = price
                    logger.success(f"\n      🎉 HYPERLIQUID FILLED @ ${price:.6f}")
                    break
        
        elif hyperliquid_filled and not extended_filled:
            logger.warning(f"\n⚠️  ASYMÉTRIQUE: Hyperliquid filled, SPAM Extended!")
            
            # Cancel existing
            if extended_order_id:
                try:
                    extended.cancel_order(extended_order_id)
                    time.sleep(0.1)
                except:
                    pass
            
            # Place agressivement au prix Hyperliquid
            spam_price = hyperliquid_fill_price * 0.99999  # -0.001% en dessous
            spam_price = extended.round_price(symbol, spam_price)
            
            logger.info(f"   🔥 SPAM Extended @ ${spam_price:.6f}...")
            result = extended.place_order(
                symbol=symbol,
                side="buy",
                size=extended_size,
                order_type="limit",
                price=spam_price
            )
            
            if result and result.get('order_id'):
                extended_order_id = result['order_id']
                logger.success(f"      ✅ Placé (OID: {extended_order_id})")
                time.sleep(0.5)
                filled, price = check_order_filled_fast(extended, "extended", result, symbol, order_timestamp)
                if filled and price:
                    extended_filled = True
                    extended_fill_price = price
                    logger.success(f"\n      🎉 EXTENDED FILLED @ ${price:.6f}")
                    break
        
        # Rate limit safety
        time.sleep(0.3)
    
    # =================================================================
    # RÉSULTATS
    # =================================================================
    
    logger.info(f"\n{'='*100}")
    logger.info("📊 RÉSULTAT FINAL")
    logger.info(f"{'='*100}")
    
    logger.info(f"\n   Extended LONG: {'✅ FILLED' if extended_filled else '❌ PAS FILLED'}")
    logger.info(f"   Hyperliquid SHORT: {'✅ FILLED' if hyperliquid_filled else '❌ PAS FILLED'}")
    
    if extended_fill_price and hyperliquid_fill_price:
        price_diff = abs(extended_fill_price - hyperliquid_fill_price)
        price_diff_pct = (price_diff / extended_fill_price) * 100
        logger.info(f"\n   📊 PRIX DE FILL:")
        logger.info(f"      Extended LONG:     ${extended_fill_price:.6f}")
        logger.info(f"      Hyperliquid SHORT: ${hyperliquid_fill_price:.6f}")
        logger.info(f"      Différence: ${price_diff:.6f} ({price_diff_pct:.4f}%)")
        
        if price_diff_pct < 0.01:
            logger.success(f"   ✅ Delta-neutral PARFAIT! (< 0.01% diff)")
        elif price_diff_pct < 0.05:
            logger.success(f"   ✅ Delta-neutral EXCELLENT! ({price_diff_pct:.4f}% diff)")
        elif price_diff_pct < 0.1:
            logger.success(f"   ✅ Delta-neutral BON! ({price_diff_pct:.4f}% diff)")
        else:
            logger.warning(f"   ⚠️  Delta-neutral acceptable ({price_diff_pct:.4f}% diff)")
    
    if extended_filled and hyperliquid_filled:
        logger.success("\n   🎉 POSITION DELTA-NEUTRAL ACTIVE!")
        logger.info("\n   ⏳ Attente 10s avant fermeture...")
        time.sleep(10)
        
        # Close positions
        logger.info(f"\n📝 Fermeture MARKET...")
        extended.close_position(symbol, "market")
        hyperliquid.close_position(symbol, "market")
        logger.success("✅ Positions fermées")
    else:
        logger.error("\n   ❌ ÉCHEC: Delta-neutral incomplet")
        # Cancel remaining orders
        if not extended_filled and extended_order_id:
            extended.cancel_order(extended_order_id)
        if not hyperliquid_filled:
            try:
                hyperliquid.cancel_all_orders(symbol)
            except:
                pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Interrompu par l'utilisateur")
    except Exception as e:
        logger.error(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()

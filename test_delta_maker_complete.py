#!/usr/bin/env python3
"""
BOT DELTA-NEUTRAL MAKER COMPLET - ZORA
Avec retry, spam, monitoring, hedge automatique
"""
import json
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)

sys.path.insert(0, str(Path(__file__).parent))

from src.exchanges.extended_api import ExtendedAPI
from src.exchanges.hyperliquid_api import HyperliquidAPI


def check_order_status(extended: ExtendedAPI, hyperliquid: HyperliquidAPI,
                       extended_oid: int, hyperliquid_oid: int,
                       symbol: str) -> Tuple[bool, bool]:
    """
    Check si les ordres sont filled
    
    Returns:
        (extended_filled, hyperliquid_filled)
    """
    # Extended: check order by ID (SDK doesn't support list all orders)
    extended_filled = False
    try:
        order_info = extended.get_order_status(extended_oid)
        if not order_info:
            # Ordre n'existe plus dans le système, check position
            logger.info(f"   🔍 Extended: Ordre disparu, checking position...")
            time.sleep(2)
            
            positions = extended.get_positions()
            logger.info(f"   🔍 Positions trouvées: {[p.get('symbol') for p in positions]}")
            
            has_position = any(symbol.upper() in p.get('symbol', '').upper() for p in positions)
            if has_position:
                logger.success(f"   ✅ Extended: Ordre FILLED (position {symbol} existe)")
                extended_filled = True
            else:
                logger.warning(f"   ⚠️ Extended: Ordre disparu mais pas de position {symbol}")
        else:
            order_status = order_info.get('status', '').lower()
            filled_qty = order_info.get('filled_size', 0)
            total_qty = order_info.get('size', 0)
            
            logger.info(f"   🔍 Extended: status={order_status}, filled={filled_qty}/{total_qty}")
            
            if order_status in ['filled', 'completed']:
                logger.success(f"   ✅ Extended: Ordre FILLED (status={order_status})")
                extended_filled = True
            else:
                logger.info(f"   ⏳ Extended: Ordre {order_status} (not filled yet)")
    except Exception as e:
        logger.error(f"   ❌ Extended check error: {e}")
    
    # Hyperliquid: check open orders (NO SYMBOL parameter!)
    hyperliquid_filled = False
    try:
        open_orders = hyperliquid.get_open_orders()  # 🔥 PAS DE SYMBOL!
        # Si l'ordre n'est plus dans open_orders, c'est qu'il est filled
        order_exists = any(o.get('oid') == hyperliquid_oid for o in open_orders)
        
        if not order_exists:
            # Ordre disparu! Wait 2s et check position (peut prendre du temps à apparaître)
            logger.info(f"   🔍 Hyperliquid: Ordre disparu des open orders, checking position...")
            time.sleep(2)
            
            positions = hyperliquid.get_open_positions()
            logger.info(f"   🔍 Positions raw: {positions}")
            logger.info(f"   🔍 Positions coins: {[p.get('position', {}).get('coin') if isinstance(p, dict) else None for p in positions]}")
            
            # Check si symbol dans les positions
            has_position = False
            for p in positions:
                if isinstance(p, dict):
                    # Tenter plusieurs structures possibles
                    coin = p.get('coin') or p.get('position', {}).get('coin')
                    if coin == symbol:
                        has_position = True
                        break
            
            if has_position:
                logger.success(f"   ✅ Hyperliquid: Ordre FILLED (position {symbol} existe)")
                hyperliquid_filled = True
            else:
                logger.warning(f"   ⚠️ Hyperliquid: Ordre disparu mais pas de position {symbol} visible")
        else:
            logger.info(f"   ⏳ Hyperliquid: Ordre encore open (not filled)")
    except Exception as e:
        logger.error(f"   ❌ Hyperliquid check error: {e}")
    
    return extended_filled, hyperliquid_filled


def cancel_order(api, exchange_name: str, order_id, symbol: str) -> bool:
    """Cancel un ordre"""
    try:
        if exchange_name == "extended":
            # Extended cancel (needs symbol)
            result = api.cancel_order(order_id)
            if result:
                logger.success(f"   ✅ {exchange_name}: Ordre cancelled")
                return True
        else:  # hyperliquid
            # Hyperliquid cancel (only order_id, no symbol!)
            result = api.cancel_order(order_id)  # 🔥 Pas de symbol!
            if result:
                logger.success(f"   ✅ {exchange_name}: Ordre cancelled")
                return True
        logger.warning(f"   ⚠️ {exchange_name}: Cancel failed")
        return False
    except Exception as e:
        logger.error(f"   ❌ {exchange_name}: Cancel error: {e}")
        return False


def place_market_hedge(api, exchange_name: str, symbol: str, side: str, size: float) -> bool:
    """Place un ordre MARKET immédiat pour hedge"""
    try:
        logger.warning(f"\n🚨 HEDGE IMMÉDIAT: {exchange_name} {side.upper()} {size} {symbol} MARKET")
        result = api.place_order(
            symbol=symbol,
            side=side,
            size=size,
            order_type="market",
            price=None
        )
        if result and (result.get('order_id') or result.get('status') == 'ok'):
            logger.success(f"   ✅ Hedge placé!")
            return True
        logger.error(f"   ❌ Hedge failed: {result}")
        return False
    except Exception as e:
        logger.error(f"   ❌ Hedge error: {e}")
        return False


def main():
    logger.info("="*100)
    logger.info("🔥 BOT DELTA-NEUTRAL MAKER COMPLET - ZORA")
    logger.info("="*100)
    
    # Load config
    with open("config/config.json", "r") as f:
        config = json.load(f)
    
    wallet = config["wallet"]["address"]
    private_key = config["wallet"]["private_key"]
    extended_config = config["extended"]
    target_usd = config["auto_trading"]["position_size_usd"]
    
    logger.info(f"\n📝 Configuration:")
    logger.info(f"   Wallet: {wallet}")
    logger.info(f"   Target margin: ${target_usd} par exchange")
    
    # Init APIs
    logger.info(f"\n🔌 Init APIs...")
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
        logger.error("❌ Extended init failed")
        return
    
    logger.success("✅ APIs OK")
    
    # ZORA uniquement
    symbol = "ZORA"
    leverage = 3
    
    logger.info(f"\n📊 Symbole: {symbol}")
    logger.info(f"📊 Leverage: {leverage}x")
    
    # Get prices
    logger.info(f"\n📊 Get prices...")
    extended_ticker = extended.get_ticker(symbol)
    hyperliquid_ticker = hyperliquid.get_ticker(symbol)
    
    extended_bid = extended_ticker['bid']
    extended_ask = extended_ticker['ask']
    extended_mid = (extended_bid + extended_ask) / 2
    
    hyperliquid_bid = hyperliquid_ticker['bid']
    hyperliquid_ask = hyperliquid_ticker['ask']
    hyperliquid_mid = (hyperliquid_bid + hyperliquid_ask) / 2
    
    logger.success(f"✅ Extended: bid=${extended_bid:.6f}, ask=${extended_ask:.6f}, mid=${extended_mid:.6f}")
    logger.success(f"✅ Hyperliquid: bid=${hyperliquid_bid:.6f}, ask=${hyperliquid_ask:.6f}, mid=${hyperliquid_mid:.6f}")
    
    # Spread analysis
    extended_spread_pct = ((extended_ask - extended_bid) / extended_mid) * 100
    hyperliquid_spread_pct = ((hyperliquid_ask - hyperliquid_bid) / hyperliquid_mid) * 100
    cross_spread = extended_ask - hyperliquid_bid
    cross_spread_pct = (cross_spread / hyperliquid_bid) * 100
    
    logger.info(f"\n💰 SPREADS:")
    logger.info(f"   Extended spread: {extended_spread_pct:.3f}%")
    logger.info(f"   Hyperliquid spread: {hyperliquid_spread_pct:.3f}%")
    logger.info(f"   Cross-exchange (TAKER cost): {cross_spread_pct:.3f}%")
    
    # Calculate size
    notional = target_usd * leverage
    size = notional / extended_mid
    size = round(size, 0)  # 0 decimals for ZORA
    
    # Check minimum et arrondi Extended (100 par 100 pour ZORA)
    extended_min = 1000
    extended_increment = 100
    
    if size < extended_min:
        logger.warning(f"   ⚠️ Size {size} < min {extended_min}, using minimum")
        size = extended_min
    else:
        # Arrondir selon l'increment Extended (ex: 1043 → 1100)
        size = round(size / extended_increment) * extended_increment
        logger.info(f"   📊 Size arrondie selon Extended increment ({extended_increment}): {size}")
    
    logger.info(f"\n💰 Size SYNCHRONISÉE: {size} {symbol}")
    logger.info(f"   Extended LONG: {size} {symbol}")
    logger.info(f"   Hyperliquid SHORT: {size} {symbol}")
    logger.warning(f"   ⚠️ Extended arrondit automatiquement par {extended_increment}")
    logger.warning(f"   → Hyperliquid utilisera la MÊME size Extended pour delta-neutral parfait")
    
    # Confirm
    logger.warning(f"\n⚠️ STRATÉGIE MAKER:")
    logger.warning(f"   1. Place LIMIT au mid-price sur les deux")
    logger.warning(f"   2. Check fills toutes les 5s")
    logger.warning(f"   3. Si pas fill après 30s → retry avec offset plus agressif")
    logger.warning(f"   4. Si fill asymétrique → hedge MARKET immédiat")
    logger.warning(f"   5. Max 3 retry avant fallback TAKER")
    
    confirm = input(f"\n✅ Confirmer? (yes/no) [no]: ").strip().lower()
    if confirm != "yes":
        logger.info("❌ Annulé")
        return
    
    # BOUCLE DE RETRY
    max_retries = 3
    offsets = [0.0001, 0.0002, 0.0005]  # 0.01%, 0.02%, 0.05%
    
    for retry in range(max_retries):
        offset = offsets[retry] if retry < len(offsets) else offsets[-1]
        
        logger.info(f"\n{'='*100}")
        logger.info(f"📝 TENTATIVE {retry + 1}/{max_retries} (offset ±{offset*100:.2f}%)")
        logger.info(f"{'='*100}")
        
        # Calculate prices with offset
        extended_limit_price = extended_mid * (1 - offset)
        hyperliquid_limit_price = hyperliquid_mid * (1 + offset)
        
        logger.info(f"\n1️⃣ Extended LONG {size} {symbol} @ ${extended_limit_price:.6f} (mid - {offset*100:.2f}%)")
        
        extended_result = extended.place_order(
            symbol=symbol,
            side="buy",
            size=size,
            order_type="limit",
            price=extended_limit_price
        )
        
        if not extended_result or not extended_result.get('order_id'):
            logger.error(f"   ❌ Extended order failed: {extended_result}")
            continue
        
        extended_oid = extended_result['order_id']
        # 🔥 RÉCUPÉRER LA SIZE RÉELLE ARRONDIE PAR EXTENDED!
        extended_real_size = extended_result.get('size', size)
        logger.success(f"   ✅ Extended OID: {extended_oid}")
        
        if extended_real_size != size:
            logger.warning(f"   ⚠️ Extended a arrondi: {size} → {extended_real_size}")
        
        time.sleep(2)
        
        logger.info(f"\n2️⃣ Hyperliquid SHORT {extended_real_size} {symbol} @ ${hyperliquid_limit_price:.6f} (mid + {offset*100:.2f}%)")
        
        hyperliquid_result = hyperliquid.place_order(
            symbol=symbol,
            side="sell",
            size=extended_real_size,  # 🔥 UTILISER LA SIZE EXTENDED!
            order_type="limit",
            price=hyperliquid_limit_price
        )
        
        if not hyperliquid_result or hyperliquid_result.get('status') != 'ok':
            logger.error(f"   ❌ Hyperliquid order failed: {hyperliquid_result}")
            # Cancel Extended
            cancel_order(extended, "extended", extended_oid, symbol)
            continue
        
        # Extract Hyperliquid OID
        hyperliquid_oid = None
        try:
            statuses = hyperliquid_result['response']['data']['statuses']
            if statuses and 'resting' in statuses[0]:
                hyperliquid_oid = statuses[0]['resting']['oid']
            logger.success(f"   ✅ Hyperliquid OID: {hyperliquid_oid}")
        except Exception as e:
            logger.error(f"   ❌ Can't extract HL OID: {e}")
            cancel_order(extended, "extended", extended_oid, symbol)
            continue
        
        # MONITORING LOOP (30s timeout)
        logger.info(f"\n{'='*100}")
        logger.info(f"⏳ MONITORING FILLS (30s timeout)...")
        logger.info(f"{'='*100}")
        
        timeout = 30
        check_interval = 5
        elapsed = 0
        
        extended_filled = False
        hyperliquid_filled = False
        
        while elapsed < timeout:
            remaining = timeout - elapsed
            logger.info(f"\n   ⏰ {remaining}s restantes...")
            
            time.sleep(check_interval)
            elapsed += check_interval
            
            # Check status
            extended_filled, hyperliquid_filled = check_order_status(
                extended, hyperliquid, extended_oid, hyperliquid_oid, symbol
            )
            
            # BOTH FILLED → SUCCESS!
            if extended_filled and hyperliquid_filled:
                logger.success(f"\n🎉 LES DEUX ORDRES SONT FILLED!")
                logger.success(f"✅ DELTA-NEUTRAL ÉTABLI!")
                return
            
            # ONE FILLED → HEDGE IMMÉDIAT!
            elif extended_filled and not hyperliquid_filled:
                logger.warning(f"\n🚨 Extended filled MAIS Hyperliquid pas filled!")
                logger.warning(f"   → Cancel Hyperliquid et hedge MARKET")
                
                cancel_order(hyperliquid, "hyperliquid", hyperliquid_oid, symbol)
                time.sleep(1)
                
                # 🔥 UTILISER LA SIZE EXTENDED RÉELLE!
                if place_market_hedge(hyperliquid, "hyperliquid", symbol, "sell", extended_real_size):
                    logger.success(f"✅ DELTA-NEUTRAL ÉTABLI (avec hedge MARKET)")
                    return
                else:
                    logger.error(f"❌ Hedge failed! POSITION NON HEDGE!")
                    return
            
            elif hyperliquid_filled and not extended_filled:
                logger.warning(f"\n🚨 Hyperliquid filled MAIS Extended pas filled!")
                logger.warning(f"   → Cancel Extended et hedge MARKET")
                
                cancel_order(extended, "extended", extended_oid, symbol)
                time.sleep(1)
                
                # 🔥 UTILISER LA SIZE EXTENDED RÉELLE!
                if place_market_hedge(extended, "extended", symbol, "buy", extended_real_size):
                    logger.success(f"✅ DELTA-NEUTRAL ÉTABLI (avec hedge MARKET)")
                    return
                else:
                    logger.error(f"❌ Hedge failed! POSITION NON HEDGE!")
                    return
        
        # TIMEOUT → Cancel et retry
        logger.warning(f"\n⏰ TIMEOUT! Pas de fill après {timeout}s")
        logger.info(f"   → Cancel les deux ordres et retry avec offset plus agressif...")
        
        cancel_order(extended, "extended", extended_oid, symbol)
        cancel_order(hyperliquid, "hyperliquid", hyperliquid_oid, symbol)
        
        time.sleep(2)
    
    # Si on arrive ici, aucun retry n'a fonctionné
    logger.error(f"\n❌ ÉCHEC après {max_retries} tentatives!")
    logger.warning(f"   → Fallback TAKER pour garantir le fill...")
    
    # FALLBACK TAKER
    logger.info(f"\n{'='*100}")
    logger.info(f"🔥 FALLBACK TAKER (exécution garantie)")
    logger.info(f"{'='*100}")
    
    logger.info(f"\n1️⃣ Extended LONG {size} {symbol} MARKET")
    extended_result = extended.place_order(
        symbol=symbol,
        side="buy",
        size=size,
        order_type="market",
        price=None
    )
    
    if not extended_result or not extended_result.get('order_id'):
        logger.error(f"   ❌ Extended TAKER failed!")
        return
    
    # 🔥 RÉCUPÉRER LA SIZE RÉELLE EXTENDED!
    extended_real_size = extended_result.get('size', size)
    logger.success(f"   ✅ Extended TAKER placé: {extended_real_size} {symbol}")
    
    time.sleep(2)
    
    logger.info(f"\n2️⃣ Hyperliquid SHORT {extended_real_size} {symbol} MARKET")
    hyperliquid_result = hyperliquid.place_order(
        symbol=symbol,
        side="sell",
        size=extended_real_size,  # 🔥 UTILISER LA SIZE EXTENDED!
        order_type="market",
        price=None
    )
    
    if not hyperliquid_result or hyperliquid_result.get('status') != 'ok':
        logger.error(f"   ❌ Hyperliquid TAKER failed!")
        logger.error(f"   🚨 POSITION NON HEDGE SUR EXTENDED!")
        return
    
    logger.success(f"   ✅ Hyperliquid TAKER placé")
    logger.success(f"\n✅ DELTA-NEUTRAL ÉTABLI (TAKER fallback)")
    
    # Note sur le coût
    cross_cost = (target_usd * leverage * 2) * (cross_spread_pct / 100)
    logger.warning(f"\n💸 Coût du spread TAKER: ${cross_cost:.2f}")
    logger.warning(f"   (cross-spread {cross_spread_pct:.3f}% sur ${target_usd * leverage * 2:,})")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("\n⚠️ Interrupted")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"❌ Error: {e}")
        sys.exit(1)

#!/usr/bin/env python3
"""
TEST RENTABILITÉ DELTA-NEUTRAL OPEN → WAIT 5min → CLOSE
Pour calculer si l'arbitrage funding est rentable après spreads et fees
"""
import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

try:
    from loguru import logger
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.INFO)

sys.path.insert(0, str(Path(__file__).parent))

from src.exchanges.extended_api import ExtendedAPI
from src.exchanges.hyperliquid_api import HyperliquidAPI


def get_position_info(extended: ExtendedAPI, hyperliquid: HyperliquidAPI, symbol: str) -> Dict:
    """Récupère les infos de positions des deux exchanges"""
    result = {
        'extended': None,
        'hyperliquid': None
    }
    
    # Extended
    try:
        positions = extended.get_positions()
        for p in positions:
            if symbol.upper() in p.get('symbol', '').upper():
                result['extended'] = {
                    'size': float(p.get('size', 0)),
                    'side': p.get('side'),
                    'entry_price': float(p.get('entry_price', 0)),
                    'unrealized_pnl': float(p.get('unrealized_pnl', 0)),
                    'value': float(p.get('notional', 0))
                }
                break
    except Exception as e:
        logger.error(f"Error getting Extended position: {e}")
    
    # Hyperliquid
    try:
        positions = hyperliquid.get_open_positions()
        for p in positions:
            if isinstance(p, dict) and 'position' in p:
                pos = p['position']
                if pos.get('coin') == symbol:
                    result['hyperliquid'] = {
                        'size': abs(float(pos.get('szi', 0))),
                        'side': 'SHORT' if float(pos.get('szi', 0)) < 0 else 'LONG',
                        'entry_price': float(pos.get('entryPx', 0)),
                        'unrealized_pnl': float(pos.get('unrealizedPnl', 0)),
                        'value': float(pos.get('positionValue', 0)),
                        'cum_funding': float(pos.get('cumFunding', {}).get('sinceOpen', 0))
                    }
                    break
    except Exception as e:
        logger.error(f"Error getting Hyperliquid position: {e}")
    
    return result


def close_position_maker(extended: ExtendedAPI, hyperliquid: HyperliquidAPI, 
                         symbol: str, size: float, 
                         extended_side: str, hyperliquid_side: str) -> bool:
    """
    Close les positions en MAKER (LIMIT orders) avec retry si post-only reject
    
    Args:
        extended_side: 'buy' ou 'sell' pour closer Extended
        hyperliquid_side: 'buy' ou 'sell' pour closer Hyperliquid
    """
    logger.info(f"\n{'='*100}")
    logger.info(f"🔒 CLOSING POSITIONS EN MAKER")
    logger.info(f"{'='*100}")
    
    # Retry strategy
    max_attempts = 3
    offsets = [0.0001, 0.0003, 0.001]  # 0.01%, 0.03%, 0.1%
    
    extended_result = None
    hyperliquid_result = None
    
    # ====== EXTENDED CLOSE AVEC RETRY ======
    for attempt in range(max_attempts):
        offset = offsets[attempt]
        
        # Get fresh prices
        extended_ticker = extended.get_ticker(symbol)
        extended_bid = extended_ticker['bid']
        extended_ask = extended_ticker['ask']
        
        # Price selon side AVEC OFFSET pour éviter post-only reject
        if extended_side.lower() == 'sell':
            # SELL → ASK + offset (plus cher = MAKER garanti)
            extended_price = extended_ask * (1 + offset)
        else:  # buy
            # BUY → BID - offset (moins cher = MAKER garanti)
            extended_price = extended_bid * (1 - offset)
        
        logger.info(f"\n1️⃣ Extended {extended_side.upper()} {size} {symbol} @ ${extended_price:.6f} (attempt {attempt+1}/{max_attempts})")
        
        try:
            extended_result = extended.place_order(
                symbol=symbol,
                side=extended_side,
                size=size,
                order_type="limit",
                price=extended_price,
                reduce_only=True
            )
            
            if extended_result and extended_result.get('order_id'):
                logger.success(f"   ✅ Extended close placed: {extended_result['order_id']}")
                break
            else:
                logger.warning(f"   ⚠️ Extended failed (attempt {attempt+1})")
        except Exception as e:
            error_msg = str(e).lower()
            if 'post-only' in error_msg or 'post_only' in error_msg:
                logger.warning(f"   ⚠️ Post-only rejection (attempt {attempt+1})")
                if attempt < max_attempts - 1:
                    logger.info(f"   → Retry avec offset {offsets[attempt+1]*100:.3f}%...")
                    time.sleep(1)
                    continue
            else:
                logger.error(f"   ❌ Error: {e}")
    
    # TAKER fallback si tous les MAKER échouent
    if not extended_result or not extended_result.get('order_id'):
        logger.error(f"\n❌ MAKER échoué après {max_attempts} tentatives")
        logger.error(f"   ⚠️ PAS DE TAKER! (fees trop élevées)")
        logger.error(f"   → Utilise clean_and_close.py pour fermer manuellement")
        return False
    
    time.sleep(2)
    
    # ====== HYPERLIQUID CLOSE ======
    hyperliquid_ticker = hyperliquid.get_ticker(symbol)
    hyperliquid_bid = hyperliquid_ticker['bid']
    hyperliquid_ask = hyperliquid_ticker['ask']
    
    if hyperliquid_side.lower() == 'sell':
        hyperliquid_price = hyperliquid_ask * 1.0001
    else:  # buy
        hyperliquid_price = hyperliquid_bid * 0.9999
    
    logger.info(f"\n2️⃣ Hyperliquid {hyperliquid_side.upper()} {size} {symbol} @ ${hyperliquid_price:.6f}")
    
    hyperliquid_result = hyperliquid.place_order(
        symbol=symbol,
        side=hyperliquid_side,
        size=size,
        order_type="limit",
        price=hyperliquid_price,
        reduce_only=True
    )
    
    if not hyperliquid_result or hyperliquid_result.get('status') != 'ok':
        logger.error(f"   ❌ Hyperliquid close failed")
        return False
    
    logger.success(f"   ✅ Hyperliquid close placed")
    
    # Wait for fills avec SPAM strategy
    logger.info(f"\n⏳ Waiting for close fills avec SPAM...")
    
    max_cycles = 6  # 6 cycles = ~60s
    check_interval = 10
    
    for cycle in range(max_cycles):
        time.sleep(check_interval)
        
        logger.info(f"\n   🔄 Cycle {cycle+1}/{max_cycles} (checking close fills...)")
        
        # Check if positions closed
        positions_check = get_position_info(extended, hyperliquid, symbol)
        
        if not positions_check['extended'] and not positions_check['hyperliquid']:
            logger.success(f"\n✅ LES DEUX POSITIONS SONT CLOSES!")
            return True
        
        # Si Extended pas closed, re-place
        if positions_check['extended'] and extended_result and extended_result.get('order_id'):
            logger.warning(f"      ⚠️ Extended pas closed → Cancel + Re-place")
            try:
                extended.cancel_order(extended_result['order_id'])
                time.sleep(1)
                
                # Get fresh prices
                extended_ticker_new = extended.get_ticker(symbol)
                
                # Re-place avec offset progressif pour éviter post-only reject
                retry_offset = 0.0001 * (cycle + 1)  # 0.01%, 0.02%, 0.03%...
                
                if extended_side.lower() == 'sell':
                    new_price = extended_ticker_new['ask'] * (1 + retry_offset)
                else:
                    new_price = extended_ticker_new['bid'] * (1 - retry_offset)
                
                logger.info(f"      🔄 Re-place Extended {extended_side.upper()} @ ${new_price:.6f} (offset={retry_offset*100:.2f}%)")
                extended_result = extended.place_order(
                    symbol=symbol,
                    side=extended_side,
                    size=size,
                    order_type="limit",
                    price=new_price,
                    reduce_only=True
                )
                if extended_result and extended_result.get('order_id'):
                    logger.success(f"      ✅ Extended re-placed: {extended_result['order_id']}")
                else:
                    logger.error(f"      ❌ Extended re-place failed - pas d'order_id")
            except Exception as e:
                logger.error(f"      ❌ Extended re-place failed: {e}")
        else:
            logger.success(f"      ✅ Extended CLOSED!")
        
        # Si Hyperliquid pas closed, re-place
        if positions_check['hyperliquid']:
            logger.warning(f"      ⚠️ Hyperliquid pas closed → Re-place")
            # Note: on peut pas facilement cancel/re-place HL sans OID tracking
            # On attend juste
            logger.info(f"      ⏳ Waiting for HL fill...")
        else:
            logger.success(f"      ✅ Hyperliquid CLOSED!")
    
    logger.warning(f"\n⚠️ Timeout close après {max_cycles} cycles")
    return True


def main():
    logger.info("="*100)
    logger.info("🧪 TEST RENTABILITÉ: OPEN → WAIT 5min → CLOSE")
    logger.info("="*100)
    
    # Load config
    with open("config/config.json", "r") as f:
        config = json.load(f)
    
    wallet = config["wallet"]["address"]
    private_key = config["wallet"]["private_key"]
    extended_config = config["extended"]
    target_usd = config["auto_trading"]["position_size_usd"]
    
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
    
    logger.success("✅ APIs OK")
    
    symbol = "ZORA"
    leverage = 3
    
    # =====================================================================
    # PHASE 1: GET INITIAL STATE
    # =====================================================================
    logger.info(f"\n{'='*100}")
    logger.info(f"📊 PHASE 1: ÉTAT INITIAL")
    logger.info(f"{'='*100}")
    
    extended_ticker = extended.get_ticker(symbol)
    hyperliquid_ticker = hyperliquid.get_ticker(symbol)
    
    extended_bid_0 = extended_ticker['bid']
    extended_ask_0 = extended_ticker['ask']
    extended_mid_0 = (extended_bid_0 + extended_ask_0) / 2
    
    hyperliquid_bid_0 = hyperliquid_ticker['bid']
    hyperliquid_ask_0 = hyperliquid_ticker['ask']
    hyperliquid_mid_0 = (hyperliquid_bid_0 + hyperliquid_ask_0) / 2
    
    # Spreads
    extended_spread_0 = extended_ask_0 - extended_bid_0
    extended_spread_pct_0 = (extended_spread_0 / extended_mid_0) * 100
    
    hyperliquid_spread_0 = hyperliquid_ask_0 - hyperliquid_bid_0
    hyperliquid_spread_pct_0 = (hyperliquid_spread_0 / hyperliquid_mid_0) * 100
    
    cross_spread_0 = extended_ask_0 - hyperliquid_bid_0
    cross_spread_pct_0 = (cross_spread_0 / hyperliquid_bid_0) * 100
    
    logger.info(f"\n💰 PRIX INITIAUX:")
    logger.info(f"   Extended: bid=${extended_bid_0:.6f}, ask=${extended_ask_0:.6f}, mid=${extended_mid_0:.6f}")
    logger.info(f"   Hyperliquid: bid=${hyperliquid_bid_0:.6f}, ask=${hyperliquid_ask_0:.6f}, mid=${hyperliquid_mid_0:.6f}")
    logger.info(f"\n💰 SPREADS INITIAUX:")
    logger.info(f"   Extended: {extended_spread_pct_0:.3f}% (${extended_spread_0:.6f})")
    logger.info(f"   Hyperliquid: {hyperliquid_spread_pct_0:.3f}% (${hyperliquid_spread_0:.6f})")
    logger.info(f"   Cross-exchange: {cross_spread_pct_0:.3f}% (${cross_spread_0:.6f})")
    
    # Get funding rates
    extended_funding = extended.get_funding_rate(symbol)
    hyperliquid_funding = hyperliquid.get_funding_rate(symbol)
    
    # Extended retourne float, Hyperliquid retourne dict
    extended_funding_rate = extended_funding if isinstance(extended_funding, (int, float)) else 0
    hyperliquid_funding_rate = hyperliquid_funding.get('rate', 0) if isinstance(hyperliquid_funding, dict) else 0
    
    # Calcul funding arbitrage (LONG Extended + SHORT Hyperliquid)
    # LONG Extended: on paye si funding positif, on reçoit si négatif
    # SHORT Hyperliquid: on paye si funding négatif, on reçoit si positif
    funding_arb_rate = -extended_funding_rate + (-hyperliquid_funding_rate)
    
    logger.info(f"\n💰 FUNDING RATES (1h):")
    logger.info(f"   Extended: {extended_funding_rate*100:.4f}% (LONG → paye {extended_funding_rate*100:.4f}%)")
    logger.info(f"   Hyperliquid: {hyperliquid_funding_rate*100:.4f}% (SHORT → paye {hyperliquid_funding_rate*100:.4f}%)")
    logger.info(f"   📊 Arbitrage net: {funding_arb_rate*100:.4f}%/h")
    
    # Calculate size
    notional = target_usd * leverage
    size = notional / extended_mid_0
    size = round(size / 100) * 100  # Arrondi Extended
    size = max(size, 1000)
    
    logger.info(f"\n💰 SIZE: {size} {symbol}")
    logger.info(f"   Notional: ${notional:.2f}")
    
    # =====================================================================
    # PHASE 2: OPEN POSITIONS EN MAKER
    # =====================================================================
    logger.info(f"\n{'='*100}")
    logger.info(f"📊 PHASE 2: OUVERTURE POSITIONS EN MAKER")
    logger.info(f"{'='*100}")
    
    logger.warning(f"\n⚠️ PLAN:")
    logger.warning(f"   1. OPEN delta-neutral MAKER (LONG Extended + SHORT Hyperliquid)")
    logger.warning(f"   2. WAIT 5 minutes")
    logger.warning(f"   3. CLOSE en MAKER")
    logger.warning(f"   4. AFFICHE rentabilité (funding - spreads - fees)")
    
    confirm = input(f"\n✅ Lancer le test complet? (yes/no) [no]: ").strip().lower()
    if confirm != "yes":
        logger.info("❌ Annulé")
        return
    
    # OPEN MAKER orders
    # 🔥 Pour éviter "post-only rejection", utiliser BID/ASK au lieu de mid±offset
    # BUY Extended: utiliser BID (prix dans l'orderbook, pas de match immédiat)
    # SELL Hyperliquid: utiliser ASK (prix dans l'orderbook)
    
    extended_open_price = extended_bid_0  # BUY au BID = MAKER garanti
    hyperliquid_open_price = hyperliquid_ask_0  # SELL au ASK = MAKER garanti
    
    logger.info(f"\n1️⃣ Extended LONG {size} {symbol} @ ${extended_open_price:.6f} (BID)")
    extended_result = extended.place_order(
        symbol=symbol,
        side="buy",
        size=size,
        order_type="limit",
        price=extended_open_price
    )
    
    if not extended_result or not extended_result.get('order_id'):
        logger.error(f"   ❌ Extended order failed")
        return
    
    extended_real_size = extended_result.get('size', size)
    logger.success(f"   ✅ Extended OID: {extended_result['order_id']} (size: {extended_real_size})")
    
    time.sleep(2)
    
    logger.info(f"\n2️⃣ Hyperliquid SHORT {extended_real_size} {symbol} @ ${hyperliquid_open_price:.6f} (ASK)")
    hyperliquid_result = hyperliquid.place_order(
        symbol=symbol,
        side="sell",
        size=extended_real_size,
        order_type="limit",
        price=hyperliquid_open_price
    )
    
    if not hyperliquid_result or hyperliquid_result.get('status') != 'ok':
        logger.error(f"   ❌ Hyperliquid order failed")
        return
    
    logger.success(f"   ✅ Hyperliquid order placed")
    
    # Check if Hyperliquid filled immediately
    hyperliquid_filled_immediately = False
    hyperliquid_oid = None
    try:
        statuses = hyperliquid_result['response']['data']['statuses']
        if 'filled' in statuses[0]:
            # FILLED immédiatement!
            hyperliquid_filled_immediately = True
            hyperliquid_oid = statuses[0]['filled']['oid']
            logger.warning(f"\n🚨 Hyperliquid FILLED IMMÉDIATEMENT @ ${statuses[0]['filled']['avgPx']}")
        elif 'resting' in statuses[0]:
            hyperliquid_oid = statuses[0]['resting']['oid']
            logger.info(f"   Hyperliquid OID: {hyperliquid_oid} (resting)")
    except Exception as e:
        logger.warning(f"   ⚠️ Can't extract Hyperliquid OID: {e}")
    
    # Si Hyperliquid filled immédiatement, cancel Extended et re-place MAKER
    if hyperliquid_filled_immediately:
        logger.warning(f"\n🚨 Hyperliquid filled MAIS Extended pas filled!")
        logger.warning(f"   → Cancel Extended et attendre que MAKER fill naturellement")
        logger.warning(f"   ⚠️ PAS DE TAKER! (fees trop élevées)")
        
        # Cancel Extended
        try:
            extended.cancel_order(extended_result['order_id'])
            logger.success(f"   ✅ Extended order cancelled")
        except Exception as e:
            logger.error(f"   ❌ Cancel failed: {e}")
        
        time.sleep(2)
        
        # Re-place MAKER Extended avec meilleur prix (BID - small offset pour fill plus vite)
        extended_ticker_new = extended.get_ticker(symbol)
        extended_bid_new = extended_ticker_new['bid']
        extended_ask_new = extended_ticker_new['ask']
        
        # BUY @ BID (MAKER garanti, meilleur que mid)
        extended_price_retry = extended_bid_new
        
        logger.info(f"\n� Re-place Extended MAKER BUY @ ${extended_price_retry:.6f}")
        hedge_result = extended.place_order(
            symbol=symbol,
            side="buy",
            size=extended_real_size,
            order_type="limit",
            price=extended_price_retry,
            post_only=True
        )
        
        if not hedge_result or not hedge_result.get('order_id'):
            logger.error(f"   ❌ Re-place failed! ABORT")
            return
        
        logger.success(f"   ✅ Extended MAKER re-placed: {hedge_result['order_id']}")
        logger.info(f"   ⏳ Attente fill naturel (peut prendre 1-2min)...")
        
        # Continue avec wait pour que Extended fill
        extended_oid = hedge_result['order_id']
    else:
        # Wait for fills avec SPAM strategy (cancel + re-place si pas filled)
        logger.info(f"\n⏳ Attente des fills avec SPAM strategy...")
        logger.warning(f"   🔄 Cancel + Re-place toutes les 10s si pas filled")
        
        max_cycles = 10  # 10 cycles max = ~100s
        check_interval = 10  # Check toutes les 10s
        cycle = 0
        
        positions_start = None
        extended_oid = extended_result['order_id']
        
        # Extract Hyperliquid OID
        try:
            statuses = hyperliquid_result['response']['data']['statuses']
            hyperliquid_oid = statuses[0]['resting']['oid']
        except:
            hyperliquid_oid = None
            logger.warning("   ⚠️ Can't extract Hyperliquid OID")
        
        while cycle < max_cycles:
            time.sleep(check_interval)
            cycle += 1
            
            logger.info(f"\n   🔄 Cycle {cycle}/{max_cycles} (checking fills...)")
            
            # Check positions first
            positions_check = get_position_info(extended, hyperliquid, symbol)
            if positions_check['extended'] and positions_check['hyperliquid']:
                logger.success(f"\n✅ LES DEUX POSITIONS SONT FILLED!")
                positions_start = positions_check
                break
            
            # Check Extended
            extended_filled = positions_check['extended'] is not None
            if not extended_filled:
                logger.warning(f"      ⚠️ Extended pas filled → Cancel + Re-place")
                try:
                    extended.cancel_order(extended_oid)
                    time.sleep(1)
                    
                    # Re-place @ BID exact
                    extended_ticker_new = extended.get_ticker(symbol)
                    extended_bid_new = extended_ticker_new['bid']
                    
                    logger.info(f"      🔄 Re-place Extended BUY @ ${extended_bid_new:.6f}")
                    extended_result_new = extended.place_order(
                        symbol=symbol,
                        side="buy",
                        size=extended_real_size,
                        order_type="limit",
                        price=extended_bid_new
                    )
                    
                    if extended_result_new and extended_result_new.get('order_id'):
                        extended_oid = extended_result_new['order_id']
                        logger.success(f"      ✅ Extended re-placed: {extended_oid}")
                except Exception as e:
                    logger.error(f"      ❌ Extended re-place failed: {e}")
            else:
                logger.success(f"      ✅ Extended FILLED!")
            
            # Check Hyperliquid
            hyperliquid_filled = positions_check['hyperliquid'] is not None
            if not hyperliquid_filled and hyperliquid_oid:
                logger.warning(f"      ⚠️ Hyperliquid pas filled → Cancel + Re-place AGRESSIF")
                try:
                    # 1. Cancel l'ordre existant
                    hl_open = hyperliquid.get_open_orders()
                    order_exists = any(o.get('oid') == hyperliquid_oid for o in hl_open)
                    
                    if order_exists:
                        logger.info(f"      🗑️ Cancel order {hyperliquid_oid}")
                        hyperliquid.cancel_order(hyperliquid_oid)
                        time.sleep(1)
                    
                    # 2. Re-place AGRESSIF: ASK - 0.1% pour fill rapidement
                    hyperliquid_ticker_new = hyperliquid.get_ticker(symbol)
                    hyperliquid_ask_new = hyperliquid_ticker_new['ask']
                    hyperliquid_bid_new = hyperliquid_ticker_new['bid']
                    
                    # SHORT = SELL plus agressif que ASK (plus proche du BID)
                    aggressive_price = hyperliquid_ask_new * 0.999  # ASK - 0.1%
                    
                    logger.info(f"      🔄 Re-place Hyperliquid SELL @ ${aggressive_price:.6f} (ASK={hyperliquid_ask_new:.6f}, BID={hyperliquid_bid_new:.6f})")
                    hyperliquid_result_new = hyperliquid.place_order(
                        symbol=symbol,
                        side="sell",
                        size=extended_real_size,
                        order_type="limit",
                        price=aggressive_price
                    )
                    
                    if hyperliquid_result_new and hyperliquid_result_new.get('status') == 'ok':
                        # Extract new OID and check if filled/partial
                        try:
                            statuses = hyperliquid_result_new['response']['data']['statuses']
                            if 'filled' in statuses[0]:
                                filled_size = float(statuses[0]['filled']['totalSz'])
                                logger.success(f"      ✅ Hyperliquid FILLED: {filled_size} ZORA")
                                
                                # Check si partial fill
                                if filled_size < extended_real_size * 0.95:  # Si < 95% du target
                                    remaining = extended_real_size - filled_size
                                    logger.warning(f"      ⚠️ PARTIAL FILL! Manque {remaining:.1f} ZORA")
                                    logger.warning(f"      → Re-place le reste en MARKET pour garantir full fill")
                                    
                                    time.sleep(1)
                                    
                                    # Place le reste en MARKET
                                    market_result = hyperliquid.place_order(
                                        symbol=symbol,
                                        side="sell",
                                        size=remaining,
                                        order_type="market",
                                        price=None
                                    )
                                    
                                    if market_result and market_result.get('status') == 'ok':
                                        logger.success(f"      ✅ Reste placé en MARKET: {remaining:.1f} ZORA")
                                    else:
                                        logger.error(f"      ❌ MARKET order failed!")
                                else:
                                    hyperliquid_filled = True
                                    
                            elif 'resting' in statuses[0]:
                                hyperliquid_oid = statuses[0]['resting']['oid']
                                logger.success(f"      ✅ Hyperliquid re-placed: {hyperliquid_oid}")
                        except Exception as e:
                            logger.error(f"      ❌ Error parsing result: {e}")
                except Exception as e:
                    logger.error(f"      ❌ Hyperliquid re-place failed: {e}")
            else:
                if hyperliquid_filled:
                    logger.success(f"      ✅ Hyperliquid FILLED!")
        
        if not positions_start or not positions_start['extended'] or not positions_start['hyperliquid']:
            logger.error(f"\n❌ Timeout après {max_cycles} cycles!")
            logger.error(f"   → ABORT (utilise clean_and_close.py)")
            return
    
    logger.success(f"\n✅ Positions ouvertes:")
    logger.info(f"   Extended: {positions_start['extended']['side']} {positions_start['extended']['size']} @ ${positions_start['extended']['entry_price']:.6f}")
    logger.info(f"   Hyperliquid: {positions_start['hyperliquid']['side']} {positions_start['hyperliquid']['size']} @ ${positions_start['hyperliquid']['entry_price']:.6f}")
    
    # Update size avec la vraie size
    size = positions_start['extended']['size']
    
    # =====================================================================
    # PHASE 3: WAIT 5 MINUTES
    # =====================================================================
    logger.info(f"\n{'='*100}")
    logger.info(f"⏰ PHASE 3: ATTENTE 5 MINUTES")
    logger.info(f"{'='*100}")
    
    wait_time = 5 * 60  # 5 minutes
    start_time = datetime.now()
    end_time = start_time + timedelta(seconds=wait_time)
    
    logger.info(f"\n⏳ Début: {start_time.strftime('%H:%M:%S')}")
    logger.info(f"⏳ Fin prévue: {end_time.strftime('%H:%M:%S')}")
    
    # Update toutes les 30s
    update_interval = 30
    elapsed = 0
    
    while elapsed < wait_time:
        remaining = wait_time - elapsed
        logger.info(f"\n⏰ {remaining}s restantes... (check positions)")
        
        # Check positions
        positions_current = get_position_info(extended, hyperliquid, symbol)
        
        if positions_current['extended']:
            logger.info(f"   Extended PnL: ${positions_current['extended']['unrealized_pnl']:.3f}")
        
        if positions_current['hyperliquid']:
            logger.info(f"   Hyperliquid PnL: ${positions_current['hyperliquid']['unrealized_pnl']:.3f}")
            logger.info(f"   Hyperliquid Funding: ${positions_current['hyperliquid']['cum_funding']:.6f}")
        
        time.sleep(update_interval)
        elapsed += update_interval
    
    logger.success(f"\n⏰ 5 minutes écoulées!")
    
    # =====================================================================
    # PHASE 4: GET FINAL STATE BEFORE CLOSE
    # =====================================================================
    logger.info(f"\n{'='*100}")
    logger.info(f"📊 PHASE 4: ÉTAT AVANT CLOSE")
    logger.info(f"{'='*100}")
    
    positions_before_close = get_position_info(extended, hyperliquid, symbol)
    
    extended_pnl = positions_before_close['extended']['unrealized_pnl'] if positions_before_close['extended'] else 0
    hyperliquid_pnl = positions_before_close['hyperliquid']['unrealized_pnl'] if positions_before_close['hyperliquid'] else 0
    hyperliquid_funding = positions_before_close['hyperliquid']['cum_funding'] if positions_before_close['hyperliquid'] else 0
    
    logger.info(f"\n💰 PnL AVANT CLOSE:")
    logger.info(f"   Extended: ${extended_pnl:.3f}")
    logger.info(f"   Hyperliquid: ${hyperliquid_pnl:.3f}")
    logger.info(f"   Hyperliquid Funding: ${hyperliquid_funding:.6f}")
    logger.info(f"   📊 TOTAL: ${extended_pnl + hyperliquid_pnl:.3f}")
    
    # =====================================================================
    # PHASE 5: CLOSE POSITIONS
    # =====================================================================
    actual_size = positions_before_close['extended']['size'] if positions_before_close['extended'] else size
    
    # Pour closer: inverse du side d'ouverture
    # Si Extended était LONG → SELL pour closer
    # Si Hyperliquid était SHORT → BUY pour closer
    extended_close_side = 'sell' if positions_start['extended']['side'].upper() == 'LONG' else 'buy'
    hyperliquid_close_side = 'buy' if positions_start['hyperliquid']['side'].upper() == 'SHORT' else 'sell'
    
    success = close_position_maker(
        extended, hyperliquid, symbol, actual_size,
        extended_close_side, hyperliquid_close_side
    )
    
    if not success:
        logger.error(f"❌ Close failed!")
        return
    
    logger.info(f"\n⏳ Attente 15s pour les fills...")
    time.sleep(15)
    
    # =====================================================================
    # PHASE 6: ANALYSE FINALE
    # =====================================================================
    logger.info(f"\n{'='*100}")
    logger.info(f"📊 PHASE 6: ANALYSE FINALE")
    logger.info(f"{'='*100}")
    
    # Get final prices
    extended_ticker_final = extended.get_ticker(symbol)
    hyperliquid_ticker_final = hyperliquid.get_ticker(symbol)
    
    extended_mid_final = (extended_ticker_final['bid'] + extended_ticker_final['ask']) / 2
    hyperliquid_mid_final = (hyperliquid_ticker_final['bid'] + hyperliquid_ticker_final['ask']) / 2
    
    # Check if positions are closed
    positions_final = get_position_info(extended, hyperliquid, symbol)
    
    positions_closed = (not positions_final['extended']) and (not positions_final['hyperliquid'])
    
    logger.info(f"\n🔍 POSITIONS STATUS:")
    if positions_closed:
        logger.success(f"   ✅ Toutes les positions sont closes!")
    else:
        logger.warning(f"   ⚠️ Des positions restent ouvertes!")
        if positions_final['extended']:
            logger.warning(f"      Extended: {positions_final['extended']}")
        if positions_final['hyperliquid']:
            logger.warning(f"      Hyperliquid: {positions_final['hyperliquid']}")
    
    # Calcul spreads payés
    # À l'ouverture: BUY Extended @ ASK, SELL Hyperliquid @ BID
    spread_open = extended_ask_0 - hyperliquid_bid_0
    spread_open_cost = spread_open * actual_size
    
    # À la fermeture: SELL Extended @ BID, BUY Hyperliquid @ ASK
    spread_close = hyperliquid_ticker_final['ask'] - extended_ticker_final['bid']
    spread_close_cost = spread_close * actual_size
    
    total_spread_cost = spread_open_cost + spread_close_cost
    
    # Fees (estimate: 0.02% MAKER Extended + 0.002% MAKER Hyperliquid)
    extended_fee_rate = 0.0002  # 0.02%
    hyperliquid_fee_rate = 0.00002  # 0.002%
    
    total_notional = notional * 2  # Open + Close
    extended_fees = total_notional * extended_fee_rate * 2  # 2 trades
    hyperliquid_fees = total_notional * hyperliquid_fee_rate * 2
    total_fees = extended_fees + hyperliquid_fees
    
    # Funding gain (5min = 5/60 = 0.0833h)
    time_fraction = 5 / 60  # 5 minutes sur 1 heure
    funding_gain = notional * funding_arb_rate * time_fraction
    
    # PnL net
    net_pnl = funding_gain - total_spread_cost - total_fees
    
    logger.info(f"\n{'='*100}")
    logger.info(f"💰 RÉSULTAT FINAL")
    logger.info(f"{'='*100}")
    
    logger.info(f"\n📊 SPREADS PAYÉS:")
    logger.info(f"   Ouverture: ${spread_open:.6f} × {actual_size} = ${spread_open_cost:.3f}")
    logger.info(f"   Fermeture: ${spread_close:.6f} × {actual_size} = ${spread_close_cost:.3f}")
    logger.info(f"   TOTAL SPREADS: ${total_spread_cost:.3f}")
    
    logger.info(f"\n📊 FEES:")
    logger.info(f"   Extended (0.02% MAKER): ${extended_fees:.3f}")
    logger.info(f"   Hyperliquid (0.002% MAKER): ${hyperliquid_fees:.3f}")
    logger.info(f"   TOTAL FEES: ${total_fees:.3f}")
    
    logger.info(f"\n📊 FUNDING:")
    logger.info(f"   Rate arbitrage: {funding_arb_rate*100:.4f}%/h")
    logger.info(f"   Time: 5 minutes = {time_fraction:.4f}h")
    logger.info(f"   Notional: ${notional:.2f}")
    logger.info(f"   GAIN FUNDING: ${funding_gain:.3f}")
    
    logger.info(f"\n📊 PnL NET:")
    logger.info(f"   Funding gain: +${funding_gain:.3f}")
    logger.info(f"   Spreads cost: -${total_spread_cost:.3f}")
    logger.info(f"   Fees cost: -${total_fees:.3f}")
    
    if net_pnl > 0:
        logger.success(f"   ✅ NET PROFIT: +${net_pnl:.3f}")
        logger.success(f"\n🎉 STRATÉGIE RENTABLE!")
    else:
        logger.error(f"   ❌ NET LOSS: ${net_pnl:.3f}")
        logger.error(f"\n❌ STRATÉGIE NON RENTABLE sur 5min")
        logger.info(f"   💡 Temps minimum pour break-even: {abs(total_spread_cost + total_fees) / (notional * funding_arb_rate) * 60:.1f} minutes")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("\n⚠️ Interrupted")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"❌ Error: {e}")
        sys.exit(1)

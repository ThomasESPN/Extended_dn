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
    # Configurer loguru pour afficher les logs DEBUG (temporaire pour debug WebSocket)
    logger.remove()  # Retirer le handler par défaut
    logger.add(sys.stderr, level="DEBUG")  # Ajouter avec niveau DEBUG
except ImportError:
    import logging
    logger = logging.getLogger(__name__)
    logging.basicConfig(level=logging.DEBUG)

sys.path.insert(0, str(Path(__file__).parent))

from src.exchanges.extended_api import ExtendedAPI
from src.exchanges.hyperliquid_api import HyperliquidAPI


def get_ticker_ws(api, symbol: str, exchange_name: str) -> Dict:
    """
    Récupère le ticker via WebSocket avec fallback sur API REST
    
    Returns:
        {"bid": float, "ask": float, "last": float}
    """
    # Essayer WebSocket d'abord
    ws_data = api.get_orderbook_data(symbol)
    
    if ws_data and ws_data.get('bid') and ws_data.get('ask'):
        mid = (ws_data['bid'] + ws_data['ask']) / 2
        logger.debug(f"   📡 {exchange_name} prix WebSocket: bid=${ws_data['bid']:.6f}, ask=${ws_data['ask']:.6f}")
        return {
            'bid': ws_data['bid'],
            'ask': ws_data['ask'],
            'last': mid
        }
    
    # Fallback sur API REST
    logger.debug(f"   🔄 {exchange_name} WebSocket indisponible, utilisation API REST")
    return api.get_ticker(symbol)


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
    
    extended_result = None
    hyperliquid_result = None
    
    # ====== EXTENDED CLOSE AVEC RETRY ======
    for attempt in range(max_attempts):
        # Get fresh prices via WebSocket
        extended_ticker = get_ticker_ws(extended, symbol, "Extended")
        extended_bid = extended_ticker['bid']
        extended_ask = extended_ticker['ask']
        
        # Price selon side : utiliser le 1er niveau (best bid/ask)
        if extended_side.lower() == 'sell':
            # SELL → utiliser le meilleur ask (pour fermer un LONG)
            extended_price = extended_ask
        else:  # buy
            # BUY → utiliser le meilleur bid (pour fermer un SHORT)
            extended_price = extended_bid
        
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
                    logger.info(f"   → Retry au 1er niveau...")
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
    hyperliquid_ticker = get_ticker_ws(hyperliquid, symbol, "Hyperliquid")
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
                
                # Get fresh prices via WebSocket
                extended_ticker_new = get_ticker_ws(extended, symbol, "Extended")
                
                # Re-place au 1er niveau (best bid/ask)
                if extended_side.lower() == 'sell':
                    # SELL → utiliser le meilleur ask
                    new_price = extended_ticker_new['ask']
                else:
                    # BUY → utiliser le meilleur bid
                    new_price = extended_ticker_new['bid']
                
                logger.info(f"      🔄 Re-place Extended {extended_side.upper()} @ ${new_price:.6f} (1er niveau)")
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
    # CONNEXION WEBSOCKETS POUR PRIX TEMPS RÉEL
    # =====================================================================
    logger.info(f"\n🔌 Connexion aux WebSockets orderbook pour {symbol}...")
    
    extended_ws_success = extended.ws_orderbook(symbol)
    hyperliquid_ws_success = hyperliquid.ws_orderbook(symbol)
    
    if extended_ws_success:
        logger.success(f"   ✅ Extended WebSocket connecté")
    else:
        logger.warning(f"   ⚠️ Extended WebSocket échoué → utilisation API REST")
    
    if hyperliquid_ws_success:
        logger.success(f"   ✅ Hyperliquid WebSocket connecté")
    else:
        logger.warning(f"   ⚠️ Hyperliquid WebSocket échoué → utilisation API REST")
    
    # Attendre un peu pour recevoir les premières données
    if extended_ws_success or hyperliquid_ws_success:
        logger.info(f"   ⏳ Attente des premières données WebSocket...")
        time.sleep(15)  # Extended peut prendre jusqu'à 15-20 secondes pour envoyer les premières données
        
        # Vérifier que les données sont bien reçues
        max_wait_data = 25  # Attendre jusqu'à 25 secondes pour recevoir des données (Extended peut être lent)
        waited_data = 0
        
        while waited_data < max_wait_data:
            extended_data = extended.get_orderbook_data(symbol) if extended_ws_success else None
            hyperliquid_data = hyperliquid.get_orderbook_data(symbol) if hyperliquid_ws_success else None
            
            # Vérifier si Extended a des données (priorité car plus lent)
            if extended_ws_success and extended_data:
                logger.success(f"   ✅ Extended WebSocket données reçues: bid=${extended_data['bid']:.6f}, ask=${extended_data['ask']:.6f}")
                # Si Extended a des données, on peut continuer même si Hyperliquid n'en a pas encore
                if hyperliquid_data:
                    logger.success(f"   ✅ Hyperliquid WebSocket données reçues: bid=${hyperliquid_data['bid']:.6f}, ask=${hyperliquid_data['ask']:.6f}")
                elif hyperliquid_ws_success:
                    logger.warning(f"   ⚠️ Hyperliquid WebSocket pas encore de données, continuons l'attente...")
                break
            elif hyperliquid_ws_success and hyperliquid_data:
                # Hyperliquid a des données mais pas Extended, continuer à attendre Extended
                logger.info(f"   ⏳ Hyperliquid OK, attente Extended... ({waited_data}s/{max_wait_data}s)")
            else:
                # Aucun n'a de données
                logger.debug(f"   ⏳ Attente données WebSocket... ({waited_data}s/{max_wait_data}s)")
            
            time.sleep(1)
            waited_data += 1
        
        # Vérification finale
        extended_data = extended.get_orderbook_data(symbol) if extended_ws_success else None
        hyperliquid_data = hyperliquid.get_orderbook_data(symbol) if hyperliquid_ws_success else None
        
        if extended_ws_success and not extended_data:
            logger.warning(f"   ⚠️ Extended WebSocket timeout après {max_wait_data}s, utilisation API REST")
        elif extended_ws_success and extended_data:
            logger.success(f"   ✅ Extended WebSocket opérationnel: bid=${extended_data['bid']:.6f}, ask=${extended_data['ask']:.6f}")
        
        if hyperliquid_ws_success and not hyperliquid_data:
            logger.warning(f"   ⚠️ Hyperliquid WebSocket pas de données, utilisation API REST")
        elif hyperliquid_ws_success and hyperliquid_data:
            logger.success(f"   ✅ Hyperliquid WebSocket opérationnel: bid=${hyperliquid_data['bid']:.6f}, ask=${hyperliquid_data['ask']:.6f}")
    
    # =====================================================================
    # PHASE 1: GET INITIAL STATE
    # =====================================================================
    logger.info(f"\n{'='*100}")
    logger.info(f"📊 PHASE 1: ÉTAT INITIAL")
    logger.info(f"{'='*100}")
    
    extended_ticker = get_ticker_ws(extended, symbol, "Extended")
    hyperliquid_ticker = get_ticker_ws(hyperliquid, symbol, "Hyperliquid")
    
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
    
    # Configurer le levier x3 pour Extended
    logger.info(f"\n⚙️ Configuration levier x3 pour Extended...")
    if not extended.set_leverage(symbol, 3):
        logger.error(f"   ❌ Échec configuration levier Extended")
        return
    logger.success(f"   ✅ Extended levier configuré: 3x")
    
    # Récupérer le ticker actuel pour prix le plus récent via WebSocket
    extended_ticker_current = get_ticker_ws(extended, symbol, "Extended")
    extended_bid_current = extended_ticker_current['bid']
    extended_ask_current = extended_ticker_current['ask']
    extended_mid_current = (extended_bid_current + extended_ask_current) / 2
    
    # Pour un LONG (BUY), utiliser le meilleur bid (1er niveau)
    extended_open_price = extended_bid_current  # Utiliser le 1er niveau (best bid)
    
    logger.info(f"\n1️⃣ Extended LONG {size} {symbol} @ ${extended_open_price:.6f} (best bid=${extended_bid_current:.6f}, best ask=${extended_ask_current:.6f})")
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
    extended_oid = extended_result['order_id']
    logger.success(f"   ✅ Extended OID: {extended_oid} (size: {extended_real_size})")
    
    # NOUVELLE STRATÉGIE: Attendre que Extended se fill d'abord, puis placer Hyperliquid
    logger.info(f"   ⏳ Attente fill Extended (re-place toutes les 10s si nécessaire)...")
    
    # Vérification immédiate (l'ordre peut être fill instantanément avec prix agressif)
    time.sleep(0.5)  # Petit délai pour laisser l'ordre se fill si prix très proche
    positions_check_immediate = get_position_info(extended, hyperliquid, symbol)
    extended_position_immediate = positions_check_immediate['extended']
    
    # Attendre que Extended se fill avec re-place toutes les 10s
    max_cycles = 30  # 30 cycles max = ~300s
    check_interval = 15  # Check toutes les 10s
    cycle = 0
    extended_filled = False
    extended_entry_price = None
    
    # Si déjà fill, skip la boucle
    if extended_position_immediate is not None:
        extended_filled = True
        extended_entry_price = extended_position_immediate['entry_price']
        extended_real_size = extended_position_immediate['size']
        logger.success(f"   ✅ Extended FILLED IMMÉDIATEMENT! Prix d'entrée: ${extended_entry_price:.6f}, Size: {extended_real_size}")
    
    while cycle < max_cycles and not extended_filled:
        time.sleep(check_interval)
        cycle += 1
        
        logger.info(f"\n   🔄 Cycle {cycle}/{max_cycles} (vérification Extended...)")
        
        # Vérifier si Extended est fill
        positions_check = get_position_info(extended, hyperliquid, symbol)
        extended_position = positions_check['extended']
        
        if extended_position is not None:
            extended_filled = True
            extended_entry_price = extended_position['entry_price']
            extended_real_size = extended_position['size']
            logger.success(f"   ✅ Extended FILLED! Prix d'entrée: ${extended_entry_price:.6f}, Size: {extended_real_size}")
            break
        
        # Extended pas fill → Cancel + Re-place au prix actuel (optimisé pour vitesse)
        logger.warning(f"      ⚠️ Extended pas filled → Cancel + Re-place agressif")
        try:
            extended.cancel_order(extended_oid)
            time.sleep(0.3)  # Réduit de 1s à 0.3s pour plus de rapidité
            
            # Re-place @ best bid via WebSocket (1er niveau)
            extended_ticker_new = get_ticker_ws(extended, symbol, "Extended")
            extended_bid_new = extended_ticker_new['bid']
            extended_ask_new = extended_ticker_new['ask']
            extended_mid_new = (extended_bid_new + extended_ask_new) / 2
            
            # Utiliser le meilleur bid pour un BUY (LONG) - 1er niveau
            extended_price_new = extended_bid_new
            
            logger.info(f"      🔄 Re-place Extended BUY @ ${extended_price_new:.6f} (best bid: ${extended_bid_new:.6f}, best ask: ${extended_ask_new:.6f})")
            extended_result_new = extended.place_order(
                symbol=symbol,
                side="buy",
                size=extended_real_size,
                order_type="limit",
                price=extended_price_new
            )
            
            if extended_result_new and extended_result_new.get('order_id'):
                extended_oid = extended_result_new['order_id']
                logger.success(f"      ✅ Extended re-placed: {extended_oid}")
            else:
                logger.error(f"      ❌ Extended re-place failed!")
        except Exception as e:
            logger.error(f"      ❌ Extended re-place failed: {e}")
    
    if not extended_filled:
        logger.error(f"\n❌ Timeout: Extended pas fill après {max_cycles} cycles (~{max_cycles * check_interval}s)!")
        logger.error(f"   → ABORT")
        return
    
    # 2. Extended est fill → Placer Hyperliquid au prix le plus proche possible
    logger.info(f"\n2️⃣ Hyperliquid SHORT {extended_real_size} {symbol}")
    logger.info(f"   🎯 Prix d'entrée Extended: ${extended_entry_price:.6f}")
    
    # Configurer le levier x3 pour Hyperliquid
    logger.info(f"\n⚙️ Configuration levier x3 pour Hyperliquid...")
    if not hyperliquid.set_leverage(symbol, 3):
        logger.error(f"   ❌ Échec configuration levier Hyperliquid")
        return
    logger.success(f"   ✅ Hyperliquid levier configuré: 3x")
    
    # Récupérer le ticker Hyperliquid actuel via WebSocket
    hyperliquid_ticker = get_ticker_ws(hyperliquid, symbol, "Hyperliquid")
    hyperliquid_bid = hyperliquid_ticker['bid']
    hyperliquid_ask = hyperliquid_ticker['ask']
    hyperliquid_mid = (hyperliquid_bid + hyperliquid_ask) / 2
    
    # Calculer le prix Hyperliquid le plus proche du prix Extended
    # Pour un SHORT (SELL), on veut être proche du prix Extended
    # Si Extended entry > Hyperliquid mid, utiliser ask (plus agressif)
    # Si Extended entry < Hyperliquid mid, utiliser bid (moins agressif mais MAKER)
    # Sinon utiliser mid
    
    if extended_entry_price > hyperliquid_mid:
        # Extended plus cher → utiliser ask pour être proche
        hyperliquid_price = hyperliquid_ask
        logger.info(f"   📊 Extended entry (${extended_entry_price:.6f}) > Hyperliquid mid (${hyperliquid_mid:.6f})")
        logger.info(f"   → Utiliser ASK: ${hyperliquid_price:.6f}")
    elif extended_entry_price < hyperliquid_bid:
        # Extended moins cher → utiliser bid pour être proche
        hyperliquid_price = hyperliquid_bid
        logger.info(f"   📊 Extended entry (${extended_entry_price:.6f}) < Hyperliquid bid (${hyperliquid_bid:.6f})")
        logger.info(f"   → Utiliser BID: ${hyperliquid_price:.6f}")
    else:
        # Entre bid et ask → utiliser mid
        hyperliquid_price = hyperliquid_mid
        logger.info(f"   📊 Extended entry (${extended_entry_price:.6f}) entre bid/ask")
        logger.info(f"   → Utiliser MID: ${hyperliquid_price:.6f}")
    
    logger.info(f"   🎯 Prix Hyperliquid: ${hyperliquid_price:.6f} (diff: ${abs(extended_entry_price - hyperliquid_price):.6f})")
    
    hyperliquid_result = hyperliquid.place_order(
        symbol=symbol,
        side="sell",
        size=extended_real_size,
        order_type="limit",
        price=hyperliquid_price
    )
    
    if not hyperliquid_result or hyperliquid_result.get('status') != 'ok':
        logger.error(f"   ❌ Hyperliquid order failed")
        return
    
    logger.success(f"   ✅ Hyperliquid order placed")
    
    # Vérifier si Hyperliquid est fill immédiatement
    try:
        statuses = hyperliquid_result['response']['data']['statuses']
        if 'filled' in statuses[0]:
            hyperliquid_filled_price = float(statuses[0]['filled']['avgPx'])
            logger.success(f"   ✅ Hyperliquid FILLED IMMÉDIATEMENT @ ${hyperliquid_filled_price:.6f}")
        elif 'resting' in statuses[0]:
            hyperliquid_oid = statuses[0]['resting']['oid']
            logger.info(f"   ⏳ Hyperliquid OID: {hyperliquid_oid} (resting)")
            logger.info(f"   → Attente fill naturel...")
            
            # Attendre un peu pour voir si ça se fill
            time.sleep(5)
            positions_check = get_position_info(extended, hyperliquid, symbol)
            if positions_check['hyperliquid'] is None:
                logger.warning(f"   ⚠️ Hyperliquid pas encore fill, peut prendre quelques secondes...")
    except Exception as e:
        logger.warning(f"   ⚠️ Can't extract Hyperliquid status: {e}")
    
    # Vérifier les positions finales
    positions_start = get_position_info(extended, hyperliquid, symbol)
    
    if not positions_start['extended'] or not positions_start['hyperliquid']:
        logger.error(f"\n❌ Positions incomplètes après placement!")
        logger.error(f"   Extended: {positions_start['extended']}")
        logger.error(f"   Hyperliquid: {positions_start['hyperliquid']}")
        return
    
    logger.success(f"\n✅ Positions ouvertes:")
    logger.info(f"   Extended: {positions_start['extended']['side']} {positions_start['extended']['size']} @ ${positions_start['extended']['entry_price']:.6f}")
    logger.info(f"   Hyperliquid: {positions_start['hyperliquid']['side']} {positions_start['hyperliquid']['size']} @ ${positions_start['hyperliquid']['entry_price']:.6f}")
    
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
    
    # Get final prices via WebSocket
    extended_ticker_final = get_ticker_ws(extended, symbol, "Extended")
    hyperliquid_ticker_final = get_ticker_ws(hyperliquid, symbol, "Hyperliquid")
    
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

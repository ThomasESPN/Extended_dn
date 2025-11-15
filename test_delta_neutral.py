#!/usr/bin/env python3
"""
Test DELTA NEUTRAL: LONG Extended + SHORT Hyperliquid
Même margin ($19 USD EXACTEMENT) sur les deux exchanges avec leverage minimum
"""

import sys
import json
import time
from loguru import logger
from pathlib import Path

# Setup logging
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO"
)

# Import APIs
sys.path.insert(0, str(Path(__file__).parent))
from src.exchanges.extended_api import ExtendedAPI
from src.exchanges.hyperliquid_api import HyperliquidAPI


def main():
    logger.info("="*100)
    logger.info("🎯 TEST DELTA NEUTRAL - LONG Extended + SHORT Hyperliquid")
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
    logger.info(f"   🔥 Margin: ${target_usd} USD EXACTEMENT sur les deux exchanges")
    
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
    
    # Symbol
    symbol = "ZORA"
    
    logger.info(f"\n📊 Récupération prix {symbol}...")
    
    extended_ticker = extended.get_ticker(symbol)
    hyperliquid_ticker = hyperliquid.get_ticker(symbol)
    
    extended_ask = extended_ticker['ask']
    extended_bid = extended_ticker['bid']
    hyperliquid_ask = hyperliquid_ticker['ask']
    hyperliquid_bid = hyperliquid_ticker['bid']
    
    logger.success(f"✅ Extended: bid=${extended_bid:.6f}, ask=${extended_ask:.6f}")
    logger.success(f"✅ Hyperliquid: bid=${hyperliquid_bid:.6f}, ask=${hyperliquid_ask:.6f}")
    
    # Delta (LONG Extended vs SHORT Hyperliquid)
    delta_abs = abs(extended_ask - hyperliquid_bid)
    delta_pct = (delta_abs / hyperliquid_bid) * 100
    
    logger.info(f"\n💰 DELTA (LONG Extended ask vs SHORT Hyperliquid bid):")
    logger.info(f"   Extended ask: ${extended_ask:.6f}")
    logger.info(f"   Hyperliquid bid: ${hyperliquid_bid:.6f}")
    logger.info(f"   Différence: ${delta_abs:.6f} ({delta_pct:.3f}%)")
    
    # Metadata & Leverage
    logger.info(f"\n📐 Configuration leverage...")
    extended_max_leverage = extended.get_max_leverage(symbol)
    hyperliquid_max_leverage = hyperliquid.get_max_leverage(symbol)
    
    # 🔥 Leverage = minimum des deux exchanges
    target_leverage = min(extended_max_leverage, hyperliquid_max_leverage)
    
    logger.info(f"   Extended max: {extended_max_leverage}x")
    logger.info(f"   Hyperliquid max: {hyperliquid_max_leverage}x")
    logger.warning(f"   🔥 FORCE {target_leverage}x leverage sur les DEUX")
    
    # Set leverage sur les deux exchanges
    try:
        extended.set_leverage(symbol, target_leverage)
        logger.success(f"   ✅ Extended leverage set to {target_leverage}x")
    except Exception as e:
        logger.error(f"   ❌ Extended leverage failed: {e}")
    
    try:
        hyperliquid.set_leverage(symbol, target_leverage)
        logger.success(f"   ✅ Hyperliquid leverage set to {target_leverage}x")
    except Exception as e:
        logger.warning(f"   ⚠️ Hyperliquid leverage failed: {e}")
    
    # Calcul des sizes pour EXACTEMENT $18 margin sur les deux
    # 🔥 STRATÉGIE: Calculer BASÉ sur Extended (contrainte minimum 1000 ZORA)
    # Puis utiliser EXACTEMENT LA MÊME SIZE sur Hyperliquid
    # Notional = Margin × Leverage
    notional = target_usd * target_leverage
    
    # 🔥 FORCE 0 decimals pour ZORA
    size_decimals = 0
    
    logger.info(f"\n💰 Calcul sizes pour ${target_usd} margin @ {target_leverage}x:")
    logger.info(f"   Target notional: ${notional:.2f}")
    
    # 🎯 STRATÉGIE 1: Calculer la size théorique basée sur Extended ASK
    # Extended LONG: diviser par ASK (prix d'achat)
    theoretical_size = round(notional / extended_ask, size_decimals)
    
    # 🎯 STRATÉGIE 2: Vérifier minimum Extended (1000 ZORA minimum)
    extended_min_size = 1000.0
    if theoretical_size < extended_min_size:
        logger.warning(f"   ⚠️ Size théorique {theoretical_size} < Extended minimum {extended_min_size}")
        logger.warning(f"   → FORCE {extended_min_size} ZORA sur les DEUX exchanges")
        actual_size = extended_min_size
    else:
        actual_size = theoretical_size
    
    # 🔥 MÊME SIZE sur les deux exchanges (delta-neutral en QUANTITÉ)
    extended_size = actual_size
    hyperliquid_size = actual_size
    
    # Calculer les notionals RÉELS avec cette size
    extended_real_notional = extended_size * extended_ask
    extended_real_margin = extended_real_notional / target_leverage
    
    hyperliquid_real_notional = hyperliquid_size * hyperliquid_bid
    hyperliquid_real_margin = hyperliquid_real_notional / target_leverage
    
    logger.info(f"\n   📗 Extended LONG:")
    logger.info(f"      {extended_size} ZORA @ ${extended_ask:.6f}")
    logger.info(f"      Notional: ${extended_real_notional:.2f}")
    logger.info(f"      Margin: ${extended_real_margin:.2f}")
    
    logger.info(f"\n   📕 Hyperliquid SHORT:")
    logger.info(f"      {hyperliquid_size} ZORA @ ${hyperliquid_bid:.6f}")
    logger.info(f"      Notional: ${hyperliquid_real_notional:.2f}")
    logger.info(f"      Margin: ${hyperliquid_real_margin:.2f}")
    
    # Vérifier l'écart de margin
    margin_diff = abs(extended_real_margin - hyperliquid_real_margin)
    margin_diff_pct = (margin_diff / target_usd) * 100
    
    logger.warning(f"\n   ⚠️ ÉCART DE MARGIN:")
    logger.warning(f"      Extended: ${extended_real_margin:.2f}")
    logger.warning(f"      Hyperliquid: ${hyperliquid_real_margin:.2f}")
    logger.warning(f"      Différence: ${margin_diff:.2f} ({margin_diff_pct:.1f}%)")
    logger.warning(f"      → Causé par le spread bid/ask entre exchanges")
    
    logger.warning(f"\n⚠️  DELTA NEUTRAL:")
    logger.warning(f"   🔥 MÊME SIZE: {extended_size} ZORA sur les DEUX exchanges")
    logger.warning(f"   Extended: LONG {extended_size} ZORA (BUY)")
    logger.warning(f"   Hyperliquid: SHORT {hyperliquid_size} ZORA (SELL)")
    logger.warning(f"   → Position neutre en QUANTITÉ, capture funding rate")
    logger.warning(f"   ⚠️ Écart de margin causé par bid/ask spread: ~${margin_diff:.2f}")
    
    logger.info(f"\n🚀 Exécution dans 3s...")
    time.sleep(3)
    
    # =================================================================
    # EXECUTION
    # =================================================================
    
    logger.info(f"\n{'='*100}")
    logger.info("🔥 EXÉCUTION DELTA NEUTRAL")
    logger.info(f"{'='*100}")
    
    extended_result = None
    hyperliquid_result = None
    
    # Extended: LONG (BUY)
    logger.info(f"\n📗 Extended LONG: BUY {extended_size} ZORA @ ${extended_ask:.6f}")
    try:
        extended_result = extended.place_order(
            symbol=symbol,
            side="buy",
            size=extended_size,
            order_type="market",
            price=None
        )
        
        if extended_result and extended_result.get('order_id'):
            logger.success(f"   ✅ Extended placé (OID: {extended_result['order_id']})")
        else:
            logger.error(f"   ❌ Extended failed: {extended_result}")
    except Exception as e:
        logger.error(f"   ❌ Extended error: {e}")
    
    time.sleep(0.5)
    
    # Hyperliquid: SHORT (SELL)
    logger.info(f"\n📕 Hyperliquid SHORT: SELL {hyperliquid_size} ZORA @ ${hyperliquid_bid:.6f}")
    try:
        hyperliquid_result = hyperliquid.place_order(
            symbol=symbol,
            side="sell",
            size=hyperliquid_size,
            order_type="market",
            price=None
        )
        
        if hyperliquid_result and hyperliquid_result.get('response', {}).get('data', {}).get('statuses'):
            status = hyperliquid_result['response']['data']['statuses'][0]
            if 'filled' in status:
                filled_data = status['filled']
                logger.success(f"   ✅ Hyperliquid FILLED: {filled_data['totalSz']} @ ${filled_data['avgPx']}")
            elif 'error' in status:
                logger.error(f"   ❌ Hyperliquid error: {status['error']}")
        else:
            logger.error(f"   ❌ Hyperliquid failed: {hyperliquid_result}")
    except Exception as e:
        logger.error(f"   ❌ Hyperliquid error: {e}")
    
    # Wait
    logger.info(f"\n⏳ Attente 3s pour exécution...")
    time.sleep(3)
    
    # Check positions
    logger.info(f"\n📊 Vérification des positions...")
    
    extended_fill_price = None
    hyperliquid_fill_price = None
    
    try:
        extended_positions = extended.get_positions()
        logger.info(f"\n📗 Extended positions:")
        for pos in extended_positions:
            if symbol.upper() in pos.get('symbol', '').upper():
                extended_fill_price = float(pos.get('entry_price', 0))
                logger.success(f"   ✅ {pos['symbol']}: {pos.get('size', 0)} @ ${extended_fill_price:.6f}")
    except Exception as e:
        logger.error(f"   ❌ Extended positions error: {e}")
    
    try:
        if hyperliquid_result and hyperliquid_result.get('response', {}).get('data', {}).get('statuses'):
            status = hyperliquid_result['response']['data']['statuses'][0]
            if 'filled' in status:
                hyperliquid_fill_price = float(status['filled']['avgPx'])
                logger.info(f"\n📕 Hyperliquid fill:")
                logger.success(f"   ✅ ZORA: {status['filled']['totalSz']} @ ${hyperliquid_fill_price:.6f}")
    except Exception as e:
        logger.error(f"   ❌ Hyperliquid fill parse error: {e}")
    
    # Delta après fill
    if extended_fill_price and hyperliquid_fill_price:
        delta_abs = abs(extended_fill_price - hyperliquid_fill_price)
        delta_pct = (delta_abs / hyperliquid_fill_price) * 100
        
        logger.info(f"\n💰 DELTA RÉEL après fill:")
        logger.info(f"   Extended LONG fill: ${extended_fill_price:.6f}")
        logger.info(f"   Hyperliquid SHORT fill: ${hyperliquid_fill_price:.6f}")
        logger.info(f"   Différence: ${delta_abs:.6f} ({delta_pct:.3f}%)")
    
    logger.info(f"\n{'='*100}")
    logger.success("✅ TEST TERMINÉ")
    logger.info(f"{'='*100}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("\n⚠️  Interrompu par l'utilisateur")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"❌ Erreur: {e}")
        sys.exit(1)
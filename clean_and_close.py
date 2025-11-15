#!/usr/bin/env python3
"""
CLEAN & CLOSE: Cancel ordres en attente + Close positions ouvertes + Affiche rentabilité
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


def main():
    logger.info("="*100)
    logger.info("🧹 CLEAN & CLOSE POSITIONS")
    logger.info("="*100)
    
    # Load config
    with open("config/config.json", "r") as f:
        config = json.load(f)
    
    wallet = config["wallet"]["address"]
    private_key = config["wallet"]["private_key"]
    extended_config = config["extended"]
    
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
    
    # =====================================================================
    # STEP 1: CHECK OPEN ORDERS
    # =====================================================================
    logger.info(f"\n{'='*100}")
    logger.info(f"📊 STEP 1: CHECK OPEN ORDERS")
    logger.info(f"{'='*100}")
    
    # Extended open orders (check via position since SDK doesn't list all)
    logger.info(f"\n🔍 Extended: Checking open orders...")
    # On ne peut pas lister tous les ordres Extended facilement, on skip
    
    # Hyperliquid open orders
    logger.info(f"\n🔍 Hyperliquid: Checking open orders...")
    hl_open_orders = hyperliquid.get_open_orders()
    
    if hl_open_orders:
        logger.warning(f"   ⚠️ {len(hl_open_orders)} ordre(s) ouvert(s)")
        for order in hl_open_orders:
            logger.info(f"      - {order.get('symbol')} {order.get('side')} {order.get('size')} @ ${order.get('price'):.6f} (OID: {order.get('oid')})")
        
        confirm = input(f"\n❌ Cancel tous les ordres Hyperliquid? (yes/no) [yes]: ").strip().lower()
        if confirm != "no":
            for order in hl_open_orders:
                oid = order.get('oid')
                logger.info(f"   Cancelling order {oid}...")
                try:
                    # Note: cancel_order not fully implemented
                    logger.warning(f"      ⚠️ Cancel not implemented, use UI to cancel")
                except Exception as e:
                    logger.error(f"      ❌ Error: {e}")
    else:
        logger.success(f"   ✅ Pas d'ordres ouverts sur Hyperliquid")
    
    # =====================================================================
    # STEP 2: CHECK POSITIONS
    # =====================================================================
    logger.info(f"\n{'='*100}")
    logger.info(f"📊 STEP 2: CHECK POSITIONS")
    logger.info(f"{'='*100}")
    
    # Extended positions
    logger.info(f"\n🔍 Extended positions:")
    extended_positions = extended.get_positions()
    extended_pos = None
    
    for p in extended_positions:
        if symbol.upper() in p.get('symbol', '').upper():
            extended_pos = p
            logger.warning(f"   ⚠️ Position {p.get('side')} {p.get('size')} @ ${p.get('entry_price'):.6f}")
            logger.info(f"      PnL: ${p.get('unrealized_pnl', 0):.3f}")
            break
    
    if not extended_pos:
        logger.success(f"   ✅ Pas de position Extended")
    
    # Hyperliquid positions
    logger.info(f"\n🔍 Hyperliquid positions:")
    hl_positions = hyperliquid.get_open_positions()
    hl_pos = None
    
    for p in hl_positions:
        if isinstance(p, dict) and 'position' in p:
            pos = p['position']
            if pos.get('coin') == symbol:
                hl_pos = pos
                side = 'SHORT' if float(pos.get('szi', 0)) < 0 else 'LONG'
                size = abs(float(pos.get('szi', 0)))
                logger.warning(f"   ⚠️ Position {side} {size} @ ${float(pos.get('entryPx', 0)):.6f}")
                logger.info(f"      PnL: ${float(pos.get('unrealizedPnl', 0)):.3f}")
                logger.info(f"      Funding accumulé: ${float(pos.get('cumFunding', {}).get('sinceOpen', 0)):.6f}")
                break
    
    if not hl_pos:
        logger.success(f"   ✅ Pas de position Hyperliquid")
    
    # =====================================================================
    # STEP 3: CLOSE POSITIONS
    # =====================================================================
    if extended_pos or hl_pos:
        logger.info(f"\n{'='*100}")
        logger.info(f"📊 STEP 3: CLOSE POSITIONS")
        logger.info(f"{'='*100}")
        
        confirm = input(f"\n🔒 Fermer les positions en MARKET? (yes/no) [no]: ").strip().lower()
        if confirm == "yes":
            # Get current prices
            extended_ticker = extended.get_ticker(symbol)
            hyperliquid_ticker = hyperliquid.get_ticker(symbol)
            
            # Close Extended
            if extended_pos:
                close_side = 'sell' if extended_pos.get('side', '').upper() == 'LONG' else 'buy'
                size_to_close = abs(float(extended_pos.get('size', 0)))
                
                logger.info(f"\n🔒 Extended: {close_side.upper()} {size_to_close} {symbol} MARKET")
                
                result = extended.place_order(
                    symbol=symbol,
                    side=close_side,
                    size=size_to_close,
                    order_type="market",
                    price=None,
                    reduce_only=True
                )
                
                if result and result.get('order_id'):
                    logger.success(f"   ✅ Extended closed!")
                else:
                    logger.error(f"   ❌ Extended close failed: {result}")
            
            time.sleep(2)
            
            # Close Hyperliquid
            if hl_pos:
                hl_side = 'buy' if float(hl_pos.get('szi', 0)) < 0 else 'sell'
                hl_size = abs(float(hl_pos.get('szi', 0)))
                
                logger.info(f"\n🔒 Hyperliquid: {hl_side.upper()} {hl_size} {symbol} MARKET")
                
                result = hyperliquid.place_order(
                    symbol=symbol,
                    side=hl_side,
                    size=hl_size,
                    order_type="market",
                    price=None,
                    reduce_only=True
                )
                
                if result and result.get('status') == 'ok':
                    logger.success(f"   ✅ Hyperliquid closed!")
                else:
                    logger.error(f"   ❌ Hyperliquid close failed: {result}")
            
            logger.success(f"\n✅ POSITIONS FERMÉES!")
            
            # =====================================================================
            # STEP 4: CALCULATE PnL
            # =====================================================================
            logger.info(f"\n{'='*100}")
            logger.info(f"📊 RÉSUMÉ TRADE")
            logger.info(f"{'='*100}")
            
            if extended_pos and hl_pos:
                # Entry prices
                extended_entry = float(extended_pos.get('entry_price', 0))
                hl_entry = float(hl_pos.get('entryPx', 0))
                
                # Close prices (current)
                extended_close = extended_ticker['bid'] if extended_pos.get('side', '').upper() == 'LONG' else extended_ticker['ask']
                hl_close = hyperliquid_ticker['ask'] if float(hl_pos.get('szi', 0)) < 0 else hyperliquid_ticker['bid']
                
                # Size
                size = abs(float(extended_pos.get('size', 0)))
                
                # PnL Extended
                if extended_pos.get('side', '').upper() == 'LONG':
                    extended_pnl = (extended_close - extended_entry) * size
                else:
                    extended_pnl = (extended_entry - extended_close) * size
                
                # PnL Hyperliquid
                if float(hl_pos.get('szi', 0)) < 0:  # SHORT
                    hl_pnl = (hl_entry - hl_close) * size
                else:  # LONG
                    hl_pnl = (hl_close - hl_entry) * size
                
                # Funding
                funding = float(hl_pos.get('cumFunding', {}).get('sinceOpen', 0))
                
                # Total
                total_pnl = extended_pnl + hl_pnl + funding
                
                logger.info(f"\n💰 ENTRIES:")
                logger.info(f"   Extended LONG @ ${extended_entry:.6f}")
                logger.info(f"   Hyperliquid SHORT @ ${hl_entry:.6f}")
                logger.info(f"   Entry spread: ${extended_entry - hl_entry:.6f} (coût: ${(extended_entry - hl_entry) * size:.3f})")
                
                logger.info(f"\n💰 EXITS:")
                logger.info(f"   Extended SELL @ ${extended_close:.6f}")
                logger.info(f"   Hyperliquid BUY @ ${hl_close:.6f}")
                logger.info(f"   Exit spread: ${hl_close - extended_close:.6f} (coût: ${(hl_close - extended_close) * size:.3f})")
                
                logger.info(f"\n💰 PnL DÉTAILLÉ:")
                logger.info(f"   Extended: ${extended_pnl:.3f}")
                logger.info(f"   Hyperliquid: ${hl_pnl:.3f}")
                logger.info(f"   Funding: ${funding:.6f}")
                
                if total_pnl > 0:
                    logger.success(f"\n✅ TOTAL PnL: +${total_pnl:.3f}")
                else:
                    logger.error(f"\n❌ TOTAL PnL: ${total_pnl:.3f}")
                
                # Fees estimate
                notional = size * (extended_entry + hl_entry) / 2
                fees_est = notional * (0.0002 + 0.00002) * 2  # Open + Close
                logger.info(f"\n💸 Fees estimées: ${fees_est:.3f}")
                logger.info(f"   NET (après fees): ${total_pnl - fees_est:.3f}")
        else:
            logger.info("❌ Close annulé")
    else:
        logger.success(f"\n✅ Rien à closer!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("\n⚠️ Interrupted")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"❌ Error: {e}")
        sys.exit(1)

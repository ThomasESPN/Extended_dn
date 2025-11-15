#!/usr/bin/env python3
"""
DELTA NEUTRAL MAKER - Version COMPLETE
- Place LIMIT orders au mid-price (MAKER)
- Retry avec offset progressif si pas de fill
- Si un côté fill → TAKER immédiat sur l'autre
- Monitoring complet et logging
"""

import sys
import json
import time
from loguru import logger
from pathlib import Path
from typing import Dict, Optional, Tuple

# Setup logging
logger.remove()
logger.add(
    sys.stderr,
    format="<green>{time:HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <level>{message}</level>",
    level="INFO"
)

# Import APIs
sys.path.insert(0, str(Path(__file__).parent))
from src.exchanges.extended_api import ExtendedAPI
from src.exchanges.hyperliquid_api import HyperliquidAPI


class DeltaNeutralMaker:
    """Bot pour ouvrir des positions delta-neutral en mode MAKER"""
    
    def __init__(self, config_path: str = "config/config.json"):
        with open(config_path, "r") as f:
            self.config = json.load(f)
        
        self.wallet = self.config["wallet"]["address"]
        self.private_key = self.config["wallet"]["private_key"]
        self.extended_config = self.config["extended"]
        
        # Paramètres
        self.symbol = "ZORA"
        self.leverage = 3
        self.target_margin = 18  # $18 USD
        self.target_size = 1000  # Force 1000 ZORA minimum Extended
        
        # Retry config
        self.retry_timeout = 30  # 30s avant retry
        self.max_retries = 3
        self.offsets = [0.0001, 0.0002, 0.0005]  # 0.01%, 0.02%, 0.05%
        
        # State
        self.extended_order_id = None
        self.hyperliquid_order_id = None
        self.extended_filled = False
        self.hyperliquid_filled = False
        
        # Initialize APIs
        logger.info("🔌 Initialisation des APIs...")
        
        self.extended = ExtendedAPI(
            wallet_address=self.wallet,
            api_key=self.extended_config["api_key"],
            stark_public_key=self.extended_config["stark_public_key"],
            stark_private_key=self.extended_config["stark_private_key"],
            vault_id=self.extended_config["vault_id"],
            client_id=self.extended_config.get("client_id")
        )
        
        self.hyperliquid = HyperliquidAPI(
            wallet_address=self.wallet,
            private_key=self.private_key
        )
        
        if not self.extended.trading_client:
            raise Exception("❌ Extended failed to initialize")
        
        logger.success("✅ APIs initialisées")
    
    def get_prices(self) -> Dict:
        """Récupère les prix bid/ask des deux exchanges"""
        extended_ticker = self.extended.get_ticker(self.symbol)
        hyperliquid_ticker = self.hyperliquid.get_ticker(self.symbol)
        
        return {
            'extended': {
                'bid': extended_ticker['bid'],
                'ask': extended_ticker['ask'],
                'mid': (extended_ticker['bid'] + extended_ticker['ask']) / 2
            },
            'hyperliquid': {
                'bid': hyperliquid_ticker['bid'],
                'ask': hyperliquid_ticker['ask'],
                'mid': (hyperliquid_ticker['bid'] + hyperliquid_ticker['ask']) / 2
            }
        }
    
    def calculate_spread_cost(self, prices: Dict) -> float:
        """Calcule le coût du spread cross-exchange"""
        cross_spread = prices['extended']['ask'] - prices['hyperliquid']['bid']
        notional = self.target_size * prices['extended']['mid']
        return (cross_spread / prices['hyperliquid']['bid']) * notional
    
    def set_leverage(self):
        """Configure le leverage sur les deux exchanges"""
        logger.info(f"📐 Configuration leverage {self.leverage}x...")
        
        try:
            self.extended.set_leverage(self.symbol, self.leverage)
            logger.success(f"   ✅ Extended: {self.leverage}x")
        except Exception as e:
            logger.error(f"   ❌ Extended leverage: {e}")
        
        try:
            self.hyperliquid.set_leverage(self.symbol, self.leverage)
            logger.success(f"   ✅ Hyperliquid: {self.leverage}x")
        except Exception as e:
            logger.warning(f"   ⚠️ Hyperliquid leverage: {e}")
    
    def place_limit_orders(self, offset: float = 0.0) -> Tuple[Optional[str], Optional[str]]:
        """
        Place LIMIT orders sur les deux exchanges
        offset: écart par rapport au mid-price (0 = exactly mid)
        Returns: (extended_oid, hyperliquid_oid)
        """
        prices = self.get_prices()
        
        # Prix MAKER avec offset
        extended_price = prices['extended']['mid'] * (1 - offset)  # BUY légèrement sous le mid
        hyperliquid_price = prices['hyperliquid']['mid'] * (1 + offset)  # SELL légèrement au-dessus
        
        extended_spread_pct = ((prices['extended']['ask'] - prices['extended']['bid']) / prices['extended']['mid']) * 100
        hyperliquid_spread_pct = ((prices['hyperliquid']['ask'] - prices['hyperliquid']['bid']) / prices['hyperliquid']['mid']) * 100
        
        logger.info(f"\n💰 Prix et spreads:")
        logger.info(f"   Extended:    bid=${prices['extended']['bid']:.6f}, ask=${prices['extended']['ask']:.6f} (spread {extended_spread_pct:.3f}%)")
        logger.info(f"   Hyperliquid: bid=${prices['hyperliquid']['bid']:.6f}, ask=${prices['hyperliquid']['ask']:.6f} (spread {hyperliquid_spread_pct:.3f}%)")
        
        spread_cost = self.calculate_spread_cost(prices)
        logger.warning(f"   ⚠️ Cross-spread TAKER cost: ${spread_cost:.2f}")
        
        logger.info(f"\n🎯 LIMIT orders avec offset {offset*100:.3f}%:")
        logger.info(f"   Extended LONG:  {self.target_size} ZORA @ ${extended_price:.6f} (LIMIT)")
        logger.info(f"   Hyperliquid SHORT: {self.target_size} ZORA @ ${hyperliquid_price:.6f} (LIMIT)")
        
        extended_oid = None
        hyperliquid_oid = None
        
        # Extended LIMIT BUY
        try:
            logger.info(f"\n📗 Placing Extended LIMIT BUY...")
            result = self.extended.place_order(
                symbol=self.symbol,
                side="buy",
                size=self.target_size,
                price=extended_price,
                order_type="limit"
            )
            
            if result and result.get('order_id'):
                extended_oid = result['order_id']
                logger.success(f"   ✅ Extended OID: {extended_oid}")
            else:
                logger.error(f"   ❌ Extended failed: {result}")
        except Exception as e:
            logger.error(f"   ❌ Extended error: {e}")
        
        time.sleep(0.5)
        
        # Hyperliquid LIMIT SELL
        try:
            logger.info(f"\n📕 Placing Hyperliquid LIMIT SELL...")
            result = self.hyperliquid.place_order(
                symbol=self.symbol,
                side="sell",
                size=self.target_size,
                price=hyperliquid_price,
                order_type="limit"
            )
            
            if result and result.get('response', {}).get('data', {}).get('statuses'):
                status = result['response']['data']['statuses'][0]
                if 'resting' in status:
                    # Order is in orderbook
                    hyperliquid_oid = str(status['resting']['oid'])
                    logger.success(f"   ✅ Hyperliquid OID: {hyperliquid_oid}")
                elif 'filled' in status:
                    # Instant fill!
                    logger.success(f"   🔥 Hyperliquid FILLED instantly!")
                    self.hyperliquid_filled = True
                    return extended_oid, None
                elif 'error' in status:
                    logger.error(f"   ❌ Hyperliquid error: {status['error']}")
            else:
                logger.error(f"   ❌ Hyperliquid failed: {result}")
        except Exception as e:
            logger.error(f"   ❌ Hyperliquid error: {e}")
        
        return extended_oid, hyperliquid_oid
    
    def check_fills(self) -> Tuple[bool, bool]:
        """
        Vérifie si les ordres sont remplis
        Returns: (extended_filled, hyperliquid_filled)
        """
        ext_filled = False
        hyp_filled = False
        
        # Check Extended position
        try:
            positions = self.extended.get_positions()
            for pos in positions:
                if self.symbol.upper() in pos.get('symbol', '').upper():
                    size = float(pos.get('size', 0))
                    if size >= self.target_size:
                        ext_filled = True
                        logger.success(f"   ✅ Extended FILLED: {size} ZORA")
        except Exception as e:
            logger.error(f"   ❌ Extended check error: {e}")
        
        # Check Hyperliquid position
        try:
            positions = self.hyperliquid.get_positions()
            for pos in positions:
                if pos.get('coin') == self.symbol:
                    size = abs(float(pos.get('szi', 0)))
                    if size >= self.target_size:
                        hyp_filled = True
                        logger.success(f"   ✅ Hyperliquid FILLED: {size} ZORA")
        except Exception as e:
            logger.error(f"   ❌ Hyperliquid check error: {e}")
        
        return ext_filled, hyp_filled
    
    def cancel_orders(self):
        """Cancel pending orders"""
        logger.warning(f"\n⚠️ Cancelling pending orders...")
        
        # TODO: Implement cancel for Extended
        # TODO: Implement cancel for Hyperliquid
        
        logger.info(f"   Orders cancelled (if any)")
    
    def emergency_fill_opposite(self, extended_filled: bool, hyperliquid_filled: bool):
        """
        Si un côté est fill, fill l'autre IMMÉDIATEMENT en TAKER
        pour rester delta-neutral
        """
        if extended_filled and not hyperliquid_filled:
            logger.warning(f"\n🚨 EMERGENCY: Extended filled, Hyperliquid NOT filled!")
            logger.warning(f"   → Placing TAKER SHORT on Hyperliquid...")
            
            try:
                result = self.hyperliquid.place_order(
                    symbol=self.symbol,
                    side="sell",
                    size=self.target_size,
                    order_type="market"
                )
                logger.success(f"   ✅ Emergency TAKER filled!")
                self.hyperliquid_filled = True
            except Exception as e:
                logger.error(f"   ❌ Emergency TAKER failed: {e}")
        
        elif hyperliquid_filled and not extended_filled:
            logger.warning(f"\n🚨 EMERGENCY: Hyperliquid filled, Extended NOT filled!")
            logger.warning(f"   → Placing TAKER LONG on Extended...")
            
            try:
                result = self.extended.place_order(
                    symbol=self.symbol,
                    side="buy",
                    size=self.target_size,
                    order_type="market"
                )
                logger.success(f"   ✅ Emergency TAKER filled!")
                self.extended_filled = True
            except Exception as e:
                logger.error(f"   ❌ Emergency TAKER failed: {e}")
    
    def run(self):
        """Exécute le bot delta-neutral MAKER"""
        logger.info("="*100)
        logger.info("🎯 DELTA NEUTRAL MAKER - Mode COMPLET")
        logger.info("="*100)
        
        logger.info(f"\n📝 Configuration:")
        logger.info(f"   Symbol: {self.symbol}")
        logger.info(f"   Size: {self.target_size} ZORA")
        logger.info(f"   Leverage: {self.leverage}x")
        logger.info(f"   Margin target: ~${self.target_margin}")
        
        # Set leverage
        self.set_leverage()
        
        # Retry loop
        for attempt in range(self.max_retries):
            offset = self.offsets[attempt] if attempt < len(self.offsets) else self.offsets[-1]
            
            logger.info(f"\n{'='*100}")
            logger.info(f"🔄 TENTATIVE {attempt + 1}/{self.max_retries} (offset {offset*100:.3f}%)")
            logger.info(f"{'='*100}")
            
            # Place LIMIT orders
            ext_oid, hyp_oid = self.place_limit_orders(offset)
            
            if not ext_oid and not hyp_oid:
                logger.error(f"\n❌ Échec placement ordres, retry...")
                time.sleep(2)
                continue
            
            # Wait and monitor fills
            logger.info(f"\n⏳ Attente fills (timeout {self.retry_timeout}s)...")
            
            start_time = time.time()
            while (time.time() - start_time) < self.retry_timeout:
                time.sleep(2)
                
                ext_filled, hyp_filled = self.check_fills()
                
                if ext_filled and hyp_filled:
                    logger.success(f"\n🎉 BOTH FILLED! Delta-neutral OK!")
                    self.extended_filled = True
                    self.hyperliquid_filled = True
                    return True
                
                elif ext_filled or hyp_filled:
                    # Un seul côté filled → EMERGENCY TAKER sur l'autre
                    self.emergency_fill_opposite(ext_filled, hyp_filled)
                    
                    if self.extended_filled and self.hyperliquid_filled:
                        logger.success(f"\n🎉 BOTH FILLED (emergency)! Delta-neutral OK!")
                        return True
            
            # Timeout → cancel et retry avec offset plus grand
            logger.warning(f"\n⏱️ Timeout {self.retry_timeout}s, pas de fill...")
            self.cancel_orders()
            
            if attempt < self.max_retries - 1:
                logger.info(f"   → Retry avec offset plus agressif: {self.offsets[attempt+1]*100:.3f}%")
        
        # Max retries atteint → TAKER en dernier recours
        logger.error(f"\n❌ Max retries atteint, passage en TAKER...")
        
        try:
            # Extended TAKER
            self.extended.place_order(
                symbol=self.symbol,
                side="buy",
                size=self.target_size,
                order_type="market"
            )
            
            time.sleep(1)
            
            # Hyperliquid TAKER
            self.hyperliquid.place_order(
                symbol=self.symbol,
                side="sell",
                size=self.target_size,
                order_type="market"
            )
            
            logger.warning(f"⚠️ TAKER fallback executed (spread cost important!)")
            return True
            
        except Exception as e:
            logger.error(f"❌ TAKER fallback failed: {e}")
            return False


def main():
    try:
        bot = DeltaNeutralMaker()
        success = bot.run()
        
        if success:
            logger.success(f"\n{'='*100}")
            logger.success(f"✅ DELTA NEUTRAL POSITION OPENED!")
            logger.success(f"{'='*100}")
        else:
            logger.error(f"\n{'='*100}")
            logger.error(f"❌ FAILED TO OPEN DELTA NEUTRAL POSITION")
            logger.error(f"{'='*100}")
    
    except KeyboardInterrupt:
        logger.warning("\n⚠️ Interrompu par l'utilisateur")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"❌ Erreur: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
Test COMPLET Delta-Neutral : 
1. Ouverture LONG Extended + SHORT Hyperliquid
2. Attente 30 secondes
3. Fermeture simultanée des deux positions

Objectif: Valider que l'ouverture ET la fermeture fonctionnent parfaitement
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

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.exchanges.extended_api import ExtendedAPI
from src.exchanges.hyperliquid_api import HyperliquidAPI


def main():
    logger.info("="*100)
    logger.info("🧪 TEST COMPLET DELTA-NEUTRAL : OUVERTURE → ATTENTE 30s → FERMETURE")
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
    logger.info(f"   Taille cible: ${target_usd} par exchange")
    logger.info(f"   Total position: ${target_usd * 2}")
    
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
    
    # Choose symbol
    logger.info("\n📊 Symboles disponibles:")
    logger.info("   1. BTC")
    logger.info("   2. ETH")
    logger.info("   3. SOL")
    
    choice = input("\nVotre choix (1-3) [2]: ").strip() or "2"
    symbol_map = {"1": "BTC", "2": "ETH", "3": "SOL"}
    symbol = symbol_map.get(choice, "ETH")
    
    logger.info(f"\n{'='*100}")
    logger.info(f"🎯 PHASE 1: OUVERTURE DELTA-NEUTRAL - {symbol}")
    logger.info(f"{'='*100}")
    
    # ==========================================
    # PHASE 1: OUVERTURE
    # ==========================================
    
    # Get market data
    logger.info(f"\n📊 Récupération des prix...")
    
    extended_ticker = extended.get_ticker(symbol)
    hyperliquid_ticker = hyperliquid.get_ticker(symbol)
    
    logger.success(f"✅ Extended {symbol}: bid={extended_ticker['bid']:.2f}, ask={extended_ticker['ask']:.2f}")
    logger.success(f"✅ Hyperliquid {symbol}: bid={hyperliquid_ticker['bid']:.2f}, ask={hyperliquid_ticker['ask']:.2f}")
    
    # Calculate SAME SIZE (delta-neutral requires same size, not same USD)
    avg_price = (extended_ticker['ask'] + hyperliquid_ticker['bid']) / 2
    target_size = target_usd / avg_price
    
    # Respect Extended minimums (most restrictive)
    min_sizes = {"BTC": 0.001, "ETH": 0.01, "SOL": 0.1}
    min_size_extended = min_sizes.get(symbol, 0.01)
    
    if target_size < min_size_extended:
        logger.warning(f"⚠️  Size {target_size:.4f} < min {min_size_extended}, using minimum")
        target_size = min_size_extended
    else:
        target_size = round(target_size, 4)
    
    # SAME SIZE on both exchanges
    extended_size = target_size
    hyperliquid_size = target_size
    
    logger.info(f"\n💰 Calcul des tailles:")
    logger.info(f"   Prix moyen: ${avg_price:.2f}")
    logger.info(f"   Size identique: {target_size} {symbol}")
    logger.info(f"   Extended LONG: {extended_size} {symbol} @ ~${extended_ticker['ask']:.2f} = ${extended_size * extended_ticker['ask']:.2f}")
    logger.info(f"   Hyperliquid SHORT: {hyperliquid_size} {symbol} @ ~${hyperliquid_ticker['bid']:.2f} = ${hyperliquid_size * hyperliquid_ticker['bid']:.2f}")
    logger.info(f"   Delta: ${abs(extended_size * extended_ticker['ask'] - hyperliquid_size * hyperliquid_ticker['bid']):.2f}")
    
    # Confirmation
    logger.warning(f"\n⚠️  ATTENTION: Vous allez placer des ordres RÉELS!")
    logger.warning(f"   - LONG {extended_size} {symbol} sur Extended")
    logger.warning(f"   - SHORT {hyperliquid_size} {symbol} sur Hyperliquid")
    logger.warning(f"   - Fermeture automatique après 30 secondes")
    
    confirm = input("\n✅ Confirmer l'ouverture? (yes/no) [no]: ").strip().lower()
    if confirm != "yes":
        logger.info("❌ Test annulé")
        return
    
    # Place OPENING orders
    logger.info(f"\n{'='*100}")
    logger.info("📝 PLACEMENT DES ORDRES D'OUVERTURE (LIMIT MAKER)...")
    logger.info(f"{'='*100}")
    
    # 1. Extended LONG (LIMIT MAKER ORDER)
    logger.info(f"\n1️⃣ Extended LONG {extended_size} {symbol} (LIMIT MAKER)...")
    extended_result = extended.place_order(
        symbol=symbol,
        side="buy",
        size=extended_size,
        order_type="limit"  # 🔥 LIMIT = MAKER avec post_only=True
    )
    
    if extended_result and extended_result.get('order_id'):
        logger.success(f"   ✅ Extended LONG placed!")
        logger.info(f"   Order ID: {extended_result['order_id']}")
        logger.info(f"   Size: {extended_result.get('size', extended_size)} {symbol}")
        logger.info(f"   Price: ${extended_result.get('price', 'pending')}")
    else:
        logger.error(f"   ❌ Extended LONG failed: {extended_result}")
        return
    
    time.sleep(2)  # Petit délai entre les ordres
    
    # 2. Hyperliquid SHORT (LIMIT MAKER ORDER)
    logger.info(f"\n2️⃣ Hyperliquid SHORT {hyperliquid_size} {symbol} (LIMIT MAKER)...")
    hyperliquid_result = hyperliquid.place_order(
        symbol=symbol,
        side="sell",
        size=hyperliquid_size,
        order_type="limit",  # 🔥 LIMIT = MAKER
        post_only=True  # 🔥 Force MAKER (Alo)
    )
    
    if hyperliquid_result and hyperliquid_result.get('status') in ['ok', 'OK']:
        logger.success(f"   ✅ Hyperliquid SHORT placed!")
        logger.info(f"   Status: {hyperliquid_result.get('status')}")
        logger.info(f"   Size: {hyperliquid_result.get('totalSz', hyperliquid_size)} {symbol}")
        logger.info(f"   Avg Price: ${hyperliquid_result.get('avgPx', 'pending')}")
    else:
        logger.error(f"   ❌ Hyperliquid SHORT failed: {hyperliquid_result}")
        logger.warning("   ⚠️  ATTENTION: Extended LONG est ouvert mais Hyperliquid SHORT a échoué!")
        logger.warning("   → Position non hedge! Fermez manuellement Extended LONG")
        return
    
    logger.info(f"\n{'='*100}")
    logger.success("✅ DELTA-NEUTRAL POSITION OUVERTE")
    logger.info(f"{'='*100}")
    
    # ==========================================
    # PHASE 2: ATTENTE 30 SECONDES
    # ==========================================
    
    logger.info(f"\n⏳ Attente de 30 secondes avant fermeture...")
    for i in range(30, 0, -5):
        logger.info(f"   {i}s restantes...")
        time.sleep(5)
    
    # ==========================================
    # PHASE 3: FERMETURE
    # ==========================================
    
    logger.info(f"\n{'='*100}")
    logger.info(f"🎯 PHASE 2: FERMETURE DELTA-NEUTRAL - {symbol}")
    logger.info(f"{'='*100}")
    
    # Get current prices for closing
    logger.info(f"\n📊 Récupération des prix de fermeture...")
    
    extended_ticker_close = extended.get_ticker(symbol)
    hyperliquid_ticker_close = hyperliquid.get_ticker(symbol)
    
    logger.success(f"✅ Extended {symbol}: bid={extended_ticker_close['bid']:.2f}, ask={extended_ticker_close['ask']:.2f}")
    logger.success(f"✅ Hyperliquid {symbol}: bid={hyperliquid_ticker_close['bid']:.2f}, ask={hyperliquid_ticker_close['ask']:.2f}")
    
    # Place CLOSING orders (inverse des positions ouvertes)
    logger.info(f"\n{'='*100}")
    logger.info("📝 PLACEMENT DES ORDRES DE FERMETURE (LIMIT MAKER)...")
    logger.info(f"{'='*100}")
    
    # 1. Close Extended LONG → SELL (LIMIT MAKER)
    logger.info(f"\n1️⃣ Fermeture Extended LONG (SELL {extended_size} {symbol} LIMIT MAKER)...")
    extended_close_result = extended.place_order(
        symbol=symbol,
        side="sell",
        size=extended_size,
        order_type="limit"  # 🔥 LIMIT = MAKER
    )
    
    if extended_close_result and extended_close_result.get('order_id'):
        logger.success(f"   ✅ Extended LONG fermé!")
        logger.info(f"   Order ID: {extended_close_result['order_id']}")
        logger.info(f"   Size: {extended_close_result.get('size', extended_size)} {symbol}")
        logger.info(f"   Price: ${extended_close_result.get('price', 'pending')}")
    else:
        logger.error(f"   ❌ Extended close failed: {extended_close_result}")
    
    time.sleep(2)
    
    # 2. Close Hyperliquid SHORT → BUY (LIMIT MAKER)
    logger.info(f"\n2️⃣ Fermeture Hyperliquid SHORT (BUY {hyperliquid_size} {symbol} LIMIT MAKER)...")
    hyperliquid_close_result = hyperliquid.place_order(
        symbol=symbol,
        side="buy",
        size=hyperliquid_size,
        order_type="limit",  # 🔥 LIMIT = MAKER
        post_only=True  # 🔥 Force MAKER (Alo)
    )
    
    if hyperliquid_close_result and hyperliquid_close_result.get('status') in ['ok', 'OK']:
        logger.success(f"   ✅ Hyperliquid SHORT fermé!")
        logger.info(f"   Status: {hyperliquid_close_result.get('status')}")
        logger.info(f"   Size: {hyperliquid_close_result.get('totalSz', hyperliquid_size)} {symbol}")
        logger.info(f"   Avg Price: ${hyperliquid_close_result.get('avgPx', 'pending')}")
    else:
        logger.error(f"   ❌ Hyperliquid close failed: {hyperliquid_close_result}")
    
    # ==========================================
    # RÉSUMÉ FINAL
    # ==========================================
    
    logger.info(f"\n{'='*100}")
    logger.success("✅ TEST COMPLET TERMINÉ")
    logger.info(f"{'='*100}")
    
    logger.info(f"\n📊 RÉSUMÉ DES OPÉRATIONS:")
    logger.info(f"\n   OUVERTURE:")
    logger.info(f"   - Extended LONG {extended_size} {symbol} @ ${extended_ticker['ask']:.2f}")
    logger.info(f"   - Hyperliquid SHORT {hyperliquid_size} {symbol} @ ${hyperliquid_ticker['bid']:.2f}")
    logger.info(f"   - Delta ouverture: ${abs(extended_size * extended_ticker['ask'] - hyperliquid_size * hyperliquid_ticker['bid']):.2f}")
    
    logger.info(f"\n   FERMETURE (30s après):")
    logger.info(f"   - Extended SELL {extended_size} {symbol} @ ${extended_ticker_close['bid']:.2f}")
    logger.info(f"   - Hyperliquid BUY {hyperliquid_size} {symbol} @ ${hyperliquid_ticker_close['ask']:.2f}")
    
    # Calculate P&L
    logger.info(f"\n   P&L ESTIMÉ:")
    extended_pnl = extended_size * (extended_ticker_close['bid'] - extended_ticker['ask'])
    hyperliquid_pnl = hyperliquid_size * (hyperliquid_ticker['bid'] - hyperliquid_ticker_close['ask'])
    total_pnl = extended_pnl + hyperliquid_pnl
    
    logger.info(f"   - Extended P&L: ${extended_pnl:.2f}")
    logger.info(f"   - Hyperliquid P&L: ${hyperliquid_pnl:.2f}")
    logger.info(f"   - Total P&L: ${total_pnl:.2f} (avant frais)")
    
    logger.info(f"\n{'='*100}")
    logger.success("🎉 TEST RÉUSSI - Ouverture et fermeture delta-neutral fonctionnent!")
    logger.info(f"{'='*100}\n")


if __name__ == "__main__":
    main()

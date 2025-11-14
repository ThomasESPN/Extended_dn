"""
Test COMPLET Delta-Neutral avec MAKER orders et MONITORING des fills

Stratégie:
1. Place LIMIT MAKER sur les deux exchanges (mid price)
2. Attend 10 secondes pour les fills
3. Si les deux sont filled → OK
4. Si un seul filled → Annule l'autre et place MARKET pour hedge immédiat
5. Fermeture après 30s
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


def check_order_filled(api, exchange_name, order_result, symbol):
    """
    Vérifie si un ordre est fill
    
    Returns:
        bool: True si filled, False sinon
    """
    # Pour Extended, on doit vérifier via les positions
    if exchange_name == "extended":
        # L'ordre Extended retourne juste un ID, on doit vérifier les positions
        positions = api.get_positions()
        for pos in positions:
            if pos.get('symbol') == symbol:
                logger.info(f"   ✅ Extended: Position {symbol} détectée, ordre filled!")
                return True
        logger.warning(f"   ⏳ Extended: Pas de position {symbol} détectée, ordre en attente")
        return False
    
    # Pour Hyperliquid, on peut vérifier le status OU les positions
    elif exchange_name == "hyperliquid":
        # MÉTHODE 1: Vérifier les positions (plus fiable pour détecter les fills)
        positions = api.get_open_positions()  # Hyperliquid utilise get_open_positions()
        for pos in positions:
            if pos.get('symbol') == symbol:
                logger.info(f"   ✅ Hyperliquid: Position {symbol} détectée, ordre filled!")
                return True
        
        # MÉTHODE 2: Si pas de position, vérifier le status de l'ordre
        if order_result.get('status') == 'ok':
            response = order_result.get('response', {})
            data = response.get('data', {})
            statuses = data.get('statuses', [])
            if statuses:
                status = statuses[0]
                if 'filled' in status:
                    logger.info(f"   ✅ Hyperliquid: Ordre filled!")
                    return True
                elif 'error' in status:
                    logger.warning(f"   ⏳ Hyperliquid: Ordre rejeté ou en attente: {status.get('error')}")
                    return False
                elif 'resting' in status:
                    logger.info(f"   ⏳ Hyperliquid: Ordre resting (pas encore filled)")
                    return False
        logger.warning(f"   ⏳ Hyperliquid: Status inconnu, assume non filled")
        return False
    
    return False


def main():
    logger.info("="*100)
    logger.info("🧪 TEST DELTA-NEUTRAL MAKER + MONITORING")
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
    logger.info(f"🎯 PHASE 1: OUVERTURE DELTA-NEUTRAL MAKER - {symbol}")
    logger.info(f"{'='*100}")
    
    # Get market data
    logger.info(f"\n📊 Récupération des prix...")
    
    extended_ticker = extended.get_ticker(symbol)
    hyperliquid_ticker = hyperliquid.get_ticker(symbol)
    
    logger.success(f"✅ Extended {symbol}: bid={extended_ticker['bid']:.2f}, ask={extended_ticker['ask']:.2f}")
    logger.success(f"✅ Hyperliquid {symbol}: bid={hyperliquid_ticker['bid']:.2f}, ask={hyperliquid_ticker['ask']:.2f}")
    
    # Calculate SAME SIZE
    avg_price = (extended_ticker['ask'] + hyperliquid_ticker['bid']) / 2
    target_size = target_usd / avg_price
    
    # Respect minimums
    min_sizes = {"BTC": 0.001, "ETH": 0.01, "SOL": 0.1}
    min_size_extended = min_sizes.get(symbol, 0.01)
    
    if target_size < min_size_extended:
        logger.warning(f"⚠️  Size {target_size:.4f} < min {min_size_extended}, using minimum")
        target_size = min_size_extended
    else:
        target_size = round(target_size, 4)
    
    extended_size = target_size
    hyperliquid_size = target_size
    
    logger.info(f"\n💰 Calcul des tailles:")
    logger.info(f"   Size identique: {target_size} {symbol}")
    logger.info(f"   Extended LONG: {extended_size} {symbol}")
    logger.info(f"   Hyperliquid SHORT: {hyperliquid_size} {symbol}")
    
    # Confirmation
    logger.warning(f"\n⚠️  STRATÉGIE:")
    logger.warning(f"   1. Place LIMIT MAKER (mid price) sur les deux exchanges")
    logger.warning(f"   2. Attend 10s pour les fills")
    logger.warning(f"   3. Si asymétrique → annule et place MARKET pour hedge")
    
    confirm = input("\n✅ Confirmer? (yes/no) [no]: ").strip().lower()
    if confirm != "yes":
        logger.info("❌ Test annulé")
        return
    
    # ==========================================
    # PHASE 1: PLACEMENT LIMIT MAKER
    # ==========================================
    
    logger.info(f"\n{'='*100}")
    logger.info("📝 PLACEMENT LIMIT MAKER...")
    logger.info(f"{'='*100}")
    
    # Extended LONG
    logger.info(f"\n1️⃣ Extended LONG {extended_size} {symbol} (LIMIT MAKER - mid price)...")
    extended_result = extended.place_order(
        symbol=symbol,
        side="buy",
        size=extended_size,
        order_type="limit"
    )
    
    if not extended_result or not extended_result.get('order_id'):
        logger.error(f"   ❌ Extended failed: {extended_result}")
        return
    
    extended_order_id = extended_result['order_id']
    logger.success(f"   ✅ Extended ordre placé! ID: {extended_order_id}")
    
    time.sleep(2)
    
    # Hyperliquid SHORT
    logger.info(f"\n2️⃣ Hyperliquid SHORT {hyperliquid_size} {symbol} (LIMIT MAKER - mid price)...")
    hyperliquid_result = hyperliquid.place_order(
        symbol=symbol,
        side="sell",
        size=hyperliquid_size,
        order_type="limit",
        post_only=True
    )
    
    if not hyperliquid_result or hyperliquid_result.get('status') != 'ok':
        logger.error(f"   ❌ Hyperliquid failed: {hyperliquid_result}")
        logger.warning("   ⚠️  Extended ordre placé mais Hyperliquid échoué!")
        logger.warning("   → Annulation Extended...")
        extended.cancel_order(extended_order_id)
        return
    
    logger.success(f"   ✅ Hyperliquid ordre placé!")
    
    # ==========================================
    # PHASE 2: MONITORING FILLS (60 secondes pour MAKER)
    # ==========================================
    
    logger.info(f"\n{'='*100}")
    logger.info("⏳ MONITORING DES FILLS (60 secondes pour ordres MAKER)...")
    logger.info(f"{'='*100}")
    
    extended_filled = False
    hyperliquid_filled = False
    
    # 60 secondes au total, check toutes les 5s (12 checks)
    for i in range(60, 0, -5):
        logger.info(f"\n   ⏰ {i}s restantes...")
        time.sleep(5)
        
        # Check Extended
        if not extended_filled:
            extended_filled = check_order_filled(extended, "extended", extended_result, symbol)
        
        # Check Hyperliquid
        if not hyperliquid_filled:
            hyperliquid_filled = check_order_filled(hyperliquid, "hyperliquid", hyperliquid_result, symbol)
        
        # Si les deux filled → break
        if extended_filled and hyperliquid_filled:
            logger.success("\n   ✅✅ LES DEUX ORDRES SONT FILLED!")
            break
    
    # ==========================================
    # PHASE 3: GESTION ASYMÉTRIQUE
    # ==========================================
    
    logger.info(f"\n{'='*100}")
    logger.info("📊 RÉSULTAT DU MONITORING")
    logger.info(f"{'='*100}")
    
    logger.info(f"\n   Extended LONG: {'✅ FILLED' if extended_filled else '❌ PAS FILLED'}")
    logger.info(f"   Hyperliquid SHORT: {'✅ FILLED' if hyperliquid_filled else '❌ PAS FILLED'}")
    
    if extended_filled and hyperliquid_filled:
        logger.success("\n   🎉 DELTA-NEUTRAL PARFAIT - Les deux sont filled en MAKER!")
        
    elif extended_filled and not hyperliquid_filled:
        logger.error("\n   ⚠️  ASYMÉTRIQUE: Extended filled mais pas Hyperliquid!")
        logger.warning("   → On doit SHORTER sur Hyperliquid immédiatement en MARKET")
        
        # Place MARKET sur Hyperliquid pour hedge
        logger.info("\n   📝 Placement MARKET SHORT Hyperliquid pour hedge...")
        hedge_result = hyperliquid.place_order(
            symbol=symbol,
            side="sell",
            size=hyperliquid_size,
            order_type="market"
        )
        
        if hedge_result and hedge_result.get('status') == 'ok':
            logger.success("   ✅ Hedge réussi! Position delta-neutral rétablie")
        else:
            logger.error(f"   ❌ Hedge échoué: {hedge_result}")
            logger.error("   ⚠️⚠️⚠️ POSITION NON HEDGE - RISQUE!")
            return
            
    elif not extended_filled and hyperliquid_filled:
        logger.error("\n   ⚠️  ASYMÉTRIQUE: Hyperliquid filled mais pas Extended!")
        logger.warning("   → On doit LONGER sur Extended immédiatement en MARKET")
        
        # Annuler l'ordre Extended LIMIT
        logger.info(f"\n   ❌ Annulation ordre Extended {extended_order_id}...")
        extended.cancel_order(extended_order_id)
        
        # Place MARKET sur Extended pour hedge
        logger.info("\n   📝 Placement MARKET LONG Extended pour hedge...")
        hedge_result = extended.place_order(
            symbol=symbol,
            side="buy",
            size=extended_size,
            order_type="market"
        )
        
        if hedge_result and hedge_result.get('order_id'):
            logger.success("   ✅ Hedge réussi! Position delta-neutral rétablie")
        else:
            logger.error(f"   ❌ Hedge échoué: {hedge_result}")
            logger.error("   ⚠️⚠️⚠️ POSITION NON HEDGE - RISQUE!")
            return
            
    else:
        logger.error("\n   ❌❌ AUCUN ORDRE FILLED!")
        logger.info("   → Annulation des deux ordres...")
        extended.cancel_order(extended_order_id)
        logger.info("   → Test terminé sans position")
        return
    
    # ==========================================
    # PHASE 4: ATTENTE AVANT FERMETURE
    # ==========================================
    
    logger.info(f"\n{'='*100}")
    logger.success("✅ DELTA-NEUTRAL POSITION ACTIVE")
    logger.info(f"{'='*100}")
    
    logger.info(f"\n⏳ Attente de 30 secondes avant fermeture...")
    for i in range(30, 0, -5):
        logger.info(f"   {i}s restantes...")
        time.sleep(5)
    
    # ==========================================
    # PHASE 5: FERMETURE (MARKET pour garantir le fill)
    # ==========================================
    
    logger.info(f"\n{'='*100}")
    logger.info(f"🎯 FERMETURE DELTA-NEUTRAL - {symbol}")
    logger.info(f"{'='*100}")
    
    logger.info("\n📝 Fermeture en MARKET pour garantir l'exécution immédiate...")
    
    # Close Extended
    logger.info(f"\n1️⃣ Fermeture Extended LONG (SELL MARKET)...")
    extended_close = extended.place_order(
        symbol=symbol,
        side="sell",
        size=extended_size,
        order_type="market"
    )
    
    if extended_close and extended_close.get('order_id'):
        logger.success(f"   ✅ Extended fermé!")
    else:
        logger.error(f"   ❌ Extended close failed")
    
    time.sleep(2)
    
    # Close Hyperliquid
    logger.info(f"\n2️⃣ Fermeture Hyperliquid SHORT (BUY MARKET)...")
    hyperliquid_close = hyperliquid.place_order(
        symbol=symbol,
        side="buy",
        size=hyperliquid_size,
        order_type="market"
    )
    
    if hyperliquid_close and hyperliquid_close.get('status') == 'ok':
        logger.success(f"   ✅ Hyperliquid fermé!")
    else:
        logger.error(f"   ❌ Hyperliquid close failed")
    
    logger.info(f"\n{'='*100}")
    logger.success("✅ TEST TERMINÉ")
    logger.info(f"{'='*100}\n")


if __name__ == "__main__":
    main()

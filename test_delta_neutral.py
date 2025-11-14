"""
Test Delta-Neutral : Extended LONG + Hyperliquid SHORT
Strictement la même valeur USD sur les deux exchanges
"""
import json
import sys
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
    logger.info("="*80)
    logger.info("🧪 TEST DELTA-NEUTRAL : Extended LONG + Hyperliquid SHORT")
    logger.info("="*80)
    
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
    
    logger.info(f"\n{'='*80}")
    logger.info(f"🎯 TEST DELTA-NEUTRAL - {symbol}")
    logger.info(f"{'='*80}")
    
    # Get market data from both exchanges
    logger.info(f"\n📊 Récupération des prix...")
    
    extended_ticker = extended.get_ticker(symbol)
    hyperliquid_ticker = hyperliquid.get_ticker(symbol)
    
    logger.success(f"✅ Extended {symbol}: bid={extended_ticker['bid']}, ask={extended_ticker['ask']}")
    logger.success(f"✅ Hyperliquid {symbol}: bid={hyperliquid_ticker['bid']}, ask={hyperliquid_ticker['ask']}")
    
    # Calculate sizes for EXACT same USD value
    # IMPORTANT: Pour delta-neutral, il faut LA MÊME SIZE sur les deux exchanges !
    # Pas la même valeur USD, car les prix diffèrent légèrement
    
    # 1. Calculer la size pour atteindre target_usd
    avg_price = (extended_ticker['ask'] + hyperliquid_ticker['bid']) / 2
    target_size = target_usd / avg_price
    
    # 2. Respecter les minimums Extended (plus restrictif)
    min_sizes = {"BTC": 0.001, "ETH": 0.01, "SOL": 0.1}
    min_size_extended = min_sizes.get(symbol, 0.01)
    
    # 3. Utiliser AU MOINS le minimum Extended
    if target_size < min_size_extended:
        logger.warning(f"⚠️ Size calculée {target_size:.4f} < min Extended {min_size_extended}")
        logger.warning(f"   → Utilisation du minimum: {min_size_extended} {symbol}")
        target_size = min_size_extended
    else:
        # Arrondir au step size
        target_size = round(target_size, 4)
    
    # 4. MÊME SIZE sur les deux exchanges (c'est ça le vrai delta-neutral !)
    extended_size = target_size
    hyperliquid_size = target_size
    
    # 5. Calculer les prix d'entrée
    extended_entry_price = extended_ticker['ask'] * 1.0005  # +0.05% for fill
    hyperliquid_entry_price = hyperliquid_ticker['bid'] * 0.9995  # -0.05% for fill
    
    # Calculate EXACT USD values
    extended_usd = extended_size * extended_entry_price
    hyperliquid_usd = hyperliquid_size * hyperliquid_entry_price
    
    logger.info(f"\n💰 Calcul des positions DELTA-NEUTRAL:")
    logger.info(f"   Extended LONG:")
    logger.info(f"      Size: {extended_size} {symbol}")
    logger.info(f"      Prix: ${extended_entry_price:.2f}")
    logger.info(f"      Valeur: ${extended_usd:.2f}")
    logger.info(f"   Hyperliquid SHORT:")
    logger.info(f"      Size: {hyperliquid_size} {symbol}")
    logger.info(f"      Prix: ${hyperliquid_entry_price:.2f}")
    logger.info(f"      Valeur: ${hyperliquid_usd:.2f}")
    
    delta = abs(extended_usd - hyperliquid_usd)
    logger.info(f"\n📊 Delta entre les deux positions: ${delta:.2f}")
    
    # Le delta devrait être proche de 0 car même size
    if delta > 2.0:
        logger.warning(f"⚠️ Delta > $2 ! Vérifier les prix")
    else:
        logger.success(f"✅ Delta < $2 - Positions delta-neutral !")
    
    logger.info(f"\n⚡ Exposition nette au prix {symbol}:")
    logger.info(f"   LONG:  +{extended_size} {symbol}")
    logger.info(f"   SHORT: -{hyperliquid_size} {symbol}")
    logger.info(f"   NET:   {extended_size - hyperliquid_size:.6f} {symbol} ≈ $0")
    
    # Summary
    logger.info(f"\n🎯 Résumé des ordres:")
    logger.info(f"   📈 LONG Extended:  BUY  {extended_size} {symbol} @ ${extended_entry_price:.2f}")
    logger.info(f"   📉 SHORT Hyperliquid: SELL {hyperliquid_size} {symbol} @ ${hyperliquid_entry_price:.2f}")
    
    # Confirmation
    logger.warning(f"\n⚠️  ATTENTION - Ordres RÉELS sur les deux exchanges !")
    logger.warning(f"   Extended: ${extended_usd:.2f} (LONG)")
    logger.warning(f"   Hyperliquid: ${hyperliquid_usd:.2f} (SHORT)")
    logger.warning(f"   Total exposition: ${extended_usd + hyperliquid_usd:.2f}")
    logger.warning(f"   Delta-neutral: Oui (delta ${delta:.2f})")
    
    response = input("\n   Placer ces ordres ? Taper 'YES' pour continuer: ")
    if response.upper() != "YES":
        logger.info("❌ Test annulé")
        return
    
    # Place orders
    logger.info(f"\n🚀 Placement des ordres DELTA-NEUTRAL...")
    
    # 1. Extended LONG
    logger.info(f"\n📤 Ordre 1/2: LONG Extended...")
    extended_result = extended.place_order(
        symbol=symbol,
        side="buy",
        size=extended_size,
        price=extended_entry_price,
        order_type="limit"
    )
    
    if extended_result.get('status') == 'OK':
        logger.success(f"✅ Extended LONG placé: {extended_result.get('order_id')}")
    else:
        logger.error(f"❌ Extended FAILED: {extended_result.get('error')}")
        logger.warning("⚠️ Arrêt - Extended n'a pas fonctionné, pas d'ordre Hyperliquid")
        return
    
    # 2. Hyperliquid SHORT
    logger.info(f"\n📤 Ordre 2/2: SHORT Hyperliquid...")
    hyperliquid_result = hyperliquid.place_order(
        symbol=symbol,
        side="sell",
        size=hyperliquid_size,
        price=hyperliquid_entry_price,
        order_type="limit"
    )
    
    if hyperliquid_result and hyperliquid_result.get('status') == 'ok':
        logger.success(f"✅ Hyperliquid SHORT placé: {hyperliquid_result}")
    else:
        logger.error(f"❌ Hyperliquid FAILED: {hyperliquid_result}")
        logger.warning("⚠️ ATTENTION: Extended LONG est placé mais Hyperliquid SHORT a échoué !")
        logger.warning(f"   → Fermer manuellement le LONG Extended (order {extended_result.get('order_id')})")
        return
    
    # Success
    logger.info(f"\n{'='*80}")
    logger.success("🎉 SUCCÈS ! Position DELTA-NEUTRAL établie")
    logger.info(f"{'='*80}")
    
    logger.info(f"\n📊 Résumé:")
    logger.info(f"   Extended LONG:  {extended_size} {symbol} @ ${extended_entry_price:.2f} = ${extended_usd:.2f}")
    logger.info(f"   Hyperliquid SHORT: {hyperliquid_size} {symbol} @ ${hyperliquid_entry_price:.2f} = ${hyperliquid_usd:.2f}")
    logger.info(f"   Delta: ${delta:.2f}")
    
    logger.info(f"\n✅ Exposition nette au prix: ~$0 (delta-neutral)")
    logger.info(f"✅ Profit attendu: Différence de funding rates entre les exchanges")
    
    logger.info(f"\n📋 Vérifiez vos positions sur:")
    logger.info(f"   • Extended: https://app.extended.exchange")
    logger.info(f"   • Hyperliquid: https://app.hyperliquid.xyz")
    
    logger.info(f"\n{'='*80}")
    logger.success("🏁 Test delta-neutral terminé !")
    logger.info(f"{'='*80}")


if __name__ == "__main__":
    main()

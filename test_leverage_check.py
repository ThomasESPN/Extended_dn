"""
Test de vérification des leviers max sur Extended et Hyperliquid

Objectif:
- Vérifier que get_max_leverage() fonctionne sur les deux exchanges
- Valider la logique min(extended_max, hyperliquid_max, 10)
- Tester avec différentes paires (BTC, ETH, SOL, etc.)
"""

import sys
import json
from loguru import logger

# Setup logging
logger.remove()
logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{message}</level>", level="INFO")

# Import des APIs
from src.exchanges.extended_api import ExtendedAPI
from src.exchanges.hyperliquid_api import HyperliquidAPI

def test_leverage_compatibility():
    """Test de compatibilité des leviers entre Extended et Hyperliquid"""
    
    logger.info("\n" + "="*100)
    logger.info("🎯 TEST COMPATIBILITÉ LEVIERS - Extended vs Hyperliquid")
    logger.info("="*100 + "\n")
    
    # 1. Charger la config
    with open('config/config.json', 'r') as f:
        config = json.load(f)
    
    # 2. Initialiser les APIs
    logger.info("📡 Initialisation des APIs...\n")
    
    wallet_address = config['wallet']['address']
    private_key = config['wallet']['private_key']
    
    extended_config = config['extended']
    extended = ExtendedAPI(
        wallet_address=wallet_address,
        private_key=private_key,
        api_key=extended_config['api_key'],
        stark_public_key=extended_config['stark_public_key'],
        stark_private_key=extended_config['stark_private_key'],
        vault_id=extended_config['vault_id'],
        client_id=extended_config['client_id']
    )
    
    hyperliquid = HyperliquidAPI(
        wallet_address=wallet_address,
        private_key=private_key
    )
    
    # 3. Tester différentes paires
    test_symbols = ["BTC", "ETH", "SOL", "ARB", "OP", "AVAX"]
    
    logger.info("🔍 Vérification des leviers max pour chaque paire:\n")
    
    results = []
    
    for symbol in test_symbols:
        logger.info(f"📊 Checking {symbol}...")
        
        try:
            # Extended max leverage
            ext_max = extended.get_max_leverage(symbol)
            
            # Hyperliquid max leverage
            hyp_max = hyperliquid.get_max_leverage(symbol)
            
            # Compatible leverage (minimum des deux, max 10)
            compatible = min(ext_max, hyp_max, 10)
            
            results.append({
                'symbol': symbol,
                'extended_max': ext_max,
                'hyperliquid_max': hyp_max,
                'compatible': compatible
            })
            
            logger.success(f"   ✅ {symbol}: Extended {ext_max}x, Hyperliquid {hyp_max}x → Using {compatible}x\n")
            
        except Exception as e:
            logger.error(f"   ❌ Error for {symbol}: {e}\n")
    
    # 4. Afficher le tableau récapitulatif
    logger.info("\n" + "="*100)
    logger.info("📋 RÉCAPITULATIF DES LEVIERS")
    logger.info("="*100 + "\n")
    
    from tabulate import tabulate
    
    table_data = []
    for r in results:
        # Highlight si levier limité par Extended (plus restrictif)
        limited_by = ""
        if r['compatible'] == r['extended_max'] and r['extended_max'] < r['hyperliquid_max']:
            limited_by = "⚠️ Extended"
        elif r['compatible'] == 10 and (r['extended_max'] > 10 or r['hyperliquid_max'] > 10):
            limited_by = "⚠️ Config (max 10x)"
        
        table_data.append([
            r['symbol'],
            f"{r['extended_max']}x",
            f"{r['hyperliquid_max']}x",
            f"{r['compatible']}x",
            limited_by
        ])
    
    headers = ["Symbol", "Extended Max", "Hyperliquid Max", "Compatible", "Limited By"]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    
    # 5. Exemples de calculs
    logger.info("\n" + "="*100)
    logger.info("💡 EXEMPLES DE CALCULS")
    logger.info("="*100 + "\n")
    
    position_size_usd = 11  # Config par défaut
    
    for r in results[:3]:  # Top 3 symbols
        symbol = r['symbol']
        leverage = r['compatible']
        
        logger.info(f"📊 {symbol} avec leverage {leverage}x:")
        logger.info(f"   Position size: ${position_size_usd}")
        logger.info(f"   Notional value: ${position_size_usd * leverage}")
        logger.info(f"   Margin required: ${position_size_usd} ({100/leverage:.1f}%)")
        logger.info("")
    
    logger.info("="*100)
    logger.success("✅ Test terminé!")
    logger.info("="*100 + "\n")

if __name__ == "__main__":
    test_leverage_compatibility()

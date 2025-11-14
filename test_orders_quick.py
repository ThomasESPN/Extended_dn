"""
Script de test rapide pour vérifier les ordres LIMIT sur Extended et Hyperliquid
Sans attendre les cycles de funding
"""

import json
import sys
from loguru import logger
from src.exchanges.extended_api import ExtendedAPI
from src.exchanges.hyperliquid_api import HyperliquidAPI

logger.remove()
logger.add(sys.stdout, format="<green>{time:HH:mm:ss}</green> | <level>{level:8}</level> | <level>{message}</level>")

def load_config():
    """Charge la configuration"""
    with open('config/config.json', 'r') as f:
        return json.load(f)

def test_market_data(ext_api, hl_api, symbol):
    """Test récupération des données de marché"""
    logger.info(f"📊 Test données marché pour {symbol}...")
    
    # Extended
    try:
        ext_ticker = ext_api.get_ticker(symbol)
        logger.success(f"✅ Extended {symbol}: bid={ext_ticker['bid']}, ask={ext_ticker['ask']}")
    except Exception as e:
        logger.error(f"❌ Extended {symbol}: {e}")
        return None, None
    
    # Hyperliquid
    try:
        hl_ticker = hl_api.get_ticker(symbol)
        logger.success(f"✅ Hyperliquid {symbol}: bid={hl_ticker['bid']}, ask={hl_ticker['ask']}")
    except Exception as e:
        logger.error(f"❌ Hyperliquid {symbol}: {e}")
        return None, None
    
    return ext_ticker, hl_ticker

def test_order_placement(ext_api, hl_api, symbol, size_usd):
    """Test placement d'ordres LIMIT (simulation puis réel si confirmé)"""
    logger.info(f"\n{'='*80}")
    logger.info(f"🧪 TEST ORDRES LIMIT - {symbol}")
    logger.info(f"{'='*80}\n")
    
    # 1. Récupération des prix
    ext_ticker, hl_ticker = test_market_data(ext_api, hl_api, symbol)
    if not ext_ticker or not hl_ticker:
        return False
    
    # 2. Calcul de la taille en contracts
    ext_price = float(ext_ticker['last'])
    hl_price = float(hl_ticker['last'])
    
    ext_size = round(size_usd / ext_price, 4)
    hl_size = round(size_usd / hl_price, 4)
    
    logger.info(f"\n📊 Calcul des tailles:")
    logger.info(f"   Extended: {ext_size} {symbol} @ ${ext_price} = ${ext_size * ext_price:.2f}")
    logger.info(f"   Hyperliquid: {hl_size} {symbol} @ ${hl_price} = ${hl_size * hl_price:.2f}")
    
    # 3. Calcul des prix LIMIT (pour fill immédiat)
    # LONG Extended = BUY au ask (prix un peu plus haut)
    # SHORT Hyperliquid = SELL au bid (prix un peu plus bas)
    ext_limit_price = float(ext_ticker['ask']) * 1.0005  # +0.05% pour être sûr du fill
    hl_limit_price = float(hl_ticker['bid']) * 0.9995    # -0.05% pour être sûr du fill
    
    logger.info(f"\n💰 Prix LIMIT calculés (pour fill immédiat):")
    logger.info(f"   Extended LONG: ${ext_limit_price:.2f} (ask + 0.05%)")
    logger.info(f"   Hyperliquid SHORT: ${hl_limit_price:.2f} (bid - 0.05%)")
    
    # 4. Simulation
    logger.info(f"\n🎯 SIMULATION des ordres:")
    logger.info(f"   📈 LONG Extended: BUY {ext_size} {symbol} @ ${ext_limit_price:.2f}")
    logger.info(f"   📉 SHORT Hyperliquid: SELL {hl_size} {symbol} @ ${hl_limit_price:.2f}")
    
    # 5. Confirmation
    logger.warning(f"\n⚠️  Voulez-vous placer ces ordres RÉELS ?")
    logger.warning(f"   Cela va utiliser ~${size_usd * 2} (${size_usd} sur chaque exchange)")
    choice = input("\n   Taper 'YES' pour continuer, autre chose pour annuler: ")
    
    if choice.upper() != 'YES':
        logger.info("❌ Test annulé")
        return False
    
    # 6. Placement des ordres RÉELS
    logger.info(f"\n🚀 Placement des ordres RÉELS...")
    
    try:
        # LONG Extended
        logger.info(f"📤 Envoi ordre LONG Extended...")
        ext_order = ext_api.place_order(
            symbol=symbol,
            side='buy',
            size=ext_size,
            order_type='limit',
            price=ext_limit_price
        )
        logger.success(f"✅ Ordre Extended placé: {ext_order}")
        
        # SHORT Hyperliquid
        logger.info(f"📤 Envoi ordre SHORT Hyperliquid...")
        hl_order = hl_api.place_order(
            symbol=symbol,
            side='sell',
            size=hl_size,
            order_type='limit',
            price=hl_limit_price
        )
        logger.success(f"✅ Ordre Hyperliquid placé: {hl_order}")
        
        logger.success(f"\n{'='*80}")
        logger.success(f"🎉 SUCCÈS ! Les deux ordres sont placés")
        logger.success(f"{'='*80}")
        
        logger.info(f"\n📋 Vérifiez vos positions sur:")
        logger.info(f"   • Extended: https://app.extended.exchange")
        logger.info(f"   • Hyperliquid: https://app.hyperliquid.xyz")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur lors du placement: {e}")
        logger.warning(f"⚠️  Vérifiez manuellement vos positions sur les exchanges !")
        return False

def main():
    """Test principal"""
    logger.info(f"{'='*80}")
    logger.info(f"🧪 TEST RAPIDE DES ORDRES LIMIT")
    logger.info(f"{'='*80}\n")
    
    # Chargement config
    config = load_config()
    wallet = config['wallet']['address']
    private_key = config['wallet']['private_key']
    size_usd = config.get('auto_trading', {}).get('position_size_usd', 10)
    
    # Clés Extended
    extended_config = config.get('extended', {})
    api_key = extended_config.get('api_key')
    stark_public_key = extended_config.get('stark_public_key')
    stark_private_key = extended_config.get('stark_private_key')
    vault_id = extended_config.get('vault_id')
    
    logger.info(f"📝 Configuration:")
    logger.info(f"   Wallet: {wallet}")
    logger.info(f"   Taille: ${size_usd} par position\n")
    
    # Init APIs
    logger.info(f"🔌 Initialisation des APIs...")
    ext_api = ExtendedAPI(
        wallet_address=wallet, 
        private_key=private_key,
        api_key=api_key,
        stark_public_key=stark_public_key,
        stark_private_key=stark_private_key,
        vault_id=vault_id
    )
    hl_api = HyperliquidAPI(wallet_address=wallet, private_key=private_key)
    logger.success(f"✅ APIs initialisées\n")
    
    # Choix du symbole
    logger.info(f"Symboles disponibles:")
    logger.info(f"   1. BTC")
    logger.info(f"   2. ETH")
    logger.info(f"   3. SOL")
    logger.info(f"   4. Autre...")
    
    choice = input("\nVotre choix (1-4) [1]: ").strip() or "1"
    
    symbols = {
        "1": "BTC",
        "2": "ETH",
        "3": "SOL"
    }
    
    if choice == "4":
        symbol = input("Entrez le symbole (ex: DOGE): ").strip().upper()
    else:
        symbol = symbols.get(choice, "BTC")
    
    # Test des ordres
    success = test_order_placement(ext_api, hl_api, symbol, size_usd)
    
    if success:
        logger.info(f"\n{'='*80}")
        logger.success(f"✅ TEST RÉUSSI !")
        logger.info(f"{'='*80}")
        logger.info(f"\n💡 Maintenant vous savez que:")
        logger.info(f"   • Les ordres LIMIT passent bien sur les deux exchanges")
        logger.info(f"   • Les tailles sont correctement calculées")
        logger.info(f"   • Votre wallet est configuré correctement")
        logger.info(f"\n🤖 Le bot bot_auto_trading.py peut maintenant trader automatiquement !")
    else:
        logger.warning(f"\n⚠️  Test non réussi - Vérifiez les erreurs ci-dessus")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning(f"\n⚠️  Test interrompu par l'utilisateur")
    except Exception as e:
        logger.error(f"\n❌ Erreur: {e}")
        import traceback
        traceback.print_exc()

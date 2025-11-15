"""
Script de test pour comparer les WebSockets orderbook Extended et Hyperliquid
Affiche les prix des deux exchanges en temps réel côte à côte
"""
import sys
import os
import time
from pathlib import Path

# Ajouter le chemin du projet au path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root / "delta" / "src"))

try:
    from loguru import logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

from delta.src.exchanges.extended_api import ExtendedAPI
from delta.src.exchanges.hyperliquid_api import HyperliquidAPI


def test_dual_ws_orderbook():
    """Test de la connexion WebSocket orderbook sur les deux exchanges"""
    
    print("\n" + "="*80)
    print("🔌 Test WebSocket Dual - Extended vs Hyperliquid")
    print("="*80 + "\n")
    
    # Demander le ticker à l'utilisateur
    ticker = input("📊 Entrez le ticker (ex: ZORA, BTC, ETH, SOL) [ZORA]: ").strip()
    if not ticker:
        ticker = "ZORA"
    
    ticker = ticker.upper()
    
    print(f"\n🎯 Ticker sélectionné: {ticker}")
    print(f"   Extended: {ticker}-USD")
    print(f"   Hyperliquid: {ticker}\n")
    
    # Initialiser les APIs
    wallet_address = "0x0000000000000000000000000000000000000000"  # Adresse dummy pour test
    extended_api = ExtendedAPI(wallet_address)
    hyperliquid_api = HyperliquidAPI(wallet_address)
    
    # Se connecter aux deux WebSockets
    print("🔌 Connexion aux WebSockets...\n")
    
    extended_success = extended_api.ws_orderbook(ticker)
    hyperliquid_success = hyperliquid_api.ws_orderbook(ticker)
    
    if not extended_success:
        print(f"❌ Échec Extended pour {ticker}-USD")
    if not hyperliquid_success:
        print(f"❌ Échec Hyperliquid pour {ticker}")
    
    if not extended_success and not hyperliquid_success:
        print("\n❌ Aucune connexion réussie. Vérifiez que le ticker existe.")
        return
    
    print(f"\n✅ WebSockets connectés ! Attente des données...\n")
    print("💡 Appuyez sur Ctrl+C pour arrêter\n")
    print("="*80)
    
    try:
        # Variables pour tracker les derniers prix
        last_extended_bid = None
        last_extended_ask = None
        last_hyperliquid_bid = None
        last_hyperliquid_ask = None
        update_count = 0
        
        while True:
            # Récupérer les données des deux exchanges
            extended_data = extended_api.get_orderbook_data(ticker) if extended_success else None
            hyperliquid_data = hyperliquid_api.get_orderbook_data(ticker) if hyperliquid_success else None
            
            # Vérifier si au moins un exchange a des données
            if extended_data or hyperliquid_data:
                # Vérifier si les prix ont changé
                extended_changed = False
                hyperliquid_changed = False
                
                if extended_data:
                    extended_changed = (
                        extended_data['bid'] != last_extended_bid or 
                        extended_data['ask'] != last_extended_ask
                    )
                
                if hyperliquid_data:
                    hyperliquid_changed = (
                        hyperliquid_data['bid'] != last_hyperliquid_bid or 
                        hyperliquid_data['ask'] != last_hyperliquid_ask
                    )
                
                # Afficher si au moins un prix a changé
                if extended_changed or hyperliquid_changed:
                    update_count += 1
                    timestamp = time.strftime("%H:%M:%S")
                    
                    print(f"\n[{timestamp}] Update #{update_count}")
                    print("-" * 80)
                    
                    # Préparer les données pour affichage
                    if extended_data:
                        ext_bid = extended_data['bid']
                        ext_ask = extended_data['ask']
                        ext_mid = (ext_bid + ext_ask) / 2
                        ext_spread = ext_ask - ext_bid
                        ext_spread_pct = (ext_spread / ext_mid) * 100
                        
                        last_extended_bid = ext_bid
                        last_extended_ask = ext_ask
                    else:
                        ext_bid = ext_ask = ext_mid = ext_spread = ext_spread_pct = None
                    
                    if hyperliquid_data:
                        hyp_bid = hyperliquid_data['bid']
                        hyp_ask = hyperliquid_data['ask']
                        hyp_mid = (hyp_bid + hyp_ask) / 2
                        hyp_spread = hyp_ask - hyp_bid
                        hyp_spread_pct = (hyp_spread / hyp_mid) * 100
                        
                        last_hyperliquid_bid = hyp_bid
                        last_hyperliquid_ask = hyp_ask
                    else:
                        hyp_bid = hyp_ask = hyp_mid = hyp_spread = hyp_spread_pct = None
                    
                    # Affichage en colonnes
                    print(f"{'':20} {'Extended':>25} {'Hyperliquid':>25}")
                    print("-" * 80)
                    
                    if ext_bid and hyp_bid:
                        diff_bid = ext_bid - hyp_bid
                        diff_bid_pct = (diff_bid / hyp_bid) * 100
                        print(f"{'Bid:':20} ${ext_bid:>23,.6f} ${hyp_bid:>23,.6f} (Δ {diff_bid:+.6f} / {diff_bid_pct:+.3f}%)")
                    elif ext_bid:
                        print(f"{'Bid:':20} ${ext_bid:>23,.6f} {'N/A':>25}")
                    elif hyp_bid:
                        print(f"{'Bid:':20} {'N/A':>25} ${hyp_bid:>23,.6f}")
                    
                    if ext_ask and hyp_ask:
                        diff_ask = ext_ask - hyp_ask
                        diff_ask_pct = (diff_ask / hyp_ask) * 100
                        print(f"{'Ask:':20} ${ext_ask:>23,.6f} ${hyp_ask:>23,.6f} (Δ {diff_ask:+.6f} / {diff_ask_pct:+.3f}%)")
                    elif ext_ask:
                        print(f"{'Ask:':20} ${ext_ask:>23,.6f} {'N/A':>25}")
                    elif hyp_ask:
                        print(f"{'Ask:':20} {'N/A':>25} ${hyp_ask:>23,.6f}")
                    
                    if ext_mid and hyp_mid:
                        diff_mid = ext_mid - hyp_mid
                        diff_mid_pct = (diff_mid / hyp_mid) * 100
                        print(f"{'Mid:':20} ${ext_mid:>23,.6f} ${hyp_mid:>23,.6f} (Δ {diff_mid:+.6f} / {diff_mid_pct:+.3f}%)")
                    elif ext_mid:
                        print(f"{'Mid:':20} ${ext_mid:>23,.6f} {'N/A':>25}")
                    elif hyp_mid:
                        print(f"{'Mid:':20} {'N/A':>25} ${hyp_mid:>23,.6f}")
                    
                    if ext_spread and hyp_spread:
                        print(f"{'Spread:':20} ${ext_spread:>23,.6f} ({ext_spread_pct:.4f}%) ${hyp_spread:>12,.6f} ({hyp_spread_pct:.4f}%)")
                    elif ext_spread:
                        print(f"{'Spread:':20} ${ext_spread:>23,.6f} ({ext_spread_pct:.4f}%) {'N/A':>25}")
                    elif hyp_spread:
                        print(f"{'Spread:':20} {'N/A':>25} ${hyp_spread:>12,.6f} ({hyp_spread_pct:.4f}%)")
                    
                    # Afficher l'opportunité d'arbitrage si les deux exchanges ont des données
                    if ext_mid and hyp_mid:
                        print("\n" + "-" * 80)
                        if ext_mid > hyp_mid:
                            arb_pct = ((ext_mid - hyp_mid) / hyp_mid) * 100
                            print(f"💰 Opportunité: Extended {arb_pct:+.4f}% plus cher → Vendre Extended, Acheter Hyperliquid")
                        elif hyp_mid > ext_mid:
                            arb_pct = ((hyp_mid - ext_mid) / ext_mid) * 100
                            print(f"💰 Opportunité: Hyperliquid {arb_pct:+.4f}% plus cher → Vendre Hyperliquid, Acheter Extended")
                        else:
                            print("✅ Prix identiques - Pas d'opportunité d'arbitrage")
                    
                    print("="*80)
            
            else:
                # Pas encore de données reçues
                if update_count == 0:
                    print("⏳ En attente des données des WebSockets...")
                    time.sleep(1)
            
            time.sleep(0.5)  # Vérifier toutes les 500ms
            
    except KeyboardInterrupt:
        print("\n\n🛑 Arrêt demandé par l'utilisateur")
        
        # Fermer les WebSockets proprement
        if extended_api.ws_app:
            try:
                extended_api.ws_app.close()
                print("✅ WebSocket Extended fermé")
            except:
                pass
        
        if hyperliquid_api.ws_app:
            try:
                hyperliquid_api.ws_app.close()
                print("✅ WebSocket Hyperliquid fermé")
            except:
                pass
        
        print("\n👋 Au revoir !\n")


if __name__ == "__main__":
    try:
        test_dual_ws_orderbook()
    except Exception as e:
        logger.error(f"Erreur lors du test: {e}")
        import traceback
        traceback.print_exc()


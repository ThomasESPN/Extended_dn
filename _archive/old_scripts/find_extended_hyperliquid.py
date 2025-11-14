#!/usr/bin/env python3
"""
Analyseur Extended vs Hyperliquid UNIQUEMENT
Utilise les API directes au lieu de Loris Tools pour des données fiables
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.exchanges.extended_api import ExtendedAPI
from src.exchanges.hyperliquid_api import HyperliquidAPI
from config import get_config
from datetime import datetime
from typing import Dict, List
from tabulate import tabulate


def find_arbitrage_opportunities(extended_rates: Dict, hyperliquid_rates: Dict) -> List[Dict]:
    """
    Trouve les opportunités d'arbitrage entre Extended et Hyperliquid
    
    Args:
        extended_rates: Dict {symbol: {rate, ...}}
        hyperliquid_rates: Dict {symbol: {rate, ...}}
        
    Returns:
        Liste d'opportunités triées par spread
    """
    opportunities = []
    
    # Symboles communs aux deux exchanges
    common_symbols = set(extended_rates.keys()) & set(hyperliquid_rates.keys())
    
    print(f"\n🔍 Analyse de {len(common_symbols)} symboles communs...")
    
    for symbol in common_symbols:
        ext_info = extended_rates[symbol]
        hyp_info = hyperliquid_rates[symbol]
        
        ext_rate = ext_info['rate']
        hyp_rate = hyp_info['rate']
        
        # Calculer le spread en basis points (bps)
        spread_bps = abs(ext_rate - hyp_rate) * 10000
        
        # Seuil minimum (0.5 bps = significatif)
        if spread_bps < 0.5:
            continue
        
        # Déterminer la direction (Buy/Sell)
        if ext_rate < hyp_rate:
            # Extended rate plus bas/négatif → Buy Extended, Sell Hyperliquid
            buy_exchange = "EXTENDED"
            sell_exchange = "HYPERLIQUID"
            buy_rate = ext_rate
            sell_rate = hyp_rate
        else:
            # Hyperliquid rate plus bas/négatif → Buy Hyperliquid, Sell Extended
            buy_exchange = "HYPERLIQUID"
            sell_exchange = "EXTENDED"
            buy_rate = hyp_rate
            sell_rate = ext_rate
        
        # Calculer le profit estimé par heure (position $10,000)
        position_size = 10000
        
        # Intervalles de funding (Extended et Hyperliquid utilisent tous les deux 1h)
        ext_interval = ext_info.get('interval_hours', 1)
        hyp_interval = hyp_info.get('interval_hours', 1)
        
        # Normaliser les rates par heure
        ext_rate_per_hour = ext_rate / ext_interval
        hyp_rate_per_hour = hyp_rate / hyp_interval
        
        # Profit par heure pour chaque côté
        # LONG: on REÇOIT si rate négatif → profit = abs(rate) si rate < 0
        # SHORT: on PAIE si rate négatif → coût = abs(rate) si rate < 0
        
        if buy_exchange == "EXTENDED":
            # LONG Extended (reçoit), SHORT Hyperliquid (paie)
            long_receives = abs(ext_rate_per_hour) * position_size if ext_rate_per_hour < 0 else 0
            short_pays = abs(hyp_rate_per_hour) * position_size if hyp_rate_per_hour < 0 else 0
        else:
            # LONG Hyperliquid (reçoit), SHORT Extended (paie)
            long_receives = abs(hyp_rate_per_hour) * position_size if hyp_rate_per_hour < 0 else 0
            short_pays = abs(ext_rate_per_hour) * position_size if ext_rate_per_hour < 0 else 0
        
        profit_per_hour = long_receives - short_pays
        
        opportunities.append({
            'symbol': symbol,
            'spread_bps': spread_bps,
            'buy_exchange': buy_exchange,
            'buy_rate': buy_rate,
            'sell_exchange': sell_exchange,
            'sell_rate': sell_rate,
            'profit_per_hour': profit_per_hour,
            'ext_interval': ext_interval,
            'hyp_interval': hyp_interval
        })
    
    # Trier par spread décroissant
    opportunities.sort(key=lambda x: x['spread_bps'], reverse=True)
    
    return opportunities


def main():
    print("=" * 120)
    print("🎯 ANALYSEUR EXTENDED vs HYPERLIQUID (API DIRECTES)")
    print("=" * 120)
    
    # Charger la config
    config = get_config()
    wallet_address = config.get('wallet', 'address')
    private_key = config.get('wallet', 'private_key')
    
    # Pour les endpoints publics, on peut utiliser un wallet dummy
    if wallet_address == "0xYOUR_WALLET_ADDRESS":
        print("\n⚠️  Wallet non configuré, utilisation d'un wallet dummy pour les endpoints publics...")
        wallet_address = "0x0000000000000000000000000000000000000000"
        private_key = None
    
    print(f"\n🔑 Wallet: {wallet_address}")
    
    # Initialiser les APIs
    print("\n📡 Initialisation des APIs...")
    extended = ExtendedAPI(wallet_address, private_key)
    hyperliquid = HyperliquidAPI(wallet_address, private_key, testnet=False)
    
    # Récupérer les funding rates
    print("\n📊 Récupération des funding rates Extended...")
    extended_rates = extended.get_all_funding_rates()
    print(f"✅ {len(extended_rates)} symboles sur Extended")
    
    print("\n📊 Récupération des funding rates Hyperliquid...")
    hyperliquid_rates = hyperliquid.get_all_funding_rates()
    print(f"✅ {len(hyperliquid_rates)} symboles sur Hyperliquid")
    
    if not extended_rates or not hyperliquid_rates:
        print("\n❌ Impossible de récupérer les funding rates!")
        return
    
    # Trouver les opportunités
    opportunities = find_arbitrage_opportunities(extended_rates, hyperliquid_rates)
    
    print(f"\n✅ {len(opportunities)} opportunités trouvées")
    
    if not opportunities:
        print("\n💤 Aucune opportunité intéressante pour le moment")
        return
    
    # Afficher le top 20
    print("\n" + "=" * 120)
    print("🏆 TOP 20 OPPORTUNITÉS")
    print("=" * 120)
    
    table_data = []
    for i, opp in enumerate(opportunities[:20], 1):
        table_data.append([
            i,
            opp['symbol'],
            f"{opp['spread_bps']:.1f}",
            opp['buy_exchange'],
            f"{opp['buy_rate']*100:.4f}%",
            opp['sell_exchange'],
            f"{opp['sell_rate']*100:.4f}%",
            f"${opp['profit_per_hour']:.2f}"
        ])
    
    headers = ["#", "Symbole", "Spread(bps)", "Buy", "Rate Buy", "Sell", "Rate Sell", "$/h"]
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    
    # Meilleure opportunité
    best = opportunities[0]
    print("\n" + "=" * 120)
    print("💰 MEILLEURE OPPORTUNITÉ")
    print("=" * 120)
    print(f"  Symbole:          {best['symbol']}")
    print(f"  Spread:           {best['spread_bps']:.1f} bps")
    print(f"  📈 BUY:            {best['buy_exchange']} @ {best['buy_rate']*100:.4f}%")
    print(f"  📉 SELL:           {best['sell_exchange']} @ {best['sell_rate']*100:.4f}%")
    print(f"  💵 Profit/h:       ${best['profit_per_hour']:.2f} (sur $10,000)")
    print(f"  🎯 Position:       LONG {best['buy_exchange']} + SHORT {best['sell_exchange']}")
    print("=" * 120)
    
    # Statistiques
    print("\n📊 STATISTIQUES:")
    total_spread = sum(opp['spread_bps'] for opp in opportunities[:10])
    total_profit = sum(opp['profit_per_hour'] for opp in opportunities[:10])
    print(f"   Total spread (top 10): {total_spread:.1f} bps")
    print(f"   Total profit potentiel (top 10): ${total_profit:.2f}/h")
    
    # Timestamp
    print(f"\n⏰ Analyse effectuée: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 120)


if __name__ == "__main__":
    main()

"""
Analyseur comme Loris Tools
Compare TOUTES les combinaisons d'exchanges (Extended, Hyperliquid, Variational)
pour trouver les meilleures opportunités d'arbitrage
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.data.loris_api import get_loris_api
from tabulate import tabulate


def main():
    print("\n" + "="*140)
    print("🎯 ANALYSEUR STYLE LORIS TOOLS - TOUTES COMBINAISONS")
    print("="*140 + "\n")
    
    # Initialiser l'API
    loris = get_loris_api()
    
    # Récupérer toutes les données
    print("📡 Récupération des funding rates depuis Loris Tools...")
    data = loris.fetch_all_funding_rates()
    
    if not data:
        print("❌ Erreur lors de la récupération des données")
        return
    
    symbols = data.get('symbols', [])
    exchanges_info = loris.get_exchange_info(data)
    funding_intervals = data.get('funding_intervals', {})
    
    print(f"✅ {len(symbols)} symboles disponibles")
    
    # 🎯 Identifier Hyperliquid, Extended et Variational
    target_exchanges = {}
    
    for exchange_name in exchanges_info.keys():
        base = exchange_name.split('_')[0].lower()
        if base in ['hyperliquid', 'extended', 'variational']:
            target_exchanges[base] = exchange_name
    
    print(f"\n📊 EXCHANGES:")
    for name, full_name in target_exchanges.items():
        interval = funding_intervals.get(full_name, '?')
        print(f"   {name.upper()}: {full_name} (interval: {interval}h)")
    print()
    
    # Analyser TOUS les symboles
    print(f"🔍 Analyse de {len(symbols)} symboles...\n")
    
    opportunities = []
    
    for symbol in symbols:
        # Récupérer les rates pour Extended, Hyperliquid, Variational
        rates = {}
        for name, exchange_name in target_exchanges.items():
            rate = loris.get_funding_rate(data, exchange_name, symbol)
            
            # Récupérer l'intervalle pour ce symbole
            interval_dict = funding_intervals.get(exchange_name, {})
            if isinstance(interval_dict, dict):
                interval = interval_dict.get(symbol, 8)  # Défaut 8h
            else:
                interval = 8
            
            if rate is not None:
                rates[name] = {
                    'rate': rate,
                    'exchange': exchange_name,
                    'interval': interval
                }
        
        # Si on a au moins 2 exchanges avec des rates
        if len(rates) >= 2:
            # Comparer TOUTES les paires possibles
            exchange_names = list(rates.keys())
            
            for i in range(len(exchange_names)):
                for j in range(i + 1, len(exchange_names)):
                    ex1_name = exchange_names[i]
                    ex2_name = exchange_names[j]
                    
                    ex1 = rates[ex1_name]
                    ex2 = rates[ex2_name]
                    
                    rate1 = ex1['rate']
                    rate2 = ex2['rate']
                    interval1 = ex1['interval']
                    interval2 = ex2['interval']
                    
                    # Calculer le spread (différence absolue en bps - basis points)
                    # Loris affiche en bps, donc multiplier par 10,000
                    spread_bps = abs(rate1 - rate2) * 10000
                    
                    # Position size
                    position_size = 10000
                    
                    # Calculer le profit par heure pour chaque exchange
                    # Normaliser selon l'intervalle de funding
                    profit1_per_hour = (rate1 * position_size) / interval1
                    profit2_per_hour = (rate2 * position_size) / interval2
                    
                    # Déterminer quelle direction (Buy/Sell)
                    if rate1 < rate2:
                        # Buy ex1 (rate plus bas/négatif), Sell ex2
                        buy_exchange = ex1_name
                        sell_exchange = ex2_name
                        # LONG sur ex1: si rate négatif, on REÇOIT → profit = -rate (positif)
                        # SHORT sur ex2: si rate négatif, on PAIE → coût = +rate (négatif)
                        # Profit net = ce qu'on reçoit - ce qu'on paie
                        long_profit_per_hour = -profit1_per_hour  # LONG reçoit l'inverse du rate
                        short_cost_per_hour = profit2_per_hour    # SHORT paie le rate
                        profit_per_hour = long_profit_per_hour - short_cost_per_hour
                    else:
                        # Buy ex2, Sell ex1
                        buy_exchange = ex2_name
                        sell_exchange = ex1_name
                        long_profit_per_hour = -profit2_per_hour
                        short_cost_per_hour = profit1_per_hour
                        profit_per_hour = long_profit_per_hour - short_cost_per_hour
                    
                    # Seuil minimum (1 bps = significatif)
                    if spread_bps >= 1.0:
                        opportunities.append({
                            'symbol': symbol,
                            'spread_bps': spread_bps,
                            'buy_exchange': buy_exchange.upper(),
                            'sell_exchange': sell_exchange.upper(),
                            'rate_buy': rate1 if buy_exchange == ex1_name else rate2,
                            'rate_sell': rate2 if sell_exchange == ex2_name else rate1,
                            'profit_per_hour': profit_per_hour,
                            'pair': f"{buy_exchange.upper()} vs {sell_exchange.upper()}"
                        })
    
    # Trier par spread (comme Loris)
    opportunities.sort(key=lambda x: x['spread_bps'], reverse=True)
    
    print(f"✅ {len(opportunities)} opportunités trouvées\n")
    
    # Afficher le top 20
    if opportunities:
        print("="*140)
        print("🏆 TOP 20 OPPORTUNITÉS (triées par spread comme Loris Tools)")
        print("="*140 + "\n")
        
        table_data = []
        for i, opp in enumerate(opportunities[:20], 1):
            table_data.append([
                i,
                opp['symbol'],
                f"{opp['spread_bps']:.1f}",
                opp['buy_exchange'],
                f"{opp['rate_buy']:.6f}",
                opp['sell_exchange'],
                f"{opp['rate_sell']:.6f}",
                f"${opp['profit_per_hour']:.2f}",
                opp['pair']
            ])
        
        headers = [
            "#", "Symbole", "Spread(bps)", "Buy", "Rate Buy",
            "Sell", "Rate Sell", "$/h", "Paire"
        ]
        
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        
        # Meilleure opportunité
        best = opportunities[0]
        print(f"\n{'='*140}")
        print("💰 MEILLEURE OPPORTUNITÉ (plus grand spread)")
        print(f"{'='*140}")
        print(f"  Symbole:          {best['symbol']}")
        print(f"  Spread:           {best['spread_bps']:.1f} bps")
        print(f"  📈 BUY:            {best['buy_exchange']} @ {best['rate_buy']:.6f}")
        print(f"  📉 SELL:           {best['sell_exchange']} @ {best['rate_sell']:.6f}")
        print(f"  💵 Profit/h:       ${best['profit_per_hour']:.2f} (sur $10,000)")
        print(f"  🎯 Position:       LONG {best['buy_exchange']} + SHORT {best['sell_exchange']}")
        print(f"{'='*140}\n")
        
        # Grouper par type de paire
        by_pair = {}
        for opp in opportunities:
            pair = opp['pair']
            if pair not in by_pair:
                by_pair[pair] = []
            by_pair[pair].append(opp)
        
        print(f"📊 RÉPARTITION PAR TYPE DE PAIRE:")
        for pair, opps in sorted(by_pair.items(), key=lambda x: len(x[1]), reverse=True):
            total_profit = sum(o['profit_per_hour'] for o in opps[:5])
            print(f"   {pair}: {len(opps)} opportunités (Top 5: ${total_profit:.2f}/h)")
        print()
        
        # Statistiques
        total_spread = sum(o['spread_bps'] for o in opportunities[:10])
        total_profit = sum(o['profit_per_hour'] for o in opportunities[:10])
        
        print(f"📈 STATISTIQUES TOP 10:")
        print(f"   Total spread: {total_spread:.1f} bps")
        print(f"   Total profit potentiel: ${total_profit:.2f}/h")
        print(f"{'='*140}\n")
        
    else:
        print("❌ Aucune opportunité trouvée\n")
    
    print("✅ Terminé!")
    print("🔗 Loris Tools: https://loris.tools")
    print("⏰ Données mises à jour toutes les 60s\n")


if __name__ == "__main__":
    main()

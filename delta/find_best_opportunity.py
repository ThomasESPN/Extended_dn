"""
Analyseur Multi-Paires
Trouve la meilleure opportunité d'arbitrage parmi toutes les paires disponibles
Utilise les données en temps réel de Loris Tools
"""
import sys
from pathlib import Path
from datetime import datetime
from tabulate import tabulate

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config
from src.data.loris_api import get_loris_api
from src.strategies import ArbitrageCalculator, ArbitrageOpportunity
from src.data.funding_collector import FundingRate


def analyze_all_symbols(top_n=20):
    """Analyse toutes les paires disponibles et trouve les meilleures opportunités"""
    
    print("\n" + "="*120)
    print("🎯 ANALYSEUR MULTI-PAIRES - RECHERCHE DE LA MEILLEURE OPPORTUNITÉ")
    print("="*120 + "\n")
    
    # Initialiser
    loris = get_loris_api()
    config = get_config()
    calculator = ArbitrageCalculator(config)
    
    # Récupérer les données
    print("📡 Récupération des funding rates en temps réel...")
    data = loris.fetch_all_funding_rates()
    
    if not data:
        print("❌ Erreur lors de la récupération des données")
        return
    
    symbols = data.get('symbols', [])
    print(f"✅ {len(symbols)} symboles disponibles")
    print(f"   Timestamp: {data.get('timestamp')}\n")
    
    # Récupérer les exchanges
    exchanges_info = loris.get_exchange_info(data)
    
    # 🎯 Chercher les exchanges 1h (Extended, Hyperliquid) et Variational
    exchanges_1h = []
    variational_exchange = None
    
    for exchange_name in exchanges_info.keys():
        base = exchange_name.split('_')[0].lower()
        if base in ['extended', 'hyperliquid']:
            exchanges_1h.append(exchange_name)
        elif base == 'variational':
            variational_exchange = exchange_name
    
    if not exchanges_1h or not variational_exchange:
        print(f"❌ Exchanges manquants")
        print(f"   1h (Extended/Hyperliquid): {exchanges_1h}")
        print(f"   8h (Variational): {variational_exchange}")
        return
    
    print(f"📊 Exchanges utilisés:")
    print(f"   1h: {', '.join([e.split('_')[0].upper() for e in exchanges_1h])}")
    print(f"   8h: {variational_exchange.split('_')[0].upper()}\n")
    
    # Analyser chaque symbole
    print("🔍 Analyse des opportunités d'arbitrage (meilleur 1h vs Variational)...\n")
    
    opportunities = []
    
    for symbol in symbols[:500]:  # Analyser les 500 premiers symboles
        # 🎯 Chercher le MEILLEUR rate 1h parmi Extended et Hyperliquid
        best_1h_rate = None
        best_1h_exchange = None
        
        for exchange in exchanges_1h:
            rate = loris.get_funding_rate(data, exchange, symbol)
            if rate is not None:
                # Prendre le rate le plus bas (négatif = on reçoit)
                if best_1h_rate is None or rate < best_1h_rate:
                    best_1h_rate = rate
                    best_1h_exchange = exchange
        
        # Récupérer Variational rate
        variational_rate = loris.get_funding_rate(data, variational_exchange, symbol)
        
        # Si on a les deux rates
        if best_1h_rate is not None and variational_rate is not None:
            # Créer des FundingRate objects
            extended_funding = FundingRate(
                exchange="Extended",
                symbol=f"{symbol}/USDT",
                rate=best_1h_rate,
                timestamp=datetime.now(),
                funding_interval=3600
            )
            
            variational_funding = FundingRate(
                exchange="Variational",
                symbol=f"{symbol}/USDT",
                rate=variational_rate,
                timestamp=datetime.now(),
                funding_interval=28800
            )
            
            # Calculer l'opportunité
            funding_data = {
                f"{symbol}/USDT": {
                    'extended': extended_funding,
                    'variational': variational_funding
                }
            }
            
            opps = calculator.find_best_opportunities(funding_data)
            
            if opps:
                opp = opps[0]
                opportunities.append({
                    'symbol': symbol,
                    'opportunity': opp,
                    'best_1h_exchange': best_1h_exchange.split('_')[0].upper(),
                    'variational_exchange': variational_exchange.split('_')[0].upper()
                })
    
    # Trier par profit/heure
    opportunities.sort(key=lambda x: x['opportunity'].profit_per_hour, reverse=True)
    
    # Afficher les résultats
    print(f"✅ Analyse terminée: {len(opportunities)} opportunités trouvées\n")
    
    if opportunities:
        # Tableau des top opportunités
        table_data = []
        for i, item in enumerate(opportunities[:top_n], 1):
            opp = item['opportunity']
            table_data.append([
                i,
                item['symbol'],
                f"{opp.extended_rate:.6f}",
                f"{opp.variational_rate:.6f}",
                f"{abs(opp.extended_rate - opp.variational_rate):.6f}",
                f"${opp.estimated_profit_full_cycle:.2f}",
                f"${opp.profit_per_hour:.2f}",
                opp.position_type,
                opp.risk_level
            ])
        
        headers = [
            "#", "Symbole", "Rate 1h", "Rate 8h", 
            "Spread", "Profit 8h", "$/heure", "Type", "Risque"
        ]
        
        print(f"\n{'='*120}")
        print(f"🏆 TOP {top_n} OPPORTUNITÉS D'ARBITRAGE")
        print(f"{'='*120}\n")
        
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        
        # Détails de la meilleure
        best = opportunities[0]
        best_opp = best['opportunity']
        
        print(f"\n{'='*120}")
        print("💰 OPPORTUNITÉ #1 - LA PLUS RENTABLE")
        print(f"{'='*120}")
        print(f"  Symbole:              {best['symbol']}")
        print(f"  Type de position:     {best_opp.position_type}")
        print(f"  ")
        print(f"  📈 LONG Exchange:      {best_opp.long_exchange}")
        print(f"     Funding rate:      {best_opp.extended_rate if best_opp.long_exchange == 'Extended' else best_opp.variational_rate:.6f}")
        print(f"  ")
        print(f"  📉 SHORT Exchange:     {best_opp.short_exchange}")
        print(f"     Funding rate:      {best_opp.extended_rate if best_opp.short_exchange == 'Extended' else best_opp.variational_rate:.6f}")
        print(f"  ")
        print(f"  💵 Profits:")
        print(f"     Position size:     $10,000")
        print(f"     Cycle complet 8h:  ${best_opp.estimated_profit_full_cycle:.2f}")
        print(f"     Fermeture anticipée: ${best_opp.estimated_profit_early_close:.2f}")
        print(f"     Par heure:         ${best_opp.profit_per_hour:.2f}")
        print(f"  ")
        print(f"  🎯 Stratégie:          {best_opp.recommended_strategy}")
        print(f"  ⚠️  Risque:             {best_opp.risk_level}")
        print(f"{'='*120}\n")
        
        # Statistiques globales
        total_profit_top5 = sum(o['opportunity'].profit_per_hour for o in opportunities[:5])
        total_profit_top10 = sum(o['opportunity'].profit_per_hour for o in opportunities[:10])
        avg_profit = sum(o['opportunity'].profit_per_hour for o in opportunities) / len(opportunities)
        
        print(f"📊 STATISTIQUES GLOBALES")
        print(f"   Opportunités analysées: {len(opportunities)}")
        print(f"   Profit moyen/heure: ${avg_profit:.2f}")
        print(f"   Potentiel top 5: ${total_profit_top5:.2f}/heure")
        print(f"   Potentiel top 10: ${total_profit_top10:.2f}/heure")
        print(f"{'='*120}\n")
        
    else:
        print("❌ Aucune opportunité trouvée\n")
    
    print("✅ Analyse terminée!")
    print("🔗 Données fournies par Loris Tools: https://loris.tools")
    print("⏰ Mise à jour toutes les 60 secondes\n")


if __name__ == "__main__":
    import sys
    
    # Nombre d'opportunités à afficher
    top_n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    
    analyze_all_symbols(top_n)

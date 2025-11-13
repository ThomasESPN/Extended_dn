"""
Example Script - Quick Start
Script d'exemple pour tester rapidement le système
"""
import sys
from pathlib import Path

# Ajouter le répertoire parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config
from src.data import FundingCollector
from src.strategies import ArbitrageCalculator
from src.execution import TradeExecutor, RebalancingManager


def main():
    print("\n" + "="*60)
    print("🎯 TIMING FUNDING ARBITRAGE - EXEMPLE")
    print("="*60 + "\n")
    
    # 1. Charger la configuration
    print("📋 Chargement de la configuration...")
    config = get_config()
    pairs = config.get_pairs()
    print(f"✅ Paires configurées: {', '.join(pairs)}\n")
    
    # 2. Collecter les funding rates
    print("📡 Collecte des funding rates...")
    collector = FundingCollector(config)
    funding_data = collector.get_all_funding_rates(pairs)
    
    for symbol, rates in funding_data.items():
        print(f"\n{symbol}:")
        if rates['extended']:
            print(f"  Extended:    {rates['extended'].rate:.6f}")
        if rates['variational']:
            print(f"  Variational: {rates['variational'].rate:.6f}")
    
    # 3. Analyser les opportunités
    print("\n🧮 Analyse des opportunités d'arbitrage...")
    calculator = ArbitrageCalculator(config)
    opportunities = calculator.find_best_opportunities(funding_data)
    
    if opportunities:
        print(f"\n✅ {len(opportunities)} opportunité(s) trouvée(s)!\n")
        
        for i, opp in enumerate(opportunities, 1):
            print(f"#{i} - {opp.symbol}")
            print(f"  Type: {opp.position_type}")
            print(f"  Long: {opp.long_exchange}")
            print(f"  Short: {opp.short_exchange}")
            print(f"  Profit estimé (cycle complet): ${opp.estimated_profit_full_cycle:.4f}")
            print(f"  Profit/heure: ${opp.profit_per_hour:.4f}")
            print(f"  Stratégie recommandée: {opp.recommended_strategy}")
            print(f"  Risque: {opp.risk_level}\n")
    else:
        print("\n❌ Aucune opportunité rentable trouvée.\n")
    
    # 4. Exemple d'ouverture de position (simulation)
    print("💼 Simulation d'ouverture de position...")
    executor = TradeExecutor(config)
    
    if opportunities:
        best = opportunities[0]
        print(f"\nOuverture d'une paire pour {best.symbol}...")
        
        pair = executor.open_arbitrage_pair(
            symbol=best.symbol,
            long_exchange=best.long_exchange,
            short_exchange=best.short_exchange,
            size=10000,  # $10,000
            strategy_type=best.position_type
        )
        
        if pair:
            print(f"✅ Paire ouverte: {pair.id}")
            print(f"  Long position: {pair.long_position.exchange} @ ${pair.long_position.entry_price:.2f}")
            print(f"  Short position: {pair.short_position.exchange} @ ${pair.short_position.entry_price:.2f}")
            print(f"  Delta-neutral: {pair.is_delta_neutral()}")
            
            # Fermeture
            print(f"\nFermeture de la paire...")
            if executor.close_arbitrage_pair(pair.id):
                print(f"✅ Paire fermée")
                print(f"  PnL net: ${pair.net_pnl:.4f}")
        else:
            print("❌ Échec de l'ouverture")
    
    # 5. Vérifier les balances
    print("\n💰 Vérification des balances...")
    rebalancer = RebalancingManager(config)
    print(rebalancer.get_balance_report())
    
    print("="*60)
    print("✅ Exemple terminé!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()

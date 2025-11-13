"""
Main Analysis Script
Analyse les opportunités d'arbitrage de funding en temps réel
"""
import sys
import time
from pathlib import Path
from datetime import datetime
from tabulate import tabulate

# Ajouter le répertoire parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_config
from src.data import FundingCollector
from src.strategies import ArbitrageCalculator


def display_opportunities(opportunities, config):
    """Affiche les opportunités sous forme de tableau"""
    if not opportunities:
        print("\n❌ Aucune opportunité rentable trouvée.\n")
        return
    
    print(f"\n{'='*100}")
    print(f"🎯 OPPORTUNITÉS D'ARBITRAGE - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*100}\n")
    
    # Préparer les données pour le tableau
    table_data = []
    for i, opp in enumerate(opportunities, 1):
        table_data.append([
            i,
            opp.symbol,
            f"{opp.extended_rate:.6f}",
            f"{opp.variational_rate:.6f}",
            f"{opp.long_exchange} / {opp.short_exchange}",
            f"${opp.estimated_profit_full_cycle:.4f}",
            f"${opp.profit_per_hour:.4f}",
            opp.recommended_strategy,
            opp.risk_level
        ])
    
    headers = [
        "#", "Paire", "Funding Ext", "Funding Var", 
        "Long/Short", "Profit 8h", "$/heure", "Stratégie", "Risque"
    ]
    
    print(tabulate(table_data, headers=headers, tablefmt="grid"))
    
    # Afficher les détails de la meilleure opportunité
    if opportunities:
        best = opportunities[0]
        print(f"\n{'='*100}")
        print("🏆 MEILLEURE OPPORTUNITÉ")
        print(f"{'='*100}")
        print(f"  Paire:           {best.symbol}")
        print(f"  Type:            {best.position_type}")
        print(f"  Long:            {best.long_exchange}")
        print(f"  Short:           {best.short_exchange}")
        print(f"  Funding Ext:     {best.extended_rate:.6f}")
        print(f"  Funding Var:     {best.variational_rate:.6f}")
        print(f"  Profit cycle:    ${best.estimated_profit_full_cycle:.4f}")
        print(f"  Profit fermeture anticipée: ${best.estimated_profit_early_close:.4f}")
        print(f"  Profit/heure:    ${best.profit_per_hour:.4f}")
        print(f"  Stratégie:       {best.recommended_strategy}")
        print(f"  Niveau risque:   {best.risk_level}")
        print(f"{'='*100}\n")


def main():
    """Point d'entrée principal"""
    print("\n" + "="*100)
    print("🚀 TIMING FUNDING ARBITRAGE - ANALYSEUR")
    print("="*100 + "\n")
    
    # Charger la configuration
    print("📋 Chargement de la configuration...")
    config = get_config()
    pairs = config.get_pairs()
    
    print(f"✅ Configuration chargée")
    print(f"   Paires à analyser: {', '.join(pairs)}")
    print(f"   Taille position: ${config.get('trading', 'max_position_size')}") 
    print(f"   Seuil profit min: {config.get('trading', 'min_profit_threshold')}\n")
    
    # Initialiser les composants
    print("🔧 Initialisation des composants...")
    collector = FundingCollector(config)
    calculator = ArbitrageCalculator(config)
    print("✅ Composants initialisés\n")
    
    # Mode continu ou analyse unique
    continuous = input("Mode continu? (o/n): ").lower() == 'o'
    interval = 60  # secondes
    
    if continuous:
        print(f"\n▶️  Démarrage du mode continu (refresh toutes les {interval}s)")
        print("   Appuyez sur Ctrl+C pour arrêter\n")
    
    try:
        while True:
            # Collecter les funding rates
            print("📡 Collecte des funding rates...")
            funding_data = collector.get_all_funding_rates(pairs)
            
            # Calculer les opportunités
            print("🧮 Calcul des opportunités d'arbitrage...")
            opportunities = calculator.find_best_opportunities(funding_data)
            
            # Afficher les résultats
            display_opportunities(opportunities, config)
            
            if not continuous:
                break
            
            # Attendre avant la prochaine itération
            print(f"⏳ Prochaine analyse dans {interval}s...")
            time.sleep(interval)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Arrêt de l'analyseur...")
        print("👋 Au revoir!\n")


if __name__ == "__main__":
    main()

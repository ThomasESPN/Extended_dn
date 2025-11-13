""""""

Test de l'intégration Loris Tools APITest de l'intégration Loris Tools API

Affiche les meilleures opportunités d'arbitrage en temps réelAffiche les meilleures opportunités d'arbitrage en temps réel

FOCUS: HYPERLIQUID, VARIATIONAL, EXTENDED uniquementFOCUS: HYPERLIQUID, VARIATIONAL, EXTENDED uniquement

""""""

import sysimport sys

from pathlib import Pathfrom pathlib import Path



# Ajouter le répertoire au path# Ajouter le répertoire au path

sys.path.insert(0, str(Path(__file__).parent))sys.path.insert(0, str(Path(__file__).parent))



from src.data.loris_api import get_loris_apifrom src.data.loris_api import get_loris_api

from tabulate import tabulatefrom tabulate import tabulate





def main():def main():

    print("\n" + "="*120)    print("\n" + "="*120)

    print("🚀 TIMING FUNDING ARBITRAGE - HYPERLIQUID + EXTENDED vs VARIATIONAL")    print("🚀 TIMING FUNDING ARBITRAGE - HYPERLIQUID + EXTENDED vs VARIATIONAL")

    print("="*120 + "\n")    print("="*120 + "\n")

        

    # Initialiser l'API    # Initialiser l'API

    loris = get_loris_api()    loris = get_loris_api()

        

    # Récupérer toutes les données    # Récupérer toutes les données

    print("📡 Récupération des funding rates depuis Loris Tools...")    print("📡 Récupération des funding rates depuis Loris Tools...")

    data = loris.fetch_all_funding_rates()    data = loris.fetch_all_funding_rates()

        

    if not data:    if not data:

        print("❌ Erreur lors de la récupération des données")        print("❌ Erreur lors de la récupération des données")

        return        return

        

    symbols = data.get('symbols', [])    symbols = data.get('symbols', [])

    print(f"✅ Données récupérées: {data.get('timestamp')}")    print(f"✅ Données récupérées: {data.get('timestamp')}")

    print(f"   Symboles disponibles: {len(symbols)}")    print(f"   Symboles disponibles: {len(symbols)}")

        

    # Identifier les exchanges (UNIQUEMENT Hyperliquid, Extended, Variational)    # Identifier les exchanges (UNIQUEMENT Hyperliquid, Extended, Variational)

    exchanges_info = loris.get_exchange_info(data)    exchanges_info = loris.get_exchange_info(data)

    funding_intervals = data.get('funding_intervals', {})    funding_intervals = data.get('funding_intervals', {})

        

    # 🎯 Identifier Hyperliquid, Extended et Variational    # 🎯 Identifier Hyperliquid, Extended et Variational

    hyperliquid_exchange = None    hyperliquid_exchange = None

    extended_exchange = None    extended_exchange = None

    variational_exchange = None    variational_exchange = None

        

    for exchange_name in exchanges_info.keys():    for exchange_name in exchanges_info.keys():

        base = exchange_name.split('_')[0].lower()        base = exchange_name.split('_')[0].lower()

        if base == 'hyperliquid':        if base == 'hyperliquid':

            hyperliquid_exchange = exchange_name            hyperliquid_exchange = exchange_name

        elif base == 'extended':        elif base == 'extended':

            extended_exchange = exchange_name            extended_exchange = exchange_name

        elif base == 'variational':        elif base == 'variational':

            variational_exchange = exchange_name            variational_exchange = exchange_name

        

    print(f"\n📊 EXCHANGES UTILISÉS:")    print(f"\n📊 EXCHANGES UTILISÉS:")

    if hyperliquid_exchange:    if hyperliquid_exchange:

        hl_interval = funding_intervals.get(hyperliquid_exchange, 8)        print(f"   ✅ Hyperliquid: {hyperliquid_exchange}")

        print(f"   ✅ Hyperliquid: {hyperliquid_exchange} (funding interval: {hl_interval}h)")    if extended_exchange:

    if extended_exchange:        print(f"   ✅ Extended: {extended_exchange}")

        ext_interval = funding_intervals.get(extended_exchange, 1)    if variational_exchange:

        print(f"   ✅ Extended: {extended_exchange} (funding interval: {ext_interval}h)")        print(f"   ✅ Variational: {variational_exchange}")

    if variational_exchange:    print()

        var_interval = funding_intervals.get(variational_exchange, 8)    

        print(f"   ✅ Variational: {variational_exchange} (funding interval: {var_interval}h)")    if not hyperliquid_exchange and not extended_exchange:

    print()        print("❌ Ni Hyperliquid ni Extended trouvés")

            return

    if not hyperliquid_exchange and not extended_exchange:    if not variational_exchange:

        print("❌ Ni Hyperliquid ni Extended trouvés")        print("❌ Variational non trouvé")

        return        return

    if not variational_exchange:    

        print("❌ Variational non trouvé")    # Analyser TOUS les symboles

        return    print(f"🔍 Analyse de {len(symbols)} symboles...\n")

        

    # Analyser TOUS les symboles    opportunities = []

    print(f"🔍 Analyse de {len(symbols)} symboles...\n")    

        for symbol in symbols:

    opportunities = []        try:

                # Trouver le MEILLEUR entre Hyperliquid et Extended

    for symbol in symbols:            best_short_interval_rate = None

        try:            best_short_interval_exchange = None

            # Trouver le MEILLEUR entre Hyperliquid et Extended            best_short_interval_hours = None

            best_short_interval_rate = None            

            best_short_interval_exchange = None            # Checker Hyperliquid

            best_short_interval_hours = None            if hyperliquid_exchange:

                            rate = loris.get_funding_rate(data, hyperliquid_exchange, symbol)

            # Checker Hyperliquid                interval_hours = funding_intervals.get(hyperliquid_exchange, 8)

            if hyperliquid_exchange:                if rate is not None:

                rate = loris.get_funding_rate(data, hyperliquid_exchange, symbol)                    best_short_interval_rate = rate

                interval_hours = funding_intervals.get(hyperliquid_exchange, 8)                    best_short_interval_exchange = hyperliquid_exchange

                if rate is not None:                    best_short_interval_hours = interval_hours

                    best_short_interval_rate = rate            

                    best_short_interval_exchange = hyperliquid_exchange            # Checker Extended

                    best_short_interval_hours = interval_hours            if extended_exchange:

                            rate = loris.get_funding_rate(data, extended_exchange, symbol)

            # Checker Extended                interval_hours = funding_intervals.get(extended_exchange, 1)

            if extended_exchange:                if rate is not None:

                rate = loris.get_funding_rate(data, extended_exchange, symbol)                    # Si Extended a un meilleur rate (plus négatif)

                interval_hours = funding_intervals.get(extended_exchange, 1)                    if best_short_interval_rate is None or rate < best_short_interval_rate:

                if rate is not None:                        best_short_interval_rate = rate

                    # Si Extended a un meilleur rate (plus négatif)                        best_short_interval_exchange = extended_exchange

                    if best_short_interval_rate is None or rate < best_short_interval_rate:                        best_short_interval_hours = interval_hours

                        best_short_interval_rate = rate            

                        best_short_interval_exchange = extended_exchange            # Récupérer Variational

                        best_short_interval_hours = interval_hours            var_rate = loris.get_funding_rate(data, variational_exchange, symbol)

                        var_interval_hours = funding_intervals.get(variational_exchange, 8)

            # Récupérer Variational            

            var_rate = loris.get_funding_rate(data, variational_exchange, symbol)            # Si on a les deux rates

            var_interval_hours = funding_intervals.get(variational_exchange, 8)            if best_short_interval_rate is not None and var_rate is not None:

                            # Position size

            # Si on a les deux rates                position_size = 10000

            if best_short_interval_rate is not None and var_rate is not None:                

                # Position size                # 🎯 CALCUL DU PROFIT PAR HEURE

                position_size = 10000                # Chaque exchange a son propre intervalle de funding

                                

                # 🎯 CALCUL DU PROFIT PAR HEURE                # Profit par funding period, normalisé en $/heure

                # Normaliser chaque rate en $/heure selon son intervalle                profit_short_per_hour = (abs(best_short_interval_rate) * position_size / best_short_interval_hours) if best_short_interval_rate < 0 else -(abs(best_short_interval_rate) * position_size / best_short_interval_hours)

                profit_short_per_hour = (abs(best_short_interval_rate) * position_size / best_short_interval_hours) if best_short_interval_rate < 0 else -(abs(best_short_interval_rate) * position_size / best_short_interval_hours)                profit_var_per_hour = (abs(var_rate) * position_size / var_interval_hours) if var_rate < 0 else -(abs(var_rate) * position_size / var_interval_hours)

                profit_var_per_hour = (abs(var_rate) * position_size / var_interval_hours) if var_rate < 0 else -(abs(var_rate) * position_size / var_interval_hours)                

                                # Stratégie both_negative (les deux négatifs)

                # Stratégie both_negative (les deux négatifs)                if best_short_interval_rate < 0 and var_rate < 0:

                if best_short_interval_rate < 0 and var_rate < 0:                    # On reçoit des deux côtés

                    # On reçoit des deux côtés                    # LONG sur le meilleur (Hyperliquid ou Extended)

                    profit_per_hour = profit_short_per_hour + profit_var_per_hour                    # SHORT sur Variational

                    strategy = "both_negative"                    profit_per_hour = profit_short_per_hour + profit_var_per_hour

                    position = f"LONG {best_short_interval_exchange.split('_')[0].upper()} + SHORT VARIATIONAL"                    strategy = "both_negative"

                                    position = f"LONG {best_short_interval_exchange.split('_')[0].upper()} + SHORT VARIATIONAL"

                # Stratégie both_positive                

                elif best_short_interval_rate < 0 and var_rate > 0:                # Stratégie both_positive

                    profit_per_hour = profit_short_per_hour + abs(profit_var_per_hour)                elif best_short_interval_rate < 0 and var_rate > 0:

                    strategy = "both_positive"                    # LONG sur short_interval (on reçoit)

                    position = f"LONG {best_short_interval_exchange.split('_')[0].upper()} + SHORT VARIATIONAL"                    # SHORT sur Variational (on reçoit car positif)

                                    profit_per_hour = profit_short_per_hour + abs(profit_var_per_hour)

                # Stratégie standard                    strategy = "both_positive"

                elif best_short_interval_rate > 0 and var_rate > 0:                    position = f"LONG {best_short_interval_exchange.split('_')[0].upper()} + SHORT VARIATIONAL"

                    profit_per_hour = profit_var_per_hour + profit_short_per_hour                

                    if profit_per_hour > 0:                # Stratégie standard

                        strategy = "standard"                elif best_short_interval_rate > 0 and var_rate > 0:

                        position = f"SHORT {best_short_interval_exchange.split('_')[0].upper()} + LONG VARIATIONAL"                    # Seulement rentable si on reçoit plus de Variational qu'on paie sur l'autre

                    else:                    profit_per_hour = profit_var_per_hour + profit_short_per_hour

                        continue                    if profit_per_hour > 0:

                                        strategy = "standard"

                # Stratégie mixed                        position = f"SHORT {best_short_interval_exchange.split('_')[0].upper()} + LONG VARIATIONAL"

                elif best_short_interval_rate > 0 and var_rate < 0:                    else:

                    profit_per_hour = profit_var_per_hour + profit_short_per_hour                        continue

                    if profit_per_hour > 0:                

                        strategy = "mixed"                # Stratégie mixed

                        position = f"SHORT {best_short_interval_exchange.split('_')[0].upper()} + LONG VARIATIONAL"                elif best_short_interval_rate > 0 and var_rate < 0:

                    else:                    profit_per_hour = profit_var_per_hour + profit_short_per_hour

                        continue                    if profit_per_hour > 0:

                                        strategy = "mixed"

                else:                        position = f"SHORT {best_short_interval_exchange.split('_')[0].upper()} + LONG VARIATIONAL"

                    continue                    else:

                                        continue

                # Seuil minimum                

                if profit_per_hour >= 2.0:                else:

                    opportunities.append({                    continue

                        'symbol': symbol,                

                        'exchange_short': best_short_interval_exchange.split('_')[0].upper(),                # Seuil minimum

                        'rate_short': best_short_interval_rate,                if profit_per_hour >= 2.0:  # Au moins $2/h

                        'interval_short': best_short_interval_hours,                    opportunities.append({

                        'rate_var': var_rate,                        'symbol': symbol,

                        'interval_var': var_interval_hours,                        'exchange_short': best_short_interval_exchange.split('_')[0].upper(),

                        'profit_per_hour': profit_per_hour,                        'rate_short': best_short_interval_rate,

                        'strategy': strategy,                        'interval_short': best_short_interval_hours,

                        'position': position                        'rate_var': var_rate,

                    })                        'interval_var': var_interval_hours,

                                'profit_per_hour': profit_per_hour,

        except Exception as e:                        'strategy': strategy,

            continue                        'position': position

                        })

    # Trier par profit        

    opportunities.sort(key=lambda x: x['profit_per_hour'], reverse=True)        except Exception as e:

                continue

    print(f"✅ Analyse terminée: {len(opportunities)} opportunités trouvées\n")    

        # Trier par profit

    # Afficher le top 20    opportunities.sort(key=lambda x: x['profit_per_hour'], reverse=True)

    if opportunities:    

        print("="*140)    print(f"✅ Analyse terminée: {len(opportunities)} opportunités trouvées\n")

        print("🏆 TOP 20 OPPORTUNITÉS - HYPERLIQUID/EXTENDED vs VARIATIONAL")    

        print("="*140 + "\n")    # Afficher le top 20

            if opportunities:

        table_data = []        print("="*140)

        for i, opp in enumerate(opportunities[:20], 1):        print("🏆 TOP 20 OPPORTUNITÉS D'ARBITRAGE")

            table_data.append([        print("="*140 + "\n")

                i,        

                opp['symbol'],        table_data = []

                opp['exchange_short'],        for i, opp in enumerate(opportunities[:20], 1):

                f"{opp['rate_short']:.5f}",            table_data.append([

                f"{opp['interval_short']}h",                i,

                "VAR",                opp['symbol'],

                f"{opp['rate_var']:.5f}",                opp['exchange_short'],

                f"{opp['interval_var']}h",                f"{opp['rate_short']:.5f}",

                f"${opp['profit_per_hour']:.2f}",                f"{opp['interval_short']}h",

                opp['strategy']                "VARIATIONAL",

            ])                f"{opp['rate_var']:.5f}",

                        f"{opp['interval_var']}h",

        headers = [                f"${opp['profit_per_hour']:.2f}",

            "#", "Symbole", "Exch1", "Rate1", "Int1",                opp['strategy']

            "Exch2", "Rate2", "Int2", "$/h", "Stratégie"            ])

        ]        

                headers = [

        print(tabulate(table_data, headers=headers, tablefmt="grid"))            "#", "Symbole", "Exchange 1", "Rate 1", "Interval 1",

                    "Exchange 2", "Rate 2", "Interval 2", "$/heure", "Stratégie"

        # Meilleure opportunité        ]

        best = opportunities[0]        

        print(f"\n{'='*140}")        print(tabulate(table_data, headers=headers, tablefmt="grid"))

        print("💰 MEILLEURE OPPORTUNITÉ")        

        print(f"{'='*140}")        # Meilleure opportunité

        print(f"  Symbole:              {best['symbol']}")        best = opportunities[0]

        print(f"  📊 Position:          {best['position']}")        print(f"\n{'='*140}")

        print(f"  📈 Exchange 1:         {best['exchange_short']}")        print("💰 MEILLEURE OPPORTUNITÉ DU MOMENT")

        print(f"     Rate:              {best['rate_short']:.6f}")        print(f"{'='*140}")

        print(f"     Interval:          {best['interval_short']}h")        print(f"  Symbole:              {best['symbol']}")

        print(f"  📉 Exchange 2:         VARIATIONAL")        print(f"  📊 Position:          {best['position']}")

        print(f"     Rate:              {best['rate_var']:.6f}")        print(f"  📈 Exchange 1:         {best['exchange_short']}")

        print(f"     Interval:          {best['interval_var']}h")        print(f"     Funding rate:      {best['rate_short']:.6f}")

        print(f"  💵 Profit/heure:       ${best['profit_per_hour']:.2f} (sur $10,000)")        print(f"     Funding interval:  {best['interval_short']} heures")

        print(f"  🎯 Stratégie:          {best['strategy']}")        print(f"  📉 Exchange 2:         VARIATIONAL")

        print(f"{'='*140}\n")        print(f"     Funding rate:      {best['rate_var']:.6f}")

                print(f"     Funding interval:  {best['interval_var']} heures")

        # Statistiques        print(f"  💵 Profits:")

        avg_profit = sum(o['profit_per_hour'] for o in opportunities) / len(opportunities)        print(f"     Position size:     $10,000")

        top5_profit = sum(o['profit_per_hour'] for o in opportunities[:5])        print(f"     Par heure:         ${best['profit_per_hour']:.2f}")

        top10_profit = sum(o['profit_per_hour'] for o in opportunities[:10])        print(f"  🎯 Stratégie:          {best['strategy']}")

                print(f"{'='*140}\n")

        print(f"📊 STATISTIQUES")        

        print(f"   Opportunités: {len(opportunities)}")        # Statistiques

        print(f"   Profit moyen/h: ${avg_profit:.2f}")        avg_profit = sum(o['profit_per_hour'] for o in opportunities) / len(opportunities)

        print(f"   Top 5: ${top5_profit:.2f}/h")        top5_profit = sum(o['profit_per_hour'] for o in opportunities[:5])

        print(f"   Top 10: ${top10_profit:.2f}/h")        top10_profit = sum(o['profit_per_hour'] for o in opportunities[:10])

        print(f"{'='*140}\n")        

                print(f"📊 STATISTIQUES GLOBALES")

    else:        print(f"   Opportunités analysées: {len(opportunities)}")

        print("❌ Aucune opportunité trouvée\n")        print(f"   Profit moyen/heure: ${avg_profit:.2f}")

            print(f"   Potentiel top 5: ${top5_profit:.2f}/heure")

    print("✅ Terminé!")        print(f"   Potentiel top 10: ${top10_profit:.2f}/heure")

    print("🔗 Loris Tools: https://loris.tools")        print(f"{'='*140}\n")

    print("⏰ Données mises à jour toutes les 60s\n")        

    else:

        print("❌ Aucune opportunité d'arbitrage trouvée\n")

if __name__ == "__main__":    

    main()    print("✅ Analyse terminée!")

    print("🔗 Données fournies par Loris Tools: https://loris.tools")
    print("⏰ Mise à jour toutes les 60 secondes\n")


if __name__ == "__main__":
    main()
    print("\n" + "="*120)
    print("🚀 SCAN COMPLET - EXTENDED + HYPERLIQUID vs VARIATIONAL")
    print("="*120 + "\n")
    
    # Initialiser l'API
    loris = get_loris_api()
    
    # Récupérer toutes les données
    print("📡 Récupération des funding rates depuis Loris Tools...")
    data = loris.fetch_all_funding_rates()
    
    if not data:
        print("❌ Erreur lors de la récupération des données")
        return
    
    symbols = data.get('symbols', [])
    print(f"✅ Données récupérées: {data.get('timestamp')}")
    print(f"   Symboles disponibles: {len(symbols)}")
    
    # Identifier les exchanges
    exchanges_info = loris.get_exchange_info(data)
    
    # 🎯 Chercher Extended, Hyperliquid et Variational
    exchanges_1h = []  # Extended + Hyperliquid
    variational_exchange = None
    
    for exchange_name in exchanges_info.keys():
        base = exchange_name.split('_')[0].lower()
        if base in ['extended', 'hyperliquid']:
            exchanges_1h.append(exchange_name)
        elif base == 'variational':
            variational_exchange = exchange_name
    
    print(f"\n📊 EXCHANGES UTILISÉS:")
    print(f"   1h: {', '.join([e.split('_')[0].upper() for e in exchanges_1h])}")
    print(f"   8h: {variational_exchange.split('_')[0].upper() if variational_exchange else 'N/A'}\n")
    
    if not exchanges_1h or not variational_exchange:
        print("❌ Exchanges manquants")
        return
    
    # Analyser TOUS les symboles
    print(f"🔍 Analyse de {len(symbols)} symboles...\n")
    
    opportunities = []
    
    for symbol in symbols:
        try:
            # Trouver le MEILLEUR rate 1h (Extended OU Hyperliquid)
            best_1h_rate = None
            best_1h_exchange = None
            
            for exchange in exchanges_1h:
                rate = loris.get_funding_rate(data, exchange, symbol)
                if rate is not None:
                    # Plus négatif = meilleur (on reçoit)
                    if best_1h_rate is None or rate < best_1h_rate:
                        best_1h_rate = rate
                        best_1h_exchange = exchange
            
            # Récupérer le rate Variational (8h)
            var_rate = loris.get_funding_rate(data, variational_exchange, symbol)
            
            # Si on a les deux rates
            if best_1h_rate is not None and var_rate is not None:
                # Position size
                position_size = 10000
                
                # 🎯 TIMING FUNDING ARBITRAGE (selon PDF)
                # Extended/Hyperliquid : funding TOUTES LES HEURES
                # Variational : funding TOUTES LES 8 HEURES
                
                # Calculer le profit PAR HEURE pour chaque exchange
                profit_1h_per_hour = abs(best_1h_rate) * position_size if best_1h_rate < 0 else -abs(best_1h_rate) * position_size
                profit_8h_per_hour = abs(var_rate) * position_size / 8 if var_rate < 0 else -abs(var_rate) * position_size / 8
                
                # Stratégie both_negative (les deux négatifs - on reçoit des deux côtés)
                if best_1h_rate < 0 and var_rate < 0:
                    # LONG sur 1h (on reçoit toutes les heures)
                    # SHORT sur 8h (on reçoit toutes les 8h)
                    # Fermeture anticipée avant funding 8h pour éviter de perdre l'avantage
                    
                    # On reçoit 7 paiements de 1h
                    profit_7_payments = abs(best_1h_rate) * position_size * 7
                    # On ne touche PAS le funding 8h car on ferme avant
                    profit_per_hour = profit_7_payments / 7  # = abs(best_1h_rate) * position_size
                    strategy = "both_negative (early_close)"
                
                # Stratégie both_positive (Extended négatif + Variational positif)
                elif best_1h_rate < 0 and var_rate > 0:
                    # LONG sur 1h (on reçoit toutes les heures)
                    # SHORT sur 8h (on reçoit car rate positif)
                    # On garde tout le cycle complet
                    
                    # 8 paiements de 1h + 1 paiement de 8h
                    profit_8_payments = abs(best_1h_rate) * position_size * 8
                    profit_var = abs(var_rate) * position_size  # Short sur positif = on reçoit
                    profit_total = profit_8_payments + profit_var
                    profit_per_hour = profit_total / 8
                    strategy = "both_positive (full_cycle)"
                
                # Stratégie standard (Extended positif + Variational positif)
                elif best_1h_rate > 0 and var_rate > 0:
                    # SHORT sur 1h (on paie toutes les heures)
                    # LONG sur 8h (on paie toutes les 8h)
                    # Seulement si Variational rate > Extended rate
                    
                    if var_rate > best_1h_rate:
                        # On paie moins sur 1h qu'on reçoit sur 8h
                        cost_8_payments = best_1h_rate * position_size * 8
                        revenue_var = var_rate * position_size
                        profit_total = revenue_var - cost_8_payments
                        profit_per_hour = profit_total / 8
                        strategy = "standard (full_cycle)"
                    else:
                        continue
                
                # Stratégie mixed (Extended positif + Variational négatif)
                elif best_1h_rate > 0 and var_rate < 0:
                    # SHORT sur 1h (on paie toutes les heures)
                    # LONG sur 8h (on reçoit car négatif)
                    
                    cost_8_payments = best_1h_rate * position_size * 8
                    revenue_var = abs(var_rate) * position_size
                    profit_total = revenue_var - cost_8_payments
                    profit_per_hour = profit_total / 8
                    strategy = "mixed (full_cycle)"
                
                else:
                    continue
                
                # Seuil minimum
                if profit_per_hour >= 2.0:  # Au moins $2/h
                    opportunities.append({
                        'symbol': symbol,
                        'exchange_1h': best_1h_exchange.split('_')[0].upper(),
                        'rate_1h': best_1h_rate,
                        'rate_8h': var_rate,
                        'profit_per_hour': profit_per_hour,
                        'strategy': strategy
                    })
        
        except Exception as e:
            continue
    
    # Trier par profit
    opportunities.sort(key=lambda x: x['profit_per_hour'], reverse=True)
    
    print(f"✅ Analyse terminée: {len(opportunities)} opportunités trouvées\n")
    
    # Afficher le top 20
    if opportunities:
        print("="*120)
        print("🏆 TOP 20 OPPORTUNITÉS D'ARBITRAGE")
        print("="*120 + "\n")
        
        table_data = []
        for i, opp in enumerate(opportunities[:20], 1):
            table_data.append([
                i,
                opp['symbol'],
                opp['exchange_1h'],
                f"{opp['rate_1h']:.5f}",
                "VARIATIONAL",
                f"{opp['rate_8h']:.5f}",
                f"${opp['profit_per_hour']:.2f}",
                opp['strategy']
            ])
        
        headers = [
            "#", "Symbole", "Exchange 1h (hourly)", "Rate 1h", 
            "Exchange 8h", "Rate 8h", "$/heure", "Stratégie"
        ]
        
        print(tabulate(table_data, headers=headers, tablefmt="grid"))
        
        # Meilleure opportunité
        best = opportunities[0]
        print(f"\n{'='*120}")
        print("💰 MEILLEURE OPPORTUNITÉ DU MOMENT")
        print(f"{'='*120}")
        print(f"  Symbole:              {best['symbol']}")
        print(f"  📈 LONG Exchange:      {best['exchange_1h']}")
        print(f"     Funding rate:      {best['rate_1h']:.6f}")
        print(f"  📉 SHORT Exchange:     VARIATIONAL")
        print(f"     Funding rate:      {best['rate_8h']:.6f}")
        print(f"  💵 Profits:")
        print(f"     Position size:     $10,000")
        print(f"     Par heure:         ${best['profit_per_hour']:.2f}")
        print(f"  🎯 Stratégie:          {best['strategy']}")
        print(f"{'='*120}\n")
        
        # Statistiques
        avg_profit = sum(o['profit_per_hour'] for o in opportunities) / len(opportunities)
        top5_profit = sum(o['profit_per_hour'] for o in opportunities[:5])
        top10_profit = sum(o['profit_per_hour'] for o in opportunities[:10])
        
        print(f"� STATISTIQUES GLOBALES")
        print(f"   Opportunités analysées: {len(opportunities)}")
        print(f"   Profit moyen/heure: ${avg_profit:.2f}")
        print(f"   Potentiel top 5: ${top5_profit:.2f}/heure")
        print(f"   Potentiel top 10: ${top10_profit:.2f}/heure")
        print(f"{'='*120}\n")
        
    else:
        print("❌ Aucune opportunité d'arbitrage trouvée\n")
    
    print("✅ Analyse terminée!")
    print("� Données fournies par Loris Tools: https://loris.tools")
    print("⏰ Mise à jour toutes les 60 secondes\n")


if __name__ == "__main__":
    main()

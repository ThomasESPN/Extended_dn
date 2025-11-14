# 🚀 Timing Funding Arbitrage Bot

Système automatisé d'arbitrage de funding rates entre exchanges Extended et Variational avec stratégie delta-neutral.

## 📋 Description

Ce projet implémente une stratégie de **timing funding arbitrage** qui exploite les différences de timing et de taux de funding entre différents exchanges pour générer des profits sans risque directionnel.

### Principe de fonctionnement

1. **Delta-Neutral** : Positions opposées (Long/Short) sur deux exchanges
2. **Timing Optimal** : Ouverture/fermeture selon les intervalles de paiement
3. **Arbitrage** : Capture des différences de funding rates

## 🎯 Caractéristiques

- ✅ Récupération en temps réel des funding rates
- ✅ Calcul automatique de rentabilité
- ✅ Exécution automatique des trades
- ✅ Rebalancing entre comptes
- ✅ Surveillance de polarité des funding
- ✅ Dashboard de monitoring
- ✅ Protection TP/SL

## 📊 Intervalles de paiement

- **Extended** : Toutes les heures (00h, 01h, 02h, ...)
- **Variational** : Variable selon la paire (1h/4h/8h)

## 🛠️ Installation

```bash
# Créer un environnement virtuel
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows

# Installer les dépendances
pip install -r requirements.txt
```

## ⚙️ Configuration

1. Copier `config/config.example.json` vers `config/config.json`
2. Remplir vos clés API Extended et Variational
3. Ajuster les paramètres de risque

## 🚀 Utilisation

```bash
# Analyser les opportunités
python src/analyzer.py

# Lancer le bot en mode automatique
python src/main.py

# Dashboard web
python src/dashboard.py
```

## 📁 Structure du projet

```
delta/
├── config/              # Configuration et clés API
├── src/
│   ├── data/           # Collecte des données
│   ├── strategies/     # Logique d'arbitrage
│   ├── execution/      # Exécution des trades
│   ├── monitoring/     # Dashboard et alertes
│   └── utils/          # Utilitaires
├── data/               # Données historiques
├── logs/               # Logs du système
└── tests/              # Tests unitaires
```

## ⚠️ Avertissement

Le trading de cryptomonnaies comporte des risques. Ce bot est fourni à titre éducatif. Testez en mode simulation avant toute utilisation réelle.

## 📝 License

MIT License

# 🚀 Quick Start - Timing Funding Arbitrage Bot

## 📦 Installation

```powershell
# 1. Installer les dépendances
py -m pip install -r requirements.txt

# 2. Configurer votre wallet
cp config\config.json.example config\config.json
# Éditer config.json avec votre wallet_address et private_key
```

## 🎯 Utilisation

### Scanner les meilleures opportunités

```powershell
# Top 15 opportunités en temps réel
py find_best_opportunity.py 15
```

### Lancer le bot

```powershell
# Mode interactif (choix du mode)
py src\main.py

# Mode AUTO (scan automatique 1430+ paires)
py test_bot_auto.py
```

### Outils d'analyse

```powershell
# Dashboard web (http://localhost:8050)
py src\dashboard.py

# Analyseur CLI (temps réel)
echo n | py src\analyzer.py
```

## ⚙️ Configuration (config/config.json)

```json
{
  "arbitrage": {
    "mode": "auto",              // manual, auto, ou smart
    "max_concurrent_pairs": 5,   // Nombre max de positions
    "min_profit_per_hour": 2.0   // Profit minimum requis ($/h)
  }
}
```

## 📊 Modes de Trading

- **MANUAL**: Surveille les paires configurées (BTC, ETH...)
- **AUTO**: Scan automatique de 1430+ symboles (recommandé)
- **SMART**: Combine manual + auto

## 📁 Structure Propre

```
delta/
├── src/                      # Code principal
│   ├── main.py              # Bot principal (3 modes)
│   ├── analyzer.py          # Analyseur CLI
│   ├── dashboard.py         # Dashboard web
│   ├── data/                # APIs (Loris, exchanges)
│   ├── strategies/          # Calculs arbitrage
│   └── execution/           # Exécution trades
├── bot_sniper.py            # Bot timing précis
├── find_best_opportunity.py # Scanner opportunités
├── test_loris.py            # Test API Loris
├── test_bot_auto.py         # Test mode AUTO
├── config/                  # Configuration
├── logs/                    # Logs bot
└── _archive/                # Anciens fichiers
    ├── old_tests/
    ├── old_scripts/
    └── old_docs/
```

## 🔗 Ressources

- **API Loris**: https://loris.tools
- **Documentation complète**: README.md
- **Setup wallet**: WALLET_SETUP.md
- **PDF Timing**: Timing funding arbitrage.pdf

---

**⚠️ Disclaimer**: Bot éducatif. Trading = risques. Ne tradez que ce que vous pouvez perdre.

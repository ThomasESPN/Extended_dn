# 🚀 Timing Funding Arbitrage Bot

Bot de trading automatisé pour l'arbitrage de funding rates entre exchanges crypto avec intervalles différents (1h vs 8h).

**✨ Intégration Loris Tools API - Données en temps réel pour 1430+ symboles**

---

## 📊 Fonctionnalités

### 🎯 Modes de Trading

#### 1. **MODE MANUAL** 
- Surveille uniquement les paires configurées (ex: BTC/USDT, ETH/USDT)
- Idéal pour un contrôle total
- Configuration via `config.json`

#### 2. **MODE AUTO** ⭐ *RECOMMANDÉ*
- **Scan automatique de 1430+ symboles depuis Loris Tools**
- Sélectionne automatiquement les 5 meilleures opportunités
- Mise à jour toutes les 60 secondes
- **Profit potentiel actuel: $173/heure (top 5 paires)**

#### 3. **MODE SMART**
- Combine MANUAL + AUTO
- Priorité aux paires configurées
- Complète avec les meilleures opportunités Loris

### 💡 Stratégies Supportées

1. **Standard**: Extended négatif, Variational positif (ou inverse)
2. **Both Positive**: Les deux positifs (arbitrage de différentiel)
3. **Both Negative**: Les deux négatifs (profit sur les deux côtés)
4. **Mixed**: Combinaison complexe

### 🛡️ Sécurité

- ✅ Positions delta-neutral (long + short simultanés)
- ✅ Stop-loss et take-profit automatiques
- ✅ Détection changement de polarité des funding rates
- ✅ Rebalancing automatique entre exchanges
- ✅ Gestion du risque par position

---

## 🚀 Installation

```powershell
# 1. Cloner le projet
cd Desktop/delta

# 2. Installer les dépendances
py -m pip install -r requirements.txt

# 3. Installer les dépendances wallet
py -m pip install eth-account web3

# 4. Configurer vos wallets
# Voir WALLET_SETUP.md pour les instructions détaillées
cp config\config.json.example config\config.json
# Puis éditer config.json avec vos wallet_address et private_key
```

---

## 📖 Utilisation

### 🔍 Trouver la meilleure opportunité

```powershell
# Analyser les 15 meilleures paires (temps réel Loris)
py find_best_opportunity.py 15
```

**Résultat actuel:**
```
🏆 ARK: $66.60/heure
   Long: Extended @ -0.00666
   Short: Variational @ -0.00904
   Profit 8h: $442.40
```

### 🤖 Lancer le bot

```powershell
# Mode interactif (choix du mode au démarrage)
py src\main.py

# ou directement en mode AUTO
py test_bot_auto.py
```

### 📊 Dashboard Web

```powershell
py src\dashboard.py
# Ouvrir http://localhost:8050
```

### 📈 Analyseur en temps réel

```powershell
# Mode single-shot
echo n | py src\analyzer.py

# Mode continu (refresh 60s)
echo o | py src\analyzer.py
```

---

## ⚙️ Configuration

### Mode AUTO (Recommandé)

Dans `config/config.json`:

```json
{
  "arbitrage": {
    "mode": "auto",
    "max_concurrent_pairs": 5,
    "min_profit_per_hour": 2.0,
    "check_interval": 60
  }
}
```

**Paramètres clés:**
- `mode`: `"manual"`, `"auto"`, ou `"smart"`
- `max_concurrent_pairs`: Nombre maximum de paires simultanées (recommandé: 5)
- `min_profit_per_hour`: Profit minimum requis en $/heure (recommandé: 2.0)
- `check_interval`: Intervalle entre chaque scan en secondes (60 = 1 minute)

---

## 📊 Performances Actuelles (Données Loris)

**Top 5 Opportunités (12 Nov 2025, 18h56):**

| # | Symbole | Profit/heure | Profit 8h | Type |
|---|---------|--------------|-----------|------|
| 1 | ARK     | $66.60       | $442.40   | both_negative |
| 2 | 0G      | $38.70       | $270.50   | both_negative |
| 3 | DOOD    | $35.80       | $243.50   | both_negative |
| 4 | BIO     | $17.30       | $91.80    | both_negative |
| 5 | DOLO    | $15.10       | $97.60    | both_negative |

**Total potentiel top 5: $173.50/heure**

---

## 🏗️ Structure du Projet

```
delta/
├── src/
│   ├── data/
│   │   ├── loris_api.py           # ⭐ Intégration Loris Tools API
│   │   └── funding_collector.py   # Collecteur de funding rates
│   ├── strategies/
│   │   └── arbitrage_calculator.py # 4 stratégies d'arbitrage
│   ├── execution/
│   │   ├── trade_executor.py      # Exécution delta-neutral
│   │   └── rebalancing.py         # Rebalancing automatique
│   ├── main.py                     # ⭐ Bot principal (3 modes)
│   ├── analyzer.py                 # Analyseur CLI
│   └── dashboard.py                # Dashboard web
├── config/
│   ├── config.json                 # Configuration principale
│   └── config.example.json         # Template
├── find_best_opportunity.py        # ⭐ Scanner multi-paires
├── test_loris.py                   # Test API Loris
└── test_bot_auto.py                # Test mode AUTO
```

---

## 🔗 API & Sources de Données

### Loris Tools API
- **URL**: https://loris.tools
- **API Endpoint**: https://api.loris.tools/funding
- **Mise à jour**: Toutes les 60 secondes
- **Symboles**: 1430+ paires crypto
- **Exchanges**: 26 exchanges (4 à 1h, 22 à 8h)

**Exchanges 1h** (type Extended):
- Extended
- Hyperliquid
- Lighter
- Vest

**Exchanges 8h** (type Variational):
- Binance, Bybit, OKX, Kucoin, BingX, Bitget, etc. (22 au total)

### Attribution
> Funding rate data provided by [Loris Tools](https://loris.tools)

⚠️ **Note**: Ne pas utiliser pour du trading en production sans vérification indépendante des données.

---

## 📝 Scripts Utiles

```powershell
# Trouver la meilleure opportunité du moment
py find_best_opportunity.py 20

# Tester l'API Loris
py test_loris.py

# Analyser BTC & ETH (mode manuel)
echo n | py src\analyzer.py

# Lancer le bot en mode AUTO (1 cycle test)
py test_bot_auto.py

# Lancer le bot en production (loop infini)
py src\main.py
```

---

## 🎯 Stratégie de Trading

### Principe: Timing Funding Arbitrage

1. **Extended Exchange** (1h funding) vs **Variational Exchange** (8h funding)
2. Positions **delta-neutral**: Long + Short simultanés
3. Profit sur la **différence de funding rates**
4. Fermeture **avant le funding Variational** (économie de frais)

### Exemple Concret: ARK

```
Long Extended @ -0.00666 (on reçoit les fundings)
Short Variational @ -0.00904 (on reçoit les fundings)

Profit = abs(-0.00666) * 8 + abs(-0.00904) - frais
       ≈ $66.60/heure sur position $10,000
```

---

## 🛠️ Développement

### Ajouter une nouvelle source de données

1. Créer un fichier dans `src/data/`
2. Implémenter l'interface `FundingRate`
3. Intégrer dans `FundingCollector`

### Ajouter une nouvelle stratégie

1. Modifier `src/strategies/arbitrage_calculator.py`
2. Ajouter une méthode `_strategy_xxx()`
3. Mettre à jour la configuration

---

## 📄 Licence

MIT License - Utilisation libre pour usage personnel uniquement.

**⚠️ Disclaimer**: Ce bot est fourni à titre éducatif. Le trading comporte des risques. Ne tradez que des montants que vous pouvez vous permettre de perdre.

---

## 🆘 Support

- **Issues**: Problèmes techniques
- **API Loris**: https://loris.tools/api-docs
- **Documentation Extended/Variational**: Voir PDF fourni

---

**Créé avec ❤️ pour l'arbitrage de funding rates**

*Dernière mise à jour: 12 Novembre 2025*

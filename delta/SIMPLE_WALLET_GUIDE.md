# 🎯 Configuration Simple avec 1 Wallet

## Pourquoi c'est simple ?

Tu utilises le **même wallet** pour Extended, Hyperliquid ET Variational. Donc tu n'as besoin que d'**une seule configuration** !

## 📝 Configuration en 3 étapes

### 1️⃣ Récupère ton wallet

Tu as déjà un wallet compatible (MetaMask, etc.) avec :
- **Adresse publique** : `0xabc123...def789`
- **Clé privée** : `0x123abc...789def`

⚠️ **SÉCURITÉ** : La clé privée donne accès à tes fonds. Ne la partage JAMAIS !

### 2️⃣ Édite `config/config.json`

Remplace uniquement ces 2 lignes :

```json
{
  "wallet": {
    "address": "0xTA_VRAIE_ADRESSE",
    "private_key": "TA_VRAIE_CLE_PRIVEE"
  },
  ...
}
```

### 3️⃣ Teste la config

```bash
py test_wallet_setup.py
```

Ce script va :
- ✅ Vérifier que ton wallet est correctement configuré
- ✅ Tester la connexion à Hyperliquid
- ✅ Tester la connexion à Variational
- ✅ Afficher tes balances sur chaque exchange
- ✅ Afficher tes positions ouvertes

## 🔐 Sécurité

### Ne JAMAIS commit la clé privée

Le fichier `.gitignore` protège déjà `config/config.json`, mais vérifie :

```bash
git status
```

Si tu vois `config/config.json` en rouge, **NE LE COMMIT PAS** !

### Utilise un wallet dédié au trading

⚠️ **MEILLEURE PRATIQUE** : Crée un nouveau wallet juste pour le bot

1. Ne garde que les fonds nécessaires au trading
2. Transfère les profits régulièrement vers ton wallet principal
3. Limite les risques en cas de problème

### Teste d'abord sur TESTNET

Les exchanges ont des testnets :
- **Hyperliquid Testnet** : `https://api.hyperliquid-testnet.xyz`
- Change `testnet=True` dans `exchange_manager.py`

## 🚀 Utilisation

### Voir les opportunités actuelles

```bash
py find_best_opportunity.py 10
```

Exemple de sortie :
```
╔═══════════════════════════════════════════════════════════════════════════╗
║                    TOP 10 DES OPPORTUNITÉS D'ARBITRAGE                    ║
╚═══════════════════════════════════════════════════════════════════════════╝

🥇 #1 - ARK
   📈 LONG Hyperliquid:  -0.00687% (-0.6870% par jour)
   📉 SHORT Variational:  -0.00782% (-0.7820% par jour)
   💰 Profit: 0.00095% par heure = $68.70/h (sur $10,000)
   📊 Position: LONG Hyperliquid + SHORT Variational
```

### Lancer le bot en mode auto

```bash
py src/main.py
```

Le bot va :
1. Scanner les 1429 paires sur Loris Tools
2. Trouver les meilleures opportunités Extended/Hyperliquid vs Variational
3. Ouvrir automatiquement les positions delta-neutral
4. Monitorer et clôturer avant les funding Variational

## 📊 Comment ça marche ?

### Delta-Neutral Trading

Le bot ouvre **2 positions simultanées** :

**Exemple avec ARK** :
- 🟢 **LONG** sur Hyperliquid : Funding -0.00687% (tu **reçois** $6.87/h)
- 🔴 **SHORT** sur Variational : Funding -0.00782% (tu **reçois** $7.82/8h = $0.98/h)

**Résultat** :
- Position **delta-neutral** (pas de risque directionnel)
- Profit net : $6.87 + $0.98 = **$7.85/h** sur $10,000
- Soit **$68.70/h** avec position de $10,000

### Pourquoi Extended + Hyperliquid vs Variational ?

C'est la stratégie du PDF "Timing Funding Arbitrage" :

- **Extended & Hyperliquid** : Funding toutes les heures (1h)
- **Variational** : Funding toutes les 8 heures

Le bot exploite cette **différence de timing** pour capturer du profit sans risque directionnel.

## 🛠️ Structure du code

```
src/exchanges/
├── exchange_manager.py    ← Gère le wallet global pour tous les DEX
├── hyperliquid_api.py     ← API Hyperliquid avec wallet signing
├── variational_api.py     ← API Variational avec wallet signing
└── extended_api.py        ← TODO: API Extended
```

### ExchangeManager

Le manager centralise tout :

```python
from src.exchanges.exchange_manager import ExchangeManager

# Initialise avec le wallet global
manager = ExchangeManager()

# Ouvre une position delta-neutral
manager.open_delta_neutral_position(
    symbol="ARK/USDT",
    size=10000,
    long_exchange="hyperliquid",
    short_exchange="variational"
)

# Récupère les balances
total = manager.get_total_balance()
print(f"Total: ${total:,.2f}")

# Récupère toutes les positions
positions = manager.get_all_positions()
```

## ❓ FAQ

### J'ai plusieurs wallets, un pour chaque DEX. Que faire ?

Tu peux les utiliser tous sur le même bot ! Mais c'est plus simple avec 1 seul wallet.

Si tu veux vraiment utiliser des wallets différents, tu peux modifier `exchange_manager.py` pour lire depuis :
```json
"exchanges": {
  "hyperliquid": {
    "wallet_address": "0x...",
    "private_key": "0x..."
  }
}
```

### Le bot trade vraiment en automatique ?

Oui, en mode `auto` dans `config.json` :
```json
"arbitrage": {
  "mode": "auto",
  ...
}
```

Le bot va scanner en continu et ouvrir/fermer des positions automatiquement.

### C'est sûr ?

⚠️ **Crypto = risques** :
- Smart contract bugs
- Slippage sur les ordres
- Changement brutal des funding rates
- Liquidation si mauvais leverage

**TOUJOURS** :
1. Teste sur testnet d'abord
2. Commence avec de petits montants
3. Monitor régulièrement
4. Garde du cash pour les appels de marge

### Pourquoi le même wallet fonctionne partout ?

Extended, Hyperliquid et Variational sont tous sur **Ethereum** (ou EVM-compatible). Donc un wallet Ethereum fonctionne sur les 3 !

C'est comme utiliser la même carte bancaire dans plusieurs magasins.

## 📚 Ressources

- **Hyperliquid Docs** : https://hyperliquid.gitbook.io/
- **Variational Docs** : https://docs.variational.io/
- **Extended Docs** : https://docs.extended.finance/
- **Loris Tools** : https://loris.tools/

## 🎉 C'est parti !

1. Configure ton wallet dans `config/config.json`
2. Lance `py test_wallet_setup.py`
3. Lance `py find_best_opportunity.py 10`
4. Commence à trader !

**Bon profit ! 💰**
